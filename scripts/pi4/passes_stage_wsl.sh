#!/usr/bin/env bash
# WSL half of passes_stage.sh: BOLT optimization passes over the small bolt_bench workloads
# (and their helpers) of the plain `baseline` image, one image per pass set.
#
#   passes_stage_wsl.sh build <outdir>
#   passes_stage_wsl.sh instrument <outdir>        prints `COUNTERS addr= size=`
#   passes_stage_wsl.sh optimize <outdir> <counters.bin>
set -euo pipefail
cd "$HOME/bolt-aarch32"
unset VARIANTS_DIR LK_PROJECT LK_MAKE_ARGS BOLT_EXTRA_ARGS BOLT_SPLIT
export BASE=atfe BOLT_PROFILE_MODE=edges
V=build-atfe/variants
cmd="$1"; out="$2"
mkdir -p "$out"

# Every small workload and helper; not the big ones (stair, composite, pgo_lab, multi), the
# PMU/console plumbing, or the ICF twins' callers' data.
funcs() {
  # BOLT names a static (local) function "<name>/1"; only that form matches.
  build-atfe/bin/llvm-nm "$V/baseline.elf" |
    awk '$2 ~ /^[tT]$/ && $3 ~ /^bolt_bench_/ {print $3 ($2 == "t" ? "/1" : "")}' |
    grep -v -E 'stair|composite|pgo_lab|pl_|multi|_mf[0-9]|pmu|_cmd|print_sink|bench_banner|_init' |
    sort -u | paste -sd, -
}

case "$cmd" in
  build)
    ./scripts/build-variants.sh baseline | tail -1
    ./scripts/check-no-fpu.sh "$V/baseline.elf" >&2
    cp "$V/baseline.bin" "$V/baseline.elf" "$out/"
    funcs > "$out/funcs.txt"
    tr ',' '\n' < "$out/funcs.txt" | wc -l | xargs echo "functions:"
    ;;
  instrument)
    # Branch-free leaf helpers get no edge counters (nothing to count), so BOLT emits no
    # descriptor for them: instrument (and later redirect) only the functions that do.
    BOLT_FUNC="$(cat "$out/funcs.txt")" ./scripts/bolt-variant.sh instrument baseline \
      > /dev/null 2>&1 || true
    cut -d' ' -f1 "$V/baseline.instr.funcmap" | sort | paste -sd, - > "$out/instr_funcs.txt"
    tr ',' '\n' < "$out/instr_funcs.txt" | wc -l | xargs echo "instrumented functions:" >&2
    BOLT_FUNC="$(cat "$out/instr_funcs.txt")" ./scripts/bolt-variant.sh instrument baseline | tail -1
    cp "$V/baseline.instr.bin" "$V/baseline.instr.elf" "$out/"
    ;;
  optimize)
    counters="$3"
    # Redirect the instrumented functions; let BOLT also see the helpers (inlining
    # candidates). -lite=0 so helpers without a profile are still considered.
    export BOLT_FUNC="$(cat "$out/instr_funcs.txt")"
    export BOLT_OPTIMIZE_FUNCS="$(cat "$out/funcs.txt")" BOLT_ALLOW_MISSING=1
    : > "$out/bolt_stats.txt"
    # suffix | extra llvm-bolt flags
    while IFS='|' read -r sfx flags; do
      BOLT_OUT_SUFFIX="_$sfx" BOLT_EXTRA_ARGS="--no-huge-pages -lite=0 $flags" \
        ./scripts/bolt-variant.sh optimize baseline "$counters" | tail -1
      cp "$V/baseline_$sfx.bin" "$V/baseline_$sfx.elf" "$out/"
      { echo "== $sfx: $flags"
        grep -h -E "BOLT-INFO: .*(inlined|simplified|split|ICF folded|peephole)" "$V/baseline_$sfx.log" || true
      } >> "$out/bolt_stats.txt"
    done <<'EOF'
bolt|
inline|-inline-all
rodata|-simplify-rodata-loads
split|-split-functions -split-all-cold
peep|-peepholes=all
sctc|-simplify-conditional-tail-calls
all|-inline-all -simplify-rodata-loads -peepholes=all -simplify-conditional-tail-calls -split-functions -split-all-cold
EOF
    cat "$out/bolt_stats.txt"
    ;;
  *) echo "usage: $0 build|instrument|optimize <outdir> [counters.bin]" >&2; exit 2 ;;
esac
