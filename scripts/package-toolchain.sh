#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BUILD_DIR="${BUILD_DIR:-$ROOT/build}"
OUT="${OUT:-$ROOT/llvm-bolt-toolchain.tar.gz}"

cd "$BUILD_DIR"
tar czf "$OUT" \
  bin/llvm-bolt bin/clang bin/clang++ bin/clang-cpp \
  bin/ld.lld bin/perf2bolt bin/merge-fdata \
  bin/llvm-objdump bin/llvm-readelf

echo "Created $OUT"
