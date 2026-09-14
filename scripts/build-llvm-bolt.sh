#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

export LLVM_COMMIT="${LLVM_COMMIT:-069ef0e7cb36ee1fcf3bfdad31533fd79ab85b58}"
BUILD_DIR="${BUILD_DIR:-$ROOT/build}"
JOBS="${JOBS:-$(nproc)}"

"$ROOT/scripts/ensure-llvm-source.sh"

if [[ ! -f "$BUILD_DIR/build.ninja" ]]; then
  cmake -G Ninja \
    -S third_party/llvm-project/llvm \
    -B "$BUILD_DIR" \
    -C "$ROOT/cmake/llvm-bolt.cmake"
fi

# `bolt` is the umbrella target: llvm-bolt, merge-fdata and the perf2bolt
# symlink. There is no `perf2bolt` or `bolt-runtime` target — the runtime is
# `bolt_rt`. lld and the llvm-* binutils are needed by build-lk-aarch64.sh and
# package-toolchain.sh and are not pulled in by clang or bolt.
ninja -C "$BUILD_DIR" -j"$JOBS" \
  clang lld \
  bolt bolt_rt \
  llvm-objdump llvm-readelf llvm-objcopy llvm-nm llvm-strip llvm-ar llvm-cxxfilt

echo "Build complete: $BUILD_DIR/bin/llvm-bolt"
