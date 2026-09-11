#!/usr/bin/env bash
# Cross-build the bare-metal BOLT instrumentation runtime for AArch64.
#
# The runtime that ships with llvm-bolt is built for the host only (our pod
# reports "Building BOLT runtime libraries for X86"), so instrumenting an
# AArch64 image needs its own archive passed via
# --runtime-instrumentation-lib. See docs/aarch64-bare-metal.md.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TOOLCHAIN="${TOOLCHAIN:-$ROOT/build/bin}"
OUT_DIR="${OUT_DIR:-$ROOT/build/bolt-rt-baremetal}"
SRC="$ROOT/overlay/llvm/bolt-rt-baremetal/instr_baremetal.cpp"
LIB="$OUT_DIR/libbolt_rt_baremetal.a"
CPU="${QEMU_CPU:-cortex-a53}"

for tool in clang llvm-ar llvm-nm; do
  if [[ ! -x "$TOOLCHAIN/$tool" ]]; then
    echo "error: $TOOLCHAIN/$tool missing — build the toolchain first" >&2
    exit 1
  fi
done

mkdir -p "$OUT_DIR"

# -mgeneral-regs-only: counter updates land inside interrupt paths where LK has
# not saved FP/SIMD state. -fno-builtin keeps clang from calling into a libc
# that is not there; BOLT links this with its own minimal ORC linker, which
# resolves nothing beyond the instrumented binary itself.
"$TOOLCHAIN/clang" \
  --target=aarch64-none-elf -mcpu="$CPU" \
  -ffreestanding -fno-builtin -fno-exceptions -fno-rtti \
  -fno-stack-protector -fomit-frame-pointer -mgeneral-regs-only \
  -std=c++17 -O2 -Wall -Wextra \
  -c "$SRC" -o "$OUT_DIR/instr_baremetal.o"

rm -f "$LIB"
"$TOOLCHAIN/llvm-ar" rcs "$LIB" "$OUT_DIR/instr_baremetal.o"

# RewriteInstance::linkRuntime() refuses the archive without these two.
for sym in __bolt_instr_start __bolt_instr_fini; do
  if ! "$TOOLCHAIN/llvm-nm" "$LIB" | grep -q " T $sym\$"; then
    echo "error: $LIB does not define $sym" >&2
    exit 1
  fi
done

# BOLT's linker cannot allocate .bss for the runtime.
if "$TOOLCHAIN/llvm-nm" "$LIB" | grep -qE " [bB] "; then
  echo "error: $LIB has .bss symbols, which BOLT's ORC linker cannot place" >&2
  "$TOOLCHAIN/llvm-nm" "$LIB" | grep -E " [bB] " >&2
  exit 1
fi

echo "built $LIB"
