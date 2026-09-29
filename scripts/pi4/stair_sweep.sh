#!/usr/bin/env bash
# Footprint sweep: how big can the stair kernel be before ThinLTO stops paying off
# (its inlined hot path overflows the L1I), and how much of that is left for BOLT?
# For each STAIR_M (64 sites per unit) it retrains PGO on the Pi, builds baseline and
# pgo_thinlto in WSL, and measures both on the Pi. One CSV per point in build/sweep/.
#
#   scripts/pi4/stair_sweep.sh 2 3 4 5 6 8
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
WIN="$(cygpath -m "$ROOT")"
for M in "$@"; do
  echo "=== STAIR_M=$M ($((64 * M)) sites) ==="
  mkdir -p "$ROOT/build/sweep/m$M"
  LK_MAKE_ARGS="STAIR_M=$M" OUTDIR="build/sweep/m$M" \
    bash "$ROOT/scripts/pi4/pgo_cycle_wsl.sh" composite,stair baseline pgo_thinlto > "$ROOT/build/sweep/m$M/cycle.log" 2>&1
  python3 "$WIN/scripts/pi4/pi4_compare.py" --out "$WIN/build/sweep/m$M/compare.csv" --rounds 2 --runs 2 --workload stair \
    "baseline=$WIN/build/sweep/m$M/baseline.bin" "pgo_thinlto=$WIN/build/sweep/m$M/pgo_thinlto.bin" \
    | grep -E "^==|cycles |inst |l1i_refill |ipc|cycles vs" | tee "$ROOT/build/sweep/m$M/summary.txt"
done
