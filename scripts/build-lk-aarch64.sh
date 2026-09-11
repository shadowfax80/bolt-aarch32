#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TOOLCHAIN="${TOOLCHAIN:-$ROOT/build/bin}"
LK_PROJECT="${LK_PROJECT:-qemu-virt-arm64-test}"

if [[ ! -x "$TOOLCHAIN/clang" ]]; then
  echo "error: build toolchain first ($TOOLCHAIN/clang missing)" >&2
  exit 1
fi

"$ROOT/scripts/ensure-lk-source.sh"
"$ROOT/scripts/apply-overlays.sh" || true

cd "$ROOT/third_party/lk"

export CC="$TOOLCHAIN/clang --target=aarch64-unknown-elf"
export CXX="$TOOLCHAIN/clang++ --target=aarch64-unknown-elf"
export CPP="$TOOLCHAIN/clang-cpp --target=aarch64-unknown-elf"
export LD="$TOOLCHAIN/ld.lld"
export TOOLCHAIN_PREFIX="$TOOLCHAIN/llvm-"
export CPPFILT="$TOOLCHAIN/llvm-cxxfilt"
export LDFLAGS="${LDFLAGS:--Wl,-q}"

make "$LK_PROJECT"

echo "LK build complete."
