#!/usr/bin/env bash
# Export the ARM backend commit series from the volume llvm-project checkout
# into overlay/llvm/patches/$BASE/ as `git format-patch` files.
#
# The backend lives as real commits on the `bolt-arm-backend` branch, on top
# of the pinned $LLVM_COMMIT; scripts/apply-overlays.sh replays them with
# `git am`. Commit on the volume first, then run this. Uncommitted changes
# are refused rather than silently dropped.
#
# BASE=upstream|atfe selects which tree/patch-dir pair; see
# scripts/resolve-base.sh.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
source "$ROOT/scripts/resolve-base.sh"
LLVM="${LLVM:-$LLVM_DIR}"
DEST="${DEST:-$PATCH_DIR}"
BRANCH="${BRANCH:-bolt-arm-backend}"

if ! git -C "$LLVM" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  echo "error: $LLVM is not a git checkout" >&2
  exit 1
fi
if [[ -n "$(git -C "$LLVM" status --porcelain --untracked-files=no)" ]]; then
  echo "error: $LLVM has uncommitted changes; commit them first" >&2
  exit 1
fi

count="$(git -C "$LLVM" rev-list --count "$LLVM_COMMIT..$BRANCH")"
if [[ "$count" -eq 0 ]]; then
  echo "error: $BRANCH has no commits on top of $LLVM_COMMIT" >&2
  exit 1
fi

mkdir -p "$DEST"
rm -f "$DEST"/*.patch
git -C "$LLVM" format-patch -q --no-signature --zero-commit \
  -o "$DEST" "$LLVM_COMMIT..$BRANCH"
ls "$DEST"/*.patch
echo "exported $count commits from $LLVM ($BRANCH) to $DEST"
