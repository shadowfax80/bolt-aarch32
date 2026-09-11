#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BUILD_DIR="${BUILD_DIR:-$ROOT/build}"
OUT="${OUT:-$ROOT/llvm-bolt-toolchain.tar.gz}"

cd "$BUILD_DIR"

FILES=(
  bin/llvm-bolt bin/perf2bolt bin/merge-fdata
  bin/clang bin/clang++ bin/clang-cpp
  bin/ld.lld bin/lld
  bin/llvm-objdump bin/llvm-readelf bin/llvm-objcopy
  bin/llvm-nm bin/llvm-strip bin/llvm-ar bin/llvm-cxxfilt
)

# Host-architecture instrumentation runtime. Present for completeness only — it
# cannot instrument AArch64 targets (see docs/aarch64-bare-metal.md).
for lib in lib/libbolt_rt_instr.a lib/libbolt_rt_hugify.a; do
  [[ -f "$lib" ]] && FILES+=("$lib")
done

missing=0
for f in "${FILES[@]}"; do
  if [[ ! -e "$f" ]]; then
    echo "error: missing $BUILD_DIR/$f — run scripts/build-llvm-bolt.sh first" >&2
    missing=1
  fi
done
[[ $missing -eq 0 ]] || exit 1

tar czhf "$OUT" "${FILES[@]}"
echo "Created $OUT"
