#!/usr/bin/env bash
# Stop (if running) and delete a pod. The network volume is untouched.
set -euo pipefail

: "${RUNPOD_API_KEY:?Set RUNPOD_API_KEY}"

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
POD_ID="${1:-}"
if [[ -z "$POD_ID" && -f "$ROOT/.runpod-pod-id" ]]; then
  POD_ID="$(cat "$ROOT/.runpod-pod-id")"
fi

if [[ -z "$POD_ID" ]]; then
  echo "usage: $0 [pod-id]" >&2
  exit 1
fi

NETWORK_VOLUME_ID="${NETWORK_VOLUME_ID:-j1d9e6wq5l}"

STATUS="$(curl -sS -H "Authorization: Bearer ${RUNPOD_API_KEY}" \
  "https://api.runpod.io/v2/pods/${POD_ID}" | jq -r '.status // empty')"
if [[ "$STATUS" == "RUNNING" ]]; then
  echo "stopping pod $POD_ID..."
  curl -sS -X POST "https://api.runpod.io/v2/pods/${POD_ID}/action" \
    -H "Authorization: Bearer ${RUNPOD_API_KEY}" \
    -H "Content-Type: application/json" \
    -d '{"action":"stop"}' >/dev/null
fi

curl -sS -X DELETE "https://rest.runpod.io/v1/pods/${POD_ID}" \
  -H "Authorization: Bearer ${RUNPOD_API_KEY}" | jq .

rm -f "$ROOT/.runpod-pod-id"
echo "Pod $POD_ID deleted. Recreate with: ./scripts/create-pod.sh (volume $NETWORK_VOLUME_ID)"
