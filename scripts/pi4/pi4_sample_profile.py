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
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
sys.path.insert(0, HERE)
from proc_util import run_bounded  # noqa: E402
from bolt_dump_reassemble import parse_dump_stream  # noqa: E402

BUF_BYTES = (1 << 17) * 4  # BB_SAMPLE_MAX words in bolt_bench.c


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("image")
    ap.add_argument("out")
    ap.add_argument("--buf", required=True, help="address of bolt_sample_buf (hex)")
    ap.add_argument("--period", type=int, default=20000, help="CPU cycles between samples")
    ap.add_argument("--workload", default="stair 0 0")
    ap.add_argument("--repeat", type=int, default=1, help="run the workload this many times")
    ap.add_argument("--port", default="COM5")
    args = ap.parse_args()

    cmd = [
        sys.executable, os.path.join(HERE, "pi4_run.py"), args.image,
        "--port", args.port, "--reboot", "--wait", "60", "--max-wait", "120",
        f"bolt_sample start {args.period}", *[f"bolt_bench {args.workload}"] * args.repeat,
        "bolt_sample stop",
        f"bolt_dump {args.buf} {BUF_BYTES:x}",
    ]
    out = run_bounded(cmd, 900)
    text = out.stdout.decode("utf-8", errors="replace")
    if out.returncode != 0:
        sys.exit(f"pi4_run.py failed ({out.returncode}):\n{text[-2000:]}")
    m = re.search(r"bolt_sample: (\d+) samples \((\d+) taken\)", text)
    if not m:
        sys.exit("no `bolt_sample stop` report in the output")
    kept, taken = int(m[1]), int(m[2])
    result = parse_dump_stream(text)
    if result.bad_seqs:
        print(f"note: {len(result.bad_seqs)} chunk(s) failed checksum", file=sys.stderr)
    if not result.is_complete():
        sys.exit(f"dump incomplete: missing {result.missing_ranges()}")
    blob = result.to_bytes()[: kept * 4]
    with open(args.out, "wb") as fh:
        fh.write(blob)
    print(f"wrote {kept} samples ({taken} taken, period {args.period} cycles) to {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
