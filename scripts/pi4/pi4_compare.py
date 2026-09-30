#!/usr/bin/env python3
"""Staged comparison of LK variants on the real Pi (Step 10).

Boots each variant image in turn, runs the workload several times per boot, and
records cycles plus the PMU event counters bolt_bench prints. Variants are
interleaved across rounds (A B C D A B C D ...) rather than run back-to-back,
so slow drift (thermal, firmware) cannot systematically favor one variant.

Every run is written to a CSV; nothing is discarded or averaged away before
that. The summary reports mean/min/max/stdev per variant and the delta of each
variant's mean against the first (baseline).

usage: pi4_compare.py --out results.csv --rounds 5 --runs 4 \
         baseline=build/x/baseline.bin pgo=build/x/pgo.bin ...
"""

from __future__ import annotations

import argparse
import csv
import os
import re
import statistics
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from stats_util import fmt_delta, mean_ci95  # noqa: E402
from proc_util import run_bounded  # noqa: E402
CYC_RE = re.compile(r"bolt_bench: (\w+) done \((\d+) cycles\)")
PMU_RE = re.compile(
    r"bolt_bench: (\w+) pmu inst=(\d+) l1i_refill=(\d+) l1d_refill=(\d+) br_mispred=(\d+)(?: taken=(\d+))?"
)
FIELDS = ["cycles", "inst", "l1i_refill", "l1d_refill", "br_mispred", "taken"]
# Result checksum the workload prints; every variant must agree or the comparison
# is between programs that compute different things.
ACC_RE = re.compile(r"bolt_bench: (\w+) acc=(0x[0-9a-fA-F]+)")


# Extra words after the workload name (PMU set, input variant), set from --args.
EXTRA_ARGS = ""


def boot_and_run(image: str, port: str, workload: str, runs: int) -> list[dict]:
    """One boot, `runs` workload runs. A boot can hang (seen once on the Pi, cause
    unknown: the Pi itself answered a soft reboot right after), so retry once."""
    try:
        return _boot_and_run(image, port, workload, runs)
    except (RuntimeError, subprocess.TimeoutExpired) as exc:
        print(f"  retrying {image} after: {str(exc)[-160:]}", file=sys.stderr)
        return _boot_and_run(image, port, workload, runs)


def _boot_and_run(image: str, port: str, workload: str, runs: int) -> list[dict]:
    cmd = [
        sys.executable, os.path.join(HERE, "pi4_run.py"), image,
        "--port", port, "--reboot", "--wait", "30", "--max-wait", "60",
    ] + [f"bolt_bench {workload} {EXTRA_ARGS}".strip()] * runs
    out = run_bounded(cmd, 150)
    text = out.stdout.decode("utf-8", errors="replace").replace("\r", "\n")
    if out.returncode != 0:
        tail = text[-600:]
        raise RuntimeError(f"pi4_run failed for {image}: {tail}")
    cycles = [int(m.group(2)) for m in CYC_RE.finditer(text) if m.group(1) == workload]
    accs = [m.group(2) for m in ACC_RE.finditer(text) if m.group(1) == workload]
    pmus = [tuple(int(x) for x in m.groups()[1:] if x is not None) for m in PMU_RE.finditer(text) if m.group(1) == workload]
    if "INVALID" in text:
        print("  note: a run reported a core migration; its PMU line is absent", file=sys.stderr)
    if len(cycles) != runs:
        raise RuntimeError(f"{image}: expected {runs} runs, got {len(cycles)} cycle lines")
    rows = []
    for i, c in enumerate(cycles):
        row = {"cycles": c, "acc": accs[i] if i < len(accs) else ""}
        if i < len(pmus):
            row.update(zip(FIELDS[1:], pmus[i]))
        rows.append(row)
    return rows


def fmt(vals: list[float]) -> str:
    if not vals:
        return "n/a"
    sd = statistics.pstdev(vals) if len(vals) > 1 else 0.0
    return f"{statistics.mean(vals):>13,.1f}  [{min(vals):,.0f} .. {max(vals):,.0f}]  sd {sd:,.1f}"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("variants", nargs="+", help="name=path/to/image.bin, in comparison order")
    ap.add_argument("--out", required=True, help="CSV of every individual run")
    ap.add_argument("--rounds", type=int, default=5)
    ap.add_argument("--runs", type=int, default=4, help="workload runs per boot")
    ap.add_argument("--workload", default="composite")
    ap.add_argument("--port", default="COM5")
    ap.add_argument("--args", default="", help="extra words after the workload name, e.g. "
                    "\"0 2\" = PMU set 0, input variant 2 (held-out input; profiles train on 0)")
    args = ap.parse_args()
    global EXTRA_ARGS
    EXTRA_ARGS = args.args

    variants = []
    for v in args.variants:
        name, _, path = v.partition("=")
        if not path or not os.path.exists(path):
            sys.exit(f"bad variant spec / missing file: {v}")
        variants.append((name, path))

    records: list[dict] = []
    with open(args.out, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["variant", "round", "run"] + FIELDS + ["acc"])
        w.writeheader()
        for rnd in range(1, args.rounds + 1):
            for name, path in variants:
                print(f"round {rnd}/{args.rounds}  {name} ...", flush=True)
                for i, row in enumerate(boot_and_run(path, args.port, args.workload, args.runs), 1):
                    rec = {"variant": name, "round": rnd, "run": i, **row}
                    records.append(rec)
                    w.writerow(rec)
                fh.flush()

    print(f"\n{len(records)} runs -> {args.out}\n")
    accs = sorted({r.get("acc", "") for r in records})
    if len(accs) != 1 or not accs[0]:
        print(f"CHECKSUM MISMATCH across runs/variants: {accs}", file=sys.stderr)
        return 1
    else:
        print(f"checksum {accs[0]} identical in all {len(records)} runs\n")
    base = None
    for name, _ in variants:
        rs = [r for r in records if r["variant"] == name]
        print(f"== {name} ({len(rs)} runs)")
        for f in FIELDS:
            vals = [r[f] for r in rs if f in r]
            print(f"   {f:<11}{fmt(vals)}")
        # Derived rates: what each stage's counter change means per unit of work.
        inst = [r["inst"] for r in rs if r.get("inst")]
        if inst:
            ipc = statistics.mean(r["inst"] / r["cycles"] for r in rs if r.get("inst"))
            print(f"   {'ipc':<11}{ipc:>13.3f}")
            for f in ("taken", "l1i_refill", "br_mispred"):
                vals = [1000.0 * r[f] / r["inst"] for r in rs if r.get(f) is not None and r.get("inst")]
                if vals and any(vals):
                    print(f"   {f + '/kinst':<11}{statistics.mean(vals):>13.3f}")
        cyc_vals = [r["cycles"] for r in rs]
        m, half = mean_ci95(cyc_vals)
        print(f"   {'cycles 95%':<11}{m:>13,.0f} +- {half:,.0f}")
        if base is None:
            base = cyc_vals
        else:
            print(f"   cycles vs {variants[0][0]}: {fmt_delta(base, cyc_vals)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
