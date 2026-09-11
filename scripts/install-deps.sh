#!/usr/bin/env bash
# Install build dependencies on Ubuntu 24.04 (RunPod pod or local).
set -euo pipefail

export DEBIAN_FRONTEND=noninteractive

apt-get update
apt-get install -y \
  build-essential cmake ninja-build python3 python3-venv git ccache \
  zlib1g-dev libxml2-dev libedit-dev libcurl4-openssl-dev \
  lld clang curl ca-certificates \
  jq \
  qemu-system-aarch64 qemu-system-arm gdb-multiarch

echo "Dependencies installed."
