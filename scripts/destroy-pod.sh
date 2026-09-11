#!/usr/bin/env bash
set -euo pipefail

: "${RUNPOD_API_KEY:?Set RUNPOD_API_KEY}"

POD_ID="${1:-}"
if [[ -z "$POD_ID" && -f .runpod-pod-id ]]; then
  POD_ID="$(cat .runpod-pod-id)"
fi

if [[ -z "$POD_ID" ]]; then
  echo "usage: $0 <pod-id>" >&2
  exit 1
fi

curl -sS -X DELETE "https://rest.runpod.io/v1/pods/${POD_ID}" \
  -H "Authorization: Bearer ${RUNPOD_API_KEY}" | jq .

rm -f .runpod-pod-id
echo "Pod $POD_ID deleted."
