#!/usr/bin/env bash
# Historical frontend-PGO footprint sweep: when ThinLTO stops paying off
# (its inlined hot path overflows the L1I), and how much of that is left for BOLT?
# For each STAIR_M (64 sites per unit) it retrains PGO on the Pi, builds baseline and
# pgo_thinlto in WSL, and measures both on the Pi. One CSV per point in build/sweep/.
#
#   scripts/pi4/stair_sweep.sh 2 3 4 5 6 8      # 64-site units
#   scripts/pi4/stair_sweep.sh 6:1 6:2 6:3      # <M>:<X> = 64*M + 16*X sites (400/416/432)
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
WIN="$(cygpath -m "$ROOT")"
for POINT in "$@"; do
  M="${POINT%%:*}"; X=0; [[ "$POINT" == *:* ]] && X="${POINT##*:}"
  TAG="m$M"; [[ "$X" != 0 ]] && TAG="m${M}x$X"
  echo "=== STAIR_M=$M STAIR_X=$X ($((64 * M + 16 * X)) sites) ==="
  mkdir -p "$ROOT/build/sweep/$TAG"
  LK_MAKE_ARGS="STAIR_M=$M STAIR_X=$X" OUTDIR="build/sweep/$TAG"     bash "$ROOT/scripts/pi4/pgo_cycle_wsl.sh" --frontend composite,stair,pgo_lab baseline pgo_thinlto > "$ROOT/build/sweep/$TAG/cycle.log" 2>&1
  python3 "$WIN/scripts/pi4/pi4_compare.py" --out "$WIN/build/sweep/$TAG/compare.csv" --rounds 2 --runs 2 --workload stair     "baseline=$WIN/build/sweep/$TAG/baseline.bin" "pgo_thinlto=$WIN/build/sweep/$TAG/pgo_thinlto.bin"     | grep -E "^==|cycles |inst |l1i_refill |ipc|cycles vs|checksum" | tee "$ROOT/build/sweep/$TAG/summary.txt"
done
