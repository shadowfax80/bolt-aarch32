#!/usr/bin/env python3
"""Run `bolt_bench all` on several images on the Pi and compare every workload's result
(the `sink=` / `acc=` lines) with the first image. Any difference, missing line or failed
boot is an error.

usage: passes_check.py name=image.bin [name=image.bin ...]      (Windows Python, COM5)
"""
import argparse
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from proc_util import run_bounded  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
RESULT_RE = re.compile(r"bolt_bench: (\w+) (?:sink|acc)=(0x[0-9a-f]+)")
EXPECTED_WORKLOADS = (
    "hot_loop", "hot_cold", "branch_chain", "memcpy", "far_call", "it_cond",
    "interwork", "switch", "spill_ret", "litpool", "indirect_call",
    "interwork_tail", "regpressure", "hotcold_split", "icf", "shrinkwrap",
    "composite", "stair",
)


def parse_results(text: str) -> dict[str, str]:
    if re.search(r"bolt_bench: \w+ FAIL\b", text):
        raise ValueError("workload reported a correctness failure")
    found: dict[str, str] = {}
    for name, value in RESULT_RE.findall(text):
        value = f"0x{int(value, 16):08x}"
        if name in found and found[name] != value:
            raise ValueError(f"conflicting results for {name}: {found[name]} and {value}")
        found[name] = value
    missing = set(EXPECTED_WORKLOADS) - found.keys()
    extra = found.keys() - set(EXPECTED_WORKLOADS)
    if missing or extra:
        raise ValueError(f"incomplete workload set: missing={sorted(missing)}, extra={sorted(extra)}")
    return found


def results(image: str, port: str = "COM5", log_prefix: str | None = None) -> dict[str, str]:
    cmd = [sys.executable, os.path.join(HERE, "pi4_run.py"), image, "--port", port,
           "--reboot", "--wait", "60", "--max-wait", "240", "bolt_bench all"]
    for attempt in range(2):
        out = run_bounded(cmd, 420)
        text = out.stdout.decode("utf-8", "replace").replace("\r", "\n")
        if log_prefix:
            with open(f"{log_prefix}.{attempt + 1}.log", "w", encoding="utf-8") as log:
                log.write(text)
        reason = f"child exit {out.returncode}"
        if out.returncode == 0:
            try:
                return parse_results(text)
            except ValueError as error:
                reason = str(error)
        print(f"  attempt {attempt + 1} failed for {image}: rc={out.returncode}, "
              f"{reason}; {text.strip()[-300:]}", file=sys.stderr)
    raise SystemExit(f"error: no complete valid results from {image}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("images", nargs="+", metavar="NAME=IMAGE")
    parser.add_argument("--port", default="COM5")
    parser.add_argument("--log-dir", help="save complete output from each boot attempt")
    args = parser.parse_args()
    if len(args.images) < 2 or any("=" not in item for item in args.images):
        parser.error("provide at least two NAME=IMAGE arguments")
    images = [item.split("=", 1) for item in args.images]
    if any(not name or not path for name, path in images) or len({name for name, _ in images}) != len(images):
        parser.error("image names and paths must be nonempty; names must be unique")
    if args.log_dir:
        os.makedirs(args.log_dir, exist_ok=True)
    ref_name, ref = images[0][0], None
    bad = 0
    for index, (name, path) in enumerate(images):
        print(f"== {name}", flush=True)
        prefix = os.path.join(args.log_dir, f"image-{index}") if args.log_dir else None
        got = results(path, args.port, prefix)
        if ref is None:
            ref = got
            print(f"   {len(got)} workload results: " + " ".join(f"{k}={v}" for k, v in got.items()))
            continue
        image_bad = 0
        for k, v in ref.items():
            if got.get(k) != v:
                image_bad += 1
                print(f"   MISMATCH {k}: {ref_name}={v} {name}={got.get(k)}")
        extra = set(got) - set(ref)
        if extra:
            image_bad += 1
            print(f"   extra results: {sorted(extra)}")
        bad += image_bad
        if not image_bad:
            print(f"   all {len(ref)} results identical to {ref_name}")
    print("RESULT:", "PASS" if not bad else f"FAIL ({bad} differences)")
    return 0 if not bad else 1


if __name__ == "__main__":
    sys.exit(main())
