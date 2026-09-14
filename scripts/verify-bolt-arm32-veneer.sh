#!/usr/bin/env bash
# P5 gate: ARM LongJmp veneers on a crafted far-BL ELF.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TOOLCHAIN="${TOOLCHAIN:-$ROOT/build/bin}"
SRC="$ROOT/third_party/llvm-project/bolt/test/ARM/Inputs/arm32-far-bl.s"
LD="$ROOT/third_party/llvm-project/bolt/test/ARM/Inputs/arm32.ld"

[[ -x "$TOOLCHAIN/llvm-bolt" ]] || { echo "missing llvm-bolt" >&2; exit 1; }
[[ -f "$SRC" ]] || { echo "missing $SRC" >&2; exit 1; }

"$TOOLCHAIN/llvm-mc" -filetype=obj -triple=armv7-unknown-linux-gnueabi "$SRC" -o /tmp/arm32-far.o
"$TOOLCHAIN/ld.lld" --emit-relocs -T "$LD" /tmp/arm32-far.o -o /tmp/arm32-far.exe
"$TOOLCHAIN/llvm-bolt" /tmp/arm32-far.exe -o /tmp/arm32-far.bolt \
  > /tmp/arm32-far-bolt.log 2>&1

grep -qE 'removed linker-inserted veneers: [1-9]' /tmp/arm32-far-bolt.log
grep -qE 'Inserted [1-9][0-9]* stubs' /tmp/arm32-far-bolt.log
grep -qE 'BOLT-ERROR|UNREACHABLE executed' /tmp/arm32-far-bolt.log && {
  echo "fatal in log" >&2
  exit 1
}
echo "PASS: P5 LongJmp veneer (linker veneer removed + stub inserted)"
