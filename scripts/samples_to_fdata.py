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
import json

from profile_identity import (check_capture, sha256, validate_sample_fdata, publish_files)


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
    ap.add_argument("--capture-manifest", help="default: SAMPLES.manifest.json")
    ap.add_argument("--functions", help="explicit comma-separated source functions; record all excluded profile counts")
    ap.add_argument("--debug-unbound", action="store_true",
                    help="diagnostic conversion only; output cannot pass the optimization identity gate")
    args = ap.parse_args()
    selected = args.functions.split(',') if args.functions is not None else None
    if selected is not None and args.debug_unbound:
        ap.error('source function scoping requires a bound capture')

    manifest_path = args.capture_manifest or args.samples + '.manifest.json'
    capture = None if args.debug_unbound else check_capture(manifest_path, args.samples, args.elf, 'pi-pc-capture')
    capture_hash = sha256(manifest_path) if capture else None
    converter_hash = sha256(os.path.join(args.toolchain, 'perf2bolt')) if capture else None
    if capture and converter_hash != capture['build']['tools']['perf2bolt']:
        raise ValueError('perf2bolt differs from the sealed toolchain')
    words = load_samples(args.samples)
    profile_scope = dict(selected_functions=None, excluded_profile_counts={})
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
        if capture:
            profile_scope = validate_sample_fdata(staged_fdata, capture['build']['functions'], selected)
            # Do not publish a conversion if its inputs changed while perf2bolt ran.
            check_capture(manifest_path, args.samples, args.elf, 'pi-pc-capture')
            if sha256(manifest_path) != capture_hash or sha256(os.path.join(args.toolchain, 'perf2bolt')) != converter_hash:
                raise ValueError('capture manifest or perf2bolt changed during conversion')
        profile_manifest = dict(schema=1, kind='bolt-profile', profile_type='pc-samples',
                                verified_binding=bool(capture), profile_sha256=sha256(staged_fdata),
                                source_elf_sha256=capture['build']['source_elf_sha256'] if capture else None,
                                capture_manifest_sha256=capture_hash, perf2bolt_sha256=converter_hash,
                                build=capture['build'] if capture else None,
                                profile_scope=profile_scope,
                                limitations='IRQ-masked code is invisible; PC frequencies are not exact edge counts')
        from pathlib import Path
        publish_files({preagg: Path(staged_preagg).read_bytes(), destination: Path(staged_fdata).read_bytes(),
                       destination + '.manifest.json': (json.dumps(profile_manifest, indent=2) + '\n').encode('utf-8')})
    print(f"{len(words)} samples, {len(counts)} distinct PCs -> {args.out}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, ValueError, KeyError) as error:
        sys.exit(f"error: invalid sample input: {error}")
