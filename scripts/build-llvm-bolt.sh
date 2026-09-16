#!/usr/bin/env bash
# BASE=upstream|atfe selects which LLVM fork to build against; each gets its
# own source tree and build directory (see scripts/resolve-base.sh) so both
# can coexist and be rebuilt independently on the same checkout.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

source "$ROOT/scripts/resolve-base.sh"
JOBS="${JOBS:-$(nproc)}"

"$ROOT/scripts/ensure-llvm-source.sh"

if [[ ! -f "$BUILD_DIR/build.ninja" ]]; then
  cmake -G Ninja \
    -S "$LLVM_DIR/llvm" \
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
