#!/usr/bin/env bash
# P5 gate: ARM LongJmp veneer is in the rewritten ELF and the far call runs.
# BASE=upstream|atfe selects which built toolchain/source tree to use.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
source "$ROOT/scripts/resolve-base.sh"
TOOLCHAIN="${TOOLCHAIN:-$BUILD_DIR/bin}"
SRC="$LLVM_DIR/bolt/test/ARM/Inputs/arm32-far-bl.s"
LD="$LLVM_DIR/bolt/test/ARM/Inputs/arm32-far.ld"

[[ -x "$TOOLCHAIN/llvm-bolt" ]] || { echo "missing llvm-bolt" >&2; exit 1; }
[[ -f "$SRC" ]] || { echo "missing $SRC" >&2; exit 1; }

"$TOOLCHAIN/llvm-mc" -filetype=obj -triple=armv7-unknown-linux-gnueabi "$SRC" -o /tmp/arm32-far.o
"$TOOLCHAIN/ld.lld" --emit-relocs -T "$LD" /tmp/arm32-far.o -o /tmp/arm32-far.exe
# Keep far_away beyond the +/-32MB ARM BL range so LongJmp writes a stub
# into the output (packed layout would make the BL in-range).
"$TOOLCHAIN/llvm-bolt" /tmp/arm32-far.exe -o /tmp/arm32-far.bolt \
  --pad-funcs-before=far_away:0x2100000 \
  > /tmp/arm32-far-bolt.log 2>&1

grep -qE 'removed linker-inserted veneers: [1-9]' /tmp/arm32-far-bolt.log
grep -qE 'Inserted [1-9][0-9]* stubs' /tmp/arm32-far-bolt.log
grep -qE 'BOLT-ERROR|UNREACHABLE executed' /tmp/arm32-far-bolt.log && {
  echo "fatal in log" >&2
  cat /tmp/arm32-far-bolt.log >&2
  exit 1
}

# Full-image objdump of the 33MB pad times out; the stub sits at the new entry.
"$TOOLCHAIN/llvm-objdump" -d --start-address=0x2400000 --stop-address=0x2400020 \
  /tmp/arm32-far.bolt > /tmp/arm32-far.objdump
# MOVW ip / MOVT ip / BX ip — llvm-objdump may print <unknown> without $a.
grep -qE 'e300c|movw' /tmp/arm32-far.objdump
grep -qE 'e340c|movt' /tmp/arm32-far.objdump
grep -qE 'e12fff1c|\bbx\b' /tmp/arm32-far.objdump

if command -v qemu-arm >/dev/null; then
  set +e
  qemu-arm -cpu cortex-a15 /tmp/arm32-far.bolt
  STATUS=$?
  set -e
  [[ "$STATUS" -eq 42 ]] || {
    echo "error: qemu-arm exit $STATUS, expected 42" >&2
    exit 1
  }
  echo "PASS: P5 LongJmp veneer (stub in output + qemu-arm exit 42)"
else
  echo "PASS: P5 LongJmp veneer (stub in output; qemu-arm not installed)"
fi
