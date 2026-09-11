#!/usr/bin/env bash
# Idempotent llvm-project checkout. Safe to call from retries/watchers.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
LLVM_DIR="${LLVM_DIR:-$ROOT/third_party/llvm-project}"
LLVM_BRANCH="${LLVM_BRANCH:-release/23.x}"
LLVM_REMOTE="${LLVM_REMOTE:-https://github.com/llvm/llvm-project.git}"
MARKER="$LLVM_DIR/.overlay-source-ok"
LOCKFILE="$LLVM_DIR/.overlay-clone.lock"

llvm_tree_ok() {
  [[ -d "$LLVM_DIR/llvm/utils/TableGen" ]] \
    && [[ -f "$LLVM_DIR/llvm/CMakeLists.txt" ]] \
    && [[ -d "$LLVM_DIR/.git" ]]
}

# A marker from a different branch must not short-circuit a requested switch.
marker_matches_branch() {
  [[ -f "$MARKER" ]] && grep -qx "branch=$LLVM_BRANCH" "$MARKER"
}

write_marker() {
  local sha
  sha="$(git -C "$LLVM_DIR" rev-parse --short HEAD)"
  printf 'branch=%s\ncommit=%s\n' "$LLVM_BRANCH" "$sha" > "$MARKER"
  echo "llvm-project ready: $LLVM_BRANCH @ $sha"
}

if marker_matches_branch && llvm_tree_ok; then
  # Fast path — skip all network/git work
  cat "$MARKER"
  exit 0
fi

mkdir -p "$(dirname "$LLVM_DIR")"
exec 9>"$LOCKFILE"
echo "Acquiring llvm-project source lock..."
flock 9

# Re-check after waiting on lock (another process may have finished)
if marker_matches_branch && llvm_tree_ok; then
  cat "$MARKER"
  exit 0
fi

if [[ -d "$LLVM_DIR/.git" ]]; then
  echo "Fetching $LLVM_BRANCH into existing checkout (no full re-clone unless necessary)..."
  rm -f "$MARKER"
  # The initial clone may have been --single-branch; widen the refspec first.
  git -C "$LLVM_DIR" remote set-branches --add origin "$LLVM_BRANCH" || true
  git -C "$LLVM_DIR" fetch origin "$LLVM_BRANCH"
  if git -C "$LLVM_DIR" rev-parse --is-shallow-repository 2>/dev/null | grep -q true; then
    echo "Shallow clone incomplete — deepening checkout..."
    git -C "$LLVM_DIR" fetch --unshallow origin "$LLVM_BRANCH" 2>/dev/null \
      || git -C "$LLVM_DIR" fetch origin "$LLVM_BRANCH" --depth=2147483647
  fi
  git -C "$LLVM_DIR" checkout -B "$LLVM_BRANCH" "origin/$LLVM_BRANCH"
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
