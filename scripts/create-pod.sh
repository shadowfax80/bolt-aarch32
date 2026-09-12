#!/usr/bin/env bash
# Create a RunPod CPU pod with the project's network volume attached.
#
# Every default here encodes something that has already cost a rebuild:
#
#   - A network volume can only be attached when the pod is created. RunPod
#     rejects a PATCH that adds a mount to a mountless pod and treats volumeId
#     as immutable, so a pod created without NETWORK_VOLUME_ID can never reach
#     /workspace and has to be thrown away. This script refuses to create one.
#   - The image must be runpod/base (plain ubuntu:24.04 ships no sshd) and it
#     must be the 24.04 tag: the toolchain on the volume was linked against
#     glibc 2.39 and will not start on the 20.04 images, which fail with
#     "GLIBC_2.32 not found". The console's "runpod-ubuntu" template defaults
#     to 20.04, so do not rely on template defaults.
#   - 20 GB container disk is the CPU-pod maximum. The build tree lives on the
#     volume, not the container.
#   - Larger vCPU shapes routinely have no capacity ("not enough free vcpu on
#     the host machine"), so smaller ones are tried in turn.
#
# SSH keys are best added once under RunPod -> Settings -> SSH Public Keys;
# account keys are injected into every new pod. SSH_PUBLIC_KEY below is a
# fallback for a pod that must authorize a specific key.
set -euo pipefail

: "${RUNPOD_API_KEY:?Set RUNPOD_API_KEY (RunPod console -> Settings -> API Keys)}"

ROOT="$(cd "$(dirname "$0")/.." && pwd)"

POD_NAME="${POD_NAME:-llvm-bolt-builder}"
NETWORK_VOLUME_ID="${NETWORK_VOLUME_ID:-j1d9e6wq5l}"
VOLUME_MOUNT_PATH="${VOLUME_MOUNT_PATH:-/workspace}"
IMAGE="${IMAGE:-runpod/base:1.0.2-ubuntu2404}"
CPU_FLAVOR="${CPU_FLAVOR:-cpu3c}"
DATA_CENTER="${DATA_CENTER:-EU-RO-1}"
CONTAINER_DISK_GB="${CONTAINER_DISK_GB:-20}"
VCPU_CANDIDATES="${VCPU_CANDIDATES:-2 4}"
SSH_PUBLIC_KEY="${SSH_PUBLIC_KEY:-}"

if [[ -z "$NETWORK_VOLUME_ID" ]]; then
  echo "error: NETWORK_VOLUME_ID is empty — a pod without it cannot be fixed later" >&2
  exit 1
fi

if [[ -z "$SSH_PUBLIC_KEY" && -f "${HOME}/.ssh/id_ed25519.pub" ]]; then
  SSH_PUBLIC_KEY="$(cat "${HOME}/.ssh/id_ed25519.pub")"
fi

# The volume is only attachable from its own data center.
VOLUME_DC="$(curl -sS -H "Authorization: Bearer ${RUNPOD_API_KEY}" \
  "https://api.runpod.io/v2/networkvolumes/${NETWORK_VOLUME_ID}" |
  jq -r '.dataCenter // empty')"
if [[ -n "$VOLUME_DC" && "$VOLUME_DC" != "$DATA_CENTER" ]]; then
  echo "note: volume $NETWORK_VOLUME_ID lives in $VOLUME_DC, using that instead of $DATA_CENTER"
  DATA_CENTER="$VOLUME_DC"
fi

create() {
  local vcpu="$1"
  jq -n \
    --arg name "$POD_NAME" \
    --arg image "$IMAGE" \
    --arg key "$SSH_PUBLIC_KEY" \
    --arg flavor "$CPU_FLAVOR" \
    --arg dc "$DATA_CENTER" \
    --arg vol "$NETWORK_VOLUME_ID" \
    --arg mount "$VOLUME_MOUNT_PATH" \
    --argjson vcpu "$vcpu" \
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
      networkVolumeId: $vol,
      volumeMountPath: $mount,
      env: (if $key == "" then {} else { PUBLIC_KEY: $key } end)
    }' |
    curl -sS -X POST "https://rest.runpod.io/v1/pods" \
      -H "Authorization: Bearer ${RUNPOD_API_KEY}" \
      -H "Content-Type: application/json" \
      -d @-
}

POD_ID=""
for vcpu in $VCPU_CANDIDATES; do
  echo "requesting $CPU_FLAVOR with ${vcpu} vCPU in $DATA_CENTER..."
  RESP="$(create "$vcpu")"
  POD_ID="$(jq -r '.id // empty' <<<"$RESP")"
  if [[ -n "$POD_ID" ]]; then
    echo "created pod $POD_ID (${vcpu} vCPU)"
    break
  fi
  echo "  declined: $(jq -r '.detail // .error // .' <<<"$RESP")"
done

if [[ -z "$POD_ID" ]]; then
  echo "error: no capacity for any of: $VCPU_CANDIDATES" >&2
  exit 1
fi

echo "$POD_ID" > "$ROOT/.runpod-pod-id"

# CPU pods are created through the v1 API but readable through v2.
for _ in $(seq 60); do
  POD="$(curl -sS -H "Authorization: Bearer ${RUNPOD_API_KEY}" \
    "https://api.runpod.io/v2/pods/${POD_ID}")"
  if [[ "$(jq -r '.status // empty' <<<"$POD")" == "RUNNING" &&
        -n "$(jq -r '.ssh.direct.port // empty' <<<"$POD")" ]]; then
    MOUNT_VOL="$(jq -r '.mounts.network[0].volumeId // empty' <<<"$POD")"
    MOUNT_PATH="$(jq -r '.mounts.network[0].path // empty' <<<"$POD")"
    if [[ "$MOUNT_VOL" != "$NETWORK_VOLUME_ID" ]]; then
      echo "error: pod $POD_ID has volume '$MOUNT_VOL', expected '$NETWORK_VOLUME_ID'" >&2
      echo "error: delete this pod and recreate — volume cannot be attached later" >&2
      exit 1
    fi
    echo "mount: $MOUNT_VOL at $MOUNT_PATH"
    jq -r '"ssh: " + .ssh.direct.command' <<<"$POD"
    exit 0
  fi
  sleep 5
done

echo "pod $POD_ID created but not ready yet — check with scripts/pod-ssh.sh" >&2
