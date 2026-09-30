#!/usr/bin/env bash
# Multi-function BOLT on the real Pi: the `multi` workload (six 5 KB functions on the
# same L1I sets, one in ARM mode, all reached through function pointers).
#
#   scripts/pi4/multi_stage.sh [rounds] [runs]
#
# baseline build -> edge instrumentation of all six functions -> profile on the Pi ->
# BOLT optimize twice (function reordering on; and off as the control) -> interleaved
# measurement of the three images with a checksum check. Output: build/multi/.
set -euo pipefail
ROUNDS="${1:-3}"; RUNS="${2:-2}"
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
export MSYS_NO_PATHCONV=1
WIN="$(cygpath -m "$ROOT")"
WROOT="/mnt/c/${ROOT#/c/}"
REL="build/multifn"
mkdir -p "$ROOT/$REL"
W=(wsl.exe -d Ubuntu -- bash)

echo "=== [multi] sync + build baseline"
"${W[@]}" "$WROOT/scripts/wsl-setup.sh" sync | tail -1
"${W[@]}" "$WROOT/scripts/pi4/multi_stage_wsl.sh" build "$WROOT/$REL"

echo "=== [multi] BOLT instrument (six functions)"
line="$("${W[@]}" "$WROOT/scripts/pi4/multi_stage_wsl.sh" instrument "$WROOT/$REL" | grep COUNTERS)"
addr="$(sed -n 's/.*addr=\([0-9a-fA-F]*\).*/\1/p' <<<"$line")"
size="$(sed -n 's/.*size=\([0-9a-fA-F]*\).*/\1/p' <<<"$line")"
echo "    $line"

echo "=== [multi] BOLT profile on the Pi"
python3 "$WIN/scripts/pi4/pi4_bolt_profile.py" "$WIN/$REL/baseline.instr.bin" \
  "$WIN/$REL/counters.bin" --addr "$addr" --size "$size" --workload multi

echo "=== [multi] BOLT optimize (+ function-order control)"
"${W[@]}" "$WROOT/scripts/pi4/multi_stage_wsl.sh" optimize "$WROOT/$REL" "$WROOT/$REL/counters.bin"

echo "=== [multi] measure ($ROUNDS rounds x $RUNS runs, interleaved)"
python3 "$WIN/scripts/pi4/pi4_compare.py" --out "$WIN/$REL/compare.csv" \
  --rounds "$ROUNDS" --runs "$RUNS" --workload multi \
  "baseline=$WIN/$REL/baseline.bin" \
  "bolt_nofnreorder=$WIN/$REL/baseline_bolt_nofnreorder.bin" \
  "bolt=$WIN/$REL/baseline_bolt.bin" 2>&1 | tee "$ROOT/$REL/summary.txt"
