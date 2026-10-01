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
import tempfile


def load_samples(path: str) -> tuple[int, ...]:
    with open(path, "rb") as stream:
        data = stream.read()
    if not data:
        raise ValueError("no samples")
    if len(data) % 4:
        raise ValueError(f"truncated PC sample: {len(data)} bytes is not a multiple of four")
    return struct.unpack(f"<{len(data) // 4}I", data)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("elf")
    ap.add_argument("samples")
    ap.add_argument("-o", "--out", required=True)
    ap.add_argument("--toolchain", default=os.environ.get("TOOLCHAIN", "build-atfe/bin"))
    args = ap.parse_args()

    words = load_samples(args.samples)
    counts = collections.Counter(w & ~1 for w in words)
    preagg = args.out + ".preagg"
    destination = os.path.abspath(args.out)
    with tempfile.TemporaryDirectory(dir=os.path.dirname(destination)) as temporary:
        staged_preagg = os.path.join(temporary, "profile.preagg")
        staged_fdata = os.path.join(temporary, "profile.fdata")
        with open(staged_preagg, "w") as fh:
            for addr, n in sorted(counts.items()):
                fh.write(f"S {addr:x} {n}\n")
        r = subprocess.run([os.path.join(args.toolchain, "perf2bolt"), args.elf, "-nl", "-pa",
                            "-p", staged_preagg, "-o", staged_fdata], capture_output=True, text=True)
        sys.stdout.write(r.stdout[-1500:])
        if r.returncode != 0 or not os.path.exists(staged_fdata) or not os.path.getsize(staged_fdata):
            sys.stderr.write(r.stderr[-1500:])
            sys.exit("perf2bolt failed")
        os.replace(staged_preagg, preagg)
        os.replace(staged_fdata, destination)
    print(f"{len(words)} samples, {len(counts)} distinct PCs -> {args.out}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, ValueError) as error:
        sys.exit(f"error: invalid sample input: {error}")
