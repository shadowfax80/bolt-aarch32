#!/usr/bin/env python3
"""Run `bolt_bench all` on several images on the Pi and compare every workload's result
(the `sink=` / `acc=` lines) with the first image. Any difference, missing line or failed
boot is an error.

usage: passes_check.py name=image.bin [name=image.bin ...]      (Windows Python, COM5)
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from proc_util import run_bounded  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
RESULT_RE = re.compile(r"bolt_bench: (\w+) (?:sink|acc)=(0x[0-9a-f]+)")


def results(image: str) -> dict[str, str]:
    cmd = [sys.executable, os.path.join(HERE, "pi4_run.py"), image, "--port", "COM5",
           "--reboot", "--wait", "60", "--max-wait", "240", "bolt_bench all"]
    for attempt in range(2):
        out = run_bounded(cmd, 420)
        text = out.stdout.decode("utf-8", "replace").replace("\r", "\n")
        found: dict[str, str] = {}
        for name, value in RESULT_RE.findall(text):
            found.setdefault(name, value)
        if out.returncode == 0 and found:
            return found
        print(f"  attempt {attempt + 1} failed for {image}: rc={out.returncode}, "
              f"{text.strip()[-300:]}", file=sys.stderr)
    raise SystemExit(f"error: no results from {image}")


def main() -> int:
    images = [a.split("=", 1) for a in sys.argv[1:]]
    ref_name, ref = images[0][0], None
    bad = 0
    for name, path in images:
        print(f"== {name}", flush=True)
        got = results(path)
        if ref is None:
            ref = got
            print(f"   {len(got)} workload results: " + " ".join(f"{k}={v}" for k, v in got.items()))
            continue
        for k, v in ref.items():
            if got.get(k) != v:
                bad += 1
                print(f"   MISMATCH {k}: {ref_name}={v} {name}={got.get(k)}")
        extra = set(got) - set(ref)
        if extra:
            bad += 1
            print(f"   extra results: {sorted(extra)}")
        if not bad:
            print(f"   all {len(ref)} results identical to {ref_name}")
    print("RESULT:", "PASS" if not bad else f"FAIL ({bad} differences)")
    return 0 if not bad else 1


if __name__ == "__main__":
    sys.exit(main())
