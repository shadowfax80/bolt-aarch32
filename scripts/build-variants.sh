#!/usr/bin/env bash
# Build named LK images. The default final build is IR-PGO + CSPGO + ThinLTO:
#
#   irpgo-collect ordinary IR training image (round 1)
#   irpgo_thinlto ordinary IR + ThinLTO comparison
#   cspgo-collect ordinary IR use + late CS training (round 2)
#   cspgo_thinlto merged ordinary+CS use + ThinLTO (default final image)
#
# Explicit legacy frontend variants:
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
# usage: BASE=atfe scripts/build-variants.sh baseline irpgo-collect
# After both training rounds: BASE=atfe scripts/build-variants.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
source "$ROOT/scripts/resolve-base.sh"
LK_PROJECT="${LK_PROJECT:-rpi4-bolt-test}"
VARIANTS_DIR="${VARIANTS_DIR:-$ROOT/build-$BASE/variants}"
PROFDATA="${PROFDATA:-$ROOT/build-$BASE/pgo/pgo.profdata}"
IR_PROFDATA="${IR_PROFDATA:-$ROOT/build-$BASE/cspgo/ir.profdata}"
CS_PROFDATA="${CS_PROFDATA:-$ROOT/build-$BASE/cspgo/merged.profdata}"
CLANG_BINDIR="${CLANG_BINDIR:-${TOOLCHAIN:-$ROOT/build-$BASE/bin}}"

# A final optimized build always uses both profile levels unless a comparison
# or legacy variant was explicitly requested. Missing profiles fail validation;
# run scripts/pi4/cspgo_cycle_wsl.py to collect both rounds first.
if [[ $# == 0 ]]; then set -- cspgo_thinlto; fi

# Cleanup is restricted to one named output directory beneath this LK tree.
if [[ ! "$LK_PROJECT" =~ ^[a-zA-Z0-9_-]+$ ]]; then
  echo 'error: LK_PROJECT must be a simple project name' >&2; exit 1
fi
LK_BUILD="$ROOT/third_party/lk/build-$LK_PROJECT"
if [[ "$(realpath -m "$LK_BUILD")" != "$(realpath -m "$ROOT/third_party/lk")/build-$LK_PROJECT" ]]; then
  echo 'error: LK build output escapes the source tree' >&2; exit 1
fi

mkdir -p "$VARIANTS_DIR"

build_one() {
  local name="$1"; shift
  echo "=== building variant: $name ==="
  rm -rf -- "$LK_BUILD"
  env -u WITH_BOLT_PGO -u WITH_BOLT_PGO_USE -u WITH_BOLT_CSPGO -u WITH_BOLT_THINLTO -u BOLT_PGO_KIND \
    "$@" BASE="$BASE" LK_PROJECT="$LK_PROJECT" \
    "$ROOT/scripts/build-lk-aarch32.sh" > "$VARIANTS_DIR/$name.build.log" 2>&1 \
    || { echo "error: $name build failed, see $VARIANTS_DIR/$name.build.log" >&2; tail -20 "$VARIANTS_DIR/$name.build.log" >&2; exit 1; }
  cp "$ROOT/third_party/lk/build-$LK_PROJECT/lk.elf" "$VARIANTS_DIR/$name.elf"
  NOFPU_TOOLCHAIN="$CLANG_BINDIR" "$ROOT/scripts/check-no-fpu.sh" "$VARIANTS_DIR/$name.elf" \
    > "$VARIANTS_DIR/$name.nofpu.log" 2>&1 \
    || { cat "$VARIANTS_DIR/$name.nofpu.log" >&2; exit 1; }
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
    irpgo-collect) build_one "$v" BOLT_PGO_KIND=ir WITH_BOLT_PGO=true WITH_BOLT_THINLTO=true ;;
    irpgo_thinlto|cspgo-collect)
      python3 "$ROOT/scripts/pgo_profile.py" validate "$IR_PROFDATA" --kind ir-only --profdata "$CLANG_BINDIR/llvm-profdata"
      if [[ "$v" == cspgo-collect ]]; then
        build_one "$v" BOLT_PGO_KIND=ir WITH_BOLT_PGO_USE="$IR_PROFDATA" WITH_BOLT_THINLTO=true WITH_BOLT_CSPGO=true
      else
        build_one "$v" BOLT_PGO_KIND=ir WITH_BOLT_PGO_USE="$IR_PROFDATA" WITH_BOLT_THINLTO=true
      fi ;;
    cspgo_thinlto)
      python3 "$ROOT/scripts/pgo_profile.py" validate "$CS_PROFDATA" --kind merged --profdata "$CLANG_BINDIR/llvm-profdata"
      build_one "$v" BOLT_PGO_KIND=ir WITH_BOLT_PGO_USE="$CS_PROFDATA" WITH_BOLT_THINLTO=true ;;
    *) echo "error: unknown variant '$v' (baseline|pgo-collect|pgo|pgo_thinlto|irpgo-collect|irpgo_thinlto|cspgo-collect|cspgo_thinlto)" >&2; exit 1 ;;
  esac
done
