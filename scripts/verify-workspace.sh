#!/usr/bin/env bash
# Verify persistent volume layout: upstream sources + built toolchain.
# Intended for the RunPod workspace at /workspace/bolt-lk-overlay.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
errors=0

require() {
  if [[ ! -e "$1" ]]; then
    echo "missing: $1" >&2
    errors=$((errors + 1))
  fi
}

require "$ROOT/third_party/llvm-project/bolt/CMakeLists.txt"
require "$ROOT/third_party/llvm-project/llvm/CMakeLists.txt"
require "$ROOT/third_party/lk/makefile"
require "$ROOT/build/bin/llvm-bolt"
require "$ROOT/build/bin/clang"

if [[ -f "$ROOT/third_party/llvm-project/.overlay-source-ok" ]]; then
  echo -n "llvm-project: "
  cat "$ROOT/third_party/llvm-project/.overlay-source-ok"
fi
if [[ -f "$ROOT/third_party/lk/.overlay-source-ok" ]]; then
  echo -n "lk: "
  cat "$ROOT/third_party/lk/.overlay-source-ok"
fi

if [[ "$errors" -gt 0 ]]; then
  echo "workspace incomplete ($errors required paths missing)" >&2
  echo "  ./scripts/fetch-sources.sh" >&2
  echo "  ./scripts/build-llvm-bolt.sh   # if build/bin is missing" >&2
  exit 1
fi

echo "workspace OK"
