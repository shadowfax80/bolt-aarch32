#!/usr/bin/env bash
# PGO training cycle with the build tree in WSL and the Pi on this Windows machine.
# Same as pgo_cycle.sh, minus the pod: builds run in WSL (~/bolt-aarch32), the
# profile is collected on the real Pi over COM5.
#
#   [LK_MAKE_ARGS="STAIR_M=5"] [OUTDIR=build/v2] scripts/pi4/pgo_cycle_wsl.sh [workloads] [variants...]
#
# workloads  comma-separated training workloads (default: composite,stair)
# variants   what to build afterwards (default: baseline pgo pgo_thinlto)
# The finished .bin/.elf of each variant are copied to $OUTDIR (default build/v2).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
export MSYS_NO_PATHCONV=1
WL="${1:-composite,stair}"; shift || true
VARIANTS="${*:-baseline pgo pgo_thinlto}"
OUTDIR="${OUTDIR:-build/v2}"
WIN="$(cygpath -m "$ROOT")"
OUT="$ROOT/build/rpi4-bolt-test"
WROOT="/mnt/c/${ROOT#/c/}"          # the same checkout, as WSL sees it
WOUT="$WROOT/build/rpi4-bolt-test"
MAKEARGS="${LK_MAKE_ARGS:-}"
mkdir -p "$OUT" "$ROOT/$OUTDIR"
W=(wsl.exe -d Ubuntu -- bash -c)
ENVS="unset VARIANTS_DIR LK_PROJECT BOLT_EXTRA_ARGS BOLT_FUNC; export LK_MAKE_ARGS='$MAKEARGS' BASE=atfe"

"${W[@]}" "bash $WROOT/scripts/wsl-setup.sh sync"
"${W[@]}" "set -o pipefail; cd ~/bolt-aarch32 && $ENVS && ./scripts/build-variants.sh pgo-collect 2>&1 | tail -1 && cp build-atfe/variants/pgo-collect.bin $WOUT/variant_pgo-collect.bin"
python3 "$WIN/scripts/pi4/pi4_pgo_collect.py" "$WIN/build/rpi4-bolt-test/variant_pgo-collect.bin" "$WIN/build/rpi4-bolt-test/train.profraw" --workload "$WL"
"${W[@]}" "set -o pipefail; cd ~/bolt-aarch32 && mkdir -p build-atfe/pgo && cp $WOUT/train.profraw build-atfe/pgo/pgo.profraw && build-atfe/bin/llvm-profdata merge build-atfe/pgo/pgo.profraw -o build-atfe/pgo/pgo.profdata && $ENVS && ./scripts/build-variants.sh $VARIANTS 2>&1 | tail -4"
for v in $VARIANTS; do
  for ext in bin elf; do
    wsl.exe -d Ubuntu -- cp "/home/user/bolt-aarch32/build-atfe/variants/$v.$ext" "$WROOT/$OUTDIR/$v.$ext"
  done
done
ls -la "$ROOT/$OUTDIR"/*.bin
