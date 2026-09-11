#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

LLVM_BRANCH="${LLVM_BRANCH:-release/19.x}"
BUILD_DIR="${BUILD_DIR:-$ROOT/build}"
JOBS="${JOBS:-$(nproc)}"

"$ROOT/scripts/ensure-llvm-source.sh"

if [[ ! -f "$BUILD_DIR/build.ninja" ]]; then
  cmake -G Ninja \
    -S third_party/llvm-project/llvm \
    -B "$BUILD_DIR" \
    -C "$ROOT/cmake/llvm-bolt.cmake"
fi

ninja -C "$BUILD_DIR" -j"$JOBS" clang llvm-bolt perf2bolt merge-fdata

echo "Build complete: $BUILD_DIR/bin/llvm-bolt"
