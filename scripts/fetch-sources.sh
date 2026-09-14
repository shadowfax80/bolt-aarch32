#!/usr/bin/env bash
# Populate third_party/ idempotently.
#
# These are plain clones, not git submodules: third_party/ is gitignored so the
# overlay repo stays free of upstream history. Pinning lives in LLVM_BRANCH /
# LK_COMMIT and in each tree's .overlay-source-ok marker.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

"$ROOT/scripts/ensure-llvm-source.sh"
"$ROOT/scripts/ensure-lk-source.sh"

echo "Third-party sources ready."
