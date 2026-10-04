#!/usr/bin/env bash
# Guard: this project has no FPU, NEON or vector unit of any kind (the target core
# has none). Fails if any given ELF / object / archive contains an FP or SIMD
# instruction. Every ARM mnemonic starting with `v` is a VFP or NEON instruction.
#
#   scripts/check-no-fpu.sh <file>...        (TOOLCHAIN=build-atfe/bin by default)
#
# Covers what is decodable: LK images built by the compiler, and the profiling
# runtimes. It does not decode BOLT's rewritten .text (no mapping symbols), which only
# holds the input's instructions plus ldrex/strex counters.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
# TOOLCHAIN is a bin directory here. LK builds export TOOLCHAIN=clang (a
# compiler family, not a path); that once made this guard pass every file
# because llvm-objdump was not found. Fail closed instead.
TC="${NOFPU_TOOLCHAIN:-${TOOLCHAIN:-$ROOT/build-${BASE:-atfe}/bin}}"
[[ -d "$TC" ]] || TC="$ROOT/build-${BASE:-atfe}/bin"
OBJDUMP="$TC/llvm-objdump"
if [[ ! -x "$OBJDUMP" ]]; then
  echo "FAIL: $OBJDUMP not found; set NOFPU_TOOLCHAIN to an LLVM bin directory" >&2
  exit 2
fi
rc=0
for f in "$@"; do
  if ! dis="$("$OBJDUMP" -d --no-show-raw-insn "$f")"; then
    echo "FAIL $f: llvm-objdump could not disassemble it" >&2
    rc=1; continue
  fi
  hits="$(grep -E '^[[:space:]]*[0-9a-f]+:[[:space:]]+v[a-z]' <<<"$dis" || true)"
  if [[ -n "$hits" ]]; then
    echo "FAIL $f: $(wc -l <<<"$hits") FP/NEON instruction(s), e.g.:"
    head -3 <<<"$hits"
    rc=1
  else
    echo "ok   $f: 0 FP/NEON instructions"
  fi
done
exit $rc
