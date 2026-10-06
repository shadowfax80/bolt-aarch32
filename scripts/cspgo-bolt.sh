#!/usr/bin/env bash
# Optional BOLT comparison after the compiler CSPGO cycle. Pi sampling runs
# separately on Windows with pi4_sample_profile.py (one seal per exact ELF).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
export BASE="${BASE:-atfe}"
export TOOLCHAIN="${TOOLCHAIN:-$ROOT/build-$BASE/bin}"
stage="${1:-}"
export VARIANTS_DIR="${2:?usage: cspgo-bolt.sh prepare OUT INPUT | optimize OUT VARIANT}"
case "$stage" in
  prepare)
    input="${3:?compiler cycle output directory required}"
    if [[ -e "$VARIANTS_DIR" ]]; then
      echo 'error: use a fresh BOLT output directory; preserve existing evidence' >&2; exit 1
    fi
    mkdir -p "$VARIANTS_DIR"
    for variant in irpgo_thinlto cspgo_thinlto; do
      cp "$input/$variant.elf" "$input/$variant.bin" "$VARIANTS_DIR/"
      "$ROOT/scripts/check-no-fpu.sh" "$VARIANTS_DIR/$variant.elf" > "$VARIANTS_DIR/$variant.nofpu.log"
      python3 "$ROOT/scripts/profile_identity.py" seal-samples \
        --elf "$VARIANTS_DIR/$variant.elf" --image "$VARIANTS_DIR/$variant.bin" \
        --toolchain "$TOOLCHAIN" --patch-dir "$ROOT/overlay/llvm/patches/atfe"
    done
    ;;
  optimize)
    variant="${3:?compiler variant required}"
    case "$variant" in irpgo_thinlto|cspgo_thinlto) ;; *) echo 'error: unknown compiler variant' >&2; exit 1 ;; esac
    if [[ -e "$VARIANTS_DIR/${variant}_bolt.elf" || -e "$VARIANTS_DIR/$variant.samples.fdata" ]]; then
      echo 'error: BOLT outputs already exist; preserve evidence and use a fresh directory' >&2; exit 1
    fi
    python3 "$ROOT/scripts/lk_coverage_report.py" --elf "$VARIANTS_DIR/$variant.elf" \
      --toolchain "$TOOLCHAIN" --out "$VARIANTS_DIR/$variant.coverage-work" \
      --json "$VARIANTS_DIR/$variant.coverage.json" > "$VARIANTS_DIR/$variant.coverage.log"
    skip=$(python3 - "$VARIANTS_DIR/$variant.coverage.json" <<'PY'
import json,sys
print(','.join(json.load(open(sys.argv[1]))['skip_funcs']))
PY
)
    python3 "$ROOT/scripts/samples_to_fdata.py" "$VARIANTS_DIR/$variant.elf" "$VARIANTS_DIR/$variant.samples" \
      -o "$VARIANTS_DIR/$variant.samples.fdata" --toolchain "$TOOLCHAIN" \
      --functions bolt_bench_stair_kernel --skip-funcs "$skip" \
      > "$VARIANTS_DIR/$variant.convert.log" 2>&1
    BOLT_FUNC=bolt_bench_stair_kernel BOLT_FDATA="$VARIANTS_DIR/$variant.samples.fdata" \
      "$ROOT/scripts/bolt-variant.sh" optimize "$variant" > "$VARIANTS_DIR/$variant.optimize.log" 2>&1
    "$ROOT/scripts/check-no-fpu.sh" "$VARIANTS_DIR/${variant}_bolt.elf" > "$VARIANTS_DIR/${variant}_bolt.nofpu.log"
    ;;
  *) echo 'usage: cspgo-bolt.sh prepare OUT INPUT | optimize OUT VARIANT' >&2; exit 1 ;;
esac
