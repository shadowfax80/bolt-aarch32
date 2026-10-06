#!/usr/bin/env python3
"""Check LLVM profile kind, require trained counters, and merge IR+CS profiles.

Use the pinned llvm-profdata: profile formats are toolchain-specific. This is
format/content validation, not proof that a profile belongs to a given image.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import re
import subprocess


def inspect_profile(path, tool):
    reports = {}
    for label, flags in (("ordinary", []), ("cs", ["--showcs"])):
        result = subprocess.run([str(tool), "show", "--all-functions", "--counts", *flags, str(path)],
                                capture_output=True, text=True, check=True)
        text = result.stdout
        level = re.search(r"Instrumentation level: (Front-end|IR)(?:\s|$)", text)
        count = re.search(r"(?:Functions shown|Total functions): (\d+)", text)
        maxima = re.findall(r"Maximum (?:function|internal block) count: (\d+)", text)
        if not level or not count or not maxima:
            raise ValueError("unrecognised llvm-profdata show output")
        reports[label] = dict(level=level[1].strip(), functions=int(count[1]), maximum=max(map(int, maxima)))
    return reports


def validate_profile(path, tool, kind):
    report = inspect_profile(path, tool)
    expected = "Front-end" if kind == "frontend" else "IR"
    if report["ordinary"]["level"] != expected:
        raise ValueError(f"expected {kind} profile, found {report['ordinary']['level']}")
    required = ("cs",) if kind == "cs" else ("ordinary", "cs") if kind == "merged" else ("ordinary",)
    for level in required:
        if not report[level]["functions"] or not report[level]["maximum"]:
            raise ValueError(f"profile has no trained {level} counters")
    if kind == "ir-only" and report["cs"]["functions"]:
        raise ValueError("ordinary baseline profile already contains CS records")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("validate", "merge"))
    parser.add_argument("profile", type=Path, help="input for validate; output for merge")
    parser.add_argument("--profdata", required=True, type=Path)
    parser.add_argument("--kind", choices=("frontend", "ir", "ir-only", "cs", "merged"), default="ir")
    parser.add_argument("--ir", type=Path)
    parser.add_argument("--cs", type=Path)
    args = parser.parse_args()
    if args.action == "merge":
        if not args.ir or not args.cs:
            parser.error("merge requires --ir and --cs")
        if args.profile.exists():
            parser.error("output exists; preserve it and choose a fresh path")
        validate_profile(args.ir, args.profdata, "ir-only")
        validate_profile(args.cs, args.profdata, "cs")
        args.profile.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run([str(args.profdata), "merge", str(args.ir), str(args.cs), "-o", str(args.profile)], check=True)
        args.kind = "merged"
    print(json.dumps(validate_profile(args.profile, args.profdata, args.kind), indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        raise SystemExit(f"error: {error}")
