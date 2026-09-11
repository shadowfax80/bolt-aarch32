#!/usr/bin/env bash
# Boot LK qemu-virt-arm64-test in QEMU on the pod.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
LK_DIR="${LK_DIR:-$ROOT/third_party/lk}"
ELF="${ELF:-$LK_DIR/build-qemu-virt-arm64-test/lk.elf}"

QEMU="${QEMU:-qemu-system-aarch64}"
MACHINE="${QEMU_MACHINE:-virt}"
CPU="${QEMU_CPU:-cortex-a53}"
MEM="${QEMU_MEM:-512}"
SMP="${QEMU_SMP:-4}"

if [[ ! -f "$ELF" ]]; then
  echo "error: $ELF not found — build LK first" >&2
  echo "  cd $LK_DIR && make qemu-virt-arm64-test TOOLCHAIN=clang CLANG_BINDIR=$ROOT/build/bin -j\$(nproc)" >&2
  exit 1
fi

exec "$QEMU" -machine "$MACHINE" -cpu "$CPU" -m "$MEM" -smp "$SMP" \
  -nographic -kernel "$ELF" "$@"
