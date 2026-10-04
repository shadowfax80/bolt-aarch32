#!/usr/bin/env python3
"""Check a `bolt_bench smp` run (T2) against the independent oracle.

Phase 1 (seq): every active core ran the full `all` suite in a thread pinned to
it, and reported running on that core; its 18 sinks equal the oracle.
Phase 2 (conc): all cores ran the shared-state-free workloads at the same time,
`reps` times; each thread stayed on its core and every sink equals the oracle.
Exits non-zero on any missing, extra, misplaced or wrong result.
"""
import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from qemu_bench_oracle import reference_results  # noqa: E402

CONC_SET = ['hot_loop', 'hot_cold', 'branch_chain', 'far_call', 'it_cond', 'interwork', 'switch',
            'spill_ret', 'litpool', 'indirect_call', 'interwork_tail', 'regpressure',
            'hotcold_split', 'icf', 'shrinkwrap']
SINK = re.compile(r'bolt_bench: (\w+) sink=(0x[0-9a-f]{8})')


def check(text, min_cpus):
    expected = {k: int(v, 16) if isinstance(v, str) else v for k, v in reference_results().items()}
    errors = []
    runs = text.split('bolt_bench: smp cpus=')
    if len(runs) != 2:
        return [f'expected exactly one smp run, found {len(runs) - 1}'], {}
    body = runs[1]
    m = re.match(r'(\d+) reps=(\d+) set=(\d+)', body)
    ncpu, reps, nset = map(int, m.groups())
    if ncpu < min_cpus:
        errors.append(f'only {ncpu} active cores (need {min_cpus})')
    if nset != len(CONC_SET):
        errors.append(f'concurrent set has {nset} workloads, checker expects {len(CONC_SET)}')
    if 'bolt_bench: smp done' not in body:
        errors.append('smp run did not complete')
    for c in range(ncpu):
        seg = re.search(rf'smp seq cpu={c} on=(\d+) begin\n(.*?)smp seq cpu={c} on=(\d+) end', body, re.S)
        if not seg:
            errors.append(f'seq cpu {c}: missing'); continue
        if int(seg.group(1)) != c or int(seg.group(3)) != c:
            errors.append(f'seq cpu {c}: ran on {seg.group(1)},{seg.group(3)}')
        got = dict((k, int(v, 16)) for k, v in SINK.findall(seg.group(2)))
        if got != expected:
            errors.append(f'seq cpu {c}: wrong/missing ' + ','.join(sorted(k for k in expected if got.get(k) != expected[k])))
    conc = re.findall(r'smp conc cpu=(\d+) rep=(\d+) (\w+) sink=(0x[0-9a-f]{8})', body)
    if len(conc) != ncpu * reps * len(CONC_SET):
        errors.append(f'conc: {len(conc)} results, expected {ncpu * reps * len(CONC_SET)}')
    seen = set()
    for c, r, name, v in conc:
        key = (int(c), int(r), name)
        if key in seen or name not in CONC_SET:
            errors.append(f'conc: duplicate/unknown {key}')
        seen.add(key)
        if int(v, 16) != expected[name]:
            errors.append(f'conc cpu {c} rep {r}: {name} = {v}')
    for c, a, b in re.findall(r'smp conc cpu=(\d+) on=(\d+),(\d+)', body):
        if not c == a == b:
            errors.append(f'conc cpu {c}: ran on {a},{b}')
    summary = dict(cpus=ncpu, reps=reps, seq_results=ncpu * len(expected), conc_results=len(conc))
    return errors, summary


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('log', type=Path)
    ap.add_argument('--min-cpus', type=int, default=4)
    a = ap.parse_args()
    errors, summary = check(a.log.read_text(errors='replace'), a.min_cpus)
    for e in errors[:40]:
        print('FAIL:', e)
    if errors:
        return 1
    print(f"PASS: {summary['cpus']} cores; seq {summary['seq_results']} sinks; "
          f"conc {summary['conc_results']} sinks ({summary['reps']} reps) equal the oracle")
    return 0


if __name__ == '__main__':
    sys.exit(main())
