#!/usr/bin/env bash
# Workload/output consistency on LK in QEMU (AArch64 or ARM32): instrument,
# profile, optimize, rerun. Only bolt_bench synthetic workloads are
# instrumented - LK is the host platform.
#
# DIAGNOSTIC ONLY (6a, user decision 2026-10-04): QEMU is a debug aid. The
# counter dump here is not sealed, so the profile is unbound
# (--debug-unbound) and nothing this script prints is a certificate.
# Certification is Pi-only: scripts/pi4/full_image_build.py +
# scripts/pi4/full_image_verify.py against an approved pi4 contract.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

ARCH="${ARCH:-aarch64}"
TOOLCHAIN="${TOOLCHAIN:-$ROOT/build-${BASE:-upstream}/bin}"
BENCH_FUNCS="${BENCH_FUNCS:-bolt_bench_hot_loop,bolt_bench_hot_cold,bolt_bench_branch_chain,bolt_bench_memcpy}"
CMDLINE="${BENCH_CMDLINE:-lk.bolt_bench=all}"
# 6a G1: every intermediate (instrumented image, counters, profile, optimized
# image, serial log, evidence) goes to a fresh directory, so nothing from an
# earlier or concurrent run can be picked up.
mkdir -p "${OUT_DIR:-$ROOT/out/workload-consistency}"
RUN="$(mktemp -d "${OUT_DIR:-$ROOT/out/workload-consistency}/run-XXXXXX")"
RUN="$(cd "$RUN" && pwd)"
echo "run directory: $RUN"

case "$ARCH" in
  aarch64|arm64)
    ELF="${ELF:-$ROOT/third_party/lk/build-qemu-virt-arm64-test/lk.elf}"
    QEMU="${QEMU:-qemu-system-aarch64}"
    QEMU_CPU="${QEMU_CPU:-cortex-a53}"
    QEMU_SMP="${QEMU_SMP:-4}"
    BUILD_LK="$ROOT/scripts/build-lk-aarch64.sh"
    INSTR_OUT="$RUN/lk.instr.elf"
    COUNTERS="$RUN/bolt-counters.bin"
    FDATA="$RUN/prof.fdata"
    BOLT_OUT="$RUN/lk.bolt.elf"
    SERIAL_PREFIX=lk-bench
    ;;
  arm|arm32|aarch32)
    ARCH=arm32
    ELF="${ELF:-$ROOT/third_party/lk/build-qemu-virt-arm32-bolt-test/lk.elf}"
    QEMU="${QEMU:-qemu-system-arm}"
    QEMU_CPU="${QEMU_CPU:-cortex-a15}"
    QEMU_SMP="${QEMU_SMP:-1}"
    BUILD_LK="$ROOT/scripts/build-lk-aarch32.sh"
    INSTR_OUT="$RUN/lk.instr.arm32.elf"
    COUNTERS="$RUN/bolt-counters-arm32.bin"
    FDATA="$RUN/prof-arm32.fdata"
    BOLT_OUT="$RUN/lk.bolt.arm32.elf"
    SERIAL_PREFIX=lk-bench-arm32
    ;;
  *)
    echo "error: ARCH must be aarch64 or arm32 (got: $ARCH)" >&2
    exit 1
    ;;
esac

if [[ "${REBUILD_LK:-1}" == 1 || ! -f "$ELF" ]]; then
  echo "=== build LK (with bolt_bench overlay) ARCH=$ARCH ==="
  "$BUILD_LK"
fi

echo "=== sanity: original LK ==="
python3 "$ROOT/scripts/qemu_workload_gate.py" --diagnostic --elf "$ELF" --qemu "$QEMU" \
  --cpu "$QEMU_CPU" --smp "$QEMU_SMP" --append "$CMDLINE" \
  --out "$RUN/baseline" --timeout 120

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
  --serial-log "$RUN/${SERIAL_PREFIX}-serial.log" \
  --toolchain "$TOOLCHAIN" \
  --qemu "$QEMU" \
  --cpu "$QEMU_CPU" \
  --smp "$QEMU_SMP" \
  --append "$CMDLINE" \
  --boot-timeout 60 --settle 4
python3 "$ROOT/scripts/qemu_workload_gate.py" --check-log "$RUN/${SERIAL_PREFIX}-serial.log"
echo "bolt_bench workloads ran"

echo "=== fdata ==="
ELF="$INSTR_OUT" DUMP="$COUNTERS" OUT="$FDATA" \
  python3 "$ROOT/scripts/ram-dump-to-fdata.py" \
    --elf "$INSTR_OUT" \
    --dump "$COUNTERS" \
    --toolchain "$TOOLCHAIN" \
    --funcs "$BENCH_FUNCS" \
    --debug-unbound \
    -o "$FDATA"
test -s "$FDATA"
grep -q "bolt_bench_" "$FDATA"
cat "$FDATA"

echo "=== optimize ==="
ARCH="$ARCH" ELF="$ELF" FDATA="$FDATA" OUT="$BOLT_OUT" OPTIMIZE_FUNCS="$BENCH_FUNCS" \
  BOLT_DIAGNOSTIC_PROFILE=1 "$ROOT/scripts/optimize-lk-bolt.sh"

echo "=== boot optimized + rerun workloads ==="
if [[ "$ARCH" == arm32 ]]; then
  python3 "$ROOT/scripts/redirect-bolt-entries.py" "$BOLT_OUT" --original "$ELF" \
    --map "$BOLT_OUT.funcmap" --func "$BENCH_FUNCS" --toolchain "$TOOLCHAIN" \
    --report "$BOLT_OUT.redirect.json"
fi
python3 "$ROOT/scripts/qemu_workload_gate.py" --diagnostic --elf "$ELF" --candidate "$BOLT_OUT" --qemu "$QEMU" \
  --cpu "$QEMU_CPU" --smp "$QEMU_SMP" --append "$CMDLINE" \
  --out "$RUN/optimized" --timeout 120
echo "DIAGNOSTIC ONLY: BOLT $ARCH output consistency in QEMU with an unbound profile;"
echo "not a certificate. Certification is Pi-only (scripts/pi4/full_image_verify.py)."
echo "run directory: $RUN"
