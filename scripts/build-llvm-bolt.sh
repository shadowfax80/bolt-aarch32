#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

export LLVM_BRANCH="${LLVM_BRANCH:-release/23.x}"
BUILD_DIR="${BUILD_DIR:-$ROOT/build}"
JOBS="${JOBS:-$(nproc)}"

"$ROOT/scripts/ensure-llvm-source.sh"

if [[ ! -f "$BUILD_DIR/build.ninja" ]]; then
  cmake -G Ninja \
    -S third_party/llvm-project/llvm \
    -B "$BUILD_DIR" \
    -C "$ROOT/cmake/llvm-bolt.cmake"
fi

# lld and the llvm-* binutils are required by build-lk-aarch64.sh and
# package-toolchain.sh; they are not pulled in by the clang/llvm-bolt targets.
ninja -C "$BUILD_DIR" -j"$JOBS" \
  clang lld \
  llvm-bolt perf2bolt merge-fdata bolt-runtime \
  llvm-objdump llvm-readelf llvm-objcopy llvm-nm llvm-strip llvm-ar

echo "Build complete: $BUILD_DIR/bin/llvm-bolt"
