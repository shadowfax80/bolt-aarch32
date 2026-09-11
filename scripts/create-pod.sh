#!/usr/bin/env bash
# Create a RunPod CPU pod via v1 REST API (supports vcpuCount / cpuFlavorIds).
set -euo pipefail

: "${RUNPOD_API_KEY:?Set RUNPOD_API_KEY}"

POD_NAME="${POD_NAME:-llvm-bolt-builder}"
VCPU_COUNT="${VCPU_COUNT:-16}"
CONTAINER_DISK_GB="${CONTAINER_DISK_GB:-150}"
IMAGE="${IMAGE:-ubuntu:24.04}"
SSH_PUBLIC_KEY="${SSH_PUBLIC_KEY:-}"

if [[ -z "$SSH_PUBLIC_KEY" && -f "${HOME}/.ssh/id_ed25519.pub" ]]; then
  SSH_PUBLIC_KEY="$(cat "${HOME}/.ssh/id_ed25519.pub")"
fi

BODY=$(jq -n \
  --arg name "$POD_NAME" \
  --arg image "$IMAGE" \
  --arg key "$SSH_PUBLIC_KEY" \
  --argjson vcpu "$VCPU_COUNT" \
  --argjson disk "$CONTAINER_DISK_GB" \
  '{
    name: $name,
    computeType: "CPU",
    cpuFlavorIds: ["cpu5m"],
    cpuFlavorPriority: "custom",
    vcpuCount: $vcpu,
    containerDiskInGb: $disk,
    imageName: $image,
    ports: ["22/tcp"],
    env: (if $key == "" then {} else { PUBLIC_KEY: $key } end)
  }')

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
