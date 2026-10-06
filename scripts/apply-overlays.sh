#!/usr/bin/env bash
# Apply overlay patches to the checkouts in third_party/. BASE=upstream|atfe
# selects which LLVM fork's patch set applies; see scripts/resolve-base.sh.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
source "$ROOT/scripts/resolve-base.sh"
case "${OVERLAY_TARGET:-all}" in
  all|lk) ;;
  *) echo "error: OVERLAY_TARGET must be all or lk" >&2; exit 1 ;;
esac

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
  # Tracks applied patches by filename instead of relying solely on a
  # reverse-apply content check: once two sequential patches touch adjacent
  # context in the same file (e.g. lk's rpi4 platform + UART-baud patches),
  # checking patch N's reverse-apply in isolation fails because patch N+1's
  # already-applied text sits right where N's hunk expects its own
  # boundary — a real conflict was never involved, just stale adjacent
  # context. The stamp file sidesteps that; the reverse-check remains only
  # as a one-time fallback for patches applied before this file existed.
  local stamp="$dir/.applied-overlay-patches"

  if ! git -C "$dir" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    echo "error: $name not checked out at $dir" >&2
    echo "Run: ./scripts/fetch-sources.sh" >&2
    exit 1
  fi

  if ! compgen -G "$patch_dir/*.patch" > /dev/null; then
    echo "no patches for $name"
    return 0
  fi

  echo "Applying patches for $name..."
  touch "$stamp"
  for patch in "$patch_dir"/*.patch; do
    local base
    base="$(basename "$patch")"
    if grep -qxF "$base" "$stamp"; then
      echo "  already applied: $patch"
      continue
    fi
    if git -C "$dir" apply --check "$patch" 2>/dev/null; then
      echo "  $patch"
      git -C "$dir" apply "$patch"
      echo "$base" >> "$stamp"
      continue
    fi
    if git -C "$dir" apply --check --reverse "$patch" >/dev/null 2>&1; then
      echo "  already applied: $patch"
      echo "$base" >> "$stamp"
      continue
    fi
    echo "error: $patch does not apply to $dir" >&2
    exit 1
  done
}

# The LLVM patches are a git format-patch series. Apply it with `git am` onto
# a branch at the pinned commit, so the checkout carries real commits.
# Re-runs skip patches whose subject is already on the branch.
apply_series() {
  local name="$1" dir="$2" patch_dir="$3" base="$4" branch="$5"
  if ! compgen -G "$patch_dir/*.patch" > /dev/null; then
    echo "no patches for $name"
    return 0
  fi
  if [[ -n "$(git -C "$dir" status --porcelain --untracked-files=no)" ]]; then
    echo "error: $dir has uncommitted changes; commit or stash them first" >&2
    exit 1
  fi
  if [[ "$(git -C "$dir" branch --show-current)" != "$branch" ]]; then
    git -C "$dir" checkout -q -B "$branch" "$base"
  fi
  local applied
  applied="$(git -C "$dir" log --format=%s "$base..HEAD")"
  echo "Applying patch series for $name onto $branch..."
  for patch in "$patch_dir"/*.patch; do
    local subject
    subject="$(git mailinfo -b /dev/null /dev/null < "$patch" | sed -n 's/^Subject: //p')"
    if grep -qxF -- "$subject" <<<"$applied"; then
      echo "  already applied: $subject"
      continue
    fi
    echo "  $subject"
    if ! GIT_COMMITTER_NAME="${GIT_COMMITTER_NAME:-bolt-aarch32 overlay}" \
        GIT_COMMITTER_EMAIL="${GIT_COMMITTER_EMAIL:-overlay@localhost}" \
        git -C "$dir" am -q --keep-non-patch --no-keep-cr "$patch"; then
      git -C "$dir" am --abort || true
      echo "error: $patch does not apply to $dir" >&2
      exit 1
    fi
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
  if grep -qE '[[:space:]]app/shell \\$' "$mk"; then
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
if [[ "${OVERLAY_TARGET:-all}" == lk ]]; then
  echo "LK overlay complete (LLVM source untouched)."
  exit 0
fi
first_patch="$(compgen -G "$PATCH_DIR/*.patch" | head -1 || true)"
if [[ -n "$first_patch" ]] && head -1 "$first_patch" | grep -q '^From [0-9a-f]\{40\} '; then
  apply_series "llvm-project ($BASE)" "$LLVM_DIR" "$PATCH_DIR" "$LLVM_COMMIT" "${LLVM_BRANCH:-bolt-arm-backend}"
else
  # Legacy file-slice patches (BASE=atfe until it gets its own series).
  apply_patches "llvm-project ($BASE)" "$LLVM_DIR" "$PATCH_DIR"
fi
echo "Done."
