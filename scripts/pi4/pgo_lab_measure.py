#!/usr/bin/env python3
"""Measure the pgo_lab kernels (pl_a..pl_d) for several LK images on the real Pi.

Each image is booted once per round and runs `bolt_bench pgo_lab` `--runs` times;
rounds interleave the images (A B A B ...) so drift cannot favour one. Every run is
kept in the CSV; the table reports, per kernel and image, mean cycles, instructions,
IPC, L1I refills and mispredicts, and the change of cycles against the first image.
This is measurement/output consistency, not proof of rewritten execution or an
independent correctness oracle. Checksums must agree across images or the comparison is between different programs.

usage: pgo_lab_measure.py --out lab.csv [--rounds 3] [--runs 2] name=image.bin ...
"""

from __future__ import annotations

import argparse
import csv
import os
import statistics
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from stats_util import welch_delta_pct  # noqa: E402
from measurement_records import capture_measurements, consistent  # noqa: E402
KERNELS = ["pl_a", "pl_b", "pl_c", "pl_d"]

# Extra words after `pgo_lab` (PMU set, input variant), set from --args.
EXTRA_ARGS = ""


def boot_and_run(image: str, port: str, runs: int) -> list[dict]:
    command = f"bolt_bench pgo_lab {EXTRA_ARGS}".strip()
    rows = capture_measurements(image,port,command,KERNELS,runs,60,120)
    return [{k:v for k,v in row.items() if k != 'taken'} for row in rows]


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
    if not 1 <= args.runs <= 32 or args.rounds < 1:
        ap.error("runs must be 1..32 and rounds must be positive")
    global EXTRA_ARGS
    EXTRA_ARGS = args.args

    variants = []
    for v in args.variants:
        name, _, path = v.partition("=")
        if not path or not os.path.exists(path):
            sys.exit(f"bad variant spec / missing file: {v}")
        if not name or name in {n for n,_ in variants}:
            ap.error("variant names must be nonempty and unique")
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
    consistent(records,KERNELS)
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
