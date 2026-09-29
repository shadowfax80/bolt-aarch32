#!/usr/bin/env bash
# Cross-build a minimal bare-metal LLVM profile (PGO instrumentation)
# runtime for ARM32.
#
# ATFE's own upstream base already supports this: compiler-rt's profile
# library has a real COMPILER_RT_PROFILE_BAREMETAL build mode (see
# compiler-rt/lib/profile/CMakeLists.txt) that excludes everything needing
# a filesystem, a runtime-init hook, or malloc (InstrProfilingFile.c,
# InstrProfilingRuntime.cpp, InstrProfilingUtil.c, InstrProfilingValue.c,
# GCDAProfiling.c) -- exactly LK's situation. What's left still exposes
# __llvm_profile_get_size_for_buffer()/__llvm_profile_write_buffer(),
# which serialize a complete, valid raw instrprof file into a caller-owned
# buffer -- no filesystem needed, and the existing bolt_dump UART command
# (Step 4) can read that buffer out exactly like any other memory range.
#
# This script builds those files directly with clang (not through
# compiler-rt's own CMake, to avoid needing a full baremetal ARM sysroot
# build) against the newlib headers apt provides (libnewlib-arm-none-eabi
# package) for string.h/stdint.h/etc -- LK's own libc headers pull in
# lk/compiler.h and other LK-internal assumptions this standalone compile
# doesn't have set up, so newlib's freestanding-friendly headers are used
# instead. clang's own resource-dir headers (stddef.h, stdarg.h, ...)
# still apply on top since -nostdinc is deliberately not used.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
source "$ROOT/scripts/resolve-base.sh"
TOOLCHAIN="${TOOLCHAIN:-$ROOT/build-$BASE/bin}"
PROFILE_SRC_DIR="$LLVM_DIR/compiler-rt/lib/profile"
NEWLIB_INC="${NEWLIB_INC:-/usr/include/newlib}"

OUT_DIR="${OUT_DIR:-$ROOT/build-$BASE/pgo-rt-baremetal-arm}"
LIB="$OUT_DIR/libpgo_rt_baremetal.a"

for tool in clang llvm-ar; do
  if [[ ! -x "$TOOLCHAIN/$tool" ]]; then
    echo "error: $TOOLCHAIN/$tool missing — build the toolchain first" >&2
    exit 1
  fi
done
if [[ ! -d "$PROFILE_SRC_DIR" ]]; then
  echo "error: $PROFILE_SRC_DIR not found — run scripts/ensure-llvm-source.sh" >&2
  exit 1
fi
if [[ ! -f "$NEWLIB_INC/string.h" ]]; then
  echo "error: $NEWLIB_INC/string.h missing — apt-get install libnewlib-arm-none-eabi" >&2
  exit 1
fi

# The COMPILER_RT_PROFILE_BAREMETAL=ON set from compiler-rt/lib/profile/CMakeLists.txt:
# the baseline PROFILE_SOURCES list, with GCDAProfiling.c/InstrProfilingFile.c/
# InstrProfilingRuntime.cpp/InstrProfilingUtil.c/InstrProfilingValue.c left out
# (those only get added when NOT baremetal). The PlatformXXX.c files for
# other OSes compile down to nothing here (each guards itself on its own
# platform macro) but are included for parity with the real CMake list.
PROFILE_SOURCES=(
  InstrProfiling.c
  InstrProfilingInternal.c
  InstrProfilingBuffer.c
  InstrProfilingMerge.c
  InstrProfilingMergeFile.c
  InstrProfilingNameVar.c
  InstrProfilingVersionVar.c
  InstrProfilingWriter.c
  InstrProfilingPlatformAIX.c
  InstrProfilingPlatformDarwin.c
  InstrProfilingPlatformFuchsia.c
  InstrProfilingPlatformLinux.c
  InstrProfilingPlatformOther.c
  InstrProfilingPlatformWindows.c
  InstrProfilingPlatformGPU.c
)

mkdir -p "$OUT_DIR"
rm -f "$LIB"

OBJS=()
for src in "${PROFILE_SOURCES[@]}"; do
  obj="$OUT_DIR/${src%.c}.o"
  "$TOOLCHAIN/clang" \
    --target=arm-none-eabi -mcpu=cortex-a15 -marm \
    -ffreestanding -fno-builtin -fno-stack-protector -fomit-frame-pointer \
    -DCOMPILER_RT_PROFILE_BAREMETAL=1 -O2 \
    -isystem "$NEWLIB_INC" \
    -I"$PROFILE_SRC_DIR" -I"$PROFILE_SRC_DIR/../../include" \
    -c "$PROFILE_SRC_DIR/$src" -o "$obj"
  OBJS+=("$obj")
done

"$TOOLCHAIN/llvm-ar" rcs "$LIB" "${OBJS[@]}"

SYMS="$("$TOOLCHAIN/llvm-nm" "$LIB")"
for sym in __llvm_profile_get_size_for_buffer __llvm_profile_write_buffer; do
  if ! grep -q " T $sym\$" <<<"$SYMS"; then
    echo "error: $LIB does not define $sym" >&2
    exit 1
  fi
done

echo "built $LIB"
