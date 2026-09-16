#!/usr/bin/env bash
# Idempotent llvm-project checkout, pinned to a specific commit. Safe to call
# from retries/watchers. BASE=upstream|atfe selects which LLVM fork/pin;
# see scripts/resolve-base.sh.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
source "$ROOT/scripts/resolve-base.sh"
MARKER="$LLVM_DIR/.overlay-source-ok"
LOCKFILE="$(dirname "$LLVM_DIR")/.overlay-clone.lock"

llvm_tree_ok() {
  [[ -d "$LLVM_DIR/llvm/utils/TableGen" ]] \
    && [[ -f "$LLVM_DIR/llvm/CMakeLists.txt" ]] \
    && [[ -d "$LLVM_DIR/.git" ]]
}

# A marker from a different commit must not short-circuit a requested pin bump.
marker_matches_commit() {
  [[ -f "$MARKER" ]] && grep -qx "commit=$LLVM_COMMIT" "$MARKER"
}

write_marker() {
  local sha
  sha="$(git -C "$LLVM_DIR" rev-parse HEAD)"
  printf 'commit=%s\n' "$sha" > "$MARKER"
  echo "llvm-project ready @ $sha"
}

if marker_matches_commit && llvm_tree_ok; then
  # Fast path — skip all network/git work
  cat "$MARKER"
  exit 0
fi

mkdir -p "$(dirname "$LLVM_DIR")"
exec 9>"$LOCKFILE"
echo "Acquiring llvm-project source lock..."
flock 9

# Re-check after waiting on lock (another process may have finished)
if marker_matches_commit && llvm_tree_ok; then
  cat "$MARKER"
  exit 0
fi

if [[ -d "$LLVM_DIR/.git" ]]; then
  echo "Fetching pinned commit $LLVM_COMMIT into existing checkout..."
  rm -f "$MARKER"
  git -C "$LLVM_DIR" fetch --depth=1 origin "$LLVM_COMMIT"
  git -C "$LLVM_DIR" checkout --detach FETCH_HEAD
  if llvm_tree_ok; then
    write_marker
    exit 0
  fi
  echo "Checkout still incomplete; removing broken tree for one full clone..."
  rm -rf "$LLVM_DIR"
fi

if [[ ! -d "$LLVM_DIR/.git" ]]; then
  if [[ -e "$LLVM_DIR" ]]; then
    echo "Removing incomplete tree at $LLVM_DIR..."
    rm -rf "$LLVM_DIR"
  fi
  echo "Cloning llvm-project and checking out pinned commit $LLVM_COMMIT..."
  git init -q "$LLVM_DIR"
  git -C "$LLVM_DIR" remote add origin "$LLVM_REMOTE"
  git -C "$LLVM_DIR" fetch --depth=1 origin "$LLVM_COMMIT"
  git -C "$LLVM_DIR" checkout --detach FETCH_HEAD
fi

if ! llvm_tree_ok; then
  echo "error: llvm-project tree invalid after checkout" >&2
  exit 1
fi

write_marker
