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
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from proc_util import run_bounded  # noqa: E402
from bolt_dump_reassemble import BEGIN_RE, END_RE, LINE_RE, parse_dump_stream  # noqa: E402
from passes_check import EXPECTED_WORKLOADS, parse_results  # noqa: E402
from measurement_records import parse_measurements  # noqa: E402

PGO_RE = re.compile(r"bolt_pgo_dump: addr=([0-9a-fA-F]+) size=([0-9a-fA-F]+)")


def run_pi(image: str, port: str, commands: list[str], log: Path | None = None) -> str:
    cmd = [
        sys.executable, os.path.join(HERE, "pi4_run.py"), image,
        "--port", port, "--reboot", "--wait", "30", "--max-wait", "60",
    ] + commands
    out = run_bounded(cmd, 900)
    if log:
        log.write_bytes(out.stdout)
        log.with_suffix(".stderr").write_bytes(out.stderr)
    text = out.stdout.decode("utf-8", errors="replace")
    if out.returncode != 0:
        sys.exit(f"pi4_run.py failed ({out.returncode}):\n{text[-2000:]}\n{out.stderr.decode(errors='replace')[-1000:]}")
    return text


def profile_buffer(text: str) -> tuple[int, int]:
    matches = PGO_RE.findall(text)
    if len(matches) != 1:
        raise ValueError("missing/duplicate profile buffer announcement")
    addr, size = (int(v, 16) for v in matches[0])
    if not addr or not 0 < size <= 16 * 1024 * 1024 or addr + size > 2**32:
        raise ValueError("invalid profile buffer range")
    return addr, size


def extract_profile(text: str, expected: tuple[int, int]) -> bytes:
    if profile_buffer(text) != expected:
        raise ValueError("profile buffer changed between boots")
    begins, ends = BEGIN_RE.findall(text), END_RE.findall(text)
    addr, size = expected
    chunks = LINE_RE.findall(text)
    if len(begins) != 1 or len(ends) != 1 or tuple(int(v, 16) for v in begins[0]) != expected:
        raise ValueError("missing/duplicate/mismatched dump frame")
    count = (size + 63) // 64
    if tuple(int(v, 16) for v in ends[0]) != (count, size) or len(chunks) != count:
        raise ValueError("incomplete/duplicate dump footer or records")
    for seq, fields in enumerate(chunks):
        s, off, length = (int(v, 16) for v in fields[:3])
        if (s, off, length) != (seq, seq * 64, min(64, size - seq * 64)):
            raise ValueError("invalid dump chunk order/range")
    result = parse_dump_stream(text)
    if result.bad_seqs or not result.is_complete():
        raise ValueError(f"dump incomplete/corrupt: missing {result.missing_ranges()}")
    return result.to_bytes()


def training_results(text: str, workloads: list[str]) -> list[dict[str, str]]:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    frames = list(re.finditer(r"^\$ ([^\n]*)$", text, re.M))
    selected = [(i, m) for i, m in enumerate(frames) if m[1].startswith("bolt_bench ")]
    if [m[1] for _, m in selected] != ["bolt_bench " + w for w in workloads]:
        raise ValueError("missing/extra/reordered training command frames")
    results = []
    for workload, (i, frame) in zip(workloads, selected):
        stop = frames[i + 1].start() if i + 1 < len(frames) else len(text)
        body = text[frame.end():stop]
        if re.search(r"bolt_bench: \w+ FAIL\b", body):
            raise ValueError("training workload reported failure")
        if workload == "all":
            results.append(parse_results(body))
        elif workload in ("stair", "composite", "multi", "pgo_lab"):
            kernels = ["pl_a", "pl_b", "pl_c", "pl_d"] if workload == "pgo_lab" else [workload]
            rows = parse_measurements(text[frame.start():stop], "bolt_bench " + workload, kernels, 1)
            results.append({row['kernel']: row['acc'] for row in rows})
        else:
            # Older individual microbenchmarks print completion but no checksum.
            # `all` prints their sinks and is the route for result comparison.
            completed = re.findall(r"^bolt_bench: " + re.escape(workload) + r" (done|skipped)\b", body, re.M)
            if len(completed) != 1:
                raise ValueError("missing/duplicate training workload completion")
            results.append({workload: completed[0]})
    return results


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("image")
    ap.add_argument("out")
    ap.add_argument("--workload", default="composite",
                    help="training workload(s), comma-separated: their counts accumulate in one profile")
    ap.add_argument("--port", default="COM5")
    ap.add_argument("--log-dir", type=Path, help="fresh directory for both boot logs and an image/profile identity receipt")
    args = ap.parse_args()

    workloads = args.workload.split(",")
    if any(w not in set(EXPECTED_WORKLOADS) | {"pgo_lab", "multi", "all"} for w in workloads):
        ap.error("training requires named sequential workloads (SMP counters are not atomic)")
    work = [f"bolt_bench {w}" for w in workloads]
    image_hash = hashlib.sha256(Path(args.image).read_bytes()).hexdigest()
    if args.log_dir:
        args.log_dir.mkdir(parents=True, exist_ok=False)

    text = run_pi(args.image, args.port, work + ["bolt_pgo_dump"], args.log_dir / "discover.log" if args.log_dir else None)
    first_results = training_results(text, workloads)
    addr, size = profile_buffer(text)
    print(f"profile buffer: addr=0x{addr:x} size=0x{size:x}")

    text = run_pi(args.image, args.port, work + ["bolt_pgo_dump", f"bolt_dump {addr:x} {size:x}"], args.log_dir / "collect.log" if args.log_dir else None)
    if training_results(text, workloads) != first_results:
        raise ValueError("training results changed between boots")
    blob = extract_profile(text, (addr, size))
    if hashlib.sha256(Path(args.image).read_bytes()).hexdigest() != image_hash:
        raise ValueError("training image changed during collection")
    with open(args.out, "wb") as fh:
        fh.write(blob)
    print(f"wrote {len(blob)} bytes to {args.out}")
    if args.log_dir:
        (args.log_dir / "collection.json").write_text(json.dumps(dict(image_sha256=image_hash,
            profile_sha256=hashlib.sha256(blob).hexdigest(), workloads=workloads,
            buffer_addr=addr, buffer_size=size, training_results=first_results,
            scope="transport, output consistency and image association; not a correctness certificate"), indent=2) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
