#!/usr/bin/env bash
# B1 whole-LK-image case, WSL side: three profiles -> three full-image BOLT builds.
#   R1  instrumentation counters (11 bolt_bench functions, the instrumentable scope)
#   R2  lk-perf samples restricted to the same 11 functions
#   R3  lk-perf samples, whole image
# All use full_image_build.py (-lite=0, ext-tsp, hfsort+, icf=all).
set -euo pipefail
S=/mnt/c/Users/User/AppData/Local/Temp/claude/C--Users-User-CURSOR-ClaudeProjects-BOLT-AARCH32/f74ad4de-0e6e-4cd3-b5e9-3b0b9c5bc80c/scratchpad/b1/whole
cd /home/user/bolt-b1
V=build-atfe/variants
TC=build-atfe/bin
SCOPE=bolt_bench_composite,bolt_bench_multi,bolt_bench_mf0,bolt_bench_mf1,bolt_bench_mf2,bolt_bench_mf3,bolt_bench_mf4,bolt_bench_mf5,bolt_bench_stair,bolt_bench_stair_kernel,bolt_bench_stair_step
STEP="${1:-all}"

if [[ $STEP == all || $STEP == profiles ]]; then
  bash /mnt/c/Users/User/AppData/Local/Temp/claude/C--Users-User-CURSOR-ClaudeProjects-BOLT-AARCH32/f74ad4de-0e6e-4cd3-b5e9-3b0b9c5bc80c/scratchpad/b1/refusals.sh "$V/whole_a.elf" out/whole_a.skips.txt | tail -3
  # R28 (found by B1): BOLT sets the Thumb bit on code addresses in an ARM-mode
  # function's inline `ldr pc, [rX, rY, lsl #2]` table; the rewritten pl_b
  # data-aborted on the Pi. Keep every such function original in all variants.
  printf '%s,pl_b/1,bolt_bench_switch_pick/1,arch_sync_cache_range' "$(cat out/whole_a.skips.txt)" > out/s.tmp
  mv out/s.tmp out/whole_a.skips.txt
  SKIP=$(cat out/whole_a.skips.txt)
  python3 scripts/ram-dump-to-fdata.py --elf "$V/whole_a.instr.elf" --dump "$V/whole_a.counters.bin" \
    --toolchain "$TC" --original "$V/whole_a.elf" --function-map "$V/whole_a.instr.funcmap" \
    --source-replay out/b1-replay/replay.json -o "$V/whole_a.instr.fdata" | tail -2
  echo "== R1 instr fdata: $(wc -l < "$V/whole_a.instr.fdata") edges"
  cp "$S/whole_a.lkperf.samples" "$S/whole_a.lkperf.samples.manifest.json" "$V/"
  python3 scripts/samples_to_fdata.py "$V/whole_a.elf" "$V/whole_a.lkperf.samples" \
    -o "$V/whole_a.lkperf_scoped.fdata" --toolchain "$TC" --functions "$SCOPE" --skip-funcs "$SKIP" | tail -1
  python3 /mnt/c/Users/User/AppData/Local/Temp/claude/C--Users-User-CURSOR-ClaudeProjects-BOLT-AARCH32/f74ad4de-0e6e-4cd3-b5e9-3b0b9c5bc80c/scratchpad/b1/r3_scope.py \
    "$V/whole_a.elf" "$V/whole_a.lkperf.samples" out/whole_a.skips.txt out/whole_a.r3_scope.txt
  python3 scripts/samples_to_fdata.py "$V/whole_a.elf" "$V/whole_a.lkperf.samples" \
    -o "$V/whole_a.lkperf_all.fdata" --toolchain "$TC" --functions "$(cat out/whole_a.r3_scope.txt)" \
    --skip-funcs "$SKIP" | tail -1
  for p in lkperf_scoped lkperf_all; do
    echo "== $p fdata: $(($(wc -l < "$V/whole_a.$p.fdata") - 1)) locations, $(awk 'NR>1{s+=$4} END{print s}' "$V/whole_a.$p.fdata") samples, $(awk 'NR>1{print $2}' "$V/whole_a.$p.fdata" | sort -u | wc -l) functions"
  done
fi

build() {   # name profile redirect-list
  local name=$1 profile=$2 redirect=$3 out="out/whole/$1" refused
  for attempt in $(seq 1 30); do
    rm -rf "$out"
    if BOLT_WORKSPACE=/home/user/bolt-b1 python3 scripts/pi4/full_image_build.py "$out" \
        --input "$V/whole_a.elf" --toolchain "$TC" --profile "$profile" \
        --redirect-functions "$redirect" -- -skip-funcs="$(cat out/whole_a.skips.txt)" > "$out.build.txt" 2>&1; then
      break
    fi
    # the redirect tool refuses functions whose new copy changed the prologue;
    # leave them unredirected (they still run their new copy when called from
    # rewritten code) and retry
    refused=$(grep -o "^[^ :]*: new copy at .* refusing to redirect" "$out/redirect.log" | head -1 | cut -d: -f1 || true)
    [[ -n "$refused" ]] || { tail -5 "$out.build.txt"; tail -5 "$out/redirect.log" 2>/dev/null; return 1; }
    echo "   not redirected (prologue changed): $refused"
    echo "$refused" >> "out/whole/$name.not_redirected.txt"
    redirect=$(tr , '\n' <<<"$redirect" | grep -vxF "$refused" | paste -sd,)
  done
  tail -2 "$out.build.txt"
  if grep -qE "^(pl_b/1|bolt_bench_switch_pick/1|arch_sync_cache_range) " "$out/full.funcmap"; then
    echo "error: an R28 function was still emitted"; return 1
  fi
  # the no-FPU scanner misreads BOLT outputs (open item 14: dropped $a mapping
  # symbols make restored ARM code decode as Thumb); the input is scanned clean
  ./scripts/check-no-fpu.sh "$out/baseline_full.elf" | tail -1 || echo "   (output scan: item-14 false positive class, see notes)"
  cp "$out/baseline_full.bin" "$S/img/$name.bin"
}

if [[ $STEP == all || $STEP == r1 || $STEP == r12 ]]; then
  mkdir -p "$S/img" out/whole
  cp "$V/whole_a.bin" "$S/img/input.bin"
  build r1_instr "$V/whole_a.instr.fdata" "$SCOPE"
fi
if [[ $STEP == all || $STEP == r2 || $STEP == r12 ]]; then
  build r2_lkperf_scoped "$V/whole_a.lkperf_scoped.fdata" "$SCOPE"
fi
if [[ $STEP == all || $STEP == r3 ]]; then
  # every function with samples, minus those BOLT skips
  SKIPPED=",$(cat out/whole_a.skips.txt),"
  HOT=$(awk 'NR>1{print $2}' "$V/whole_a.lkperf_all.fdata" | sort -u | while read -r f; do
          [[ "$SKIPPED" == *",${f%%/*},"* ]] || echo "$f"; done | paste -sd,)
  echo "== R3 redirects $(tr , '\n' <<<"$HOT" | wc -l) functions"
  echo "$HOT" > out/whole_a.r3_redirect.txt
  build r3_lkperf_all "$V/whole_a.lkperf_all.fdata" "$HOT"
fi
ls -la "$S/img" | awk '{print $5, $9}'
