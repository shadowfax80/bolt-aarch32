#!/usr/bin/env python3
"""Collect a BOLT PC-sample profile with lk-perf's sampler (B1).

The image must contain lk-perf's `app/profiler` (lk-perf kernel overlays on this
repo's LK). Sampling uses lk-perf's timer mode (K10): the per-core virtual
timer, one sample at a random point of every period, independent of the PMU
that bolt_bench's own measurements reprogram. Each capture cycle clears the
buffer, samples the workload commands, stops, and dumps; lk-perf's host parser
verifies every record checksum, the dump footer, and the dump's image hash
against the ELF. The PCs (bit 0 = Thumb, from the sampled SPSR) are written in
samples_to_fdata.py's input format with a `pi-pc-capture` identity manifest
bound to the sealed image (`profile_identity.py seal-samples`), so the rest of
the verified sampling route is unchanged:

    profile_identity.py seal-samples --elf E --image B ... --out B.manifest.json
    pi4_lkperf_profile.py B E out.samples --cycles 10 -- "bolt_bench stair"
    samples_to_fdata.py E out.samples -o out.fdata
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tempfile

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from profile_identity import check_build, publish_files, read_json, sha256  # noqa: E402

SPSR_T = 1 << 5


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('image')
    ap.add_argument('elf')
    ap.add_argument('out')
    ap.add_argument('--build-manifest', help='default: IMAGE.manifest.json (seal-samples)')
    ap.add_argument('--lkperf-scripts', default=str(HERE.parents[2] / 'lk-perf' / 'scripts'),
                    help="lk-perf's scripts directory (host parser)")
    ap.add_argument('--period-us', type=int, default=50)
    ap.add_argument('--cycles', type=int, default=4, help='clear/sample/dump cycles')
    ap.add_argument('--setup', action='append', default=[],
                    help='command run once before the capture cycles, e.g. "profiler nmion" '
                         '(pseudo-NMI: samples reach IRQ-masked code); repeatable')
    ap.add_argument('--per-command', action='store_true',
                    help='one clear/sample/dump cycle per workload command, so a long suite does '
                         'not wrap the per-core ring (samples stay proportional to run time)')
    ap.add_argument('--port', default='COM5')
    ap.add_argument('--max-wait', type=float, default=300)
    ap.add_argument('workload', nargs='+', help='shell commands run while sampling (after --)')
    args = ap.parse_args()
    sys.path.insert(0, args.lkperf_scripts)
    from pi4_pc_histogram import (check_build as lkperf_check_build, parse_samples, parse_session,
                                  read_lines, split_dumps)

    manifest_path = args.build_manifest or args.image + '.manifest.json'
    build = read_json(manifest_path)
    check_build(build, args.image, args.elf)
    manifest_hash = sha256(manifest_path)
    evidence = Path(tempfile.mkdtemp(prefix='lkperf-capture-', dir=Path(args.out).resolve().parent))
    image = evidence / 'image.bin'
    shutil.copyfile(args.image, image)
    if sha256(image) != build['binary_sha256']:
        raise ValueError('image changed while making the upload copy')
    log = evidence / 'capture.log'
    commands = list(args.setup)
    groups = [[w] for w in args.workload] if args.per_command else [args.workload]
    for _ in range(args.cycles):
        for group in groups:
            commands += ['profiler clear', f'profiler start {args.period_us}', *group,
                         'profiler stop', 'profiler dump']
    expected = args.cycles * len(groups)
    cmd = [sys.executable, str(HERE / 'pi4_run.py'), str(image), '--port', args.port, '--reboot',
           '--wait', '30', '--max-wait', str(args.max_wait), '--log', str(log), *commands]
    r = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
    if r.returncode:
        raise ValueError('capture run failed: ' + r.stderr[-800:])

    dumps = split_dumps(read_lines(log)) or []
    if len(dumps) != expected:
        raise ValueError(f'expected {expected} dumps, found {len(dumps)}')
    words, sent, accepted, per_dump = [], 0, 0, []
    for d in range(expected):
        session = parse_session(dumps[d]['lines'])
        built, host_hash = lkperf_check_build(args.elf, session)
        if not built:
            raise ValueError(f'dump {d}: image hash {session["header"]["build"]:08x} '
                             f'does not match the ELF ({host_hash})')
        samples = parse_samples(str(log), d)
        n = session['footer']['samples'] if session['footer'] else None
        if session['header']['tperiod'] is not None and session['cpus'] and any(
                c.get('overwritten') for c in session['cpus'].values()):
            raise ValueError(f'dump {d}: the per-core ring wrapped; use --per-command or a longer period')
        sent += n or 0
        accepted += len(samples)
        per_dump.append(dict(sent=n, accepted=len(samples), problems=session['problems']))
        for s in samples:
            words.append((s['pc'] & ~1) | (1 if s['spsr'] & SPSR_T else 0))
    if not words:
        raise ValueError('no samples')
    staged = evidence / 'samples.bin'
    staged.write_bytes(struct.pack(f'<{len(words)}I', *words))
    capture = dict(schema=1, kind='pi-pc-capture', verified_binding=True, build=build,
                   build_manifest_sha256=manifest_hash, payload_sha256=sha256(staged),
                   log_sha256=sha256(log), log_path=str(log),
                   period=f'lk-perf timer {args.period_us} us (virtual timer, stratified)',
                   sampler='lk-perf app/profiler', setup=args.setup, workload=args.workload,
                   repetitions=args.cycles, per_command=args.per_command, port=args.port, collector_sha256=sha256(__file__),
                   kept=len(words), records_sent=sent, records_accepted=accepted, dumps=per_dump)
    publish_files({args.out: staged.read_bytes(),
                   args.out + '.manifest.json': (json.dumps(capture, indent=2) + '\n').encode('utf-8')})
    print(f'{len(words)} samples ({sent - accepted} of {sent} records lost in transfer) -> {args.out}')
    print(f'capture evidence: {evidence}')
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except (OSError, ValueError, KeyError) as error:
        sys.exit(f'error: {error}')
