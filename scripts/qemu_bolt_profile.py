#!/usr/bin/env python3
"""QEMU counterpart of pi4/pi4_bolt_profile.py, for debugging the BOLT pipeline
where the Pi's output is unreadable or a crash would need a power-cycle. Runs
the training workload in a BOLT-instrumented ELF under QEMU, reads the counter
section back with `bolt_dump`, and writes the same raw file ram-dump-to-fdata.py
consumes. Counts from QEMU are not performance data -- only structure/debugging.

usage: qemu_bolt_profile.py <instr.elf> <out.bin> --addr 8014b000 --size 218a
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from bolt_dump_reassemble import parse_dump_stream  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("elf")
    ap.add_argument("out")
    ap.add_argument("--addr", required=True)
    ap.add_argument("--size", required=True)
    ap.add_argument("--workload", default="composite")
    ap.add_argument("--smp", default="4")
    args = ap.parse_args()

    cmd = [
        sys.executable, os.path.join(HERE, "qemu_console.py"), args.elf,
        "--smp", args.smp, "--wait", "25",
        f"bolt_bench {args.workload}", f"bolt_dump {args.addr} {args.size}",
    ]
    text = subprocess.run(cmd, capture_output=True, timeout=200).stdout.decode("utf-8", "replace")
    if "panic" in text:
        sys.exit("panic while profiling:\n" + text[-1500:])
    result = parse_dump_stream(text.replace("\r", ""))
    if not result.is_complete():
        sys.exit(f"dump incomplete: missing {result.missing_ranges()}\n{text[-800:]}")
    with open(args.out, "wb") as fh:
        fh.write(result.to_bytes())
    print(f"wrote {args.size} bytes (0x) to {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
