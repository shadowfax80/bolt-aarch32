#!/usr/bin/env bash
# P0 gate: ARM32 LK + QEMU + bolt_bench workloads (no BOLT backend yet).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

LK_PROJECT="${LK_PROJECT:-qemu-virt-arm32-test}"
ELF="${ELF:-$ROOT/third_party/lk/build-$LK_PROJECT/lk.elf}"
QEMU="${QEMU:-qemu-system-arm}"
MACHINE="${QEMU_MACHINE:-virt}"
CPU="${QEMU_CPU:-cortex-a15}"
MEM="${QEMU_MEM:-512}"
SMP="${QEMU_SMP:-1}"
CMDLINE="${BENCH_CMDLINE:-lk.bolt_bench=all}"

echo "=== build LK ARM32 (with bolt_bench overlay) ==="
"$ROOT/scripts/build-lk-aarch32.sh"

echo "=== sanity: original LK ==="
timeout 15 "$QEMU" -machine "$MACHINE" -cpu "$CPU" -m "$MEM" -smp "$SMP" \
  -nographic -kernel "$ELF" > /tmp/orig-arm32-serial.log 2>&1 || true
grep -q "entering main console loop" /tmp/orig-arm32-serial.log
echo "original LK ARM32 booted"

echo "=== bolt_bench via cmdline ==="
timeout 120 "$QEMU" -machine "$MACHINE" -cpu "$CPU" -m "$MEM" -smp "$SMP" \
  -display none -serial file:/tmp/bench-arm32-serial.log \
  -append "$CMDLINE" \
  -kernel "$ELF" || true
grep -q "bolt_bench: running all from cmdline" /tmp/bench-arm32-serial.log
grep -q "bolt_bench: hot_loop done" /tmp/bench-arm32-serial.log
grep -q "bolt_bench: hot_cold done" /tmp/bench-arm32-serial.log
grep -q "bolt_bench: branch_chain done" /tmp/bench-arm32-serial.log
grep -q "bolt_bench: memcpy done" /tmp/bench-arm32-serial.log
echo "P0 ARM32 harness verification OK"
