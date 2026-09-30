#!/usr/bin/env bash
# LEGACY (2026-09-30): RunPod is no longer used -- EU-RO-1 ran out of CPU capacity and both
# network volumes are deleted. Kept for reference only; the current workflow is
# docs/WSL_BUILD.md (local WSL2 + the real Pi).
# One-shot setup of a freshly created Ubuntu 24.04 pod.
#
# Container-disk packages (QEMU, ninja, lld, ccache) are lost on every
# redeploy, while the toolchain, sources and this overlay live on the volume.
# Run this after SSH is up and before any verification:
#
#   ./scripts/pod-ssh.sh 'cd /workspace/bolt-lk-overlay && git pull && ./scripts/bootstrap-pod.sh'
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"

DEBIAN_FRONTEND=noninteractive apt-get update -qq
DEBIAN_FRONTEND=noninteractive apt-get install -y -qq \
  qemu-system-arm ninja-build cmake build-essential ccache lld python3 git \
  libnewlib-arm-none-eabi

"$ROOT/scripts/fetch-sources.sh"
"$ROOT/scripts/verify-workspace.sh"

"$ROOT/build-${BASE:-upstream}/bin/llvm-bolt" --version | head -3
command -v qemu-system-aarch64
command -v qemu-system-arm
echo "pod bootstrap complete"
