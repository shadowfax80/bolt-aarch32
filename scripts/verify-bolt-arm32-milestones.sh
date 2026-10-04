#!/usr/bin/env bash
# Verify AArch32 BOLT milestones P0 through P4 on the volume.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TOOLCHAIN="${TOOLCHAIN:-$ROOT/build-${BASE:-upstream}/bin}"
LK_PROJECT="${LK_PROJECT:-qemu-virt-arm32-test}"
ELF="${ELF:-$ROOT/third_party/lk/build-$LK_PROJECT/lk.elf}"
OUT="${OUT:-/tmp/lk.bolt.arm}"
FUNCS_FILE="${FUNCS_FILE:-/tmp/arm-bolt-bench-funcs.txt}"
QEMU="${QEMU:-qemu-system-arm}"
CMDLINE="${BENCH_CMDLINE:-lk.bolt_bench=all}"

BOLT_BENCH_FUNCS="${BOLT_BENCH_FUNCS:-bolt_bench_hot_loop,bolt_bench_hot_cold,bolt_bench_branch_chain,bolt_bench_memcpy}"

pass() { echo "PASS: $*"; }
fail() { echo "FAIL: $*" >&2; exit 1; }

[[ -x "$TOOLCHAIN/llvm-bolt" ]] || fail "llvm-bolt missing"
[[ -f "$ELF" ]] || fail "$ELF missing - run BOLT_BENCH_ISA=arm ./scripts/build-lk-aarch32.sh"

printf '%s\n' ${BOLT_BENCH_FUNCS//,/ } > "$FUNCS_FILE"

echo "=== P0: original ELF boots + bolt_bench all ==="
python3 "$ROOT/scripts/qemu_workload_gate.py" --elf "$ELF" --qemu "$QEMU" \
  --append "$CMDLINE" --out "${OUT_DIR:-$ROOT/out/arm32-milestones}/p0" --timeout 120
 echo "P0 complete workload and independent sink arithmetic (no rewrite certificate)"

echo "=== P1: print-sections (full image) ==="
"$TOOLCHAIN/llvm-bolt" "$ELF" -o /tmp/lk.arm.sections.elf \
  --print-sections \
  > /tmp/p1-arm32.log 2>&1 || fail "P1 llvm-bolt exited $?"
grep -q "Target architecture: arm" /tmp/p1-arm32.log || fail "P1 arch"
grep -q "Sections from original binary" /tmp/p1-arm32.log || fail "P1 sections header"
grep -q "\.text" /tmp/p1-arm32.log || fail "P1 .text"
grep -qE 'Aborted|UNREACHABLE executed|BOLT-ERROR: Unrecognized machine' /tmp/p1-arm32.log && fail "P1 abort"
pass "P1"

echo "=== P2/P3: disasm + CFG on bolt_bench_hot_loop ==="
"$TOOLCHAIN/llvm-bolt" "$ELF" -o /tmp/lk.arm.cfg.elf \
  --funcs-file="$FUNCS_FILE" --print-cfg \
  > /tmp/p23-arm32.log 2>&1 || fail "P2/P3 llvm-bolt exited $?"
grep -q 'Binary Function "bolt_bench_hot_loop"' /tmp/p23-arm32.log || fail "P2/P3 missing hot_loop CFG"
grep -q "Successors:" /tmp/p23-arm32.log || fail "P2/P3 missing successors"
grep -qE 'BOLT-ERROR|UNREACHABLE executed' /tmp/p23-arm32.log && fail "P2/P3 fatal in log"
pass "P2/P3"

echo "=== P4: selected identity rewrite + QEMU execution ==="
[[ "$CMDLINE" == lk.bolt_bench=all ]] || fail "P4 requires the complete workload"
python3 "$ROOT/scripts/qemu_rewrite_build.py" --elf "$ELF" --toolchain "$TOOLCHAIN" \
  --funcs "$BOLT_BENCH_FUNCS" --qemu "$QEMU" \
  --out "${OUT_DIR:-$ROOT/out/arm32-milestones}/p4" --timeout 120
 echo "P4 selected-entry execution / independent sink arithmetic verified"
 echo "P0/P4 complete workloads; P1/P2/P3 remain artifact diagnostics"
