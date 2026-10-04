#!/usr/bin/env python3
"""Whole-image BOLT coverage report for an AArch32 LK test binary.

Covers everything in the image: LK kernel/platform code, libc, startup and
vector assembly, and the bolt_bench_* workloads. Every FUNC symbol gets a
status (rewritten, folded, rejected with reason, not processed), and every
byte of each executable section is attributed (sized function, size-0
assembly extent, data in code, unattributed).

Collect local admission rejections in one report-only BOLT scan, then run
normal fatal admission with those explicit skips to measure actual emission.
The diagnostic report is not a correctness or execution certificate. Use
--legacy-scan explicitly only for toolchains predating overlay 0054.
Run in WSL against the ATFE toolchain:

  python3 scripts/lk_coverage_report.py --elf lk.elf \
      --toolchain /home/user/bolt-aarch32/build-atfe/bin \
      --out out/lk-coverage-YYYYMMDD --doc docs/LK_COVERAGE.md \
      --json docs/results/lk_coverage_YYYYMMDD.json
"""
import argparse
import collections
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Same transformation options as scripts/pi4/full_image_build.py.
BOLT_OPTS = ['--no-huge-pages', '-lite=0', '-reorder-blocks=ext-tsp',
             '-reorder-functions=hfsort+', '-icf=all']

# Rejection classes: matched against the diagnostic, with the justification
# and the work item that would recover coverage.
CLASSES = [
    ('fallthrough', r'unmodeled AArch32 function fallthrough',
     'Usually a terminal call to a noreturn callee; real fallthrough (e.g. '
     'bzero into memset) must stay rejected.', 'R5 (Codex)'),
    ('it-transfer', r'unsupported control transfer in Thumb IT group',
     'Predicated return or branch inside an IT block; unsafe to move until '
     'modeled.', 'R6 (Codex)'),
    ('cfg-crash', r'invalid AArch32 CFG after branch post-processing',
     'Not justified: crash on an IT-predicated conditional tail call.',
     'R4 (Codex)'),
    ('pc-write', r'PC-writing control transfer',
     'Exception-return or computed PC write; vectors and early setup stay in '
     'place permanently.', 'keep out'),
    ('pc-read', r'position-dependent PC read',
     'Reads the PC as data; startup runs before the MMU and must not move. '
     'ADR to an inline switch table is supportable.', 'keep out / R12'),
    ('other', r'.', 'Unclassified diagnostic; inspect the log.', 'triage'),
]


def run(cmd, log=None, check=False):
    p = subprocess.run([str(c) for c in cmd], capture_output=True, text=True)
    text = p.stdout + p.stderr
    if log:
        Path(log).write_text(text, encoding='utf-8')
    if check and p.returncode:
        sys.exit(f'error: {cmd[0]} failed ({p.returncode})\n{text[-2000:]}')
    return p.returncode, text


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def base_name(name):
    return re.sub(r'/\d+$', '', re.sub(r'\(\*\d+\)$', '', name))


def read_symbols(tc, elf):
    _, text = run([tc / 'llvm-readelf', '-sW', elf], check=True)
    funcs, mapping = [], []
    for line in text.splitlines():
        f = line.split()
        if len(f) < 8 or not f[0].rstrip(':').isdigit():
            continue
        value, size, typ, name = int(f[1], 16), int(f[2], 0), f[3], f[7]
        if typ == 'FUNC':
            funcs.append(dict(name=name, addr=value & ~1, size=size,
                              isa='T32' if value & 1 else 'A32', bind=f[4]))
        elif re.fullmatch(r'\$[atd](\..*)?', name):
            mapping.append((value, name[1]))
    return funcs, sorted(mapping)


def read_sections(tc, elf):
    _, text = run([tc / 'llvm-readelf', '-SW', elf], check=True)
    secs = []
    for line in text.splitlines():
        m = re.match(r'\s*\[\s*\d+\]\s+(\S+)\s+\S+\s+([0-9a-f]+)\s+[0-9a-f]+\s+'
                     r'([0-9a-f]+)\s+\S+\s+(\S+)', line)
        if m and 'X' in m.group(4):
            secs.append(dict(name=m.group(1), addr=int(m.group(2), 16),
                             size=int(m.group(3), 16)))
    return secs


def attribute_bytes(secs, funcs, mapping, image):
    """Split each executable section into byte classes."""
    out = collections.Counter()
    starts = sorted({f['addr'] for f in funcs} | {a for a, _ in mapping})
    for sec in secs:
        lo, hi = sec['addr'], sec['addr'] + sec['size']
        owner = bytearray(sec['size'])  # 0 unattributed, 1 sized, 2 size-0
        for f in funcs:
            if not lo <= f['addr'] < hi:
                continue
            if f['size']:
                end = min(hi, f['addr'] + f['size'])
                kind = 1
            else:
                nxt = [s for s in starts if s > f['addr']]
                end = min(hi, nxt[0] if nxt else hi)
                kind = 2
            for a in range(f['addr'], end):
                if owner[a - lo] == 0:
                    owner[a - lo] = kind
        data = bytearray(sec['size'])
        marks = [(a, k) for a, k in mapping if lo <= a < hi]
        for i, (a, k) in enumerate(marks):
            if k == 'd':
                end = marks[i + 1][0] if i + 1 < len(marks) else hi
                for b in range(a, end):
                    data[b - lo] = 1
        for i in range(sec['size']):
            if data[i]:
                out['data in code'] += 1
            elif owner[i] == 0:
                # Alignment filler between functions (ld.lld fills code gaps
                # with 0xd4; e.g. the aligned(16384) bolt_bench_mf* layout
                # benchmark) vs bytes no symbol accounts for.
                out['alignment filler (0x00/0xd4)'
                    if image(sec, lo + i) in (0x00, 0xd4)
                    else 'unattributed non-filler'] += 1
            else:
                out[('unattributed', 'sized function', 'size-0 assembly extent')
                    [owner[i]]] += 1
    return dict(out)


def classify(message):
    for key, pattern, _, _ in CLASSES:
        if re.search(pattern, message):
            return key
    return 'other'


def scan_rejections_legacy(tc, elf, out, max_rounds):
    """Rerun llvm-bolt, skipping every function named in a fatal error."""
    skip, reasons = [], {}
    for rnd in range(1, max_rounds + 1):
        opts = list(BOLT_OPTS)
        if skip:
            opts.append('-skip-funcs=' + ','.join(skip))
        rc, log = run([tc / 'llvm-bolt', elf, '-o', out / 'scan.elf', *opts,
                       '--emit-function-map=' + str(out / 'scan.funcmap')])
        if rc == 0:
            return skip, reasons, rnd
        new = []
        # The function follows the last " in " ("... in Thumb IT group in f").
        for m in re.finditer(r'BOLT-ERROR: ([^\n]*) in ([A-Za-z0-9_.$/]+)', log):
            new.append((m.group(2), m.group(1)))
        if not new and 'LLVM ERROR' in log:
            fn = re.findall(r'End of Function "([^"(]+)', log)
            err = re.search(r'LLVM ERROR: [^\n]*', log)
            if fn:
                new.append((fn[-1], err.group(0) if err else 'LLVM ERROR'))
        added = False
        for name, msg in new:
            if name not in skip:
                skip.append(name)
                reasons[name] = msg
                added = True
        if not added:
            (out / 'scan-stuck.log').write_text(log, encoding='utf-8')
            sys.exit(f'error: rejection scan made no progress in round {rnd}; '
                     f'see {out / "scan-stuck.log"}')
    sys.exit(f'error: rejection scan did not converge in {max_rounds} rounds')


def read_admission_report(path, input_sha256):
    report = json.loads(Path(path).read_text(encoding='utf-8'))
    if (not isinstance(report, dict)
            or type(report.get('schema')) is not int or report['schema'] != 1
            or report.get('kind') != 'aarch32-admission-diagnostic'
            or report.get('complete') is not True
            or report.get('execution_verified') is not False
            or report.get('input_sha256') != input_sha256):
        raise ValueError('incomplete, wrong-input or non-diagnostic admission report')
    rows = report.get('functions')
    if not isinstance(rows, list):
        raise ValueError('missing admission functions')
    seen = set()
    names = set()
    counts = collections.Counter()
    reasons = {}
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError('malformed admission function')
        name, address, status = row.get('name'), row.get('address'), row.get('status')
        if (not isinstance(name, str) or not name or ',' in name
                or '\n' in name or '\r' in name or name in names
                or type(address) is not int or not 0 <= address <= 0xffffffff
                or address in seen or row.get('isa') not in ('A32', 'T32')
                or status not in ('admitted', 'rejected', 'not-analyzed')):
            raise ValueError('ambiguous or malformed admission function')
        seen.add(address)
        names.add(name)
        counts[status] += 1
        if status == 'rejected':
            reason = row.get('reason')
            if (row.get('stage') not in ('disassembly', 'cfg')
                    or not isinstance(reason, str) or not reason):
                raise ValueError('rejection has no stage/reason')
            reasons[name] = reason
    if any(type(report.get(key)) is not int or report[key] != counts[status]
           for key, status in [('admitted', 'admitted'), ('rejected', 'rejected'),
                               ('not_analyzed', 'not-analyzed')]):
        raise ValueError('admission totals do not match functions')
    return list(reasons), reasons


def scan_rejections(tc, elf, out):
    report = out / 'admission.json'
    before = sha256(elf)
    rc, _ = run([tc / 'llvm-bolt', elf, '-o', '/dev/null', *BOLT_OPTS,
                 '--arm-admission-report=' + str(report)],
                log=out / 'admission.log')
    if rc or not report.is_file():
        raise ValueError('diagnostic admission scan failed; see admission.log')
    if sha256(elf) != before:
        raise ValueError('input changed during admission scan')
    skip, reasons = read_admission_report(report, before)
    return skip, reasons, 1


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument('--elf', type=Path, required=True)
    ap.add_argument('--toolchain', type=Path, required=True)
    ap.add_argument('--out', type=Path, required=True,
                    help='fresh working directory for logs and outputs')
    ap.add_argument('--doc', type=Path, help='Markdown report to write')
    ap.add_argument('--json', type=Path, help='JSON report to write')
    ap.add_argument('--max-rounds', type=int, default=200)
    ap.add_argument('--legacy-scan', action='store_true',
                    help='explicit compatibility mode for pre-0054 toolchains')
    ap.add_argument('--skip-instrumentation', action='store_true')
    a = ap.parse_args()
    if a.out.exists() and any(a.out.iterdir()):
        sys.exit(f'error: {a.out} is not empty; use a fresh directory')
    a.out.mkdir(parents=True, exist_ok=True)
    tc, elf = a.toolchain.resolve(), a.elf.resolve()

    funcs, mapping = read_symbols(tc, elf)
    secs = read_sections(tc, elf)
    contents = {}
    for sec in secs:
        dump = a.out / (sec['name'].strip('.') + '.bin')
        run([tc / 'llvm-objcopy', '-O', 'binary', '--only-section=' + sec['name'],
             elf, dump], check=True)
        contents[sec['name']] = dump.read_bytes()
    bytes_by_class = attribute_bytes(
        secs, funcs, mapping,
        lambda sec, addr: contents[sec['name']][addr - sec['addr']])

    skip, reasons, rounds = (scan_rejections_legacy(tc, elf, a.out, a.max_rounds)
                            if a.legacy_scan else scan_rejections(tc, elf, a.out))
    final = [tc / 'llvm-bolt', elf, '-o', a.out / 'final.elf', *BOLT_OPTS,
             '--emit-function-map=' + str(a.out / 'final.funcmap'), '-v=1']
    if skip:
        final.insert(-2, '-skip-funcs=' + ','.join(skip))
    rc, log = run(final, log=a.out / 'final.log')
    if rc:
        sys.exit(f'error: final llvm-bolt run failed; see {a.out / "final.log"}')

    emitted = {}
    for line in (a.out / 'final.funcmap').read_text().splitlines():
        f = line.split()
        if len(f) >= 3:
            emitted[base_name(f[0])] = int(f[2], 16)
    out_funcs, _ = read_symbols(tc, a.out / 'final.elf')
    out_addr = {f['name']: f['addr'] for f in out_funcs}
    emitted_at = {addr: name for name, addr in emitted.items()}
    rejected = {base_name(n): (classify(m), m) for n, m in reasons.items()}

    # Group aliases: symbols at one address are one body.
    by_addr = collections.defaultdict(list)
    for f in funcs:
        by_addr[f['addr']].append(f['name'])

    rows = []
    for f in sorted(funcs, key=lambda f: (f['addr'], f['name'])):
        n = f['name']
        aliases = [x for x in by_addr[f['addr']] if x != n]
        row = dict(name=n, addr=f'{f["addr"]:#x}', size=f['size'], isa=f['isa'],
                   aliases=aliases, instrumentation=(
                       'in scope (bolt_bench workload)'
                       if n.startswith('bolt_bench_') else
                       'out of scope by policy (LK host code)'))
        if n in emitted:
            row.update(status='rewritten')
        elif n in rejected or any(x in rejected for x in aliases):
            key, msg = rejected.get(n) or next(rejected[x] for x in aliases
                                               if x in rejected)
            row.update(status='rejected', reason_class=key, reason=msg)
        elif any(x in emitted for x in aliases):
            row.update(status='alias of rewritten function')
        elif out_addr.get(n) in emitted_at:
            row.update(status='folded (ICF)', into=emitted_at[out_addr[n]])
        elif f['size'] == 0:
            row.update(status='not processed',
                       reason='symbol size 0 (assembly without .size)')
        else:
            row.update(status='not processed',
                       reason='not emitted; see final.log')
        rows.append(row)

    # Byte extent per body: symbol size, or up to the next symbol for size-0
    # assembly. Aliases share one body and count once.
    starts = sorted({f['addr'] for f in funcs} | {a for a, _ in mapping})
    sec_end = max(s['addr'] + s['size'] for s in secs)
    seen, code_status = set(), collections.Counter()
    for f, row in zip(sorted(funcs, key=lambda f: (f['addr'], f['name'])), rows):
        if f['addr'] in seen:
            continue
        seen.add(f['addr'])
        ext = f['size'] or (min([x for x in starts if x > f['addr']] or
                                [sec_end]) - f['addr'])
        st = row['status']
        code_status['rewritten' if st in ('rewritten', 'alias of rewritten function')
                    else 'folded' if st.startswith('folded') else st] += ext

    status_counts = collections.Counter(r['status'] for r in rows)
    status_bytes = collections.Counter()
    for r in rows:
        status_bytes[r['status']] += r['size']
    class_counts = collections.Counter(r.get('reason_class') for r in rows
                                       if r['status'] == 'rejected')

    instr = None
    if not a.skip_instrumentation:
        env = dict(os.environ, BASE='atfe', ARCH='arm32', ELF=str(elf),
                   OUT=str(a.out / 'lk.instr.elf'), TOOLCHAIN=str(tc),
                   BOLT_RT_LIB=str(tc.parent / 'bolt-rt-baremetal-arm' /
                                   'libbolt_rt_baremetal.a'),
                   ARM_INSTRUMENTATION_CONTRACT='privileged-single-core-no-fiq')
        p = subprocess.run(['bash', str(ROOT / 'scripts/instrument-lk-bolt.sh')],
                           env=env, capture_output=True, text=True)
        (a.out / 'instrument.log').write_text(p.stdout + p.stderr)
        err = re.search(r'BOLT-ERROR: [^\n]*', p.stdout + p.stderr)
        instr = dict(exit=p.returncode,
                     result='instrumented' if p.returncode == 0 else 'failed',
                     first_error=err.group(0) if err else None)

    report = dict(
        schema=1, input=str(elf), input_sha256=sha256(elf),
        toolchain=str(tc), llvm_bolt_sha256=sha256(tc / 'llvm-bolt'),
        bolt_options=BOLT_OPTS, scan_rounds=rounds,
        admission_scan='legacy-multi-round' if a.legacy_scan else 'report-only',
        admission_report_sha256=None if a.legacy_scan else sha256(a.out / 'admission.json'),
        executable_sections=secs, bytes_by_class=bytes_by_class,
        functions=len(rows), status_counts=dict(status_counts),
        code_bytes_by_status=dict(code_status),
        status_bytes=dict(status_bytes),
        rejection_classes={k: dict(count=class_counts.get(k, 0),
                                   justification=j, action=act)
                           for k, _, j, act in CLASSES},
        instrumentation=instr, skip_funcs=skip, rows=rows)
    if a.json:
        a.json.write_text(json.dumps(report, indent=1) + '\n')
    if a.doc:
        a.doc.write_text(render(report), encoding='utf-8')
    print(json.dumps(dict(functions=len(rows), status=dict(status_counts),
                          rejection_classes=dict(class_counts),
                          bytes=bytes_by_class, instrumentation=instr),
                     indent=1))


def render(r):
    total = r['functions']
    sec_bytes = sum(s['size'] for s in r['executable_sections'])
    L = ['# Full-image LK coverage', '',
         f'Generated by `scripts/lk_coverage_report.py`. Input sha256 '
         f'`{r["input_sha256"][:16]}…`; llvm-bolt sha256 '
         f'`{r["llvm_bolt_sha256"][:16]}…`; options `{" ".join(r["bolt_options"])}`. '
         f'Rejections collected in {r["scan_rounds"]} rounds. The whole binary '
         'counts: LK kernel and platform, libc, startup and vector assembly, '
         'and the bolt_bench workloads.', '',
         '## Functions', '',
         '| Status | Functions | Share | Symbol bytes |', '|---|---|---|---|']
    for k, v in sorted(r['status_counts'].items(), key=lambda x: -x[1]):
        L.append(f'| {k} | {v} | {100 * v / total:.1f}% | '
                 f'{r["status_bytes"].get(k, 0)} |')
    code = sum(r['code_bytes_by_status'].values())
    rew = r['code_bytes_by_status'].get('rewritten', 0)
    L[L.index('## Functions'):L.index('## Functions')] = [
        '## Summary', '',
        f'BOLT rewrites {rew} of {code} function code bytes '
        f'({100 * rew / code:.1f}%), and '
        f'{r["status_counts"].get("rewritten", 0)} of {total} functions. '
        'Alignment filler is excluded; size-0 assembly functions count up to '
        'the next symbol.', '',
        '| Code bytes by status | Bytes | Share |', '|---|---|---|'] + [
        f'| {k} | {v} | {100 * v / code:.1f}% |'
        for k, v in sorted(r['code_bytes_by_status'].items(),
                           key=lambda x: -x[1])] + ['']
    L += ['', '## Code bytes', '',
          f'Executable sections: '
          + ', '.join(f'`{s["name"]}` {s["size"]} bytes'
                      for s in r['executable_sections']) + '.', '',
          '| Byte class | Bytes | Share |', '|---|---|---|']
    for k, v in sorted(r['bytes_by_class'].items(), key=lambda x: -x[1]):
        L.append(f'| {k} | {v} | {100 * v / sec_bytes:.1f}% |')
    L += ['', '## Rejections', '',
          '| Class | Functions | Justification | Action |', '|---|---|---|---|']
    for k, c in r['rejection_classes'].items():
        if c['count']:
            L.append(f'| {k} | {c["count"]} | {c["justification"]} | '
                     f'{c["action"]} |')
    L += ['', '## Instrumentation', '',
          'Policy: only `bolt_bench_*` workloads are instrumented '
          '(`scripts/instrument-lk-bolt.sh`); LK host code is out of scope.', '']
    i = r['instrumentation']
    if i is None:
        L.append('Not run.')
    elif i['result'] == 'instrumented':
        L.append('The in-scope workloads instrument successfully.')
    else:
        L.append(f'Instrumentation of this image fails: `{i["first_error"]}`')
    L += ['', '## Functions not rewritten', '',
          '| Function | Address | Size | ISA | Status | Reason |',
          '|---|---|---|---|---|---|']
    for row in r['rows']:
        if row['status'] == 'rewritten':
            continue
        why = row.get('reason') or (f'folded into `{row["into"]}`'
                                    if 'into' in row else '')
        why = why.replace('|', '\\|')
        L.append(f'| `{row["name"]}` | {row["addr"]} | {row["size"]} | '
                 f'{row["isa"]} | {row["status"]} | {why} |')
    return '\n'.join(L) + '\n'


if __name__ == '__main__':
    main()
