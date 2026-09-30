#!/usr/bin/env bash
# LEGACY (2026-09-30): RunPod is no longer used -- EU-RO-1 ran out of CPU capacity and both
# network volumes are deleted. Kept for reference only; the current workflow is
# docs/WSL_BUILD.md (local WSL2 + the real Pi).
# Poll for CPU capacity and create the project pod the moment any is free.
# EU-RO-1 (where the network volume lives) runs out of CPU capacity at times.
#
#   MAX_ATTEMPTS=24 INTERVAL=300 scripts/poll-create-pod.sh
#
# Tries the biggest size first. Stops after the first pod is created (prints
# "CREATED <flavor> x<vcpu>" plus create-pod.py's SSH details) or after
# MAX_ATTEMPTS rounds (exit 1). Never creates more than one pod.
set -uo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
MAX_ATTEMPTS="${MAX_ATTEMPTS:-24}"
INTERVAL="${INTERVAL:-300}"
export NETWORK_VOLUME_ID="${NETWORK_VOLUME_ID:-3g114i4sby}"
export MSYS_NO_PATHCONV=1

for attempt in $(seq 1 "$MAX_ATTEMPTS"); do
  for cfg in "cpu3c 8" "cpu5c 8" "cpu3g 8" "cpu3c 4" "cpu5c 4" "cpu3g 4" "cpu3c 2" "cpu5c 2"; do
    set -- $cfg
    if POD_NAME="bolt-lk-$2c" CPU_FLAVOR="$1" VCPU_CANDIDATES="$2" \
        python3 "$ROOT/scripts/create-pod.py" > /tmp/poll-create-pod.log 2>&1; then
      echo "CREATED $1 x$2 (attempt $attempt)"
      tail -8 /tmp/poll-create-pod.log
      exit 0
    fi
  done
  echo "attempt $attempt/$MAX_ATTEMPTS: no capacity ($(date +%H:%M:%S))"
  sleep "$INTERVAL"
done
echo "gave up after $MAX_ATTEMPTS attempts"
exit 1
