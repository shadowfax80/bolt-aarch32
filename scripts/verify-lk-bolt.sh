#!/usr/bin/env bash
# End-to-end Stage 1 check: original LK still boots, then the instrumented
# image boots and at least one BOLT counter is non-zero.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

ELF_ORIG="${ELF_ORIG:-$ROOT/third_party/lk/build-qemu-virt-arm64-test/lk.elf}"
QEMU="${QEMU:-qemu-system-aarch64}"

echo "=== sanity: original LK ==="
timeout 8 "$QEMU" -machine virt -cpu cortex-a53 -m 512 -smp 4 \
  -nographic -kernel "$ELF_ORIG" \
  > /tmp/orig-serial.log 2>&1 || true
if grep -q "entering main console loop" /tmp/orig-serial.log; then
  echo "original LK booted"
else
  echo "error: original LK did not reach the shell" >&2
  tail -20 /tmp/orig-serial.log >&2
  exit 1
fi

echo "=== runtime ==="
"$ROOT/scripts/build-bolt-rt-baremetal.sh"

echo "=== instrument ==="
"$ROOT/scripts/instrument-lk-bolt.sh"

echo "=== boot instrumented ==="
python3 "$ROOT/scripts/dump-bolt-counters.py" \
  --elf "$ROOT/build/lk.instr.elf" \
  --out /tmp/bolt-counters.bin \
  --serial-log /tmp/lk-serial.log \
  --toolchain "$ROOT/build/bin" \
  --boot-timeout 45 --settle 6

echo "=== serial tail ==="
tail -20 /tmp/lk-serial.log || true
