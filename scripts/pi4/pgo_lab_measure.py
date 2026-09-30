#!/usr/bin/env python3
"""Measure the pgo_lab kernels (pl_a..pl_d) for several LK images on the real Pi.

Each image is booted once per round and runs `bolt_bench pgo_lab` `--runs` times;
rounds interleave the images (A B A B ...) so drift cannot favour one. Every run is
kept in the CSV; the table reports, per kernel and image, mean cycles, instructions,
IPC, L1I refills and mispredicts, and the change of cycles against the first image.
Checksums must agree across images or the comparison is between different programs.

usage: pgo_lab_measure.py --out lab.csv [--rounds 3] [--runs 2] name=image.bin ...
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
from stats_util import welch_delta_pct  # noqa: E402
from proc_util import run_bounded  # noqa: E402
CYC_RE = re.compile(r"bolt_bench: (pl_\w) done \((\d+) cycles\)")
PMU_RE = re.compile(
    r"bolt_bench: (pl_\w) pmu inst=(\d+) l1i_refill=(\d+) l1d_refill=(\d+) br_mispred=(\d+)"
)
ACC_RE = re.compile(r"bolt_bench: (pl_\w) acc=(0x[0-9a-fA-F]+)")
KERNELS = ["pl_a", "pl_b", "pl_c", "pl_d"]


# Extra words after `pgo_lab` (PMU set, input variant), set from --args.
EXTRA_ARGS = ""


def boot_and_run(image: str, port: str, runs: int) -> list[dict]:
    try:
        return _boot_and_run(image, port, runs)
    except (RuntimeError, subprocess.TimeoutExpired) as exc:
        print(f"  retrying {image} after: {str(exc)[-160:]}", file=sys.stderr)
        return _boot_and_run(image, port, runs)


def _boot_and_run(image: str, port: str, runs: int) -> list[dict]:
    cmd = [
        sys.executable, os.path.join(HERE, "pi4_run.py"), image,
        "--port", port, "--reboot", "--wait", "60", "--max-wait", "120",
    ] + [f"bolt_bench pgo_lab {EXTRA_ARGS}".strip()] * runs
    out = run_bounded(cmd, 600)
    text = out.stdout.decode("utf-8", errors="replace").replace("\r", "\n")
    if out.returncode != 0:
        raise RuntimeError(f"pi4_run failed for {image}: {text[-600:]}")
    rows = []
    for k in KERNELS:
        cyc = [int(m.group(2)) for m in CYC_RE.finditer(text) if m.group(1) == k]
        pmu = [tuple(int(x) for x in m.groups()[1:]) for m in PMU_RE.finditer(text) if m.group(1) == k]
        acc = [m.group(2) for m in ACC_RE.finditer(text) if m.group(1) == k]
        if len(cyc) != runs or len(pmu) != runs or len(acc) != runs:
            raise RuntimeError(f"{image}: {k}: expected {runs} runs, got {len(cyc)}/{len(pmu)}/{len(acc)}")
        for i in range(runs):
            rows.append({"kernel": k, "run": i + 1, "cycles": cyc[i], "inst": pmu[i][0],
                         "l1i_refill": pmu[i][1], "l1d_refill": pmu[i][2], "br_mispred": pmu[i][3],
                         "acc": acc[i]})
    return rows


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("variants", nargs="+", help="name=path/to/image.bin, first is the reference")
    ap.add_argument("--out", required=True)
    ap.add_argument("--rounds", type=int, default=3)
    ap.add_argument("--runs", type=int, default=2)
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
        w = csv.DictWriter(fh, fieldnames=["variant", "round", "kernel", "run", "cycles", "inst",
                                           "l1i_refill", "l1d_refill", "br_mispred", "acc"])
        w.writeheader()
        for rnd in range(1, args.rounds + 1):
            for name, path in variants:
                print(f"round {rnd}/{args.rounds}  {name} ...", flush=True)
                for row in boot_and_run(path, args.port, args.runs):
                    rec = {"variant": name, "round": rnd, **row}
                    records.append(rec)
                    w.writerow(rec)
                fh.flush()

    print(f"\n{len(records)} kernel runs -> {args.out}\n")
    for k in KERNELS:
        accs = {r["acc"] for r in records if r["kernel"] == k}
        note = "checksum " + next(iter(accs)) if len(accs) == 1 else f"CHECKSUM MISMATCH {sorted(accs)}"
        print(f"== {k}   ({note})")
        base = None
        for name, _ in variants:
            rs = [r for r in records if r["kernel"] == k and r["variant"] == name]
            cyc = statistics.mean(r["cycles"] for r in rs)
            inst = statistics.mean(r["inst"] for r in rs)
            sd = statistics.pstdev(r["cycles"] for r in rs)
            mis = statistics.mean(r["br_mispred"] for r in rs)
            l1i = statistics.mean(r["l1i_refill"] for r in rs)
            cyc_vals = [r["cycles"] for r in rs]
            if base is None:
                base = cyc_vals
                delta = "                 -"
            else:
                pct, half, sig = welch_delta_pct(base, cyc_vals)
                delta = f"{pct:+6.2f}%+-{half:.2f}{'' if sig else '?'}"
            print(f"   {name:<12}{cyc:>14,.0f} cyc (sd {sd:>7,.0f}) {delta}  inst {inst:>13,.0f}  "
                  f"ipc {inst / cyc:5.2f}  mispred {mis:>9,.0f}  l1i {l1i:>7,.0f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
