#!/usr/bin/env bash
# Scoped identity rewrite with selected-entry execution and output consistency.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TOOLCHAIN="${TOOLCHAIN:-$ROOT/build-${BASE:-upstream}/bin}"
LK_PROJECT="${LK_PROJECT:-qemu-virt-arm32-test}"
ELF="${ELF:-$ROOT/third_party/lk/build-$LK_PROJECT/lk.elf}"
BOLT_BENCH_FUNCS="${BOLT_BENCH_FUNCS:-bolt_bench_hot_loop,bolt_bench_hot_cold,bolt_bench_branch_chain,bolt_bench_memcpy}"
if [[ "${BOOT_REWRITTEN:-1}" != 1 || "${BENCH_CMDLINE:-lk.bolt_bench=all}" != lk.bolt_bench=all ]]; then
  echo "error: identity execution gate requires live boot and the complete workload" >&2
  exit 1
fi
if [[ "${REBUILD_LK:-0}" == 1 || ! -f "$ELF" ]]; then
  BOLT_BENCH_ISA="${BOLT_BENCH_ISA:-}" "$ROOT/scripts/build-lk-aarch32.sh"
fi
python3 "$ROOT/scripts/qemu_rewrite_build.py" --elf "$ELF" --toolchain "$TOOLCHAIN" \
  --funcs "$BOLT_BENCH_FUNCS" --qemu "${QEMU:-qemu-system-arm}" \
  --out "${OUT_DIR:-$ROOT/out/arm32-identity}" --timeout 120
