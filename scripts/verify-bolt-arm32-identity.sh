#!/usr/bin/env bash
# P1 + P4 progress check on ARM32 LK.
#
# P4 is ARM-mode identity rewrite. Default qemu-virt-arm32-test benches are
# Thumb; they will be discovered and then ignored until P6. To actually
# overwrite bolt_bench_*, rebuild first with BOLT_BENCH_ISA=arm.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TOOLCHAIN="${TOOLCHAIN:-$ROOT/build/bin}"
LK_PROJECT="${LK_PROJECT:-qemu-virt-arm32-test}"
ELF="${ELF:-$ROOT/third_party/lk/build-$LK_PROJECT/lk.elf}"
OUT="${OUT:-/tmp/lk.bolt.arm}"
FUNCS_FILE="${FUNCS_FILE:-/tmp/arm-bolt-bench-funcs.txt}"
LOG="${LOG:-/tmp/bolt-arm32-identity.log}"

BOLT_BENCH_FUNCS="${BOLT_BENCH_FUNCS:-bolt_bench_hot_loop,bolt_bench_hot_cold,bolt_bench_branch_chain,bolt_bench_memcpy}"

if [[ ! -x "$TOOLCHAIN/llvm-bolt" ]]; then
  echo "error: $TOOLCHAIN/llvm-bolt missing — rebuild on the volume" >&2
  exit 1
fi

if [[ "${REBUILD_LK:-0}" == 1 || ! -f "$ELF" ]]; then
  echo "=== build LK ARM32 (BOLT_BENCH_ISA=${BOLT_BENCH_ISA:-default}) ==="
  BOLT_BENCH_ISA="${BOLT_BENCH_ISA:-}" "$ROOT/scripts/build-lk-aarch32.sh"
fi

if [[ ! -f "$ELF" ]]; then
  echo "error: $ELF not found" >&2
  exit 1
fi

echo "=== P1: print-sections (full image) ==="
"$TOOLCHAIN/llvm-bolt" -o /tmp/lk.arm.sections.elf --print-sections \
  "$ELF" \
  > /tmp/bolt-arm32-sections.log 2>&1 || {
  echo "error: print-sections failed (see /tmp/bolt-arm32-sections.log)" >&2
  exit 1
}
grep -q "Target architecture: arm" /tmp/bolt-arm32-sections.log
grep -q "Sections from original binary" /tmp/bolt-arm32-sections.log
grep -q "\.text" /tmp/bolt-arm32-sections.log
grep -qE 'Aborted|UNREACHABLE executed|BOLT-ERROR: Unrecognized machine' /tmp/bolt-arm32-sections.log && {
  echo "error: print-sections aborted (see /tmp/bolt-arm32-sections.log)" >&2
  exit 1
}
echo "P1 print-sections OK"

printf '%s\n' ${BOLT_BENCH_FUNCS//,/ } > "$FUNCS_FILE"

echo "=== P4: identity rewrite (funcs-file) ==="
set +e
"$TOOLCHAIN/llvm-bolt" "$ELF" -o "$OUT" --funcs-file="$FUNCS_FILE" \
  > "$LOG" 2>&1
STATUS=$?
set -e
tail -20 "$LOG"
if [[ "$STATUS" -ne 0 ]]; then
  echo "error: llvm-bolt exited $STATUS" >&2
  exit "$STATUS"
fi

if grep -qE 'BOLT-ERROR|UNREACHABLE|Assertion' "$LOG"; then
  echo "error: llvm-bolt reported a fatal error (see $LOG)" >&2
  exit 1
fi

OVERWRITE="$(grep -E 'out of .* functions were overwritten' "$LOG" | tail -1 || true)"
echo "$OVERWRITE"

if [[ "${REQUIRE_OVERWRITE:-0}" == 1 ]]; then
  if ! grep -qE 'BOLT: [1-9][0-9]* out of .* functions were overwritten' "$LOG"; then
    echo "error: REQUIRE_OVERWRITE=1 but no functions were rewritten" >&2
    echo "hint: BOLT_BENCH_ISA=arm REBUILD_LK=1 $0" >&2
    exit 1
  fi
  echo "P4 overwrite OK"
else
  echo "P4 emit OK (set REQUIRE_OVERWRITE=1 after -marm benches)"
fi

if [[ "${BOOT_REWRITTEN:-1}" == 1 && "${REQUIRE_OVERWRITE:-0}" == 1 ]]; then
  echo "=== QEMU boot rewritten ELF ==="
  QEMU="${QEMU:-qemu-system-arm}"
  timeout 120 "$QEMU" -machine virt -cpu cortex-a15 -m 512 -smp 1 \
    -nographic \
    -append "${BENCH_CMDLINE:-lk.bolt_bench=all}" \
    -kernel "$OUT" > /tmp/bench-arm32-rewritten.log 2>&1 || true
  grep -q "bolt_bench: hot_loop done" /tmp/bench-arm32-rewritten.log
  grep -q "bolt_bench: hot_cold done" /tmp/bench-arm32-rewritten.log
  grep -q "bolt_bench: branch_chain done" /tmp/bench-arm32-rewritten.log
  grep -q "bolt_bench: memcpy done" /tmp/bench-arm32-rewritten.log
  grep -q "entering main console loop" /tmp/bench-arm32-rewritten.log
  echo "P4 rewritten image booted and benches ran"
fi
