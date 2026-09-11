#!/usr/bin/env bash
# Idempotent LK checkout (for later phases).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
LK_DIR="${LK_DIR:-$ROOT/third_party/lk}"
LK_BRANCH="${LK_BRANCH:-master}"
LK_REMOTE="${LK_REMOTE:-https://github.com/littlekernel/lk.git}"
MARKER="$LK_DIR/.overlay-source-ok"
LOCKFILE="$(dirname "$LK_DIR")/.lk-clone.lock"

lk_tree_ok() {
  [[ -d "$LK_DIR/.git" ]] && [[ -f "$LK_DIR/makefile" || -f "$LK_DIR/Makefile" ]]
}

write_marker() {
  local sha
  sha="$(git -C "$LK_DIR" rev-parse --short HEAD)"
  printf 'branch=%s\ncommit=%s\n' "$LK_BRANCH" "$sha" > "$MARKER"
  echo "lk ready: $LK_BRANCH @ $sha"
}

if [[ -f "$MARKER" ]] && lk_tree_ok; then
  cat "$MARKER"
  exit 0
fi

mkdir -p "$(dirname "$LK_DIR")"
exec 9>"$LOCKFILE"
flock 9

if [[ -f "$MARKER" ]] && lk_tree_ok; then
  cat "$MARKER"
  exit 0
fi

if [[ -d "$LK_DIR/.git" ]]; then
  git -C "$LK_DIR" fetch origin "$LK_BRANCH"
  git -C "$LK_DIR" checkout "$LK_BRANCH"
  if lk_tree_ok; then
    write_marker
    exit 0
  fi
  rm -rf "$LK_DIR"
fi

git clone --branch "$LK_BRANCH" --single-branch "$LK_REMOTE" "$LK_DIR"
write_marker
