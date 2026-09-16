#!/usr/bin/env bash
# End-to-end BOLT verification on bare-metal LK (AArch64 or ARM32).
# Only bolt_bench synthetic workloads are instrumented — LK is the host platform.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

ARCH="${ARCH:-aarch64}"
TOOLCHAIN="${TOOLCHAIN:-$ROOT/build-${BASE:-upstream}/bin}"
BENCH_FUNCS="${BENCH_FUNCS:-bolt_bench_hot_loop,bolt_bench_hot_cold,bolt_bench_branch_chain,bolt_bench_memcpy}"
CMDLINE="${BENCH_CMDLINE:-lk.bolt_bench=all}"

case "$ARCH" in
  aarch64|arm64)
    ELF="${ELF:-$ROOT/third_party/lk/build-qemu-virt-arm64-test/lk.elf}"
    QEMU="${QEMU:-qemu-system-aarch64}"
    QEMU_CPU="${QEMU_CPU:-cortex-a53}"
    QEMU_SMP="${QEMU_SMP:-4}"
    BUILD_LK="$ROOT/scripts/build-lk-aarch64.sh"
    INSTR_OUT="$ROOT/build-${BASE:-upstream}/lk.instr.elf"
    COUNTERS="$ROOT/build-${BASE:-upstream}/bolt-counters.bin"
    FDATA="$ROOT/build-${BASE:-upstream}/prof.fdata"
    BOLT_OUT="$ROOT/build-${BASE:-upstream}/lk.bolt.elf"
    SERIAL_PREFIX=lk-bench
    ;;
  arm|arm32|aarch32)
    ARCH=arm32
    ELF="${ELF:-$ROOT/third_party/lk/build-qemu-virt-arm32-test/lk.elf}"
    QEMU="${QEMU:-qemu-system-arm}"
    QEMU_CPU="${QEMU_CPU:-cortex-a15}"
    QEMU_SMP="${QEMU_SMP:-1}"
    BUILD_LK="$ROOT/scripts/build-lk-aarch32.sh"
    INSTR_OUT="$ROOT/build-${BASE:-upstream}/lk.instr.arm32.elf"
    COUNTERS="$ROOT/build-${BASE:-upstream}/bolt-counters-arm32.bin"
    FDATA="$ROOT/build-${BASE:-upstream}/prof-arm32.fdata"
    BOLT_OUT="$ROOT/build-${BASE:-upstream}/lk.bolt.arm32.elf"
    SERIAL_PREFIX=lk-bench-arm32
    ;;
  *)
    echo "error: ARCH must be aarch64 or arm32 (got: $ARCH)" >&2
    exit 1
    ;;
esac

echo "=== build LK (with bolt_bench overlay) ARCH=$ARCH ==="
"$BUILD_LK"

echo "=== sanity: original LK ==="
timeout 8 "$QEMU" -machine virt -cpu "$QEMU_CPU" -m 512 -smp "$QEMU_SMP" \
  -nographic -kernel "$ELF" > "/tmp/orig-${SERIAL_PREFIX}.log" 2>&1 || true
grep -q "entering main console loop" "/tmp/orig-${SERIAL_PREFIX}.log"
echo "original LK booted"

echo "=== runtime ==="
ARCH="$ARCH" "$ROOT/scripts/build-bolt-rt-baremetal.sh"

echo "=== instrument bench functions ==="
export INSTRUMENT_FUNCS="$BENCH_FUNCS"
export ARCH
OUT="$INSTR_OUT" "$ROOT/scripts/instrument-lk-bolt.sh"

echo "=== profile (run bolt_bench via cmdline) ==="
python3 "$ROOT/scripts/dump-bolt-counters.py" \
  --elf "$INSTR_OUT" \
  --out "$COUNTERS" \
  --serial-log "/tmp/${SERIAL_PREFIX}-serial.log" \
  --toolchain "$TOOLCHAIN" \
  --qemu "$QEMU" \
  --cpu "$QEMU_CPU" \
  --smp "$QEMU_SMP" \
  --append "$CMDLINE" \
  --boot-timeout 60 --settle 4
grep -q "bolt_bench:" "/tmp/${SERIAL_PREFIX}-serial.log"
echo "bolt_bench workloads ran"

echo "=== fdata ==="
ELF="$INSTR_OUT" DUMP="$COUNTERS" OUT="$FDATA" \
  python3 "$ROOT/scripts/ram-dump-to-fdata.py" \
    --elf "$INSTR_OUT" \
    --dump "$COUNTERS" \
    --toolchain "$TOOLCHAIN" \
    --funcs "$BENCH_FUNCS" \
    -o "$FDATA"
test -s "$FDATA"
grep -q "bolt_bench_" "$FDATA"
cat "$FDATA"

echo "=== optimize ==="
ARCH="$ARCH" ELF="$ELF" FDATA="$FDATA" OUT="$BOLT_OUT" \
  "$ROOT/scripts/optimize-lk-bolt.sh"

echo "=== boot optimized + rerun workloads ==="
timeout 90 "$QEMU" -machine virt -cpu "$QEMU_CPU" -m 512 -smp "$QEMU_SMP" \
  -display none -serial "file:/tmp/${SERIAL_PREFIX}-bolt-serial.log" \
  -append "$CMDLINE" \
  -kernel "$BOLT_OUT" || true
grep -q "entering main console loop" "/tmp/${SERIAL_PREFIX}-bolt-serial.log"
grep -q "bolt_bench: hot_loop done" "/tmp/${SERIAL_PREFIX}-bolt-serial.log"
grep -q "bolt_bench: memcpy done" "/tmp/${SERIAL_PREFIX}-bolt-serial.log"
echo "BOLT $ARCH workload verification OK"
