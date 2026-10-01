#!/usr/bin/env python3
"""PC samples (pi4_sample_profile.py output, or any list of interrupted PCs) -> BOLT profile.

Aggregates the samples into perf2bolt's pre-aggregated format (`S <address> <count>`, the
no-LBR "basic sample" record) and runs `perf2bolt -nl -pa` on the image the samples were
taken from. The result is an ordinary .fdata for llvm-bolt -data=. Samples outside any
function (e.g. the idle loop of another core is still a function, but a PC in a constant
island is not) are counted and reported, not dropped silently.

usage: samples_to_fdata.py <image.elf> <in.samples> -o <out.fdata> [--toolchain build-atfe/bin]
"""

from __future__ import annotations

import argparse
import collections
import os
import struct
import subprocess
import sys


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("elf")
    ap.add_argument("samples")
    ap.add_argument("-o", "--out", required=True)
    ap.add_argument("--toolchain", default=os.environ.get("TOOLCHAIN", "build-atfe/bin"))
    args = ap.parse_args()

    data = open(args.samples, "rb").read()
    words = struct.unpack(f"<{len(data) // 4}I", data[: len(data) // 4 * 4])
    if not words:
        sys.exit("no samples")
    counts = collections.Counter(w & ~1 for w in words)
    preagg = args.out + ".preagg"
    with open(preagg, "w") as fh:
        for addr, n in sorted(counts.items()):
            fh.write(f"S {addr:x} {n}\n")
    r = subprocess.run([os.path.join(args.toolchain, "perf2bolt"), args.elf, "-nl", "-pa",
                        "-p", preagg, "-o", args.out], capture_output=True, text=True)
    sys.stdout.write(r.stdout[-1500:])
    if r.returncode != 0 or not os.path.exists(args.out) or not os.path.getsize(args.out):
        sys.stderr.write(r.stderr[-1500:])
        sys.exit("perf2bolt failed")
    print(f"{len(words)} samples, {len(counts)} distinct PCs -> {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
