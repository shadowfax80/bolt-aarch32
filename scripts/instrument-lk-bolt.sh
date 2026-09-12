#!/usr/bin/env bash
# Instrument bolt_bench synthetic workloads embedded in the LK image.
#
# LK itself is the bare-metal host only — do not instrument kernel or platform
# functions. BOLT targets are the bolt_bench_* entry points from overlay/lk/files/.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TOOLCHAIN="${TOOLCHAIN:-$ROOT/build/bin}"
LK_DIR="${LK_DIR:-$ROOT/third_party/lk}"
ELF="${ELF:-$LK_DIR/build-qemu-virt-arm64-test/lk.elf}"
LIB="${BOLT_RT_LIB:-$ROOT/build/bolt-rt-baremetal/libbolt_rt_baremetal.a}"
OUT="${OUT:-$ROOT/build/lk.instr.elf}"

BOLT_BENCH_FUNCS="${BOLT_BENCH_FUNCS:-bolt_bench_hot_loop,bolt_bench_hot_cold,bolt_bench_branch_chain,bolt_bench_memcpy}"
INSTRUMENT_FUNCS="${INSTRUMENT_FUNCS:-$BOLT_BENCH_FUNCS}"

if [[ ! -f "$ELF" ]]; then
  echo "error: $ELF not found — run scripts/build-lk-aarch64.sh" >&2
  exit 1
fi
if [[ ! -f "$LIB" ]]; then
  echo "error: $LIB not found — run scripts/build-bolt-rt-baremetal.sh" >&2
  exit 1
fi

SECTIONS="$("$TOOLCHAIN/llvm-readelf" --sections "$ELF")"
if ! grep -q '\.rela\.text' <<<"$SECTIONS"; then
  echo "error: $ELF has no .rela.text — rebuild with WITH_BOLT_RELOCS=true" >&2
  exit 1
fi

FUNCS_FILE="$(mktemp)"
trap 'rm -f "$FUNCS_FILE"' EXIT
tr ',' '\n' <<<"$INSTRUMENT_FUNCS" | sed '/^$/d' > "$FUNCS_FILE"
while IFS= read -r func; do
  if [[ "$func" != bolt_bench_* ]]; then
    echo "error: only bolt_bench_* synthetic workloads may be instrumented (got: $func)" >&2
    echo "LK kernel/platform code must stay out of the BOLT profile." >&2
    exit 1
  fi
done < "$FUNCS_FILE"

mkdir -p "$(dirname "$OUT")"

# Static ET_EXEC images have no DT_FINI, so BOLT refuses to instrument them
# unless a watchdog interval is set. The watchdog is a Linux fork path that
# our runtime never calls, so the value is only a key to unlock the rewrite.
BOLT_ARGS=(
  -instrument
  --no-lse-atomics
  --instrument-calls=false
  --instrumentation-sleep-time=1
  --skip-funcs=_start,arm64_elX_to_el1,arm64_enable_mmu,arch_early_init,arm64_early_init_percpu,platform_early_init
  --runtime-instrumentation-lib="$LIB"
  --instrument-funcs-file="$FUNCS_FILE"
  -o "$OUT"
)

"$TOOLCHAIN/llvm-bolt" "$ELF" "${BOLT_ARGS[@]}" "$@"

OUT_SECTIONS="$("$TOOLCHAIN/llvm-readelf" --sections "$OUT")"
grep -E 'bolt\.instr' <<<"$OUT_SECTIONS" || true
echo "instrumented image: $OUT"
python3 "$ROOT/scripts/fix-kernel-elf-paddr.py" "$OUT"
python3 "$ROOT/scripts/fix-kernel-elf-entry.py" "$OUT" --original "$ELF" \
  --readelf "$TOOLCHAIN/llvm-readelf"

python3 "$ROOT/scripts/fix-kernel-elf-sections.py" "$OUT" --original "$ELF" \
  --readelf "$TOOLCHAIN/llvm-readelf" \
  --hook-funcs "$INSTRUMENT_FUNCS"
