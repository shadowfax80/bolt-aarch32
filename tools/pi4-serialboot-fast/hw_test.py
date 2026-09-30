#!/usr/bin/env python3
"""Reliability test of the fast (3 Mbaud) chainloader on the real Pi, hot-loaded through the
SD card's chainloader: N back-to-back cycles, each = soft reset, hot-load, fast upload of one
image, boot, run `bolt_bench stair`. Counts successes, fast-upload failures that fell back to
the slow path, hard failures, and wrong results, and reports upload time per image size.

usage: hw_test.py [N=30] [image ...]      (Windows Python, Pi on COM5, Non-secure SVC)
"""
import os
import re
import subprocess
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "scripts", "pi4"))
from proc_util import run_bounded  # noqa: E402

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
LOADER = os.path.join(ROOT, "tools", "pi4-serialboot-fast", "out", "kernel7l_fast.img")
RUN = os.path.join(ROOT, "scripts", "pi4", "pi4_run.py")
DEFAULT = ["baseline", "pgo", "pgo_thinlto", "pgo_thinlto_bolt_noreorder", "pgo_thinlto_bolt"]
EXPECT_ACC = "0x5b19056f"   # stair, 432 sites, input variant 0


def main() -> int:
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 30
    imgs = sys.argv[2:] or [os.path.join(ROOT, "build", "stage", "m6x3", f"{i}.bin") for i in DEFAULT]
    ok = fell_back = hard = wrong = 0
    times: dict[int, list[float]] = {}
    for i in range(n):
        img = imgs[i % len(imgs)]
        size = os.path.getsize(img)
        t0 = time.monotonic()
        try:
            p = run_bounded([sys.executable, RUN, img, "--port", "COM5", "--reboot", "--wait", "60",
                             "--max-wait", "120", "--fast-loader", LOADER, "bolt_bench stair"], 90)
            text = p.stdout.decode("utf-8", "replace").replace("\r", "\n")
            rc = p.returncode
        except Exception as exc:  # noqa: BLE001
            text, rc = str(exc), -9
        dt = time.monotonic() - t0
        fb = "fast upload failed" in text
        acc = re.search(r"stair acc=(0x[0-9a-f]+)", text)
        good = rc == 0 and acc and acc.group(1) == EXPECT_ACC
        if good:
            ok += 1
            fell_back += fb
            times.setdefault(size, []).append(dt)
        elif rc == 0 and acc:
            wrong += 1
        else:
            hard += 1
        why = ""
        if not good:
            m = re.findall(r"(ER [^\n]*|error:[^\n]*|fast upload failed[^\n]*)", text)
            why = "  " + (m[-1] if m else f"rc={rc}")
        print(f"[{i + 1:2d}/{n}] {os.path.basename(img):<36}{size / 1024:6.0f} KiB  {dt:5.1f}s  "
              f"{'ok' if good else 'FAIL'}{' (fell back to slow)' if fb else ''}{why}", flush=True)
        if rc == -9 or hard >= 3:
            print("stopping: the Pi is not answering (power cycle needed?)")
            break
    print(f"\n{ok}/{i + 1} cycles correct; {fell_back} of them fell back to the slow upload; "
          f"{hard} hard failures; {wrong} wrong results")
    for size in sorted(times):
        v = times[size]
        print(f"  {size / 1024:6.0f} KiB image: whole cycle {sum(v) / len(v):5.1f}s  (n={len(v)})")
    return 0 if ok == i + 1 and not fell_back else 1


if __name__ == "__main__":
    sys.exit(main())
