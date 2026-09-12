#!/usr/bin/env bash
# Apply overlay patches to the upstream checkouts in third_party/.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"

apply_patches() {
  local name="$1"
  local dir="$2"
  local patch_dir="$3"

  if [[ ! -d "$dir/.git" ]]; then
    echo "error: $name not checked out at $dir" >&2
    echo "Run: ./scripts/fetch-sources.sh" >&2
    exit 1
  fi

  if ! compgen -G "$patch_dir/*.patch" > /dev/null; then
    echo "no patches for $name"
    return 0
  fi

  echo "Applying patches for $name..."
  for patch in "$patch_dir"/*.patch; do
    if git -C "$dir" apply --check --reverse "$patch" >/dev/null 2>&1; then
      echo "  already applied: $patch"
      continue
    fi
    echo "  $patch"
    git -C "$dir" apply --check "$patch"
    git -C "$dir" apply "$patch"
  done
}

# LK patches first — llvm apply failures must not block bolt_bench overlay.
apply_patches lk "$ROOT/third_party/lk" "$ROOT/overlay/lk/patches"
apply_patches llvm-project "$ROOT/third_party/llvm-project" "$ROOT/overlay/llvm/patches"
echo "Done."
