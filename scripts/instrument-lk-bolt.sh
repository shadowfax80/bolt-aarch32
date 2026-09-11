#!/usr/bin/env bash
# Instrument the LK AArch64 image with llvm-bolt using the bare-metal runtime.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TOOLCHAIN="${TOOLCHAIN:-$ROOT/build/bin}"
LK_DIR="${LK_DIR:-$ROOT/third_party/lk}"
ELF="${ELF:-$LK_DIR/build-qemu-virt-arm64-test/lk.elf}"
LIB="${BOLT_RT_LIB:-$ROOT/build/bolt-rt-baremetal/libbolt_rt_baremetal.a}"
OUT="${OUT:-$ROOT/build/lk.instr.elf}"

if [[ ! -f "$ELF" ]]; then
  echo "error: $ELF not found — run scripts/build-lk-aarch64.sh" >&2
  exit 1
fi
if [[ ! -f "$LIB" ]]; then
  echo "error: $LIB not found — run scripts/build-bolt-rt-baremetal.sh" >&2
  exit 1
fi

# Without relocations in the final image BOLT cannot move code. LK only emits
# them with the overlay patch to make/build.mk, because engine.mk assigns
# GLOBAL_LDFLAGS with := and ignores LDFLAGS from the environment.
#
# Read into a variable rather than piping: grep -q exits on the first match,
# which sends SIGPIPE upstream and makes pipefail report the success as failure.
SECTIONS="$("$TOOLCHAIN/llvm-readelf" --sections "$ELF")"
if ! grep -q '\.rela\.text' <<<"$SECTIONS"; then
  echo "error: $ELF has no .rela.text — rebuild with WITH_BOLT_RELOCS=true" >&2
  exit 1
fi

mkdir -p "$(dirname "$OUT")"

# Counters live at a high virtual address. Any store to them before the MMU
# is on takes a fault at reset, so the default is to instrument only lk_main,
# which runs after arch_early_init has enabled the MMU. Override with
# INSTRUMENT_FUNCS=all to instrument everything (and then skip the boot path
# some other way).
FUNCS_FILE=""
if [[ "${INSTRUMENT_FUNCS:-lk_main}" != "all" ]]; then
  FUNCS_FILE="$(mktemp)"
  tr ',' '\n' <<<"${INSTRUMENT_FUNCS:-lk_main}" > "$FUNCS_FILE"
  trap 'rm -f "$FUNCS_FILE"' EXIT
fi

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
  -o "$OUT"
)
if [[ -n "$FUNCS_FILE" ]]; then
  BOLT_ARGS+=(--instrument-funcs-file="$FUNCS_FILE")
fi

"$TOOLCHAIN/llvm-bolt" "$ELF" "${BOLT_ARGS[@]}" "$@"

OUT_SECTIONS="$("$TOOLCHAIN/llvm-readelf" --sections "$OUT")"
grep -E 'bolt\.instr' <<<"$OUT_SECTIONS" || true
echo "instrumented image: $OUT"
python3 "$ROOT/scripts/fix-kernel-elf-paddr.py" "$OUT"
python3 "$ROOT/scripts/fix-kernel-elf-entry.py" "$OUT" --original "$ELF" \
  --readelf "$TOOLCHAIN/llvm-readelf"
HOOK_FUNCS="${INSTRUMENT_FUNCS:-lk_main}"
if [[ "$HOOK_FUNCS" == "all" ]]; then
  HOOK_FUNCS=""
fi
SECTION_FIX=(python3 "$ROOT/scripts/fix-kernel-elf-sections.py" "$OUT" --original "$ELF"
  --readelf "$TOOLCHAIN/llvm-readelf")
if [[ -n "$HOOK_FUNCS" ]]; then
  SECTION_FIX+=(--hook-funcs "$HOOK_FUNCS")
fi
"${SECTION_FIX[@]}"
