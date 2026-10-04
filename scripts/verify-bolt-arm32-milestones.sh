#!/usr/bin/env bash
# AArch32 BOLT milestones P0 through P4 in QEMU.
#
# QEMU is a debug aid (6a, user decision 2026-10-04): P0 and the P4 identity
# route are DIAGNOSTIC unless a reviewed qemu-virt oracle contract exists for
# the input image; P1-P3 are artifact diagnostics. Certification is Pi-only
# (scripts/pi4/full_image_verify.py, scripts/pi4/smp_verify.py).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TOOLCHAIN="${TOOLCHAIN:-$ROOT/build-${BASE:-upstream}/bin}"
LK_PROJECT="${LK_PROJECT:-qemu-virt-arm32-bolt-test}"
ELF="${ELF:-$ROOT/third_party/lk/build-$LK_PROJECT/lk.elf}"
QEMU="${QEMU:-qemu-system-arm}"
CMDLINE="${BENCH_CMDLINE:-lk.bolt_bench=all}"

BOLT_BENCH_FUNCS="${BOLT_BENCH_FUNCS:-bolt_bench_hot_loop,bolt_bench_hot_cold,bolt_bench_branch_chain,bolt_bench_memcpy}"

pass() { echo "PASS: $*"; }
fail() { echo "FAIL: $*" >&2; exit 1; }

[[ -x "$TOOLCHAIN/llvm-bolt" ]] || fail "llvm-bolt missing"
[[ -f "$ELF" ]] || fail "$ELF missing - run BOLT_BENCH_ISA=arm ./scripts/build-lk-aarch32.sh"

# 6a G1: every intermediate goes to a fresh directory, never fixed /tmp paths.
mkdir -p "${OUT_DIR:-$ROOT/out/arm32-milestones}"
RUN="$(mktemp -d "${OUT_DIR:-$ROOT/out/arm32-milestones}/run-XXXXXX")"
RUN="$(cd "$RUN" && pwd)"
echo "run directory: $RUN"
FUNCS_FILE="$RUN/funcs.txt"
printf '%s\n' ${BOLT_BENCH_FUNCS//,/ } > "$FUNCS_FILE"

echo "=== P0: original ELF boots + bolt_bench all ==="
python3 "$ROOT/scripts/qemu_workload_gate.py" --diagnostic --elf "$ELF" --qemu "$QEMU" \
  --append "$CMDLINE" --out "$RUN/p0" --timeout 120
echo "P0 complete workload (DIAGNOSTIC: no oracle contract, no certificate)"

# Section table of the full image; rewriting is scoped to the selected functions
# (startup/vector code is rejected by admission and must never be selected).
echo "=== P1: print-sections ==="
"$TOOLCHAIN/llvm-bolt" "$ELF" -o "$RUN/p1.elf" \
  --funcs-file="$FUNCS_FILE" --print-sections \
  > "$RUN/p1.log" 2>&1 || fail "P1 llvm-bolt exited $?"
grep -q "Target architecture: arm" "$RUN/p1.log" || fail "P1 arch"
grep -q "Sections from original binary" "$RUN/p1.log" || fail "P1 sections header"
grep -q "\.text" "$RUN/p1.log" || fail "P1 .text"
grep -qE 'Aborted|UNREACHABLE executed|BOLT-ERROR: Unrecognized machine' "$RUN/p1.log" && fail "P1 abort"
pass "P1"

echo "=== P2/P3: disasm + CFG on bolt_bench_hot_loop ==="
"$TOOLCHAIN/llvm-bolt" "$ELF" -o "$RUN/p23.elf" \
  --funcs-file="$FUNCS_FILE" --print-cfg \
  > "$RUN/p23.log" 2>&1 || fail "P2/P3 llvm-bolt exited $?"
grep -q 'Binary Function "bolt_bench_hot_loop"' "$RUN/p23.log" || fail "P2/P3 missing hot_loop CFG"
grep -q "Successors:" "$RUN/p23.log" || fail "P2/P3 missing successors"
grep -qE 'BOLT-ERROR|UNREACHABLE executed' "$RUN/p23.log" && fail "P2/P3 fatal in log"
pass "P2/P3"

echo "=== P4: selected identity rewrite + QEMU execution ==="
[[ "$CMDLINE" == lk.bolt_bench=all ]] || fail "P4 requires the complete workload"
# Certifies only with a reviewed qemu-virt contract; otherwise a labelled diagnostic.
ELF="$ELF" TOOLCHAIN="$TOOLCHAIN" QEMU="$QEMU" BOLT_BENCH_FUNCS="$BOLT_BENCH_FUNCS" \
  OUT_DIR="$RUN/p4" "$ROOT/scripts/verify-bolt-arm32-identity.sh"
echo "P0-P4 done; P1/P2/P3 are artifact diagnostics; certification is Pi-only"
