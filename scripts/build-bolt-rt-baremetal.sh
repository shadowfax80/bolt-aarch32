#!/usr/bin/env bash
# Cross-build the bare-metal BOLT instrumentation runtime (AArch64 or ARM32).
#
# The runtime that ships with llvm-bolt is built for the host only (our pod
# reports "Building BOLT runtime libraries for X86"), so instrumenting a
# guest image needs its own archive passed via --runtime-instrumentation-lib.
# See docs/aarch64-bare-metal.md / docs/aarch32-bolt.md P9.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TOOLCHAIN="${TOOLCHAIN:-$ROOT/build/bin}"
SRC="$ROOT/overlay/llvm/bolt-rt-baremetal/instr_baremetal.cpp"
ARCH="${ARCH:-aarch64}"

case "$ARCH" in
  aarch64|arm64)
    OUT_DIR="${OUT_DIR:-$ROOT/build/bolt-rt-baremetal}"
    TARGET="${TARGET:-aarch64-none-elf}"
    CPU="${QEMU_CPU:-cortex-a53}"
    EXTRA_FLAGS=()
    ;;
  arm|arm32|aarch32)
    OUT_DIR="${OUT_DIR:-$ROOT/build/bolt-rt-baremetal-arm}"
    TARGET="${TARGET:-arm-none-eabi}"
    CPU="${QEMU_CPU:-cortex-a15}"
    # ARM-state entry stubs (e_entry). Do not compile as Thumb.
    EXTRA_FLAGS=(-marm)
    ;;
  *)
    echo "error: ARCH must be aarch64 or arm32 (got: $ARCH)" >&2
    exit 1
    ;;
esac

LIB="$OUT_DIR/libbolt_rt_baremetal.a"

for tool in clang llvm-ar llvm-nm; do
  if [[ ! -x "$TOOLCHAIN/$tool" ]]; then
    echo "error: $TOOLCHAIN/$tool missing — build the toolchain first" >&2
    exit 1
  fi
done

mkdir -p "$OUT_DIR"

# -mgeneral-regs-only (AArch64): counter updates can land where FP/SIMD is not
# saved. ARM32 clang rejects that flag; -marm entry stubs are enough for LK.
CLANG_COMMON=(
  --target="$TARGET" -mcpu="$CPU"
  "${EXTRA_FLAGS[@]}"
  -ffreestanding -fno-builtin -fno-exceptions -fno-rtti
  -fno-stack-protector -fomit-frame-pointer
  -std=c++17 -O2 -Wall -Wextra
)
if [[ "$TARGET" == aarch64-none-elf ]]; then
  CLANG_COMMON+=(-mgeneral-regs-only)
fi

"$TOOLCHAIN/clang" \
  "${CLANG_COMMON[@]}" \
  -c "$SRC" -o "$OUT_DIR/instr_baremetal.o"

rm -f "$LIB"
"$TOOLCHAIN/llvm-ar" rcs "$LIB" "$OUT_DIR/instr_baremetal.o"

# Read the symbol table once: grep -q exits on the first match, which sends
# SIGPIPE upstream and makes pipefail report the success as a failure.
SYMS="$("$TOOLCHAIN/llvm-nm" "$LIB")"

# RewriteInstance::linkRuntime() refuses the archive without these two.
for sym in __bolt_instr_start __bolt_instr_fini; do
  if ! grep -q " T $sym\$" <<<"$SYMS"; then
    echo "error: $LIB does not define $sym" >&2
    exit 1
  fi
done

# BOLT's linker cannot allocate .bss for the runtime.
if grep -qE " [bB] " <<<"$SYMS"; then
  echo "error: $LIB has .bss symbols, which BOLT's ORC linker cannot place" >&2
  grep -E " [bB] " <<<"$SYMS" >&2
  exit 1
fi

echo "built $LIB ($ARCH / $TARGET / $CPU)"
