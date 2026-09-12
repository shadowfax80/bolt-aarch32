#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
CLANG_BINDIR="${CLANG_BINDIR:-${TOOLCHAIN:-$ROOT/build/bin}}"
LK_PROJECT="${LK_PROJECT:-qemu-virt-arm32-test}"

if [[ ! -x "$CLANG_BINDIR/clang" ]]; then
  echo "error: build toolchain first ($CLANG_BINDIR/clang missing)" >&2
  exit 1
fi

"$ROOT/scripts/ensure-lk-source.sh"
"$ROOT/scripts/apply-overlays.sh"

cd "$ROOT/third_party/lk"

export TOOLCHAIN=clang
export CLANG_BINDIR
export LD=ld.lld
export PATH="$CLANG_BINDIR:$PATH"

make "$LK_PROJECT" -j"${JOBS:-$(nproc)}"

echo "LK ARM32 build complete: build-$LK_PROJECT/lk.elf"
