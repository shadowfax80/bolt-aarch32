#!/usr/bin/env bash
# Apply overlay patches to upstream submodules.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"

apply_patches() {
  local name="$1"
  local dir="$2"
  local patch_dir="$3"

  if [[ ! -d "$dir/.git" ]]; then
    echo "error: submodule $name not initialized at $dir" >&2
    echo "Run: git submodule update --init --recursive" >&2
    exit 1
  fi

  if ! compgen -G "$patch_dir/*.patch" > /dev/null; then
    echo "no patches for $name"
    return 0
  fi

  echo "Applying patches for $name..."
  for patch in "$patch_dir"/*.patch; do
    echo "  $patch"
    git -C "$dir" apply --check "$patch"
    git -C "$dir" apply "$patch"
  done
}

apply_patches llvm-project "$ROOT/third_party/llvm-project" "$ROOT/overlay/llvm/patches"
apply_patches lk "$ROOT/third_party/lk" "$ROOT/overlay/lk/patches"
echo "Done."
