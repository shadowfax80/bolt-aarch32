#!/usr/bin/env bash
# Idempotent LK checkout, pinned to a specific commit (for later phases).
#
# LK's master has no release process, so tracking it directly would let an
# untested upstream commit land in the build with no warning. Pin to the
# commit that has been verified through the P0-P5 milestones (see
# docs/RESUME.md) instead, and bump LK_COMMIT deliberately — with
# re-verification — rather than letting this float.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
LK_DIR="${LK_DIR:-$ROOT/third_party/lk}"
LK_COMMIT="${LK_COMMIT:-79d2f56096fa32365846ceaba8b4a9d1c6b75cf0}"
LK_REMOTE="${LK_REMOTE:-https://github.com/littlekernel/lk.git}"
MARKER="$LK_DIR/.overlay-source-ok"
LOCKFILE="$(dirname "$LK_DIR")/.lk-clone.lock"

lk_tree_ok() {
  [[ -d "$LK_DIR/.git" ]] && [[ -f "$LK_DIR/makefile" || -f "$LK_DIR/Makefile" ]]
}

# A marker from a different commit must not short-circuit a requested pin bump.
marker_matches_commit() {
  [[ -f "$MARKER" ]] && grep -qx "commit=$LK_COMMIT" "$MARKER"
}

write_marker() {
  local sha
  sha="$(git -C "$LK_DIR" rev-parse HEAD)"
  printf 'commit=%s\n' "$sha" > "$MARKER"
  echo "lk ready @ $sha"
}

if marker_matches_commit && lk_tree_ok; then
  # Fast path — skip all network/git work
  cat "$MARKER"
  exit 0
fi

mkdir -p "$(dirname "$LK_DIR")"
exec 9>"$LOCKFILE"
echo "Acquiring lk source lock..."
flock 9

# Re-check after waiting on lock (another process may have finished)
if marker_matches_commit && lk_tree_ok; then
  cat "$MARKER"
  exit 0
fi

if [[ -d "$LK_DIR/.git" ]]; then
  echo "Fetching pinned commit $LK_COMMIT into existing checkout..."
  rm -f "$MARKER"
  git -C "$LK_DIR" fetch origin "$LK_COMMIT"
  git -C "$LK_DIR" checkout --detach FETCH_HEAD
  if lk_tree_ok; then
    write_marker
    exit 0
  fi
  echo "Checkout still incomplete; removing broken tree for one full clone..."
  rm -rf "$LK_DIR"
fi

if [[ ! -d "$LK_DIR/.git" ]]; then
  if [[ -e "$LK_DIR" ]]; then
    echo "Removing incomplete tree at $LK_DIR..."
    rm -rf "$LK_DIR"
  fi
  echo "Cloning lk and checking out pinned commit $LK_COMMIT..."
  git init -q "$LK_DIR"
  git -C "$LK_DIR" remote add origin "$LK_REMOTE"
  git -C "$LK_DIR" fetch --depth=1 origin "$LK_COMMIT"
  git -C "$LK_DIR" checkout --detach FETCH_HEAD
fi

if ! lk_tree_ok; then
  echo "error: lk tree invalid after checkout" >&2
  exit 1
fi

write_marker
