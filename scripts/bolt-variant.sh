#!/usr/bin/env bash
# The BOLT stage of the staged Pi comparison (build host side; the Pi runs are
# on the dev machine, see scripts/pi4/pi4_bolt_profile.py).
#
#   bolt-variant.sh instrument <variant>
#       BOLT-instrument build-$BASE/variants/<variant>.elf -> <variant>.instr.{elf,bin}
#       and print `COUNTERS addr=<hex> size=<hex>` for pi4_bolt_profile.py.
#
#   bolt-variant.sh optimize <variant> <counters.bin>
#       counters (dumped from the Pi) -> .fdata -> llvm-bolt -> redirect the
#       original entry to the optimized copy -> <variant>_bolt.{elf,bin}.
#
# Everything here is rpi4/bare-metal specific, and each choice has a reason:
#   --no-huge-pages   BOLT's default forces "hot text" onto 2MB huge-page
#                     boundaries (a Linux feature; instrumentation forces it on
#                     unconditionally), turning a ~150KB image into ~6MB -- a
#                     ~10 minute upload at the chainloader's 115200 baud.
#                     Requires overlay patch 0006 (reserves a window after _end
#                     so LK's page array does not land on BOLT's segments).
#   one function      the profiled/optimized set is bolt_bench_composite alone;
#                     redirect-bolt-entries.py depends on that.
#   redirect          without it the optimized copy is never executed (the
#                     restored original text runs), so any measurement would
#                     compare the input with itself.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
source "$ROOT/scripts/resolve-base.sh"
TOOLCHAIN="${TOOLCHAIN:-$ROOT/build-$BASE/bin}"
V="$ROOT/build-$BASE/variants"
FUNC="${BOLT_FUNC:-bolt_bench_composite}"

cmd="${1:-}"; variant="${2:-}"
[[ -n "$cmd" && -n "$variant" ]] || { sed -n '2,12p' "$0" >&2; exit 1; }
[[ -f "$V/$variant.elf" ]] || { echo "error: $V/$variant.elf missing (build-variants.sh first)" >&2; exit 1; }

case "$cmd" in
  instrument)
    rm -f "$V/$variant.instr."*
    BASE="$BASE" ARCH=arm32 ELF="$V/$variant.elf" OUT="$V/$variant.instr.elf" \
      BOLT_BENCH_FUNCS="$FUNC" "$ROOT/scripts/instrument-lk-bolt.sh" --no-huge-pages \
      > "$V/$variant.instr.log" 2>&1 || { tail -20 "$V/$variant.instr.log" >&2; exit 1; }
    # BOLT silently instruments nothing if the function name does not match
    # (e.g. ThinLTO internalized it to a local `name/1`): fail loudly instead.
    if ! grep -q "thumb hook $FUNC" "$V/$variant.instr.log"; then
      echo "error: BOLT instrumented no counters for $FUNC -- see $V/$variant.instr.log" >&2
      grep -E 'function descriptors|skipping|no BOLT counter' "$V/$variant.instr.log" >&2 || true
      exit 1
    fi
    "$TOOLCHAIN/llvm-objcopy" -O binary "$V/$variant.instr.elf" "$V/$variant.instr.bin"
    read -r addr size < <("$TOOLCHAIN/llvm-readelf" --sections "$V/$variant.instr.elf" \
      | awk '/\.bolt\.instr\.counters/ {print $4, $6}')
    echo "image: $V/$variant.instr.bin ($(stat -c %s "$V/$variant.instr.bin") bytes)"
    echo "COUNTERS addr=$addr size=$size"
    ;;
  optimize)
    counters="${3:-}"; [[ -f "$counters" ]] || { echo "error: counters file required" >&2; exit 1; }
    python3 "$ROOT/scripts/ram-dump-to-fdata.py" --elf "$V/$variant.instr.elf" \
      --dump "$counters" --toolchain "$TOOLCHAIN" -o "$V/$variant.fdata"
    BASE="$BASE" ARCH=arm32 ELF="$V/$variant.elf" FDATA="$V/$variant.fdata" \
      OUT="$V/${variant}_bolt.elf" OPTIMIZE_FUNCS="$FUNC" \
      "$ROOT/scripts/optimize-lk-bolt.sh" --no-huge-pages > "$V/${variant}_bolt.log" 2>&1 \
      || { tail -20 "$V/${variant}_bolt.log" >&2; exit 1; }
    python3 "$ROOT/scripts/redirect-bolt-entries.py" "$V/${variant}_bolt.elf" \
      --original "$V/$variant.elf" --func "$FUNC" --toolchain "$TOOLCHAIN"
    "$TOOLCHAIN/llvm-objcopy" -O binary "$V/${variant}_bolt.elf" "$V/${variant}_bolt.bin"
    echo "image: $V/${variant}_bolt.bin ($(stat -c %s "$V/${variant}_bolt.bin") bytes)"
    ;;
  *) echo "error: unknown command '$cmd'" >&2; exit 1 ;;
esac
