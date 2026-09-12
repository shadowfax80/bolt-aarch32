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

add_bolt_bench_to_project() {
  local mk="$1"
  if [[ ! -f "$mk" ]] || grep -q 'app/bolt_bench' "$mk"; then
    return 0
  fi

  # arm64 already lists "app/shell \\"; arm32 often ends with "app/shell" alone.
  if grep -q $'app/shell \\' "$mk"; then
    sed -i '/app\/shell/a\\tapp/bolt_bench \\' "$mk"
  else
    sed -i 's/^\([[:space:]]*app\/shell\)$/\1 \\/' "$mk"
    sed -i '/app\/shell/a\\tapp/bolt_bench' "$mk"
  fi
  echo "added app/bolt_bench to $(basename "$mk")"
}

add_bolt_bench_to_project "$ROOT/third_party/lk/project/qemu-virt-arm64-test.mk"
add_bolt_bench_to_project "$ROOT/third_party/lk/project/qemu-virt-arm32-test.mk"
apply_patches lk "$ROOT/third_party/lk" "$ROOT/overlay/lk/patches"
apply_patches llvm-project "$ROOT/third_party/llvm-project" "$ROOT/overlay/llvm/patches"
echo "Done."
