#!/usr/bin/env python3
"""Pi gate: exact artifacts, all workloads, and PCs in required rewritten bodies.

Usage: full_image_verify.py OUTDIR --require-executed NAME[,NAME...] [--port COM5]
OUTDIR is produced by full_image_build.py. Coverage is scoped to the required set,
not every emitted symbol. Each invocation uses a fresh evidence directory.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import struct
import sys
import tempfile

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parent)]
from passes_check import parse_results
from proc_util import run_bounded
from bolt_dump_reassemble import parse_dump_stream


def sha256(path):
    digest = hashlib.sha256()
    with open(path, 'rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def loadable_sections(blob):
    if len(blob) < 52 or blob[:7] != b'\x7fELF\x01\x01\x01' or struct.unpack_from('<H', blob, 18)[0] != 40:
        raise ValueError('expected a little-endian AArch32 ELF32 image')
    phoff, shoff = struct.unpack_from('<II', blob, 28)
    phsize, phnum, shsize, shnum, strings_index = struct.unpack_from('<HHHHH', blob, 42)
    if phsize != 32 or shsize != 40 or not phnum or not shnum or strings_index >= shnum:
        raise ValueError('unsupported or malformed ELF header tables')
    if phoff + phsize * phnum > len(blob) or shoff + shsize * shnum > len(blob):
        raise ValueError('ELF header tables are truncated')
    loads = [struct.unpack_from('<IIIIIIII', blob, phoff + i * phsize) for i in range(phnum)]
    loads = [p for p in loads if p[0] == 1]
    headers = [struct.unpack_from('<IIIIIIIIII', blob, shoff + i * shsize) for i in range(shnum)]
    string_header = headers[strings_index]
    start, size = string_header[4:6]
    if start + size > len(blob):
        raise ValueError('ELF section names are truncated')
    strings = blob[start:start + size]
    sections = []
    for name_offset, kind, flags, address, offset, size, *_ in headers:
        if not flags & 2 or kind == 8 or not size:
            continue
        if offset + size > len(blob) or name_offset >= len(strings):
            raise ValueError('ELF allocated section is truncated')
        end = strings.find(b'\0', name_offset)
        if end < 0:
            raise ValueError('unterminated ELF section name')
        name = strings[name_offset:end].decode('ascii')
        segment = next((p for p in loads if p[2] <= address and address + size <= p[2] + p[4]
                        and p[1] + address - p[2] == offset), None)
        if segment is None:
            raise ValueError(f'allocated section {name} has no matching file-backed LOAD')
        physical = segment[3] + address - segment[2]
        sections.append(dict(name=name, address=address, physical=physical, offset=offset, size=size, flags=flags))
    if not sections:
        raise ValueError('no allocated file-backed sections')
    return sections


def branch_target(branch, pc, thumb):
    if len(branch) != 4:
        raise ValueError('redirect must be four bytes')
    if thumb:
        first, second = struct.unpack('<HH', branch)
        if first & 0xf800 != 0xf000 or second & 0xd000 != 0x9000 or pc % 2:
            raise ValueError('redirect is not an aligned Thumb B.W')
        sign = (first >> 10) & 1
        i1, i2 = 1 ^ ((second >> 13) & 1) ^ sign, 1 ^ ((second >> 11) & 1) ^ sign
        offset = (sign << 24) | (i1 << 23) | (i2 << 22) | ((first & 0x3ff) << 12) | ((second & 0x7ff) << 1)
        if sign:
            offset -= 1 << 25
        return pc + 4 + offset
    word = struct.unpack('<I', branch)[0]
    if word & 0xff000000 != 0xea000000 or pc % 4:
        raise ValueError('redirect is not an aligned unconditional ARM B')
    offset = word & 0xffffff
    if offset & 0x800000:
        offset -= 1 << 24
    return pc + 8 + (offset << 2)


def check_artifacts(out, manifest):
    files = {'baseline.elf': 'input_sha256', 'baseline.bin': 'baseline_binary_sha256',
             'baseline_full.elf': 'elf_sha256', 'baseline_full.bin': 'binary_sha256', 'full.funcmap': 'map_sha256'}
    if manifest.get('schema') != 1:
        raise ValueError('unsupported build manifest')
    for name, key in files.items():
        if sha256(out / name) != manifest[key]:
            raise ValueError(f'{name} does not match the build manifest')
    image = (out / 'baseline_full.bin').read_bytes()
    elf = (out / 'baseline_full.elf').read_bytes()
    sections = loadable_sections(elf)
    physical_base = min(s['physical'] for s in sections)
    emitted = {row['name']: row for row in manifest['emitted']}
    redirects = manifest['redirected']
    if not redirects or len({r['name'] for r in redirects}) != len(redirects):
        raise ValueError('empty or duplicate redirect set')
    for row in redirects:
        mapped = emitted.get(row['name'])
        if not mapped or any(row[k] != mapped[k] for k in ('input', 'output', 'output_size')):
            raise ValueError('redirect does not match emitted coverage')
        section = next((s for s in sections if s['name'] == '.bolt.org.text'
                        and s['address'] <= row['input'] and row['input'] + 4 <= s['address'] + s['size']), None)
        target = next((s for s in sections if s['name'].startswith('.text') and s['flags'] & 4
                       and s['address'] <= row['output'] and row['output'] + row['output_size'] <= s['address'] + s['size']), None)
        if not section or not target or row['output_size'] <= 0 or row['input'] == row['output']:
            raise ValueError('redirect source/destination is outside code sections or unmoved')
        delta = row['input'] - section['address']
        elf_offset, bin_offset = section['offset'] + delta, section['physical'] + delta - physical_base
        branch = bytes.fromhex(row['branch_hex'])
        if branch_target(branch, row['input'], row['thumb']) != row['output']:
            raise ValueError('redirect branch does not target the recorded rewritten body')
        if len(branch) != 4 or bin_offset < 0 or image[bin_offset:bin_offset + 4] != branch or elf[elf_offset:elf_offset + 4] != branch:
            raise ValueError('redirect bytes are missing from ELF or uploaded binary')
        target_delta = row['output'] - target['address']
        start = target['physical'] + target_delta - physical_base
        code = elf[target['offset'] + target_delta:target['offset'] + target_delta + row['output_size']]
        if start < 0 or image[start:start + row['output_size']] != code:
            raise ValueError('rewritten body differs between ELF and uploaded binary')


def execution_evidence(text, manifest, required):
    parse_results(text)  # Reject interrupted/mismatched workload sets independently.
    reports = list(re.finditer(r'bolt_sample: (\d+) samples \((\d+) taken\) buf=0x([0-9a-f]+) bytes=0x([0-9a-f]+)', text))
    if len(reports) != 1:
        raise ValueError('expected exactly one sample completion report')
    kept, taken, address, size = reports[0].groups()
    kept, taken, address, size = int(kept), int(taken), int(address, 16), int(size, 16)
    buffer = manifest['sample_buffer']
    if not 0 < kept == taken < buffer['size'] // 4 or size != kept * 4 or address != buffer['address']:
        raise ValueError('invalid, saturated or mismatched sample report')
    if len(re.findall('BOLT_DUMP_BEGIN', text)) != 1 or len(re.findall('BOLT_DUMP_END', text)) != 1:
        raise ValueError('expected one complete PC buffer dump')
    dumped = parse_dump_stream(text)
    if (dumped.addr, dumped.size) != (buffer['address'], buffer['size']):
        raise ValueError('PC dump does not match the image buffer')
    if dumped.bad_seqs or not dumped.is_complete() or dumped.total_seq != (buffer['size'] + 63) // 64:
        raise ValueError('incomplete or corrupt PC dump')
    if any(offset < 0 or offset + len(chunk) > dumped.size for offset, chunk in dumped.chunks.items()):
        raise ValueError('PC dump chunk exceeds buffer bounds')
    raw = dumped.to_bytes()[:size]
    samples = struct.unpack(f'<{kept}I', raw)
    coverage = []
    for row in manifest['redirected']:
        hits = sum(row['output'] <= (pc & ~1) < row['output'] + row['output_size']
                   and bool(pc & 1) == row['thumb'] for pc in samples)
        coverage.append(dict(name=row['name'], pc_samples=hits, execution_observed=bool(hits), required=row['name'] in required))
    observed = {r['name'] for r in coverage if r['execution_observed']}
    if set(required) - observed:
        raise ValueError('no rewritten execution observed for: ' + ', '.join(sorted(set(required) - observed)))
    return dict(kept_samples=kept, taken_samples=taken, redirected_coverage=coverage,
                required_executed=required, sampled_pc_sha256=hashlib.sha256(raw).hexdigest())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('outdir', type=Path)
    parser.add_argument('--require-executed', required=True, help='exact comma-separated redirect names requiring PC evidence')
    parser.add_argument('--port', default='COM5')
    parser.add_argument('--fast-loader', type=Path)
    parser.add_argument('--period', type=int, default=20000)
    parser.add_argument('--repeat', type=int, default=5,
                        help='repeat all workloads to sample short rewritten bodies (1..32; default 5)')
    args = parser.parse_args()
    out = args.outdir.resolve()
    manifest = json.loads((out / 'full_manifest.json').read_text())
    required = args.require_executed.split(',')
    if not all(required) or len(set(required)) != len(required) or set(required) - {r['name'] for r in manifest['redirected']}:
        parser.error('require distinct names from the manifest redirect set')
    if args.period < 20000:
        parser.error('period must be >= 20000')
    if not 1 <= args.repeat <= 32:
        parser.error('repeat must be 1..32')
    check_artifacts(out, manifest)
    evidence_dir = Path(tempfile.mkdtemp(prefix='pi-verify-', dir=out))

    def boot(name, image, commands):
        cmd = [sys.executable, str(HERE / 'pi4_run.py'), str(image), '--port', args.port,
               '--reboot', '--wait', '30', '--max-wait', '120', '--wdog', '180']
        if args.fast_loader:
            cmd += ['--fast-loader', str(args.fast_loader.resolve())]
        run = run_bounded([*cmd, *commands], 600)
        text = run.stdout.decode('utf-8', 'replace')
        (evidence_dir / (name + '.log')).write_text(text, encoding='utf-8')
        if run.returncode:
            raise ValueError(f'{name} child failed ({run.returncode}); see {evidence_dir}')
        return text

    baseline = boot('baseline', out / 'baseline.bin', ['bolt_bench all'])
    expected = parse_results(baseline)
    buffer = manifest['sample_buffer']
    candidate = boot('candidate', out / 'baseline_full.bin', [f'bolt_sample start {args.period}',
                     *(['bolt_bench all'] * args.repeat), 'bolt_sample stop',
                     f'bolt_dump {buffer["address"]:x} {buffer["size"]:x}'])
    actual = parse_results(candidate)
    if expected != actual:
        raise ValueError('candidate workload results differ from baseline')
    check_artifacts(out, manifest)  # Do not certify artifacts modified during a run.
    evidence = execution_evidence(candidate, manifest, required)
    result = dict(schema=1, execution_verified=True, verified_at=datetime.now(timezone.utc).isoformat(),
                  scope='required redirected functions only; emitted functions are not execution coverage',
                  manifest_sha256=sha256(out / 'full_manifest.json'),
                  baseline_log_sha256=sha256(evidence_dir / 'baseline.log'),
                  candidate_log_sha256=sha256(evidence_dir / 'candidate.log'),
                  workload_results=actual, sampling_period=args.period, workload_repetitions=args.repeat, **evidence)
    (evidence_dir / 'verification.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(f'PASS: {len(actual)} workload results; PC evidence for {len(required)} required rewritten functions')
    print(evidence_dir / 'verification.json')
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except (OSError, ValueError, KeyError, struct.error) as error:
        sys.exit(f'error: {error}')
