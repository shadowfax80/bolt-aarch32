#!/usr/bin/env bash
# Wrapper: sealed counter capture -> verified ARM .fdata.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TOOLCHAIN="${TOOLCHAIN:-$ROOT/build-${BASE:-upstream}/bin}"
ELF="${ELF:-$ROOT/build-${BASE:-upstream}/lk.instr.elf}"
DUMP="${DUMP:-$ROOT/build-${BASE:-upstream}/bolt-counters.bin}"
OUT="${OUT:-$ROOT/build-${BASE:-upstream}/prof.fdata}"

exec python3 "$ROOT/scripts/ram-dump-to-fdata.py" \
  --elf "$ELF" \
  --dump "$DUMP" \
  --toolchain "$TOOLCHAIN" \
  --original "${ORIGINAL_ELF:?set ORIGINAL_ELF to the exact BOLT input}" \
  --function-map "${FUNCTION_MAP:?set FUNCTION_MAP to the exact instrumented map}" \
  --source-replay "${SOURCE_REPLAY:?set SOURCE_REPLAY to the exact successful overlay replay report}" \
  -o "$OUT"
