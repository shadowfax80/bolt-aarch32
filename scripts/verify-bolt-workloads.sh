#!/usr/bin/env bash
# Concise BOLT AArch64 verification: bolt_bench workloads → profile → optimize → boot.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

ELF="${ELF:-$ROOT/third_party/lk/build-qemu-virt-arm64-test/lk.elf}"
QEMU="${QEMU:-qemu-system-aarch64}"
TOOLCHAIN="${TOOLCHAIN:-$ROOT/build/bin}"
BENCH_FUNCS="${BENCH_FUNCS:-bolt_bench_hot_loop,bolt_bench_hot_cold,bolt_bench_branch_chain,bolt_bench_memcpy}"
CMDLINE="${BENCH_CMDLINE:-lk.bolt_bench=all}"

echo "=== build LK (with bolt_bench overlay) ==="
"$ROOT/scripts/build-lk-aarch64.sh"

echo "=== sanity: original LK ==="
timeout 8 "$QEMU" -machine virt -cpu cortex-a53 -m 512 -smp 4 \
  -nographic -kernel "$ELF" > /tmp/orig-serial.log 2>&1 || true
grep -q "entering main console loop" /tmp/orig-serial.log
echo "original LK booted"

echo "=== runtime ==="
"$ROOT/scripts/build-bolt-rt-baremetal.sh"

echo "=== instrument bench functions ==="
export INSTRUMENT_FUNCS="$BENCH_FUNCS"
"$ROOT/scripts/instrument-lk-bolt.sh"

echo "=== profile (run bolt_bench via cmdline) ==="
python3 "$ROOT/scripts/dump-bolt-counters.py" \
  --elf "$ROOT/build/lk.instr.elf" \
  --out "$ROOT/build/bolt-counters.bin" \
  --serial-log /tmp/lk-bench-serial.log \
  --toolchain "$TOOLCHAIN" \
  --append "$CMDLINE" \
  --boot-timeout 60 --settle 4
grep -q "bolt_bench:" /tmp/lk-bench-serial.log
echo "bolt_bench workloads ran"

echo "=== fdata ==="
"$ROOT/scripts/ram-dump-to-fdata.sh"
test -s "$ROOT/build/prof.fdata"
cat "$ROOT/build/prof.fdata"

echo "=== optimize ==="
"$ROOT/scripts/optimize-lk-bolt.sh"

echo "=== boot optimized + rerun workloads ==="
timeout 90 "$QEMU" -machine virt -cpu cortex-a53 -m 512 -smp 4 \
  -display none -serial file:/tmp/lk-bolt-bench-serial.log \
  -append "$CMDLINE" \
  -kernel "$ROOT/build/lk.bolt.elf" || true
grep -q "entering main console loop" /tmp/lk-bolt-bench-serial.log
grep -q "bolt_bench: hot_loop done" /tmp/lk-bolt-bench-serial.log
grep -q "bolt_bench: memcpy done" /tmp/lk-bolt-bench-serial.log
echo "BOLT AArch64 workload verification OK"
