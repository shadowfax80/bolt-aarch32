#!/usr/bin/env bash
# Resolve the pod's current SSH endpoint and connect.
#
# RunPod reassigns the public IP and port on every deploy, and a stale pair
# fails as "Connection refused" or "banner exchange" rather than anything that
# points at the real cause. Always resolve, never hardcode.
#
# Any arguments are passed to ssh, so this doubles as a remote runner:
#   ./scripts/pod-ssh.sh 'cd /workspace/bolt-lk-overlay && git pull'
set -euo pipefail

: "${RUNPOD_API_KEY:?Set RUNPOD_API_KEY (RunPod console -> Settings -> API Keys)}"

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
POD_ID="${POD_ID:-$(cat "$ROOT/.runpod-pod-id" 2>/dev/null || true)}"

if [[ -z "$POD_ID" ]]; then
  echo "error: no pod id — set POD_ID or run scripts/create-pod.sh" >&2
  exit 1
fi

POD="$(curl -sS -H "Authorization: Bearer ${RUNPOD_API_KEY}" \
  "https://api.runpod.io/v2/pods/${POD_ID}")"

STATUS="$(jq -r '.status // "UNKNOWN"' <<<"$POD")"
if [[ "$STATUS" != "RUNNING" ]]; then
  echo "error: pod $POD_ID is $STATUS" >&2
  exit 1
fi

if [[ "$(jq -r '.mounts.network[0].volumeId // empty' <<<"$POD")" == "" ]]; then
  echo "warning: pod $POD_ID has no network volume — /workspace will be empty" >&2
fi

HOST="$(jq -r '.ssh.direct.host // empty' <<<"$POD")"
PORT="$(jq -r '.ssh.direct.port // empty' <<<"$POD")"

if [[ -z "$HOST" || -z "$PORT" ]]; then
  echo "no direct SSH yet; falling back to the proxy" >&2
  exec ssh -o StrictHostKeyChecking=accept-new \
    "$(jq -r '.ssh.proxy.username' <<<"$POD")@ssh.runpod.io" "$@"
fi

exec ssh -o StrictHostKeyChecking=accept-new -o ConnectTimeout=20 \
  "root@${HOST}" -p "${PORT}" "$@"
