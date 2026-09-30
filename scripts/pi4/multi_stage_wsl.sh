#!/usr/bin/env bash
# WSL half of multi_stage.sh: BOLT over SEVERAL functions of the plain `baseline` image.
#
#   multi_stage_wsl.sh build <outdir>
#       build the baseline image, check it has no FPU/NEON, copy baseline.{bin,elf}
#   multi_stage_wsl.sh instrument <outdir>
#       edge-instrument all six bolt_bench_mf* functions, print `COUNTERS addr= size=`
#   multi_stage_wsl.sh optimize <outdir> <counters.bin>
#       BOLT-optimize twice from one profile: baseline_bolt (function reordering on) and
#       baseline_bolt_nofnreorder (-reorder-functions=none, the control); write
#       bolt_stats.txt (BOLT's report and the function map)
set -euo pipefail
cd "$HOME/bolt-aarch32"
unset VARIANTS_DIR LK_PROJECT LK_MAKE_ARGS BOLT_EXTRA_ARGS
export BASE=atfe BOLT_PROFILE_MODE=edges
export BOLT_FUNC="bolt_bench_mf0,bolt_bench_mf1,bolt_bench_mf2,bolt_bench_mf3,bolt_bench_mf4,bolt_bench_mf5"
V=build-atfe/variants
cmd="$1"; out="$2"
mkdir -p "$out"

case "$cmd" in
  build)
    ./scripts/build-variants.sh baseline | tail -1
    ./scripts/check-no-fpu.sh "$V/baseline.elf" >&2
    cp "$V/baseline.bin" "$V/baseline.elf" "$out/"
    ;;
  instrument)
    ./scripts/check-no-fpu.sh build-atfe/bolt-rt-baremetal-arm/libbolt_rt_baremetal.a >&2
    ./scripts/bolt-variant.sh instrument baseline | tail -1
    cp "$V/baseline.instr.bin" "$V/baseline.instr.elf" "$out/"
    ;;
  optimize)
    counters="$3"
    ./scripts/bolt-variant.sh optimize baseline "$counters" | tail -1
    BOLT_REORDER_FUNCTIONS=none BOLT_OUT_SUFFIX=_bolt_nofnreorder \
      ./scripts/bolt-variant.sh optimize baseline "$counters" | tail -1
    # The real control: rewritten, but the functions still 16 KB apart (same L1I sets as
    # the input). BOLT emits functions back to back otherwise -- even with
    # -reorder-functions=none, and even with --align-functions=16384 (its max-bytes limit
    # blocked the padding) -- so pad explicitly: 16384 - 0x1418 = 11240 after each of mf0..mf4.
    BOLT_PAD_FUNCS="bolt_bench_mf0:11240,bolt_bench_mf1:11240,bolt_bench_mf2:11240,bolt_bench_mf3:11240,bolt_bench_mf4:11240" \
      BOLT_OUT_SUFFIX=_bolt_pad16k \
      ./scripts/bolt-variant.sh optimize baseline "$counters" | tail -1
    {
      echo "== fdata: edges, total count, max count"
      awk '{n++; s+=$NF; if ($NF>m) m=$NF} END {print n, s, m}' "$V/baseline.fdata"
      for s in _bolt _bolt_nofnreorder _bolt_pad16k; do
        echo "== baseline$s"
        grep -E "BOLT-(INFO|WARNING): .*(profile|stale|reorder|split|layout|functions in the binary)" \
          "$V/baseline$s.log" || true
        echo "function map (name input-addr output-addr size):"
        cat "$V/baseline$s.elf.funcmap"
      done
    } > "$out/bolt_stats.txt"
    for s in _bolt _bolt_nofnreorder _bolt_pad16k; do
      cp "$V/baseline$s.bin" "$V/baseline$s.elf" "$out/"
    done
    cat "$out/bolt_stats.txt"
    ;;
  *) echo "usage: $0 build|instrument|optimize <outdir> [counters.bin]" >&2; exit 2 ;;
esac
