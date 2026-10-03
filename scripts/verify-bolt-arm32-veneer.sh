#!/usr/bin/env bash
# P5: independently checked A32 far-call execution, with durable QEMU witnesses.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
source "$ROOT/scripts/resolve-base.sh"
TOOLCHAIN="${TOOLCHAIN:-$BUILD_DIR/bin}"
exec python3 "$ROOT/scripts/verify_far_execution.py" \
  --toolchain "$TOOLCHAIN" \
  --out "${OUT_DIR:-$ROOT/out/arm32-veneer}" \
  --qemu "${QEMU_ARM:-qemu-arm}"
