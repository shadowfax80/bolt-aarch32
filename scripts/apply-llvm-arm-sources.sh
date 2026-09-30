#!/usr/bin/env bash
# Copy overlay/llvm/src/ tree into third_party/llvm-project and rebuild llvm-bolt.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SRC="${SRC:-$ROOT/overlay/llvm/src}"
LLVM="${LLVM:-$ROOT/third_party/llvm-project}"
BUILD="${BUILD:-$ROOT/build}"

if [[ ! -d "$SRC/bolt" ]]; then
  echo "error: $SRC/bolt not found — ARM backend sources not checked in yet" >&2
  exit 1
fi

"$ROOT/scripts/ensure-llvm-source.sh"
"$ROOT/scripts/apply-overlays.sh"

echo "Installing ARM backend sources from overlay/llvm/src/..."
cp -a "$SRC/bolt/." "$LLVM/bolt/"
if [[ -d "$SRC/llvm/test/tools/llvm-bolt" ]]; then
  mkdir -p "$LLVM/llvm/test/tools/llvm-bolt"
  cp -a "$SRC/llvm/test/tools/llvm-bolt/." "$LLVM/llvm/test/tools/llvm-bolt/"
fi

echo "Rebuilding llvm-bolt..."
ninja -C "$BUILD" -j"${JOBS:-$(nproc)}" bolt

echo "ARM backend sources applied and llvm-bolt rebuilt."
