#!/usr/bin/env bash
# Build named LK images for the staged real-Pi comparison (Step 10):
#
#   baseline      plain build
#   pgo-collect   instrumented (-fprofile-instr-generate), for collecting a profile
#   pgo           +PGO: profile applied (needs build-$BASE/pgo/pgo.profdata)
#   pgo_thinlto   +PGO +ThinLTO on the bolt_bench module (same profile)
#
# Each lands in build-$BASE/variants/<name>.{elf,bin}. Every variant is built
# from the same overlay source, from a clean LK build dir, so any difference
# between them is the flags and nothing else.
#
# usage: BASE=atfe scripts/build-variants.sh baseline pgo-collect
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
source "$ROOT/scripts/resolve-base.sh"
LK_PROJECT="${LK_PROJECT:-rpi4-bolt-test}"
VARIANTS_DIR="$ROOT/build-$BASE/variants"
PROFDATA="${PROFDATA:-$ROOT/build-$BASE/pgo/pgo.profdata}"

mkdir -p "$VARIANTS_DIR"

build_one() {
  local name="$1"; shift
  echo "=== building variant: $name ==="
  rm -rf "$ROOT/third_party/lk/build-$LK_PROJECT"
  env "$@" BASE="$BASE" LK_PROJECT="$LK_PROJECT" \
    "$ROOT/scripts/build-lk-aarch32.sh" > "$VARIANTS_DIR/$name.build.log" 2>&1 \
    || { echo "error: $name build failed, see $VARIANTS_DIR/$name.build.log" >&2; tail -20 "$VARIANTS_DIR/$name.build.log" >&2; exit 1; }
  cp "$ROOT/third_party/lk/build-$LK_PROJECT/lk.elf" "$VARIANTS_DIR/$name.elf"
  cp "$ROOT/third_party/lk/build-$LK_PROJECT/lk.bin" "$VARIANTS_DIR/$name.bin"
  echo "  -> $VARIANTS_DIR/$name.bin ($(stat -c %s "$VARIANTS_DIR/$name.bin") bytes)"
}

need_profile() {
  if [[ ! -f "$PROFDATA" ]]; then
    echo "error: $PROFDATA missing -- build pgo-collect, run it on the Pi, dump + merge a profile first" >&2
    exit 1
  fi
}

for v in "$@"; do
  case "$v" in
    baseline)    build_one baseline ;;
    pgo-collect) build_one pgo-collect WITH_BOLT_PGO=true ;;
    pgo)         need_profile; build_one pgo WITH_BOLT_PGO_USE="$PROFDATA" ;;
    pgo_thinlto) need_profile; build_one pgo_thinlto WITH_BOLT_PGO_USE="$PROFDATA" WITH_BOLT_THINLTO=true ;;
    *) echo "error: unknown variant '$v' (baseline|pgo-collect|pgo|pgo_thinlto)" >&2; exit 1 ;;
  esac
done
