#!/usr/bin/env bash
# Run every QEMU verification gate (ARM32, BASE=atfe) inside the WSL copy and summarize.
# QEMU is a debugging/regression gate here, never the source of a reported number.
#
#   wsl -d Ubuntu -- bash <repo>/scripts/verify-all-wsl.sh        (after wsl-setup.sh sync)
#
# Each gate's full output goes to ~/verify-logs/<gate>.log.
set -uo pipefail
cd "$HOME/bolt-aarch32"
export BASE=atfe
LOGS="$HOME/verify-logs"
mkdir -p "$LOGS"

# The gates build and boot the QEMU project, not the rpi4 one.
./scripts/build-lk-aarch32.sh > "$LOGS/build-qemu-lk.log" 2>&1 \
  || { echo "FAIL build-lk-aarch32 (qemu-virt-arm32-test), see $LOGS/build-qemu-lk.log"; exit 1; }

declare -a RESULTS=()
FAILED=0
run() { # name, command...
  local name="$1"; shift
  local t0=$SECONDS
  if timeout 1800 "$@" > "$LOGS/$name.log" 2>&1; then
    RESULTS+=("PASS  $name  ($((SECONDS - t0)) s)")
  else
    local status=$?
    FAILED=1
    RESULTS+=("FAIL  $name  ($((SECONDS - t0)) s, exit $status)  -> $LOGS/$name.log")
  fi
}

run harness    ./scripts/verify-bolt-arm32-harness.sh
run milestones ./scripts/verify-bolt-arm32-milestones.sh
run identity   ./scripts/verify-bolt-arm32-identity.sh
run veneer     ./scripts/verify-bolt-arm32-veneer.sh
run workloads  env ARCH=arm32 ./scripts/verify-bolt-workloads.sh

echo "=== QEMU gates (BASE=atfe, ARCH=arm32)"
printf '%s\n' "${RESULTS[@]}"
exit "$FAILED"
