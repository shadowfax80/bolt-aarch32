#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

git submodule update --init --recursive

LLVM_BRANCH="${LLVM_BRANCH:-release/19.x}"
if [[ -d third_party/llvm-project/.git ]]; then
  git -C third_party/llvm-project fetch origin "$LLVM_BRANCH" --depth 1 || true
  git -C third_party/llvm-project checkout "$LLVM_BRANCH" || true
fi

echo "Submodules ready."
