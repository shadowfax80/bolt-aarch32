#!/usr/bin/env bash
# BOLT optimization passes on the real Pi, checked for correctness: baseline build -> edge
# instrumentation of the small bolt_bench workloads -> profile (`bolt_bench all`) -> one
# BOLT image per pass set (plain, -inline-all, -simplify-rodata-loads, -split-functions,
# all of them) -> run `bolt_bench all` on each and compare every workload's result with the
# baseline image. Output: build/passes/. Non-secure SVC.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
export MSYS_NO_PATHCONV=1
WIN="$(cygpath -m "$ROOT")"
WROOT="/mnt/c/${ROOT#/c/}"
REL="build/passes"
mkdir -p "$ROOT/$REL"
W=(wsl.exe -d Ubuntu -- bash)

echo "=== [passes] build baseline"
"${W[@]}" "$WROOT/scripts/pi4/passes_stage_wsl.sh" build "$WROOT/$REL"

echo "=== [passes] BOLT instrument"
line="$("${W[@]}" "$WROOT/scripts/pi4/passes_stage_wsl.sh" instrument "$WROOT/$REL" | grep COUNTERS)"
addr="$(sed -n 's/.*addr=\([0-9a-fA-F]*\).*/\1/p' <<<"$line")"
size="$(sed -n 's/.*size=\([0-9a-fA-F]*\).*/\1/p' <<<"$line")"
echo "    $line"

echo "=== [passes] BOLT profile on the Pi (bolt_bench all)"
python3 "$WIN/scripts/pi4/pi4_bolt_profile.py" "$WIN/$REL/baseline.instr.bin" \
  "$WIN/$REL/counters.bin" --addr "$addr" --size "$size" --workload all

echo "=== [passes] BOLT optimize, one image per pass set"
"${W[@]}" "$WROOT/scripts/pi4/passes_stage_wsl.sh" optimize "$WROOT/$REL" "$WROOT/$REL/counters.bin"

echo "=== [passes] results on the Pi vs baseline"
python3 "$WIN/scripts/pi4/passes_check.py" "baseline=$WIN/$REL/baseline.bin" \
  "bolt=$WIN/$REL/baseline_bolt.bin" "inline=$WIN/$REL/baseline_inline.bin" \
  "rodata=$WIN/$REL/baseline_rodata.bin" "split=$WIN/$REL/baseline_split.bin" \
  "peep=$WIN/$REL/baseline_peep.bin" "sctc=$WIN/$REL/baseline_sctc.bin" \
  "all=$WIN/$REL/baseline_all.bin" 2>&1 | tee "$ROOT/$REL/check.txt"
