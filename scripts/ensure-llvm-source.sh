#!/usr/bin/env bash
# Idempotent llvm-project checkout. Safe to call from retries/watchers.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
LLVM_DIR="${LLVM_DIR:-$ROOT/third_party/llvm-project}"
LLVM_BRANCH="${LLVM_BRANCH:-release/19.x}"
LLVM_REMOTE="${LLVM_REMOTE:-https://github.com/llvm/llvm-project.git}"
MARKER="$LLVM_DIR/.overlay-source-ok"
LOCKFILE="$LLVM_DIR/.overlay-clone.lock"

llvm_tree_ok() {
  [[ -d "$LLVM_DIR/llvm/utils/TableGen" ]] \
    && [[ -f "$LLVM_DIR/llvm/CMakeLists.txt" ]] \
    && [[ -d "$LLVM_DIR/.git" ]]
}

write_marker() {
  local sha
  sha="$(git -C "$LLVM_DIR" rev-parse --short HEAD)"
  printf 'branch=%s\ncommit=%s\n' "$LLVM_BRANCH" "$sha" > "$MARKER"
  echo "llvm-project ready: $LLVM_BRANCH @ $sha"
}

if [[ -f "$MARKER" ]] && llvm_tree_ok; then
  # Fast path — skip all network/git work
  cat "$MARKER"
  exit 0
fi

mkdir -p "$(dirname "$LLVM_DIR")"
exec 9>"$LOCKFILE"
echo "Acquiring llvm-project source lock..."
flock 9

# Re-check after waiting on lock (another process may have finished)
if [[ -f "$MARKER" ]] && llvm_tree_ok; then
  cat "$MARKER"
  exit 0
fi

if [[ -d "$LLVM_DIR/.git" ]]; then
  echo "Repairing existing llvm-project checkout (no full re-clone unless necessary)..."
  git -C "$LLVM_DIR" fetch origin "$LLVM_BRANCH" --tags
  git -C "$LLVM_DIR" checkout "$LLVM_BRANCH"
  if git -C "$LLVM_DIR" rev-parse --is-shallow-repository 2>/dev/null | grep -q true; then
    echo "Shallow clone incomplete — deepening checkout..."
    git -C "$LLVM_DIR" fetch --unshallow origin "$LLVM_BRANCH" 2>/dev/null \
      || git -C "$LLVM_DIR" fetch origin "$LLVM_BRANCH" --depth=2147483647
  fi
  git -C "$LLVM_DIR" checkout "$LLVM_BRANCH"
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
  echo "Cloning llvm-project ($LLVM_BRANCH) — one-time full clone..."
  git clone --branch "$LLVM_BRANCH" --single-branch "$LLVM_REMOTE" "$LLVM_DIR"
fi

if ! llvm_tree_ok; then
  echo "error: llvm-project tree invalid after clone" >&2
  exit 1
fi

write_marker
