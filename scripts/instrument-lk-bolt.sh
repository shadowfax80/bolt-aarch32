#!/usr/bin/env bash
# Instrument bolt_bench synthetic workloads embedded in the LK image.
#
# LK itself is the bare-metal host only — do not instrument kernel or platform
# functions. BOLT targets are the bolt_bench_* entry points from overlay/lk/files/.
#
# ARCH=aarch64 (default) or ARCH=arm32
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TOOLCHAIN="${TOOLCHAIN:-$ROOT/build-${BASE:-upstream}/bin}"
LK_DIR="${LK_DIR:-$ROOT/third_party/lk}"
ARCH="${ARCH:-aarch64}"

case "$ARCH" in
  aarch64|arm64)
    ELF="${ELF:-$LK_DIR/build-qemu-virt-arm64-test/lk.elf}"
    LIB="${BOLT_RT_LIB:-$ROOT/build-${BASE:-upstream}/bolt-rt-baremetal/libbolt_rt_baremetal.a}"
    SKIP_FUNCS="${SKIP_FUNCS:-_start,arm64_elX_to_el1,arm64_enable_mmu,arch_early_init,arm64_early_init_percpu,platform_early_init}"
    HOOK_SECTIONS=1
    ;;
  arm|arm32|aarch32)
    ARCH=arm32
    ELF="${ELF:-$LK_DIR/build-qemu-virt-arm32-bolt-test/lk.elf}"
    LIB="${BOLT_RT_LIB:-$ROOT/build-${BASE:-upstream}/bolt-rt-baremetal-arm/libbolt_rt_baremetal.a}"
    SKIP_FUNCS="${SKIP_FUNCS:-_start,arm_reset,arm_undefined,arm_swi,arm_prefetch_abort,arm_data_abort,arm_reserved,arm_irq,arm_fiq,platform_early_init,arch_early_init}"
    # Restore org.text/data and install Thumb counter hooks (same bare-metal
    # path as AArch64). BOLT's hot .text trampolines smash ARM literal pools.
    HOOK_SECTIONS=1
    ;;
  *)
    echo "error: ARCH must be aarch64 or arm32 (got: $ARCH)" >&2
    exit 1
    ;;
esac

OUT="${OUT:-$ROOT/build-${BASE:-upstream}/lk.instr.elf}"
# Full loop-based bench set, including bolt_bench_switch (TBB/TBH -- a
# known-unsupported-for-rewrite construct, kept in the default instrument
# set deliberately to observe how instrumentation itself handles it, not
# just identity-rewrite) and every 2026-09-16 addition targeting a specific
# optimization pass (indirect_call/interwork_tail: richer interworking +
# ICP target; regpressure: -reg-reassign target; hotcold_split:
# -split-functions target; icf: -icf target; shrinkwrap: shrink-wrapping
# target).
BOLT_BENCH_FUNCS="${BOLT_BENCH_FUNCS:-bolt_bench_hot_loop,bolt_bench_hot_cold,bolt_bench_branch_chain,bolt_bench_memcpy,bolt_bench_interwork,bolt_bench_switch,bolt_bench_spill_ret,bolt_bench_litpool,bolt_bench_indirect_call,bolt_bench_interwork_tail,bolt_bench_regpressure,bolt_bench_hotcold_split,bolt_bench_icf,bolt_bench_shrinkwrap}"
INSTRUMENT_FUNCS="${INSTRUMENT_FUNCS:-$BOLT_BENCH_FUNCS}"

if [[ ! -f "$ELF" ]]; then
  echo "error: $ELF not found — run scripts/build-lk-aarch64.sh or build-lk-aarch32.sh" >&2
  exit 1
fi
if [[ ! -f "$LIB" ]]; then
  echo "error: $LIB not found — run scripts/build-bolt-rt-baremetal.sh ARCH=$ARCH" >&2
  exit 1
fi

SECTIONS="$("$TOOLCHAIN/llvm-readelf" --sections "$ELF")"
if ! grep -qE '\.(rela|rel)\.text' <<<"$SECTIONS"; then
  echo "error: $ELF has no .rela.text/.rel.text — rebuild with WITH_BOLT_RELOCS=true" >&2
  exit 1
fi

FUNCS_FILE="$(mktemp)"
trap 'rm -f "$FUNCS_FILE"' EXIT
tr ',' '\n' <<<"$INSTRUMENT_FUNCS" | sed '/^$/d' > "$FUNCS_FILE"
while IFS= read -r func; do
  if [[ "$func" != bolt_bench_* ]]; then
    echo "error: only bolt_bench_* synthetic workloads may be instrumented (got: $func)" >&2
    echo "LK kernel/platform code must stay out of the BOLT profile." >&2
    exit 1
  fi
done < "$FUNCS_FILE"

mkdir -p "$(dirname "$OUT")"

# Static ET_EXEC images have no DT_FINI, so BOLT refuses to instrument them
# unless a watchdog interval is set. The watchdog is a Linux fork path that
# our runtime never calls, so the value is only a key to unlock the rewrite.
BOLT_ARGS=(
  -instrument
  --instrument-calls=false
  --instrumentation-sleep-time=1
  --runtime-instrumentation-lib="$LIB"
  # --instrument-funcs-file existed on the upstream base's pinned commit but
  # was removed entirely upstream by the time arm-toolchain's arm-software
  # branch synced past it (found merging the two bases, 2026-09-15) --
  # --funcs-file (generic "limit optimizations to functions from the list")
  # exists identically on both and, since it scopes BOLT's entire pass over
  # the binary rather than just the instrumentation counter injection, is
  # actually a closer match to this script's own intent ("LK kernel/platform
  # code must stay out of the BOLT profile" above) than the narrower flag
  # it replaces. $SKIP_FUNCS is now redundant with an allowlist in place
  # (and at least one base's BOLT rejects combining an allowlist with
  # --skip-funcs outright) -- dropped.
  --funcs-file="$FUNCS_FILE"
  -o "$OUT"
)

# Edge profiles need every edge counted. BOLT's default instruments only the edges
# off a spanning tree and infers the rest from flow, which needs the function's
# entry count; that comes from call-site counters, and --instrument-calls=false
# (above) turns those off. On the Pi the tree then took all the hot edges, the
# only counters sat on cold edges that never ran, and a function that executed
# 1600 times dumped all-zero counters (bolt_bench_stair_kernel, 2026-09-30).
# Conservative mode puts a counter on every edge: slower instrumented runs, but
# the profile needs no inference.
[[ "${BOLT_INSTR_EDGES:-0}" == 1 ]] && BOLT_ARGS+=(--conservative-instrumentation)

# ARM32 counters require privileged execution on one participating core with
# FIQ masked; resets and external reads must occur at quiescent boundaries.
if [[ "$ARCH" == arm32 ]]; then
  if [[ "${ARM_INSTRUMENTATION_CONTRACT:-}" != privileged-single-core-no-fiq ]]; then
    echo "error: set ARM_INSTRUMENTATION_CONTRACT=privileged-single-core-no-fiq after establishing the ARM32 operating contract" >&2
    exit 1
  fi
  BOLT_ARGS+=(--arm-instrumentation-contract="$ARM_INSTRUMENTATION_CONTRACT")
fi

# --no-lse-atomics is AArch64's option (QEMU cortex-a53 has no LSE). The ARM
# target never reads it -- its counter path masks IRQ around a 64-bit update.
[[ "$ARCH" != arm32 ]] && BOLT_ARGS+=(--no-lse-atomics)

"$TOOLCHAIN/llvm-bolt" "$ELF" "${BOLT_ARGS[@]}" "$@"

OUT_SECTIONS="$("$TOOLCHAIN/llvm-readelf" --sections "$OUT")"
grep -E 'bolt\.instr' <<<"$OUT_SECTIONS" || true
echo "instrumented image: $OUT"
python3 "$ROOT/scripts/fix-kernel-elf-paddr.py" "$OUT"
python3 "$ROOT/scripts/fix-kernel-elf-entry.py" "$OUT" --original "$ELF" \
  --readelf "$TOOLCHAIN/llvm-readelf"

if [[ "$HOOK_SECTIONS" == 1 ]]; then
  # BOLT_INSTR_EDGES=1: do not install the entry hook. Restore the boot-critical
  # sections only; the caller then redirects the function entry into BOLT's
  # *instrumented copy* (redirect-bolt-entries.py --instrumented), so the real
  # per-edge counters execute. The hook alone bumps every counter once per call,
  # which leaves every edge in the .fdata at 1.
  HOOK_ARGS=(--hook-funcs "$INSTRUMENT_FUNCS")
  [[ "${BOLT_INSTR_EDGES:-0}" == 1 ]] && HOOK_ARGS=()
  python3 "$ROOT/scripts/fix-kernel-elf-sections.py" "$OUT" --original "$ELF" \
    --readelf "$TOOLCHAIN/llvm-readelf" "${HOOK_ARGS[@]}"
fi
