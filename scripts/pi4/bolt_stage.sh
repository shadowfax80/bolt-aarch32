#!/usr/bin/env bash
# One complete staged point on the real Pi for the stair workload at STAIR_M=<M>
# (64*M call sites): baseline -> +PGO -> +PGO+ThinLTO -> +BOLT, plus a BOLT
# no-reorder control, all from fresh builds and fresh profiles.
#
#   scripts/pi4/bolt_stage.sh <M> [rounds] [runs]
#
# Steps: PGO training on the Pi + WSL builds (pgo_cycle_wsl.sh); BOLT edge
# instrumentation (every edge counted); profile on the Pi; BOLT optimize twice
# (ext-tsp and the -reorder-blocks=none control); interleaved measurement of all
# five images with a checksum check. Everything lands in build/stage/m<M>/.
set -euo pipefail
M="${1:?usage: $0 <STAIR_M> [rounds] [runs]}"
ROUNDS="${2:-3}"; RUNS="${3:-2}"
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
export MSYS_NO_PATHCONV=1
WIN="$(cygpath -m "$ROOT")"
WROOT="/mnt/c/${ROOT#/c/}"
REL="build/stage/m$M"
mkdir -p "$ROOT/$REL"
W=(wsl.exe -d Ubuntu -- bash)

echo "=== [m$M] PGO training + variant builds"
LK_MAKE_ARGS="STAIR_M=$M" OUTDIR="$REL" \
  bash "$ROOT/scripts/pi4/pgo_cycle_wsl.sh" composite,stair baseline pgo pgo_thinlto \
  > "$ROOT/$REL/cycle.log" 2>&1

echo "=== [m$M] BOLT instrument"
line="$("${W[@]}" "$WROOT/scripts/pi4/bolt_stage_wsl.sh" instrument "$WROOT/$REL" | grep COUNTERS)"
addr="$(sed -n 's/.*addr=\([0-9a-fA-F]*\).*/\1/p' <<<"$line")"
size="$(sed -n 's/.*size=\([0-9a-fA-F]*\).*/\1/p' <<<"$line")"
echo "    $line"

echo "=== [m$M] BOLT profile on the Pi"
python3 "$WIN/scripts/pi4/pi4_bolt_profile.py" "$WIN/$REL/pgo_thinlto.instr.bin" \
  "$WIN/$REL/counters.bin" --addr "$addr" --size "$size" --workload stair

echo "=== [m$M] BOLT optimize (+ no-reorder control)"
"${W[@]}" "$WROOT/scripts/pi4/bolt_stage_wsl.sh" optimize "$WROOT/$REL" "$WROOT/$REL/counters.bin"

echo "=== [m$M] measure ($ROUNDS rounds x $RUNS runs, interleaved)"
python3 "$WIN/scripts/pi4/pi4_compare.py" --out "$WIN/$REL/compare.csv" \
  --rounds "$ROUNDS" --runs "$RUNS" --workload stair \
  "baseline=$WIN/$REL/baseline.bin" "pgo=$WIN/$REL/pgo.bin" \
  "pgo_thinlto=$WIN/$REL/pgo_thinlto.bin" \
  "bolt_noreorder=$WIN/$REL/pgo_thinlto_bolt_noreorder.bin" \
  "bolt=$WIN/$REL/pgo_thinlto_bolt.bin" 2>&1 | tee "$ROOT/$REL/summary.txt"
