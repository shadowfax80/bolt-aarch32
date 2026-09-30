#!/usr/bin/env bash
# One complete staged point on the real Pi:
# baseline -> +PGO -> +PGO+ThinLTO -> +BOLT, plus a BOLT no-reorder control, all
# from fresh builds and fresh profiles.
#
#   scripts/pi4/bolt_stage.sh <M | M:X> [rounds] [runs]      sites = 64*M + 16*X
#   WORKLOAD=composite BOLT_FUNC=bolt_bench_composite SKIP_LAB=1 \
#       scripts/pi4/bolt_stage.sh 6:3                        # the composite workload
#
# Steps: PGO training on the Pi (composite + stair + pgo_lab) and WSL builds
# (pgo_cycle_wsl.sh); BOLT edge instrumentation (every edge counted); profile on the
# Pi; BOLT optimize twice (ext-tsp and the -reorder-blocks=none control);
# interleaved measurement of the five images on $WORKLOAD with a checksum check; then
# (unless SKIP_LAB=1) the same five images on the pgo_lab kernels (pl_b, a skewed
# switch, is the PGO stage). Everything lands in build/stage/<tag>/.
#
# WORKLOAD   the bolt_bench workload to profile and measure   (default: stair)
# BOLT_FUNC  the function(s) BOLT instruments and rewrites    (default: bolt_bench_stair_kernel)
set -euo pipefail
POINT="${1:?usage: $0 <M | M:X> [rounds] [runs]}"
M="${POINT%%:*}"
X=0
if [[ "$POINT" == *:* ]]; then X="${POINT##*:}"; fi
WORKLOAD="${WORKLOAD:-stair}"
FUNC="${BOLT_FUNC:-bolt_bench_stair_kernel}"
TAG="m$M"
if [[ "$X" != 0 ]]; then TAG="m${M}x$X"; fi
if [[ "$WORKLOAD" != stair ]]; then TAG="${WORKLOAD}_$TAG"; fi
ROUNDS="${2:-3}"; RUNS="${3:-2}"
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
export MSYS_NO_PATHCONV=1
WIN="$(cygpath -m "$ROOT")"
WROOT="/mnt/c/${ROOT#/c/}"
REL="build/stage/$TAG"
mkdir -p "$ROOT/$REL"
# wsl.exe does not carry the Windows-side environment into WSL: pass BOLT_FUNC explicitly.
W=(wsl.exe -d Ubuntu -- env BOLT_FUNC="$FUNC" bash)

echo "=== [$TAG] PGO training + variant builds"
LK_MAKE_ARGS="STAIR_M=$M STAIR_X=$X" OUTDIR="$REL" \
  bash "$ROOT/scripts/pi4/pgo_cycle_wsl.sh" composite,stair,pgo_lab baseline pgo pgo_thinlto \
  > "$ROOT/$REL/cycle.log" 2>&1

echo "=== [$TAG] BOLT instrument ($FUNC)"
line="$("${W[@]}" "$WROOT/scripts/pi4/bolt_stage_wsl.sh" instrument "$WROOT/$REL" | grep COUNTERS)"
addr="$(sed -n 's/.*addr=\([0-9a-fA-F]*\).*/\1/p' <<<"$line")"
size="$(sed -n 's/.*size=\([0-9a-fA-F]*\).*/\1/p' <<<"$line")"
echo "    $line"

echo "=== [$TAG] BOLT profile on the Pi ($WORKLOAD)"
python3 "$WIN/scripts/pi4/pi4_bolt_profile.py" "$WIN/$REL/pgo_thinlto.instr.bin" \
  "$WIN/$REL/counters.bin" --addr "$addr" --size "$size" --workload "$WORKLOAD"

echo "=== [$TAG] BOLT optimize (+ no-reorder control)"
"${W[@]}" "$WROOT/scripts/pi4/bolt_stage_wsl.sh" optimize "$WROOT/$REL" "$WROOT/$REL/counters.bin"

IMAGES=("baseline=$WIN/$REL/baseline.bin" "pgo=$WIN/$REL/pgo.bin"
        "pgo_thinlto=$WIN/$REL/pgo_thinlto.bin"
        "bolt_noreorder=$WIN/$REL/pgo_thinlto_bolt_noreorder.bin"
        "bolt=$WIN/$REL/pgo_thinlto_bolt.bin")

echo "=== [$TAG] measure $WORKLOAD ($ROUNDS rounds x $RUNS runs, interleaved)"
python3 "$WIN/scripts/pi4/pi4_compare.py" --out "$WIN/$REL/compare.csv" \
  --rounds "$ROUNDS" --runs "$RUNS" --workload "$WORKLOAD" "${IMAGES[@]}" 2>&1 \
  | tee "$ROOT/$REL/summary.txt"

if [[ "${SKIP_LAB:-0}" != 1 ]]; then
  echo "=== [$TAG] measure pgo_lab kernels on the same images (pl_b = PGO stage)"
  python3 "$WIN/scripts/pi4/pgo_lab_measure.py" --out "$WIN/$REL/lab.csv" \
    --rounds "$ROUNDS" --runs "$RUNS" "${IMAGES[@]}" 2>&1 \
    | tee "$ROOT/$REL/lab_summary.txt"
fi
