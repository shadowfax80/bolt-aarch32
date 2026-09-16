#!/usr/bin/env bash
# Verify persistent volume layout: sources + built toolchain for one or both
# LLVM bases. Intended for the RunPod workspace at /workspace/bolt-lk-overlay.
# BASES defaults to both; pass BASES=upstream (or BASES=atfe) to check one.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BASES="${BASES:-upstream atfe}"
errors=0

require() {
  if [[ ! -e "$1" ]]; then
    echo "missing: $1" >&2
    errors=$((errors + 1))
  fi
}

require "$ROOT/third_party/lk/makefile"

for b in $BASES; do
  # Each resolve-base.sh default only fills in an unset var, so clear the
  # previous iteration's resolved values first or BASE=atfe would silently
  # keep reusing BASE=upstream's LLVM_DIR/etc.
  unset LLVM_DIR LLVM_COMMIT LLVM_REMOTE PATCH_DIR BUILD_DIR
  BASE="$b"
  source "$ROOT/scripts/resolve-base.sh"
  echo "--- $BASE ($LLVM_DIR) ---"
  require "$LLVM_DIR/bolt/CMakeLists.txt"
  require "$LLVM_DIR/llvm/CMakeLists.txt"
  require "$BUILD_DIR/bin/llvm-bolt"
  require "$BUILD_DIR/bin/clang"
  if [[ -f "$LLVM_DIR/.overlay-source-ok" ]]; then
    echo -n "  llvm-project ($BASE): "
    cat "$LLVM_DIR/.overlay-source-ok"
  fi
done

if [[ -f "$ROOT/third_party/lk/.overlay-source-ok" ]]; then
  echo -n "lk: "
  cat "$ROOT/third_party/lk/.overlay-source-ok"
fi

if [[ "$errors" -gt 0 ]]; then
  echo "workspace incomplete ($errors required paths missing)" >&2
  echo "  BASE=upstream ./scripts/fetch-sources.sh   # or BASE=atfe" >&2
  echo "  BASE=upstream ./scripts/build-llvm-bolt.sh # if build-\$BASE/bin is missing" >&2
  exit 1
fi

echo "workspace OK"
