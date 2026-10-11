#!/usr/bin/env bash
# Source this script to ensure the toolchain is built and set up in the environment.
#   source "$(dirname "$0")/ensure-toolchain.sh"

: "${ROOT:=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
CLANG_BINDIR="${CLANG_BINDIR:-${TOOLCHAIN:-$ROOT/build-${BASE:-upstream}/bin}}"

if [[ ! -x "$CLANG_BINDIR/clang" ]]; then
  echo "error: build toolchain first ($CLANG_BINDIR/clang missing)" >&2
  # Use return for when the script is sourced, exit as fallback
  return 1 2>/dev/null || exit 1
fi

export TOOLCHAIN=clang
export CLANG_BINDIR
export LD=ld.lld
export PATH="$CLANG_BINDIR:$PATH"
