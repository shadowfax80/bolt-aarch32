#!/usr/bin/env bash
# Wrapper: instrumented ELF + QMP counter dump -> .fdata on stdout or -o path.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TOOLCHAIN="${TOOLCHAIN:-$ROOT/build/bin}"
ELF="${ELF:-$ROOT/build/lk.instr.elf}"
DUMP="${DUMP:-$ROOT/build/bolt-counters.bin}"
OUT="${OUT:-$ROOT/build/prof.fdata}"

exec python3 "$ROOT/scripts/ram-dump-to-fdata.py" \
  --elf "$ELF" \
  --dump "$DUMP" \
  --toolchain "$TOOLCHAIN" \
  -o "$OUT"
