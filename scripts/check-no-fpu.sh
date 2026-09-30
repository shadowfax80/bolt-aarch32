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
TC="${TOOLCHAIN:-$ROOT/build-${BASE:-atfe}/bin}"
rc=0
for f in "$@"; do
  n="$("$TC/llvm-objdump" -d --no-show-raw-insn "$f" 2>/dev/null \
        | grep -c -E '^[[:space:]]*[0-9a-f]+:[[:space:]]+v[a-z]' || true)"
  if [[ "$n" != 0 ]]; then
    echo "FAIL $f: $n FP/NEON instruction(s), e.g.:"
    "$TC/llvm-objdump" -d --no-show-raw-insn "$f" 2>/dev/null \
      | grep -E '^[[:space:]]*[0-9a-f]+:[[:space:]]+v[a-z]' | head -3
    rc=1
  else
    echo "ok   $f: 0 FP/NEON instructions"
  fi
done
exit $rc
