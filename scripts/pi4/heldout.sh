#!/usr/bin/env bash
# Held-out-input test (item 4): do the PGO / ThinLTO / BOLT gains survive inputs the
# profiles never saw? Profiles are trained on input variant 0 (bolt_stage.sh does that);
# this measures the same five images on variants 0, 1 and 2:
#   0 = the training input, 1 = same distribution with new data (other seeds),
#   2 = shifted distribution (other sites hot in stair; another switch case hot in pl_b).
#
#   scripts/pi4/heldout.sh <M | M:X> [rounds] [runs]        (after bolt_stage.sh <same point>)
#
# All Pi runs are in Non-secure SVC (see docs/TODO / memory: Secure SVC is on hold).
set -euo pipefail
POINT="${1:?usage: $0 <M | M:X> [rounds] [runs]}"
M="${POINT%%:*}"; X=0
if [[ "$POINT" == *:* ]]; then X="${POINT##*:}"; fi
TAG="m$M"; if [[ "$X" != 0 ]]; then TAG="m${M}x$X"; fi
ROUNDS="${2:-3}"; RUNS="${3:-2}"
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
export MSYS_NO_PATHCONV=1
WIN="$(cygpath -m "$ROOT")"
REL="build/stage/$TAG"
[[ -f "$ROOT/$REL/pgo_thinlto_bolt.bin" ]] || { echo "run bolt_stage.sh $POINT first" >&2; exit 1; }
IMAGES=("baseline=$WIN/$REL/baseline.bin" "pgo=$WIN/$REL/pgo.bin"
        "pgo_thinlto=$WIN/$REL/pgo_thinlto.bin"
        "bolt_noreorder=$WIN/$REL/pgo_thinlto_bolt_noreorder.bin"
        "bolt=$WIN/$REL/pgo_thinlto_bolt.bin")
for v in 0 1 2; do
  echo "=== [$TAG] stair, input variant $v"
  python3 "$WIN/scripts/pi4/pi4_compare.py" --out "$WIN/$REL/heldout_stair_v$v.csv" \
    --rounds "$ROUNDS" --runs "$RUNS" --workload stair --args "0 $v" "${IMAGES[@]}" 2>&1 \
    | tee "$ROOT/$REL/heldout_stair_v$v.txt"
  echo "=== [$TAG] pgo_lab, input variant $v"
  python3 "$WIN/scripts/pi4/pgo_lab_measure.py" --out "$WIN/$REL/heldout_lab_v$v.csv" \
    --rounds "$ROUNDS" --runs "$RUNS" --args "0 $v" "${IMAGES[@]}" 2>&1 \
    | tee "$ROOT/$REL/heldout_lab_v$v.txt"
done
