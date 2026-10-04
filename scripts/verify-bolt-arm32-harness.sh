#!/usr/bin/env bash
# P0 gate: ARM32 LK + QEMU + bolt_bench workloads (no rewrite required).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

LK_PROJECT="${LK_PROJECT:-qemu-virt-arm32-bolt-test}"
ELF="${ELF:-$ROOT/third_party/lk/build-$LK_PROJECT/lk.elf}"
QEMU="${QEMU:-qemu-system-arm}"
MACHINE="${QEMU_MACHINE:-virt}"
CPU="${QEMU_CPU:-cortex-a15}"
MEM="${QEMU_MEM:-512}"
SMP="${QEMU_SMP:-1}"
CMDLINE="${BENCH_CMDLINE:-lk.bolt_bench=all}"

# Never rebuild by default: build-lk-aarch32.sh re-applies overlays (not on a dirty tree).
if [[ "${REBUILD_LK:-0}" == 1 || ! -f "$ELF" ]]; then
  echo "=== build LK ARM32 (with bolt_bench overlay) ==="
  "$ROOT/scripts/build-lk-aarch32.sh"
fi

echo "=== complete original workload (DIAGNOSTIC: QEMU is a debug aid; no certificate) ==="
python3 "$ROOT/scripts/qemu_workload_gate.py" --diagnostic --elf "$ELF" --qemu "$QEMU" \
  --machine "$MACHINE" --cpu "$CPU" --memory "$MEM" --smp "$SMP" \
  --append "$CMDLINE" --out "${OUT_DIR:-$ROOT/out/arm32-harness}" --timeout 120
