#!/usr/bin/env python3
"""Watch the recorded correctness tracker and Git commits; does not run fixes."""
import argparse
import datetime
import json
from pathlib import Path
import subprocess
import time


def snapshot(root):
    tracker = root / "docs/CORRECTNESS_STATUS.md"
    items = []
    for line in tracker.read_text(encoding="utf-8").splitlines():
        columns = [column.strip() for column in line.split("|")[1:-1]]
        if len(columns) == 4 and columns[0].isdigit():
            items.append(dict(zip(("number", "item", "status", "remaining"), columns)))
    if len(items) != 12:
        raise ValueError(f"Expected 12 tracker items, found {len(items)}")
    result = subprocess.run(
        ["git", "log", "-1", "--format=%h %s"], cwd=root,
        capture_output=True, text=True, timeout=10, check=True,
    )
    return {
        "observed_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "tracker_modified_at": datetime.datetime.fromtimestamp(
            tracker.stat().st_mtime, datetime.timezone.utc).isoformat(),
        "commit": result.stdout.strip(),
        "items": items,
        "note": "Recorded tracker status only; a running monitor does not mean fixes are running.",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--interval", type=float, default=30)
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    if args.interval <= 0:
        parser.error("--interval must be positive")
    root = Path(__file__).resolve().parents[1]
    out = root / "out/correctness"
    out.mkdir(parents=True, exist_ok=True)
    previous = None
    while True:
        try:
            current = snapshot(root)
            temporary = out / "progress-monitor.tmp"
            temporary.write_text(json.dumps(current, indent=2) + "\n", encoding="utf-8")
            temporary.replace(out / "progress-monitor.json")
            signature = (current["commit"], json.dumps(current["items"], sort_keys=True))
            if signature != previous:
                print(json.dumps(current), flush=True)
                previous = signature
            else:
                print(f'{current["observed_at"]} heartbeat: tracker unchanged', flush=True)
        except (OSError, ValueError, subprocess.SubprocessError) as error:
            print(f"monitor error: {error}", flush=True)
            if args.once:
                return 1
        if args.once:
            return 0
        time.sleep(args.interval)


if __name__ == "__main__":
    raise SystemExit(main())
