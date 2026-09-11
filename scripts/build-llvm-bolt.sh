#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

LLVM_BRANCH="${LLVM_BRANCH:-release/19.x}"
BUILD_DIR="${BUILD_DIR:-$ROOT/build}"
JOBS="${JOBS:-$(nproc)}"

if [[ ! -d third_party/llvm-project/llvm ]]; then
  echo "Initializing llvm-project submodule..."
  "$ROOT/scripts/init-submodules.sh"
fi

if [[ ! -f "$BUILD_DIR/build.ninja" ]]; then
  cmake -G Ninja \
    -S third_party/llvm-project/llvm \
    -B "$BUILD_DIR" \
    -C "$ROOT/cmake/llvm-bolt.cmake"
fi

ninja -C "$BUILD_DIR" -j"$JOBS" clang llvm-bolt perf2bolt merge-fdata

echo "Build complete: $BUILD_DIR/bin/llvm-bolt"
