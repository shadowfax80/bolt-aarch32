#!/usr/bin/env python3
"""Collect BOLT instrumentation counters from a real Pi.

Boots a BOLT-instrumented LK image (llvm-bolt -instrument, then objcopy -O
binary), runs the training workload, then reads the `.bolt.instr.counters`
section back over UART with `bolt_dump` (checksum-verified chunk by chunk).
The output is byte-for-byte what QEMU's QMP memsave used to produce, so
ram-dump-to-fdata.py converts it to .fdata unchanged.

The section address/size come from the instrumented ELF on the build host:
    llvm-readelf --sections lk.instr.elf | grep bolt.instr.counters

usage: pi4_bolt_profile.py <instr.bin> <out.bin> --addr 8002a000 --size 100d
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
from bolt_dump_reassemble import parse_dump_stream  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("image")
    ap.add_argument("out")
    ap.add_argument("--addr", required=True, help="counter section address (hex)")
    ap.add_argument("--size", required=True, help="counter section size (hex)")
    ap.add_argument("--workload", default="composite")
    ap.add_argument("--port", default="COM5")
    args = ap.parse_args()

    cmd = [
        sys.executable, os.path.join(HERE, "pi4_run.py"), args.image,
        "--port", args.port, "--reboot", "--wait", "30", "--max-wait", "60",
        f"bolt_bench {args.workload}", f"bolt_dump {args.addr} {args.size}",
    ]
    out = subprocess.run(cmd, capture_output=True)
    text = out.stdout.decode("utf-8", errors="replace")
    if out.returncode != 0:
        sys.exit(f"pi4_run.py failed ({out.returncode}):\n{text[-2000:]}")

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
