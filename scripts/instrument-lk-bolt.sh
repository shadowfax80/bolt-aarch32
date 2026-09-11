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

# --emit-relocs is set by build-lk-aarch64.sh; without it BOLT cannot move code.
if ! "$TOOLCHAIN/llvm-readelf" --sections "$ELF" | grep -q '\.rela\.text'; then
  echo "error: $ELF has no .rela.text — relink with LDFLAGS=--emit-relocs" >&2
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

"$TOOLCHAIN/llvm-readelf" --sections "$OUT" | grep -E 'bolt\.instr' || true
echo "instrumented image: $OUT"
