#!/usr/bin/env bash
# Wrapper: instrumented ELF + QMP counter dump -> .fdata on stdout or -o path.
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
  -o "$OUT"
