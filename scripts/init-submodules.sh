#!/usr/bin/env bash
# Populate third_party trees idempotently (no submodule init for llvm/lk — they are gitignored).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

"$ROOT/scripts/ensure-llvm-source.sh"
"$ROOT/scripts/ensure-lk-source.sh"

echo "Third-party sources ready."
