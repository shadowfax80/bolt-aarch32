#!/usr/bin/env python3
"""Offline repository integrity checks; never builds, applies overlays or uses hardware."""
import argparse
import ast
import hashlib
import json
from pathlib import Path
import re
import subprocess
from urllib.parse import unquote

from handoff_state import read_items


def check(root):
    paths = subprocess.check_output(["git", "ls-files", "-z"], cwd=root).decode().split("\0")[:-1]
    errors, counts = [], {"tracked_files": len(paths), "json": 0, "python": 0, "markdown": 0, "fixtures": 0}
    for name in paths:
        path = root / name
        if not path.is_file():
            errors.append(f"Missing tracked file: {name}")
            continue
        try:
            if path.suffix == ".json":
                json.loads(path.read_bytes())
                counts["json"] += 1
            elif path.suffix == ".py":
                ast.parse(path.read_text(encoding="utf-8-sig"), filename=name)
                counts["python"] += 1
            elif path.suffix == ".md":
                counts["markdown"] += 1
                code = False
                for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                    if line.lstrip().startswith(("```", "~~~")):
                        code = not code
                        continue
                    if code:
                        continue
                    for target in re.findall(r'\]\(([^)\s]+)(?:\s+"[^"]*")?\)', line):
                        target = unquote(target.strip("<>"))
                        if ":" in target or target.startswith("#"):
                            continue
                        local = target.split("#")[0]
                        if local and not (path.parent / local).exists():
                            errors.append(f"{name}:{number}: missing link target {target}")
        except (ValueError, SyntaxError, UnicodeError) as error:
            errors.append(f"{name}: {error}")

    try:
        items = read_items(root / "docs/HANDOFF.md")
        counts["work_items"] = len(items)
        handoff = (root / "docs/HANDOFF.md").read_text(encoding="utf-8")
        last = re.search(r"patches/atfe/0001[–-](\d{4})", handoff)
        if not last:
            errors.append("HANDOFF has no current overlay range")
        else:
            numbers = sorted(int(Path(p).name[:4]) for p in paths
                             if p.startswith("overlay/llvm/patches/atfe/") and p.endswith(".patch"))
            if numbers != list(range(1, int(last[1]) + 1)):
                errors.append("ATFE overlay inventory is gapped/duplicated or differs from HANDOFF")
            counts["atfe_overlays"] = len(numbers)
        for name in ["TODO.md", "CORRECTNESS_TODO.md", "CORRECTNESS_STATUS.md", "CORRECTNESS_PRIORITY_TODO.md"]:
            text = (root / "docs" / name).read_text(encoding="utf-8")
            if "HANDOFF.md" not in text or re.search(r"^\| (?:R\d+|T\d+|M\d+) \|", text, re.M):
                errors.append(f"docs/{name}: current queue must link to HANDOFF, not duplicate it")
    except (ValueError, OSError) as error:
        errors.append(f"HANDOFF: {error}")

    fixture_index = (root / "fixtures/README.md").read_text(encoding="utf-8")
    for name, digest in re.findall(r"\| `([^`]+\.elf)` \| `([0-9a-f]{64})`", fixture_index):
        path = root / "fixtures" / name
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            errors.append(f"Fixture identity mismatch: {name}")
        counts["fixtures"] += 1
    receipt = json.loads((root / "docs/results/r11_completion_20261004.json").read_bytes())
    for name, digest in receipt["artifact_sha256"].items():
        if hashlib.sha256((root / name).read_bytes()).hexdigest() != digest:
            errors.append(f"Immutable R11 receipt identity mismatch: {name}")
    counts["r11_bound_artifacts"] = len(receipt["artifact_sha256"])
    return {"success": not errors, "checks": counts, "errors": errors,
            "scope": "Tracked-file structure, local Markdown file targets (not anchors/external links), Python syntax, JSON, current work tables, overlay inventory and selected fixture/receipt hashes. No backend execution, clean-build or hardware proof."}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--json", type=Path, help="Optional report path (use out/ for diagnostics)")
    args = parser.parse_args()
    result = check(args.root)
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))
    return 0 if result["success"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
