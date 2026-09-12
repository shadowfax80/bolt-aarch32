#!/usr/bin/env bash
# Apply overlay patches to the upstream checkouts in third_party/.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"

install_overlay_files() {
  local dir="$1"
  local files_dir="$2"
  if [[ -d "$files_dir" ]]; then
    echo "Installing overlay files from $files_dir..."
    cp -a "$files_dir/." "$dir/"
  fi
}

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
    if ! git -C "$dir" apply --check "$patch" 2>/dev/null; then
      echo "  warning: patch check failed, skipping: $patch" >&2
      continue
    fi
    git -C "$dir" apply "$patch"
  done
}

# LK files + patches first — llvm apply failures must not block bolt_bench.
install_overlay_files "$ROOT/third_party/lk" "$ROOT/overlay/lk/files"
LK_PROJECT_MK="$ROOT/third_party/lk/project/qemu-virt-arm64-test.mk"
if [[ -f "$LK_PROJECT_MK" ]] && ! grep -q 'app/bolt_bench' "$LK_PROJECT_MK"; then
  sed -i '/app\/shell/a\\tapp/bolt_bench \\' "$LK_PROJECT_MK"
  echo "added app/bolt_bench to qemu-virt-arm64-test.mk"
fi
apply_patches lk "$ROOT/third_party/lk" "$ROOT/overlay/lk/patches"
apply_patches llvm-project "$ROOT/third_party/llvm-project" "$ROOT/overlay/llvm/patches"
echo "Done."
