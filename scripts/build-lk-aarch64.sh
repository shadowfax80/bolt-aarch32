#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
CLANG_BINDIR="${CLANG_BINDIR:-${TOOLCHAIN:-$ROOT/build/bin}}"
LK_PROJECT="${LK_PROJECT:-qemu-virt-arm64-test}"

if [[ ! -x "$CLANG_BINDIR/clang" ]]; then
  echo "error: build toolchain first ($CLANG_BINDIR/clang missing)" >&2
  exit 1
fi

"$ROOT/scripts/ensure-lk-source.sh"
"$ROOT/scripts/apply-overlays.sh"

cd "$ROOT/third_party/lk"

# LK's clang path uses TOOLCHAIN=clang + CLANG_BINDIR (see engine.mk).
export TOOLCHAIN=clang
export CLANG_BINDIR
export LD=ld.lld
export PATH="$CLANG_BINDIR:$PATH"

# Relocations come from overlay/lk/patches/0001-emit-relocs-for-bolt.patch,
# applied above. engine.mk assigns GLOBAL_LDFLAGS with :=, so exporting
# LDFLAGS here has no effect on the link.

make "$LK_PROJECT" -j"${JOBS:-$(nproc)}"

echo "LK build complete."
