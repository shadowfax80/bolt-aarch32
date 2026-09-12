#!/usr/bin/env bash
# Boot LK in QEMU (AArch64 or ARM32 virt targets).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
LK_DIR="${LK_DIR:-$ROOT/third_party/lk}"
LK_PROJECT="${LK_PROJECT:-qemu-virt-arm64-test}"
ELF="${ELF:-$LK_DIR/build-$LK_PROJECT/lk.elf}"

case "$LK_PROJECT" in
  qemu-virt-arm32-test)
    QEMU="${QEMU:-qemu-system-arm}"
    MACHINE="${QEMU_MACHINE:-virt}"
    CPU="${QEMU_CPU:-cortex-a15}"
    MEM="${QEMU_MEM:-512}"
    SMP="${QEMU_SMP:-1}"
    ;;
  *)
    QEMU="${QEMU:-qemu-system-aarch64}"
    MACHINE="${QEMU_MACHINE:-virt}"
    CPU="${QEMU_CPU:-cortex-a53}"
    MEM="${QEMU_MEM:-512}"
    SMP="${QEMU_SMP:-4}"
    ;;
esac

if [[ ! -f "$ELF" ]]; then
  echo "error: $ELF not found — build LK first" >&2
  echo "  LK_PROJECT=$LK_PROJECT $ROOT/scripts/build-lk-aarch64.sh  # or build-lk-aarch32.sh" >&2
  exit 1
fi

exec "$QEMU" -machine "$MACHINE" -cpu "$CPU" -m "$MEM" -smp "$SMP" \
  -nographic -kernel "$ELF" "$@"
