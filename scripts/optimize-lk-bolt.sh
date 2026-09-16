#!/usr/bin/env bash
# Apply BOLT layout optimizations to LK using a host-generated .fdata profile.
#
# ARCH=aarch64 (default) or ARCH=arm32
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TOOLCHAIN="${TOOLCHAIN:-$ROOT/build-${BASE:-upstream}/bin}"
LK_DIR="${LK_DIR:-$ROOT/third_party/lk}"
ARCH="${ARCH:-aarch64}"

case "$ARCH" in
  aarch64|arm64)
    ELF="${ELF:-$LK_DIR/build-qemu-virt-arm64-test/lk.elf}"
    FDATA="${FDATA:-$ROOT/build-${BASE:-upstream}/prof.fdata}"
    OUT="${OUT:-$ROOT/build-${BASE:-upstream}/lk.bolt.elf}"
    ;;
  arm|arm32|aarch32)
    ARCH=arm32
    ELF="${ELF:-$LK_DIR/build-qemu-virt-arm32-test/lk.elf}"
    FDATA="${FDATA:-$ROOT/build-${BASE:-upstream}/prof-arm32.fdata}"
    OUT="${OUT:-$ROOT/build-${BASE:-upstream}/lk.bolt.arm32.elf}"
    ;;
  *)
    echo "error: ARCH must be aarch64 or arm32 (got: $ARCH)" >&2
    exit 1
    ;;
esac

if [[ ! -f "$ELF" ]]; then
  echo "error: $ELF not found — run scripts/build-lk-aarch64.sh or build-lk-aarch32.sh" >&2
  exit 1
fi
if [[ ! -s "$FDATA" ]]; then
  echo "error: $FDATA missing or empty — run ram-dump-to-fdata first" >&2
  exit 1
fi

mkdir -p "$(dirname "$OUT")"

BOLT_ARGS=(
  -data="$FDATA"
  -o "$OUT"
  --no-lse-atomics
  -reorder-blocks=ext-tsp
  -reorder-functions=hfsort+
  # Confirmed ARM-compatible 2026-09-16 (run clean on this target, no
  # errors): identical-code-folding, generic peepholes, hot/cold splitting.
  -icf=all
  -peepholes=all
  -split-functions
  # NOT included -- confirmed hard-gated to X86/AArch64 only in this LLVM
  # version, not merely untested (each errors out immediately rather than
  # silently no-op'ing): -indirect-call-promotion ("supported only on X86
  # and AArch64"), -reg-reassign ("specific to X86"), -frame-opt / shrink-
  # wrapping ("frame-optimizer is supported only on X86").
)

# Prefer rewriting only profiled benches on ARM32 — full-image layout
# still hits trampoline/literal-pool issues outside bolt_bench_*.
if [[ "$ARCH" == "arm32" ]]; then
  FUNCS="${OPTIMIZE_FUNCS:-bolt_bench_hot_loop,bolt_bench_hot_cold,bolt_bench_branch_chain,bolt_bench_memcpy,bolt_bench_interwork,bolt_bench_switch,bolt_bench_spill_ret,bolt_bench_litpool,bolt_bench_indirect_call,bolt_bench_interwork_tail,bolt_bench_regpressure,bolt_bench_hotcold_split,bolt_bench_icf,bolt_bench_shrinkwrap}"
  FUNCS_FILE="$(mktemp)"
  trap 'rm -f "$FUNCS_FILE"' EXIT
  tr ',' '\n' <<<"$FUNCS" | sed '/^$/d' > "$FUNCS_FILE"
  BOLT_ARGS+=(--funcs-file-no-regex="$FUNCS_FILE")
fi

"$TOOLCHAIN/llvm-bolt" "$ELF" "${BOLT_ARGS[@]}" "$@"

python3 "$ROOT/scripts/fix-kernel-elf-paddr.py" "$OUT"
python3 "$ROOT/scripts/fix-kernel-elf-entry.py" "$OUT" --original "$ELF" \
  --readelf "$TOOLCHAIN/llvm-readelf"
python3 "$ROOT/scripts/fix-kernel-elf-sections.py" "$OUT" --original "$ELF" \
  --readelf "$TOOLCHAIN/llvm-readelf"

echo "optimized image: $OUT"
