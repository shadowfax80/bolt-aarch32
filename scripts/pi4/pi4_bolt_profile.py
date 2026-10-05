#!/usr/bin/env python3
"""Collect BOLT instrumentation counters from a real Pi.

Boots a BOLT-instrumented LK image (llvm-bolt -instrument, then objcopy -O
binary), runs the training workload, then reads the `.bolt.instr.counters`
section back over UART with `bolt_dump` (checksum-verified chunk by chunk).
Verified collection requires a pre-capture seal plus the exact original ELF,
instrumented ELF, emitted function map, toolchain and source replay report.
The counter extent comes from that seal. --debug-unbound requires a manual
extent and produces diagnostic output excluded from verified optimization.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import json
import shutil
import tempfile
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from proc_util import run_bounded  # noqa: E402
from bolt_dump_reassemble import validate_single_dump  # noqa: E402
from profile_identity import read_json, sha256, publish_files  # noqa: E402
from counter_identity import check_build  # noqa: E402


def validate_dump(text, layout):
    return validate_single_dump(text, layout['address'], layout['size'])


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("image")
    ap.add_argument("out")
    ap.add_argument("--addr", help="optional counter address (hex); must match seal")
    ap.add_argument("--size", help="optional counter size (hex); must match seal")
    ap.add_argument('--elf')
    ap.add_argument('--original')
    ap.add_argument('--function-map')
    ap.add_argument('--source-replay')
    ap.add_argument('--toolchain', default='build-atfe/bin')
    ap.add_argument('--patch-dir', default=str(Path(HERE).parents[1] / 'overlay/llvm/patches/atfe'))
    ap.add_argument('--build-manifest', help='default: IMAGE.manifest.json, sealed before capture')
    ap.add_argument('--debug-unbound', action='store_true')
    ap.add_argument("--workload", default="composite")
    ap.add_argument("--command", action="append", default=[],
                    help="shell command to run instead of `bolt_bench WORKLOAD` (repeatable; "
                         "B1 whole-image suites)")
    ap.add_argument("--max-wait", default="60", help="per-command timeout, seconds")
    ap.add_argument("--port", default="COM5")
    args = ap.parse_args()
    evidence = Path(tempfile.mkdtemp(prefix='pi-counters-', dir=Path(args.out).resolve().parent))
    build = None
    manifest_path = args.build_manifest or args.image + '.manifest.json'
    if not args.debug_unbound:
        if not all((args.elf, args.original, args.function_map, args.source_replay)):
            ap.error('verified counter capture requires --elf, --original, --function-map and --source-replay')
        build = read_json(manifest_path)
        check_build(build, args.original, args.elf, args.function_map, args.image,
                    args.toolchain, args.patch_dir, args.source_replay)
        manifest_hash = sha256(manifest_path)
        layout = build['metadata']['counter_layout']
        if ((args.addr and int(args.addr, 16) != layout['address'])
                or (args.size and int(args.size, 16) != layout['size'])):
            raise ValueError('requested counter range differs from sealed ELF')
        args.addr, args.size = f"{layout['address']:x}", f"{layout['size']:x}"
    elif not args.addr or not args.size:
        ap.error('diagnostic capture requires --addr and --size')
    image = evidence / 'image.bin'
    shutil.copyfile(args.image, image)
    if build and sha256(image) != build['artifacts']['image']:
        raise ValueError('image changed while making immutable upload copy')

    cmd = [
        sys.executable, os.path.join(HERE, "pi4_run.py"), str(image),
        "--port", args.port, "--reboot", "--wait", "30", "--max-wait", str(args.max_wait),
        *(args.command or [f"bolt_bench {args.workload}"]), f"bolt_dump {args.addr} {args.size}",
    ]
    out = run_bounded(cmd, 900)
    text = out.stdout.decode("utf-8", errors="replace")
    log = evidence / 'capture.log'; log.write_text(text, encoding='utf-8')
    if out.returncode != 0:
        sys.exit(f"pi4_run.py failed ({out.returncode}):\n{text[-2000:]}")

    blob = validate_dump(text, dict(address=int(args.addr, 16), size=int(args.size, 16)))
    if build:
        import struct
        if struct.unpack_from('<I', blob, layout['count_address'] - layout['address'])[0] != layout['count']:
            raise ValueError('captured counter count differs from pre-capture seal')
    if build:
        check_build(build, args.original, args.elf, args.function_map, args.image,
                    args.toolchain, args.patch_dir, args.source_replay)
        if sha256(manifest_path) != manifest_hash:
            raise ValueError('counter build manifest changed during capture')
    import hashlib
    capture = dict(schema=1, kind='arm-counter-capture', verified_binding=bool(build),
                   build=build, build_manifest_sha256=manifest_hash if build else None,
                   payload_sha256=hashlib.sha256(blob).hexdigest(), log_sha256=sha256(log),
                   collector_sha256=sha256(__file__), evidence=str(evidence),
                   range=dict(address=int(args.addr, 16), size=int(args.size, 16)),
                   workload=args.command or args.workload, limitation='identity binding only; workload semantics are a separate gate')
    publish_files({args.out: blob, args.out + '.manifest.json':
                   (json.dumps(capture, indent=2) + '\n').encode('utf-8')})
    print(f"wrote {len(blob)} bytes to {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
