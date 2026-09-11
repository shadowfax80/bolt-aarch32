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

# --no-lse-atomics: QEMU's cortex-a53 has no LSE, so counter updates must use
# the ldaxr/stlxr helper instead of stadd.
# --instrument-calls=false: leaves indirect-call stubs out of the image, which
# the minimal runtime does not profile anyway.
"$TOOLCHAIN/llvm-bolt" "$ELF" \
  -instrument \
  --no-lse-atomics \
  --instrument-calls=false \
  --runtime-instrumentation-lib="$LIB" \
  -o "$OUT" \
  "$@"

OUT_SECTIONS="$("$TOOLCHAIN/llvm-readelf" --sections "$OUT")"
grep -E 'bolt\.instr' <<<"$OUT_SECTIONS" || true
echo "instrumented image: $OUT"
