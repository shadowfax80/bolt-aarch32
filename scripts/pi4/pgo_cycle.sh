#!/usr/bin/env bash
# LEGACY (2026-09-30): the RunPod-pod version of the PGO cycle. Use
# scripts/pi4/pgo_cycle_wsl.sh (builds in local WSL2); see docs/WSL_BUILD.md.
# One PGO training cycle across the build pod and the real Pi, then rebuild the
# profile-using variants. Run from the dev machine (it needs the Pi on COM5).
#
#   POD=root@<ip> PODPORT=<port> scripts/pi4/pgo_cycle.sh [workloads] [variants...]
#
# workloads  comma-separated training workloads (default: composite,layout_a)
# variants   what to build afterwards (default: baseline pgo pgo_thinlto)
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
POD="${POD:?set POD=root@<pod ip>}"
PODPORT="${PODPORT:?set PODPORT=<ssh port>}"
WL="${1:-composite,layout_a}"; shift || true
VARIANTS=("${@:-baseline pgo pgo_thinlto}")
SSH=(ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o LogLevel=ERROR -p "$PODPORT" "$POD")
SCP=(scp -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o LogLevel=ERROR -P "$PODPORT")
REMOTE=/workspace/bolt-lk-overlay
OUT="$ROOT/build/rpi4-bolt-test"
mkdir -p "$OUT"

"${SSH[@]}" "set -o pipefail; cd $REMOTE && unset VARIANTS_DIR LK_PROJECT BOLT_EXTRA_ARGS BOLT_FUNC && BASE=atfe ./scripts/build-variants.sh pgo-collect 2>&1 | tail -1"
"${SCP[@]}" "$POD:$REMOTE/build-atfe/variants/pgo-collect.bin" "$OUT/variant_pgo-collect.bin"
python3 "$ROOT/scripts/pi4/pi4_pgo_collect.py" "$OUT/variant_pgo-collect.bin" "$OUT/train.profraw" --workload "$WL"
"${SCP[@]}" "$OUT/train.profraw" "$POD:$REMOTE/build-atfe/pgo/pgo.profraw"
"${SSH[@]}" "set -o pipefail; cd $REMOTE/build-atfe && bin/llvm-profdata merge pgo/pgo.profraw -o pgo/pgo.profdata && cd .. && unset VARIANTS_DIR LK_PROJECT BOLT_EXTRA_ARGS BOLT_FUNC && BASE=atfe ./scripts/build-variants.sh ${VARIANTS[*]} 2>&1 | tail -${#VARIANTS[@]}"
