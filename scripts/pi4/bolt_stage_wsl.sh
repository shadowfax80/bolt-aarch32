#!/usr/bin/env bash
# WSL half of bolt_stage.sh (run inside WSL; the Pi steps run on Windows).
#
#   bolt_stage_wsl.sh instrument <outdir>
#       edge-instrument build-atfe/variants/pgo_thinlto.elf (stair function),
#       copy pgo_thinlto.instr.{bin,elf} to <outdir>, print `COUNTERS addr= size=`
#   bolt_stage_wsl.sh optimize <outdir> <counters.bin>
#       BOLT-optimize pgo_thinlto twice from the same profile:
#         pgo_thinlto_bolt            -reorder-blocks=ext-tsp (the real stage)
#         pgo_thinlto_bolt_noreorder  -reorder-blocks=none (control: rewritten and
#                                     moved, block order unchanged)
#       and write <outdir>/bolt_stats.txt (BOLT's profile/layout report + fdata summary)
set -euo pipefail
cd "$HOME/bolt-aarch32"
unset VARIANTS_DIR LK_PROJECT LK_MAKE_ARGS BOLT_EXTRA_ARGS
export BASE=atfe BOLT_FUNC="${BOLT_FUNC:-bolt_bench_stair_kernel}" BOLT_PROFILE_MODE=edges
V=build-atfe/variants
cmd="$1"; out="$2"
mkdir -p "$out"

case "$cmd" in
  instrument)
    # No FPU/NEON/vector unit anywhere in this project: refuse to profile with a
    # runtime or image that contains any.
    ./scripts/check-no-fpu.sh "build-atfe/bolt-rt-baremetal-arm/libbolt_rt_baremetal.a"       build-atfe/pgo-rt-baremetal-arm/*.o "$V/pgo_thinlto.elf" "$V/baseline.elf" "$V/pgo.elf" >&2
    ./scripts/bolt-variant.sh instrument pgo_thinlto | tail -1
    cp "$V/pgo_thinlto.instr.bin" "$V/pgo_thinlto.instr.elf" "$out/"
    ;;
  optimize)
    counters="$3"
    ./scripts/bolt-variant.sh optimize pgo_thinlto "$counters" | tail -1
    BOLT_REORDER_BLOCKS=none BOLT_OUT_SUFFIX=_bolt_noreorder \
      ./scripts/bolt-variant.sh optimize pgo_thinlto "$counters" | tail -1
    {
      echo "== fdata: edges, total count, max count"
      awk '{n++; s+=$NF; if ($NF>m) m=$NF} END {print n, s, m}' "$V/pgo_thinlto.fdata"
      for s in _bolt _bolt_noreorder; do
        echo "== pgo_thinlto$s"
        grep -E "BOLT-(INFO|WARNING): .*(profile|stale|reorder|split|layout|functions in the binary)" \
          "$V/pgo_thinlto$s.log" || true
        cat "$V/pgo_thinlto$s.elf.funcmap"
      done
    } > "$out/bolt_stats.txt"
    for s in _bolt _bolt_noreorder; do
      cp "$V/pgo_thinlto$s.bin" "$V/pgo_thinlto$s.elf" "$out/"
    done
    cp "$V/pgo_thinlto.fdata" "$out/"
    cat "$out/bolt_stats.txt"
    ;;
  *) echo "usage: $0 instrument|optimize <outdir> [counters.bin]" >&2; exit 2 ;;
esac
