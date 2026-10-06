#!/usr/bin/env bash
# Guard: this project has no FPU, NEON or vector unit of any kind (the target core
# has none). Fails if any given ELF / object / archive contains an FP or SIMD
# instruction. Every ARM mnemonic starting with `v` is a VFP or NEON instruction.
#
#   scripts/check-no-fpu.sh <file>...        (TOOLCHAIN=build-atfe/bin by default)
#
# The disassembler takes the instruction set at each address from the mapping
# symbols ($a/$t/$d), so the result is only as good as they are. Before
# decoding, every file is checked: each STT_FUNC symbol must start in its own
# state (bit 0 of its value) and no address may carry conflicting marks.
# Otherwise the file FAILS as undecodable rather than passing or failing on
# misdecoded bytes. BOLT outputs from overlay 0072 on carry correct mapping
# symbols for the new code, the kept original section and linker stubs (R30);
# earlier BOLT outputs fail this check.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
# TOOLCHAIN is a bin directory here. LK builds export TOOLCHAIN=clang (a
# compiler family, not a path); that once made this guard pass every file
# because llvm-objdump was not found. Fail closed instead.
TC="${NOFPU_TOOLCHAIN:-${TOOLCHAIN:-$ROOT/build-${BASE:-atfe}/bin}}"
[[ -d "$TC" ]] || TC="$ROOT/build-${BASE:-atfe}/bin"
OBJDUMP="$TC/llvm-objdump"
READELF="$TC/llvm-readelf"
for tool in "$OBJDUMP" "$READELF"; do
  if [[ ! -x "$tool" ]]; then
    echo "FAIL: $tool not found; set NOFPU_TOOLCHAIN to an LLVM bin directory" >&2
    exit 2
  fi
done

# Prints one line per function that does not start in its own state, or per
# address with conflicting marks. Archives list one symbol table per member.
mapping_errors() {
  # POSIX awk only (no gawk): readelf prints fixed-width hex values, so bit 0
  # is in the last digit and string order is address order. Addresses carry
  # an "@" so awk never compares them as numbers ("800e6600" is 800e6600).
  "$READELF" -s -W "$1" | awk '
    /^File: / { member++ }
    $1 ~ /^[0-9]+:$/ && $7 ~ /^[0-9]+$/ {
      key = member ":" $7; hex = "0123456789abcdef"
      if ($8 ~ /^\$[atd](\.|$)/) print key, "@" $2, 0, substr($8, 2, 1)
      else if ($4 == "FUNC") {
        n = length($2); d = index(hex, substr($2, n, 1)) - 1
        print key, "@" substr($2, 1, n - 1) substr(hex, d - d % 2 + 1, 1), 1, (d % 2 ? "t" : "a"), $8
      }
    }' | sort -k1,1 -k2,2 -k3,3n | awk '
    $1 != sec { sec = $1; state = ""; at = ""; seen = "" }
    $3 == 0 {
      if ($2 != at) { at = $2; seen = "" }
      if (seen != "" && index(seen, $4) == 0) print "conflicting marks at 0x" substr($2, 2) ": " seen $4
      seen = seen $4; state = $4; next
    }
    state != $4 { print $5 " at 0x" substr($2, 2) " starts in state " (state == "" ? "none" : state) ", expected " $4 }'
}

rc=0
for f in "$@"; do
  if ! errs="$(mapping_errors "$f")"; then
    echo "FAIL $f: llvm-readelf could not read it" >&2
    rc=1; continue
  fi
  if [[ -n "$errs" ]]; then
    echo "FAIL $f: mapping symbols do not give each function its instruction set; cannot decode reliably ($(wc -l <<<"$errs") problem(s)), e.g.:"
    head -3 <<<"$errs"
    rc=1; continue
  fi
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
