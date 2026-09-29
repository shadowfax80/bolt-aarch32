#!/usr/bin/env python3
"""Collect a PGO raw profile from a `pgo-collect` LK image on the real Pi.

Boots the image, runs the training workload, and has the device serialize its
counters into a buffer (`bolt_pgo_dump`, which prints the buffer's address and
size). The size is fixed per binary but not known until the device says so, so
this boots twice: once to learn addr/size, once to run the workload again and
`bolt_dump` exactly that range. The dump is checksum-verified chunk by chunk
(bolt_dump_reassemble.py); the result is a raw instrprof file that
llvm-profdata reads directly.

usage: pi4_pgo_collect.py <pgo-collect.bin> <out.profraw> [--workload composite]
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
from bolt_dump_reassemble import parse_dump_stream  # noqa: E402

PGO_RE = re.compile(r"bolt_pgo_dump: addr=([0-9a-fA-F]+) size=([0-9a-fA-F]+)")


def run_pi(image: str, port: str, commands: list[str]) -> str:
    cmd = [
        sys.executable, os.path.join(HERE, "pi4_run.py"), image,
        "--port", port, "--reboot", "--wait", "30", "--max-wait", "60",
    ] + commands
    out = subprocess.run(cmd, capture_output=True)
    text = out.stdout.decode("utf-8", errors="replace")
    if out.returncode != 0:
        sys.exit(f"pi4_run.py failed ({out.returncode}):\n{text[-2000:]}\n{out.stderr.decode(errors='replace')[-1000:]}")
    return text


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("image")
    ap.add_argument("out")
    ap.add_argument("--workload", default="composite")
    ap.add_argument("--port", default="COM5")
    args = ap.parse_args()

    work = f"bolt_bench {args.workload}"

    text = run_pi(args.image, args.port, [work, "bolt_pgo_dump"])
    m = PGO_RE.search(text)
    if not m:
        sys.exit("no 'bolt_pgo_dump: addr=.. size=..' in output -- is this a pgo-collect image?")
    addr, size = m.group(1), m.group(2)
    print(f"profile buffer: addr=0x{addr} size=0x{size}")

    text = run_pi(args.image, args.port, [work, "bolt_pgo_dump", f"bolt_dump {addr} {size}"])
    result = parse_dump_stream(text)
    if result.bad_seqs:
        print(f"note: {len(result.bad_seqs)} chunk(s) failed checksum", file=sys.stderr)
    if not result.is_complete():
        sys.exit(f"dump incomplete: missing {result.missing_ranges()}")
    blob = result.to_bytes()
    with open(args.out, "wb") as fh:
        fh.write(blob)
    print(f"wrote {len(blob)} bytes to {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
