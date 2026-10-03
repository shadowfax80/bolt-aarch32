#!/usr/bin/env python3
"""Sample-based BOLT profile from a real Pi: no instrumented image.

Boots the image that will be optimized (unmodified), samples the interrupted PC every
<period> CPU cycles with bolt_bench's `bolt_sample` (PMU counter-5 overflow) while the
workload runs, reads the sample buffer back with `bolt_dump` (checksum-verified chunk by
chunk), and writes the samples as raw little-endian words (bit 0 = Thumb).
samples_to_fdata.py turns them into a perf2bolt profile.

usage: pi4_sample_profile.py <image.bin> <out.samples> --buf 800420e0 [--period 20000]
                             [--workload "stair 0 0"] [--repeat N]
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import sys
import tempfile
import json
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
sys.path.insert(0, HERE)
from proc_util import run_bounded  # noqa: E402
from bolt_dump_reassemble import parse_dump_stream  # noqa: E402
from profile_identity import read_json, check_build, sha256, publish_files  # noqa: E402
from passes_check import EXPECTED_WORKLOADS, RESULT_RE, parse_results  # noqa: E402

BUF_BYTES = (1 << 17) * 4  # BB_SAMPLE_MAX words in bolt_bench.c


def validate_capture(text, buffer, workload, repeat, period):
    name = workload.split()[0]
    if name == 'all':
        results = parse_results(text)
        expected = set(EXPECTED_WORKLOADS)
    else:
        if name not in (*EXPECTED_WORKLOADS, 'multi'):
            raise ValueError('unsupported training workload')
        if re.search(r'bolt_bench: \w+ FAIL\b', text):
            raise ValueError('workload reported a failure')
        expected = {name}
        results = {}
        for found, value in RESULT_RE.findall(text):
            if found in results and results[found] != value:
                raise ValueError('conflicting training results')
            results[found] = value
    reports = re.findall(r'bolt_bench: (\w+) (sink|acc)=(0x[0-9a-f]+)', text)
    names = [n for n, _, _ in reports]
    # `all` prints a final sink for every workload. Composite and stair also
    # print their internal acc result: these are two observations of one run.
    # For a single workload, prefer its sink when present, otherwise its acc.
    completion = {n: ('sink' if name == 'all' or any(w == n and k == 'sink' for w, k, _ in reports)
                      else 'acc') for n in expected}
    if set(names) != expected or any(sum(w == n and k == completion[n] for w, k, _ in reports) != repeat for n in expected):
        raise ValueError('training workloads did not complete the requested repetitions')
    if 'pmu INVALID' in text:
        raise ValueError('training thread migrated during PMU measurement')
    starts = re.findall(r'bolt_sample: on, every (\d+) cycles', text)
    if starts != [str(period)]:
        raise ValueError('sampling start/period report does not match request')
    reports = re.findall(r'bolt_sample: (\d+) samples \((\d+) taken\) buf=0x([0-9a-f]+) bytes=0x([0-9a-f]+)', text)
    if len(reports) != 1:
        raise ValueError('expected exactly one sample completion report')
    kept, taken, address, size = reports[0]
    kept, taken, address, size = int(kept), int(taken), int(address, 16), int(size, 16)
    if not 0 < kept == taken < buffer['size'] // 4 or address != buffer['address'] or size != kept * 4:
        raise ValueError('sample buffer is empty, saturated, truncated or mismatched')
    cores = re.findall(r'bolt_sample: cpu (\d+); PMU interrupts per core: (\d+) (\d+) (\d+) (\d+)', text)
    if len(cores) != 1:
        raise ValueError('missing sampling core/PMU report')
    cpu, *irqs = map(int, cores[0])
    if cpu not in range(4) or irqs[cpu] == 0 or sum(irqs) < taken:
        raise ValueError('inconsistent sampling core/PMU counts')
    # The present runtime arms all cores. Preserve that fact instead of
    # claiming the sample stream belongs exclusively to the workload core.
    if len(re.findall('BOLT_DUMP_BEGIN', text)) != 1 or len(re.findall('BOLT_DUMP_END', text)) != 1:
        raise ValueError('expected one complete sample buffer dump')
    result = parse_dump_stream(text)
    if ((result.addr, result.size) != (buffer['address'], buffer['size']) or result.bad_seqs
            or not result.is_complete() or result.total_seq != (buffer['size'] + 63) // 64
            or any(off < 0 or off + len(data) > result.size for off, data in result.chunks.items())):
        raise ValueError('sample dump is corrupt, incomplete or outside the image buffer')
    return result.to_bytes()[:size], dict(kept=kept, taken=taken, workload_results=results,
                                         workload_core=cpu, interrupts_per_core=irqs,
                                         sampling_scope='all cores; IRQ-masked code is invisible; not exact edge counts')


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("image")
    ap.add_argument("out")
    ap.add_argument("--elf", required=True, help="exact ELF used to create the uploaded binary")
    ap.add_argument("--build-manifest", help="default: IMAGE.manifest.json (seal before capture)")
    ap.add_argument("--buf", help="optional buffer address (hex); must match the sealed ELF")
    ap.add_argument("--period", type=int, default=20000, help="CPU cycles between samples")
    ap.add_argument("--workload", default="all")
    ap.add_argument("--repeat", type=int, default=1, help="run the workload this many times")
    ap.add_argument("--port", default="COM5")
    ap.add_argument("--fast-loader", help="temporary loader uploaded without changing the SD card")
    args = ap.parse_args()

    if not 20000 <= args.period <= 0x7fffffff or not 1 <= args.repeat <= 32:
        ap.error('period must be 20000..2147483647; repeat must be 1..32')
    if not args.workload.split() or args.workload.split()[0] not in (*EXPECTED_WORKLOADS, 'all', 'multi'):
        ap.error('unsupported training workload')
    manifest_path = args.build_manifest or args.image + '.manifest.json'
    manifest = read_json(manifest_path)
    check_build(manifest, args.image, args.elf)
    manifest_hash = sha256(manifest_path)
    buffer = manifest['sample_buffer']
    if buffer['size'] != BUF_BYTES or args.buf and int(args.buf, 16) != buffer['address']:
        ap.error('buffer does not match sealed image')
    evidence = Path(tempfile.mkdtemp(prefix='pi-samples-', dir=Path(args.out).resolve().parent))
    # Upload immutable session copies, so an in-progress rebuild cannot silently
    # change the image between the identity check and the uploader opening it.
    image, elf = evidence / 'image.bin', evidence / 'image.elf'
    shutil.copyfile(args.image, image)
    shutil.copyfile(args.elf, elf)
    check_build(manifest, image, elf)
    cmd = [
        sys.executable, os.path.join(HERE, "pi4_run.py"), str(image),
        "--port", args.port, "--reboot", "--wait", "60", "--max-wait", "120",
        "--wdog", "180",
    ]
    if args.fast_loader:
        cmd += ['--fast-loader', args.fast_loader]
    cmd += [
        f"bolt_sample start {args.period}", *[f"bolt_bench {args.workload}"] * args.repeat,
        "bolt_sample stop",
        f"bolt_dump {buffer['address']:x} {buffer['size']:x}",
    ]
    out = run_bounded(cmd, 900)
    text = out.stdout.decode("utf-8", errors="replace")
    log = evidence / 'capture.log'
    log.write_text(text, encoding='utf-8')
    if out.returncode != 0:
        sys.exit(f"pi4_run.py failed ({out.returncode}):\n{text[-2000:]}")
    blob, observations = validate_capture(text, buffer, args.workload, args.repeat, args.period)
    check_build(manifest, image, elf)
    check_build(manifest, args.image, args.elf)
    if sha256(manifest_path) != manifest_hash:
        raise ValueError('build manifest changed during capture')
    staged = evidence / 'capture.samples'
    staged.write_bytes(blob)
    capture = dict(schema=1, kind='pi-pc-capture', verified_binding=True, build=manifest,
                   build_manifest_sha256=manifest_hash, payload_sha256=sha256(staged),
                   log_sha256=sha256(log), log_path=str(log), period=args.period,
                   workload=args.workload, repetitions=args.repeat, port=args.port,
                   collector_sha256=sha256(__file__), **observations)
    publish_files({args.out: staged.read_bytes(), args.out + '.manifest.json':
                   (json.dumps(capture, indent=2) + '\n').encode('utf-8')})
    print(f"wrote {observations['kept']} samples (period {args.period} cycles) to {args.out}")
    print(f'capture evidence: {evidence}')
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, ValueError, KeyError) as error:
        sys.exit(f'error: invalid sample capture: {error}')
