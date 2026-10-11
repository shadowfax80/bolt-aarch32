#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
LK_PROJECT="${LK_PROJECT:-qemu-virt-arm64-test}"

source "$ROOT/scripts/ensure-toolchain.sh"

"$ROOT/scripts/ensure-lk-source.sh"
"$ROOT/scripts/apply-overlays.sh"

cd "$ROOT/third_party/lk"

# Relocations come from overlay/lk/patches/0001-emit-relocs-for-bolt.patch,
# applied above. engine.mk assigns GLOBAL_LDFLAGS with :=, so exporting
# LDFLAGS here has no effect on the link.

make "$LK_PROJECT" -j"${JOBS:-$(nproc)}"

echo "LK build complete."
