#!/usr/bin/env bash
# B2 whole LK image (Thumb), WSL side: three profiles -> three full-image builds.
#   R1  instrumentation counters (11 bolt_bench functions)
#   R2  lk-perf samples restricted to the same 11 functions
#   R3  lk-perf samples, whole image (no R28 workaround: 0070 is in)
set -euo pipefail
S=/mnt/c/Users/User/AppData/Local/Temp/claude/C--Users-User-CURSOR-ClaudeProjects-BOLT-AARCH32/f74ad4de-0e6e-4cd3-b5e9-3b0b9c5bc80c/scratchpad/b2
B1=/mnt/c/Users/User/AppData/Local/Temp/claude/C--Users-User-CURSOR-ClaudeProjects-BOLT-AARCH32/f74ad4de-0e6e-4cd3-b5e9-3b0b9c5bc80c/scratchpad/b1
cd /home/user/bolt-b1
V=build-atfe/variants
TC=build-atfe/bin
PD=/home/user/bolt-aarch32/overlay/llvm/patches/atfe
SCOPE=bolt_bench_composite,bolt_bench_multi,bolt_bench_mf0,bolt_bench_mf1,bolt_bench_mf2,bolt_bench_mf3,bolt_bench_mf4,bolt_bench_mf5,bolt_bench_stair,bolt_bench_stair_kernel,bolt_bench_stair_step

bash "$B1/refusals.sh" "$V/b2_whole.elf" out/b2_whole.skips.txt | tail -1
SKIP=$(cat out/b2_whole.skips.txt)
python3 scripts/ram-dump-to-fdata.py --elf "$V/b2_whole.instr.elf" --dump "$V/b2_whole.counters.bin" \
  --toolchain "$TC" --original "$V/b2_whole.elf" --function-map "$V/b2_whole.instr.funcmap" \
  --patch-dir "$PD" --source-replay /home/user/r29/replay/replay.json -o "$V/b2_whole.instr.fdata" | tail -1
echo "== R1 instr fdata: $(wc -l < "$V/b2_whole.instr.fdata") edges"
cp "$S/b2_whole.lkperf.samples" "$S/b2_whole.lkperf.samples.manifest.json" "$V/"
python3 scripts/samples_to_fdata.py "$V/b2_whole.elf" "$V/b2_whole.lkperf.samples" \
  -o "$V/b2_whole.lkperf_scoped.fdata" --toolchain "$TC" --functions "$SCOPE" --skip-funcs "$SKIP" | tail -1
python3 "$B1/r3_scope.py" "$V/b2_whole.elf" "$V/b2_whole.lkperf.samples" out/b2_whole.skips.txt out/b2_whole.r3_scope.txt
python3 scripts/samples_to_fdata.py "$V/b2_whole.elf" "$V/b2_whole.lkperf.samples" \
  -o "$V/b2_whole.lkperf_all.fdata" --toolchain "$TC" --functions "$(cat out/b2_whole.r3_scope.txt)" \
  --skip-funcs "$SKIP" | tail -1
for p in lkperf_scoped lkperf_all; do
  echo "== $p fdata: $(($(wc -l < "$V/b2_whole.$p.fdata") - 1)) locations, $(awk 'NR>1{s+=$4} END{print s}' "$V/b2_whole.$p.fdata") samples, $(awk 'NR>1{print $2}' "$V/b2_whole.$p.fdata" | sort -u | wc -l) functions"
done
echo "== composite samples: scoped $(awk '$2=="bolt_bench_composite"{s+=$4} END{print s+0}' "$V/b2_whole.lkperf_scoped.fdata")"

build() {   # name profile redirect-list
  local name=$1 profile=$2 redirect=$3 out="out/b2/$1" refused
  mkdir -p out/b2
  rm -f "out/b2/$name.not_redirected.txt"
  for attempt in $(seq 1 30); do
    rm -rf "$out"
    if BOLT_WORKSPACE=/home/user/bolt-b1 python3 scripts/pi4/full_image_build.py "$out" \
        --input "$V/b2_whole.elf" --toolchain "$TC" --profile "$profile" \
        --redirect-functions "$redirect" -- -skip-funcs="$SKIP" > "$out.build.txt" 2>&1; then
      break
    fi
    refused=$(grep -o "^[^ :]*: new copy at .* refusing to redirect" "$out/redirect.log" | head -1 | cut -d: -f1 || true)
    [[ -n "$refused" ]] || { tail -5 "$out.build.txt"; tail -5 "$out/redirect.log" 2>/dev/null; return 1; }
    echo "   not redirected (prologue changed): $refused"
    echo "$refused" >> "out/b2/$name.not_redirected.txt"
    redirect=$(tr , '\n' <<<"$redirect" | grep -vxF "$refused" | paste -sd,)
  done
  tail -2 "$out.build.txt" | head -1
  grep -E "Inserted" "$out/full.log" || true
  cp "$out/baseline_full.bin" "$S/img/$name.bin"
}
mkdir -p "$S/img"
cp "$V/b2_whole.bin" "$S/img/whole_input.bin"
build whole_r1_instr "$V/b2_whole.instr.fdata" "$SCOPE"
build whole_r2_lkperf_scoped "$V/b2_whole.lkperf_scoped.fdata" "$SCOPE"
SKIPPED=",$SKIP,"
HOT=$(awk 'NR>1{print $2}' "$V/b2_whole.lkperf_all.fdata" | sort -u | while read -r f; do
        [[ "$SKIPPED" == *",${f%%/*},"* ]] || echo "$f"; done | paste -sd,)
echo "== R3 redirects $(tr , '\n' <<<"$HOT" | wc -l) functions"
build whole_r3_lkperf_all "$V/b2_whole.lkperf_all.fdata" "$HOT"
ls -la "$S/img" | awk '{print $5, $9}'
