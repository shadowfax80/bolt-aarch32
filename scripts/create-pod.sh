#!/usr/bin/env bash
# Create a RunPod CPU pod for toolchain builds.
#
# Defaults encode what actually worked (see docs/PROJECT_PLAN.md):
#   - runpod/base image: plain ubuntu:24.04 ships no sshd, so SSH is refused.
#   - 20 GB container disk: the maximum for CPU pods. The build tree lives on
#     the network volume mounted at /workspace instead.
#   - 8 vCPU in EU-RO-1: 16 vCPU had no capacity at the time of provisioning.
set -euo pipefail

: "${RUNPOD_API_KEY:?Set RUNPOD_API_KEY}"

POD_NAME="${POD_NAME:-llvm-bolt-builder}"
VCPU_COUNT="${VCPU_COUNT:-8}"
CONTAINER_DISK_GB="${CONTAINER_DISK_GB:-20}"
IMAGE="${IMAGE:-runpod/base:1.0.2-ubuntu2404}"
CPU_FLAVOR="${CPU_FLAVOR:-cpu5m}"
DATA_CENTER="${DATA_CENTER:-EU-RO-1}"
NETWORK_VOLUME_ID="${NETWORK_VOLUME_ID:-}"
VOLUME_MOUNT_PATH="${VOLUME_MOUNT_PATH:-/workspace}"
SSH_PUBLIC_KEY="${SSH_PUBLIC_KEY:-}"

if [[ -z "$SSH_PUBLIC_KEY" && -f "${HOME}/.ssh/id_ed25519.pub" ]]; then
  SSH_PUBLIC_KEY="$(cat "${HOME}/.ssh/id_ed25519.pub")"
fi

# A network volume is only attachable from its own data center.
if [[ -z "$NETWORK_VOLUME_ID" ]]; then
  echo "warning: NETWORK_VOLUME_ID unset — 20 GB container disk is too small for an LLVM build" >&2
fi

BODY=$(jq -n \
  --arg name "$POD_NAME" \
  --arg image "$IMAGE" \
  --arg key "$SSH_PUBLIC_KEY" \
  --arg flavor "$CPU_FLAVOR" \
  --arg dc "$DATA_CENTER" \
  --arg vol "$NETWORK_VOLUME_ID" \
  --arg mount "$VOLUME_MOUNT_PATH" \
  --argjson vcpu "$VCPU_COUNT" \
  --argjson disk "$CONTAINER_DISK_GB" \
  '{
    name: $name,
    computeType: "CPU",
    cpuFlavorIds: [$flavor],
    cpuFlavorPriority: "custom",
    vcpuCount: $vcpu,
    containerDiskInGb: $disk,
    imageName: $image,
    dataCenterIds: [$dc],
    ports: ["22/tcp"],
    env: (if $key == "" then {} else { PUBLIC_KEY: $key } end)
  }
  + (if $vol == "" then {} else { networkVolumeId: $vol, volumeMountPath: $mount } end)')

# REST v1 is deprecated in favour of https://api.runpod.io/v2 but is the endpoint
# verified to accept vcpuCount/cpuFlavorIds for CPU pods.
RESP=$(curl -sS -X POST "https://rest.runpod.io/v1/pods" \
  -H "Authorization: Bearer ${RUNPOD_API_KEY}" \
  -H "Content-Type: application/json" \
  -d "$BODY")

echo "$RESP" | jq .
POD_ID=$(echo "$RESP" | jq -r '.id // empty')
if [[ -n "$POD_ID" ]]; then
  echo "$POD_ID" > .runpod-pod-id
  echo "Saved pod id to .runpod-pod-id"
fi
