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

# Every ARM profile must carry the receipt for this exact source ELF.
if [[ "$ARCH" == arm32 ]]; then
  python3 "$ROOT/scripts/profile_identity.py" check-profile --elf "$ELF" --profile "$FDATA"
fi

mkdir -p "$(dirname "$OUT")"

BOLT_ARGS=(
  -data="$FDATA"
  -o "$OUT"
  # BOLT_REORDER_BLOCKS=none gives the no-reorder control: the function is still
  # rewritten and moved to the new .text, but keeps its block order.
  -reorder-blocks="${BOLT_REORDER_BLOCKS:-ext-tsp}"
  # BOLT_REORDER_FUNCTIONS=none gives the control for function ordering: the functions
  # are still rewritten but keep their original relative order and spacing.
  -reorder-functions="${BOLT_REORDER_FUNCTIONS:-hfsort+}"
  -icf=all
  # NOT included -- confirmed hard-gated to X86/AArch64 only in this LLVM
  # version, not merely untested (each errors out immediately rather than
  # silently no-op'ing): -indirect-call-promotion ("supported only on X86
  # and AArch64"), -reg-reassign ("specific to X86"), -frame-opt / shrink-
  # wrapping ("frame-optimizer is supported only on X86").
  #
  # Also NOT included -- these run clean in isolation but break once a real
  # profile makes -reorder-blocks actually move Thumb/ARM blocks (2026-09-16):
  #   -peepholes=all    corrupts pseudo accounting on ARM-mode functions --
  #                     "calculated pseudos 1, set pseudos 0" on
  #                     bolt_bench_interwork, then asserts in
  #                     BinaryBasicBlock::size() (hasInstructions()).
  # -split-functions works since overlay 0022 (R_ARM_THM_JUMP19 in JITLink, Thumb
  # fragment symbols); opt in with BOLT_SPLIT=1.
)
[[ "${BOLT_SPLIT:-0}" == 1 ]] && BOLT_ARGS+=(-split-functions -split-all-cold)

# Prefer rewriting only profiled benches on ARM32 — full-image layout
# still hits trampoline/literal-pool issues outside bolt_bench_*.
if [[ "$ARCH" == "arm32" ]]; then
  FUNCS="${OPTIMIZE_FUNCS:-bolt_bench_hot_loop,bolt_bench_hot_cold,bolt_bench_branch_chain,bolt_bench_memcpy,bolt_bench_interwork,bolt_bench_switch,bolt_bench_spill_ret,bolt_bench_litpool,bolt_bench_indirect_call,bolt_bench_interwork_tail,bolt_bench_regpressure,bolt_bench_hotcold_split,bolt_bench_icf,bolt_bench_shrinkwrap}"
  FUNCS_FILE="$(mktemp)"
  trap 'rm -f "$FUNCS_FILE"' EXIT
  tr ',' '\n' <<<"$FUNCS" | sed '/^$/d' > "$FUNCS_FILE"
  BOLT_ARGS+=(--funcs-file-no-regex="$FUNCS_FILE")
  # Where each rewritten function landed (overlay patch 0013); the Pi pipeline's
  # redirect-bolt-entries.py needs it to branch every original entry to its copy.
  BOLT_ARGS+=(--emit-function-map="$OUT.funcmap")
fi

# BOLT_ALIGN_FUNCTIONS=<n>: align every emitted function at n bytes (relocation mode). With
# n=16384 the rewritten functions keep the original 16 KB spacing -- the control that
# separates "rewritten" from "packed" (BOLT emits functions back to back otherwise).
[[ -n "${BOLT_ALIGN_FUNCTIONS:-}" ]] && BOLT_ARGS+=(--align-functions="$BOLT_ALIGN_FUNCTIONS" --align-functions-max-bytes="$BOLT_ALIGN_FUNCTIONS")
# BOLT_PAD_FUNCS="f1:n,f2:n": pad after the named functions. --align-functions did NOT keep
# the 16 KB spacing (its max-bytes limit blocked the ~11 KB of padding: the functions came
# out back to back), so the spacing control pads explicitly.
[[ -n "${BOLT_PAD_FUNCS:-}" ]] && BOLT_ARGS+=(--pad-funcs="$BOLT_PAD_FUNCS")

# --no-lse-atomics is AArch64's option (QEMU cortex-a53 has no LSE). The ARM
# target never reads it -- its counter path is ldrex/strex unconditionally.
[[ "$ARCH" != arm32 ]] && BOLT_ARGS+=(--no-lse-atomics)

"$TOOLCHAIN/llvm-bolt" "$ELF" "${BOLT_ARGS[@]}" "$@"

python3 "$ROOT/scripts/fix-kernel-elf-paddr.py" "$OUT"
python3 "$ROOT/scripts/fix-kernel-elf-entry.py" "$OUT" --original "$ELF" \
  --readelf "$TOOLCHAIN/llvm-readelf"
python3 "$ROOT/scripts/fix-kernel-elf-sections.py" "$OUT" --original "$ELF" \
  --readelf "$TOOLCHAIN/llvm-readelf"

echo "optimized image: $OUT"
