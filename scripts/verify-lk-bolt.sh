#!/usr/bin/env bash
# End-to-end bare-metal BOLT check on LK: instrument, profile, optimize, boot.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

ELF_ORIG="${ELF_ORIG:-$ROOT/third_party/lk/build-qemu-virt-arm64-test/lk.elf}"
QEMU="${QEMU:-qemu-system-aarch64}"
TOOLCHAIN="${TOOLCHAIN:-$ROOT/build/bin}"

echo "=== sanity: original LK ==="
timeout 8 "$QEMU" -machine virt -cpu cortex-a53 -m 512 -smp 4 \
  -nographic -kernel "$ELF_ORIG" \
  > /tmp/orig-serial.log 2>&1 || true
grep -q "entering main console loop" /tmp/orig-serial.log
echo "original LK booted"

echo "=== runtime ==="
"$ROOT/scripts/build-bolt-rt-baremetal.sh"

echo "=== instrument ==="
"$ROOT/scripts/instrument-lk-bolt.sh"

echo "=== profile dump ==="
python3 "$ROOT/scripts/dump-bolt-counters.py" \
  --elf "$ROOT/build/lk.instr.elf" \
  --out "$ROOT/build/bolt-counters.bin" \
  --serial-log /tmp/lk-serial.log \
  --toolchain "$TOOLCHAIN" \
  --boot-timeout 45 --settle 6

echo "=== fdata ==="
"$ROOT/scripts/ram-dump-to-fdata.sh"
test -s "$ROOT/build/prof.fdata"

echo "=== optimize ==="
"$ROOT/scripts/optimize-lk-bolt.sh"

echo "=== boot optimized ==="
timeout 35 "$QEMU" -machine virt -cpu cortex-a53 -m 512 -smp 4 \
  -display none -serial file:/tmp/lk-bolt-serial.log \
  -kernel "$ROOT/build/lk.bolt.elf" || true
grep -q "entering main console loop" /tmp/lk-bolt-serial.log
echo "optimized LK booted"
echo "BOLT pipeline OK"
