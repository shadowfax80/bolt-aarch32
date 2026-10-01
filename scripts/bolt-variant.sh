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
V="${VARIANTS_DIR:-$ROOT/build-$BASE/variants}"
# Extra llvm-bolt args. The default is right for the rpi4 (it needs overlay patch
# 0006). Set BOLT_EXTRA_ARGS="" on a platform without that reserve window (QEMU
# virt), where BOLT's new segments at _end would land on the PMM page array.
BOLT_EXTRA_ARGS="${BOLT_EXTRA_ARGS---no-huge-pages}"
FUNC="${BOLT_FUNC:-bolt_bench_composite}"
# Profile mode. edges (default): redirect the original entry into BOLT's
# instrumented copy so its real per-edge counters run -- the profile then has true
# edge frequencies. entry: the old entry hook, which bumps every counter once per
# *call* (every edge reads 1); kept for functions whose instrumented copy does not
# run correctly.
MODE="${BOLT_PROFILE_MODE:-edges}"
# Output name for `optimize`: <variant><SUFFIX>.{elf,bin}. A second optimize of the
# same profile with another SUFFIX (e.g. _bolt_noreorder + BOLT_REORDER_BLOCKS=none)
# gives a control image without clobbering the first.
OSUF="${BOLT_OUT_SUFFIX:-_bolt}"

cmd="${1:-}"; variant="${2:-}"
[[ -n "$cmd" && -n "$variant" ]] || { sed -n '2,12p' "$0" >&2; exit 1; }
[[ -f "$V/$variant.elf" ]] || { echo "error: $V/$variant.elf missing (build-variants.sh first)" >&2; exit 1; }

case "$cmd" in
  instrument)
    rm -f "$V/$variant.instr."*
    BASE="$BASE" ARCH=arm32 ELF="$V/$variant.elf" OUT="$V/$variant.instr.elf" \
      BOLT_INSTR_EDGES=$([[ "$MODE" == edges ]] && echo 1 || echo 0) \
      BOLT_BENCH_FUNCS="$FUNC" "$ROOT/scripts/instrument-lk-bolt.sh" $BOLT_EXTRA_ARGS       --emit-function-map="$V/$variant.instr.funcmap" \
      > "$V/$variant.instr.log" 2>&1 || { tail -20 "$V/$variant.instr.log" >&2; exit 1; }
    # BOLT silently instruments nothing if the function name does not match
    # (e.g. ThinLTO internalized it to a local `name/1`): fail loudly instead.
    if [[ "$MODE" == edges ]]; then
      NFUNCS=$(awk -F, '{print NF}' <<<"$FUNC")
      if ! grep -q "Number of function descriptors: $NFUNCS\$" "$V/$variant.instr.log"; then
        echo "error: BOLT instrumented no counters for $FUNC -- see $V/$variant.instr.log" >&2
        grep -E 'function descriptors|skipping' "$V/$variant.instr.log" >&2 || true
        exit 1
      fi
      python3 "$ROOT/scripts/redirect-bolt-entries.py" "$V/$variant.instr.elf" \
        --original "$V/$variant.elf" --map "$V/$variant.instr.funcmap" --func "$FUNC"         --toolchain "$TOOLCHAIN" --instrumented
    elif ! grep -q "thumb hook $FUNC" "$V/$variant.instr.log"; then
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
    if [[ -n "${BOLT_FDATA:-}" ]]; then
      # A ready profile, e.g. from PC sampling (samples_to_fdata.py): no instrumented
      # image or counter dump involved.
      cp "$BOLT_FDATA" "$V/$variant.fdata"
    else
      counters="${3:-}"; [[ -f "$counters" ]] || { echo "error: counters file required" >&2; exit 1; }
      python3 "$ROOT/scripts/ram-dump-to-fdata.py" --elf "$V/$variant.instr.elf" \
        --dump "$counters" --toolchain "$TOOLCHAIN" -o "$V/$variant.fdata"
    fi
    BASE="$BASE" ARCH=arm32 ELF="$V/$variant.elf" FDATA="$V/$variant.fdata" \
      OUT="$V/${variant}${OSUF}.elf" OPTIMIZE_FUNCS="${BOLT_OPTIMIZE_FUNCS:-$FUNC}" \
      "$ROOT/scripts/optimize-lk-bolt.sh" $BOLT_EXTRA_ARGS > "$V/${variant}${OSUF}.log" 2>&1 \
      || { tail -20 "$V/${variant}${OSUF}.log" >&2; exit 1; }
    # BOLT_OPTIMIZE_FUNCS (optional, a superset of BOLT_FUNC): functions BOLT may also
    # rewrite, e.g. small helpers given only as inlining candidates. They are not
    # redirected; code outside the rewritten set keeps calling the original copies.
    python3 "$ROOT/scripts/redirect-bolt-entries.py" "$V/${variant}${OSUF}.elf" \
      --original "$V/$variant.elf" --map "$V/${variant}${OSUF}.elf.funcmap" --func "$FUNC" \
      --also-rewritten "${BOLT_OPTIMIZE_FUNCS:-}" ${BOLT_ALLOW_MISSING:+--allow-missing} \
      --toolchain "$TOOLCHAIN"
    "$TOOLCHAIN/llvm-objcopy" -O binary "$V/${variant}${OSUF}.elf" "$V/${variant}${OSUF}.bin"
    echo "image: $V/${variant}${OSUF}.bin ($(stat -c %s "$V/${variant}${OSUF}.bin") bytes)"
    ;;
  *) echo "error: unknown command '$cmd'" >&2; exit 1 ;;
esac
