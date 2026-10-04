#!/usr/bin/env python3
"""Pi gate: exact artifacts, all workloads, and PCs in required rewritten bodies.

Usage: full_image_verify.py OUTDIR --require-executed NAME[,NAME...] [--port COM5]
OUTDIR is produced by full_image_build.py. Every selected redirect requires PC
evidence; other emitted symbols are outside that execution claim.
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
import shutil
import subprocess
import os

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parent)]
from passes_check import parse_results
from proc_util import run_bounded
from bolt_dump_reassemble import validate_single_dump
from profile_identity import check_profile
from pi4_sample_profile import validate_capture
from qemu_bench_oracle import check_contract,check_results


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
    if 'profile' in manifest:
        profile = manifest['profile']
        if (sha256(out / 'profile.fdata') != profile['profile_sha256']
                or sha256(out / 'profile.fdata.manifest.json') != profile['manifest_sha256']):
            raise ValueError('profile or its identity manifest changed after the build')
        check_profile(out / 'baseline.elf', out / 'profile.fdata')
    image = (out / 'baseline_full.bin').read_bytes()
    elf = (out / 'baseline_full.elf').read_bytes()
    sections = loadable_sections(elf)
    physical_base = min(s['physical'] for s in sections)
    emitted = {row['name']: row for row in manifest['emitted']}
    if len(emitted) != len(manifest['emitted']):
        raise ValueError('duplicate emitted coverage')
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


def execution_evidence(text, manifest, required, repetitions=1, sampling_period=None):
    parse_results(text, repetitions)  # Every requested workload repetition must finish.
    names = [r['name'] for r in manifest['redirected']]
    if not names or len(set(names)) != len(names) or len(set(required)) != len(required) or set(required) != set(names):
        raise ValueError('execution requirement must cover every selected redirect exactly')
    reports = list(re.finditer(r'bolt_sample: (\d+) samples \((\d+) taken\) buf=0x([0-9a-f]+) bytes=0x([0-9a-f]+)', text))
    if len(reports) != 1:
        raise ValueError('expected exactly one sample completion report')
    kept, taken, address, size = reports[0].groups()
    kept, taken, address, size = int(kept), int(taken), int(address, 16), int(size, 16)
    buffer = manifest['sample_buffer']
    capture_metadata = None
    if sampling_period is not None:
        _, capture_metadata = validate_capture(text, buffer, 'all', repetitions, sampling_period)
    if not 0 < kept == taken < buffer['size'] // 4 or size != kept * 4 or address != buffer['address']:
        raise ValueError('invalid, saturated or mismatched sample report')
    raw = validate_single_dump(text, buffer['address'], buffer['size'])[:size]
    samples = struct.unpack(f'<{kept}I', raw)
    coverage = []
    for row in manifest['redirected']:
        hits = sum(row['output'] <= (pc & ~1) < row['output'] + row['output_size']
                   and bool(pc & 1) == row['thumb'] and (row['thumb'] or pc % 4 == 0) for pc in samples)
        coverage.append(dict(name=row['name'], pc_samples=hits, execution_observed=bool(hits), required=row['name'] in required))
    observed = {r['name'] for r in coverage if r['execution_observed']}
    if set(required) - observed:
        raise ValueError('no rewritten execution observed for: ' + ', '.join(sorted(set(required) - observed)))
    return dict(kept_samples=kept, taken_samples=taken, redirected_coverage=coverage,
                required_executed=required, sampled_pc_sha256=hashlib.sha256(raw).hexdigest(),
                sampling_capture=capture_metadata)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('outdir', type=Path)
    parser.add_argument('--require-executed', help='optional exact comma-separated redirect set; default: every redirect')
    parser.add_argument('--port', default='COM5')
    parser.add_argument('--fast-loader', type=Path)
    parser.add_argument('--period', type=int, default=20000)
    parser.add_argument('--repeat', type=int, default=5,
                        help='repeat all workloads to sample short rewritten bodies (1..32; default 5)')
    args = parser.parse_args()
    if args.fast_loader is None and os.environ.get('PI4_FAST_LOADER'):
        args.fast_loader = Path(os.environ['PI4_FAST_LOADER'])
    out = args.outdir.resolve()
    manifest_bytes = (out / 'full_manifest.json').read_bytes()
    manifest = json.loads(manifest_bytes)
    manifest_hash = hashlib.sha256(manifest_bytes).hexdigest()
    script_paths = [Path(__file__), HERE/'pi4_run.py', HERE/'pi4_serial_boot.py', HERE/'passes_check.py',
                    HERE/'pi4_sample_profile.py', HERE/'proc_util.py', HERE.parent/'bolt_dump_reassemble.py',
                    HERE.parent/'profile_identity.py',HERE.parent/'qemu_bench_oracle.py']
    script_hashes = {p.name: sha256(p) for p in script_paths}
    revision = subprocess.check_output(['git', '-C', str(HERE.parent.parent), 'rev-parse', 'HEAD'], text=True).strip()
    required = args.require_executed.split(',') if args.require_executed else [r['name'] for r in manifest['redirected']]
    if not all(required) or len(set(required)) != len(required) or set(required) != {r['name'] for r in manifest['redirected']}:
        parser.error('require distinct names covering every selected redirect')
    if args.period < 20000:
        parser.error('period must be >= 20000')
    if not 1 <= args.repeat <= 32:
        parser.error('repeat must be 1..32')
    check_artifacts(out, manifest)
    # Baseline equality alone cannot certify correctness. Whole-LK inputs still
    # require their own reviewed Pi source/configuration oracle contract.
    check_contract(manifest['input_sha256'],'pi4')
    evidence_dir = Path(tempfile.mkdtemp(prefix='pi-verify-', dir=out))
    (evidence_dir / 'build_manifest.json').write_bytes(manifest_bytes)
    if sha256(evidence_dir / 'build_manifest.json') != manifest_hash:
        raise ValueError('build manifest changed while snapshotting')
    uploads = {}
    for name, filename, key in [('baseline', 'baseline.bin', 'baseline_binary_sha256'),
                                 ('candidate', 'baseline_full.bin', 'binary_sha256')]:
        upload = evidence_dir / (name + '.bin')
        shutil.copyfile(out / filename, upload)
        if sha256(upload) != manifest[key]:
            raise ValueError('image changed while snapshotting: ' + name)
        uploads[name] = upload
    loader_hash = sha256(args.fast_loader.resolve()) if args.fast_loader else None
    loader_copy = None
    if args.fast_loader:
        loader_copy = evidence_dir / 'fast-loader.img'
        shutil.copyfile(args.fast_loader.resolve(), loader_copy)
        if sha256(loader_copy) != loader_hash:
            raise ValueError('fast loader changed while snapshotting')

    def boot(name, image, commands):
        cmd = [sys.executable, str(HERE / 'pi4_run.py'), str(image), '--port', args.port,
               '--reboot', '--wait', '30', '--max-wait', '120', '--wdog', '180']
        if args.fast_loader:
            if sha256(args.fast_loader.resolve()) != loader_hash:
                raise ValueError('fast loader changed during verification')
            cmd += ['--fast-loader', str(loader_copy)]
        run = run_bounded([*cmd, *commands], 600)
        text = run.stdout.decode('utf-8', 'replace')
        (evidence_dir / (name + '.log')).write_text(text, encoding='utf-8')
        if run.returncode:
            raise ValueError(f'{name} child failed ({run.returncode}); see {evidence_dir}')
        return text

    baseline = boot('baseline', uploads['baseline'], ['bolt_bench all'])
    expected = parse_results(baseline)
    baseline_oracle=check_results(manifest['input_sha256'],expected,'pi4')
    buffer = manifest['sample_buffer']
    candidate = boot('candidate', uploads['candidate'], [f'bolt_sample start {args.period}',
                     *(['bolt_bench all'] * args.repeat), 'bolt_sample stop',
                     f'bolt_dump {buffer["address"]:x} {buffer["size"]:x}'])
    actual = parse_results(candidate, args.repeat)
    candidate_oracle=check_results(manifest['input_sha256'],actual,'pi4')
    if expected != actual:
        raise ValueError('candidate workload results differ from baseline')
    check_artifacts(out, manifest)  # Do not certify artifacts modified during a run.
    if sha256(out / 'full_manifest.json') != manifest_hash:
        raise ValueError('build manifest changed during verification')
    for name, key in [('baseline', 'baseline_binary_sha256'), ('candidate', 'binary_sha256')]:
        if sha256(uploads[name]) != manifest[key]:
            raise ValueError('immutable upload copy changed: ' + name)
    if args.fast_loader and sha256(args.fast_loader.resolve()) != loader_hash:
        raise ValueError('fast loader changed during verification')
    if loader_copy and sha256(loader_copy) != loader_hash:
        raise ValueError('fast loader upload copy changed during verification')
    if (script_hashes != {p.name: sha256(p) for p in script_paths}
            or revision != subprocess.check_output(['git', '-C', str(HERE.parent.parent), 'rev-parse', 'HEAD'], text=True).strip()):
        raise ValueError('verifier scripts or repository revision changed during verification')
    evidence = execution_evidence(candidate, manifest, required, args.repeat, args.period)
    result = dict(schema=1, execution_verified=True, verified_at=datetime.now(timezone.utc).isoformat(),
                  scope='every selected redirect; other emitted functions are not execution coverage',
                  manifest_sha256=manifest_hash, verifier_sha256=sha256(__file__),
                  fast_loader_sha256=loader_hash,
                  uploaded_images={name: sha256(path) for name, path in uploads.items()},
                  selected_functions=required, emitted_functions=[r['name'] for r in manifest['emitted']],
                  redirected_functions=[r['name'] for r in manifest['redirected']],
                  expected_workload_results=expected,
                  independent_oracles=dict(baseline=baseline_oracle,candidate=candidate_oracle),
                  repository_revision=revision, script_sha256=script_hashes,
                  build_provenance={key: manifest.get(key) for key in ('repository_revision', 'bolt_options', 'tool_sha256', 'patch_sha256', 'script_sha256')},
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
