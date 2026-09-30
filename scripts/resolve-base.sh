#!/usr/bin/env bash
# Resolve BASE (upstream|atfe) into the LLVM_DIR/LLVM_COMMIT/LLVM_REMOTE/
# PATCH_DIR/BUILD_DIR values every LLVM-touching script needs. Source this,
# don't execute it:
#   source "$(dirname "$0")/resolve-base.sh"
# Explicit env var overrides (e.g. LLVM_COMMIT=... for a one-off pin bump)
# still win -- this only fills in defaults that aren't already set.
#
# upstream = llvm/llvm-project, pinned commit, the primary upstreaming target.
# atfe     = arm/arm-toolchain (Arm Toolchain for Embedded), arm-software
#            branch, pinned to its own commit -- diverged from upstream's
#            pin, not an ancestor of it. See docs/KNOWN_LIMITATIONS.md.
set -euo pipefail

BASE="${BASE:-upstream}"
: "${ROOT:=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"

# Precedence, highest first: a bare LLVM_COMMIT/LLVM_REMOTE (one-off
# session override, e.g. `LLVM_COMMIT=abc123 ./scripts/build-llvm-bolt.sh`)
# > the base-suffixed var from .env (LLVM_COMMIT_UPSTREAM/_ATFE — the
# durable per-base pin) > the hardcoded fallback below.
case "$BASE" in
  upstream)
    : "${LLVM_COMMIT:=${LLVM_COMMIT_UPSTREAM:-069ef0e7cb36ee1fcf3bfdad31533fd79ab85b58}}"
    : "${LLVM_REMOTE:=${LLVM_REMOTE_UPSTREAM:-https://github.com/llvm/llvm-project.git}}"
    ;;
  atfe)
    : "${LLVM_COMMIT:=${LLVM_COMMIT_ATFE:-bcc08884995ff3cbee70749524621803b9bd258a}}"
    : "${LLVM_REMOTE:=${LLVM_REMOTE_ATFE:-https://github.com/arm/arm-toolchain.git}}"
    ;;
  *)
    echo "error: BASE must be upstream or atfe (got: $BASE)" >&2
    return 1 2>/dev/null || exit 1
    ;;
esac

: "${LLVM_DIR:=$ROOT/third_party/llvm-project-$BASE}"
: "${PATCH_DIR:=$ROOT/overlay/llvm/patches/$BASE}"
: "${BUILD_DIR:=$ROOT/build-$BASE}"

export BASE ROOT LLVM_DIR LLVM_COMMIT LLVM_REMOTE PATCH_DIR BUILD_DIR
