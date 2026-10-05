#!/usr/bin/env bash
# B2 showcase, WSL side: both profiles -> BOLT (Thumb ThinLTO stair, 512 sites).
set -euo pipefail
S=/mnt/c/Users/User/AppData/Local/Temp/claude/C--Users-User-CURSOR-ClaudeProjects-BOLT-AARCH32/f74ad4de-0e6e-4cd3-b5e9-3b0b9c5bc80c/scratchpad/b2
R1=/mnt/c/Users/User/AppData/Local/Temp/claude/C--Users-User-CURSOR-ClaudeProjects-BOLT-AARCH32/f74ad4de-0e6e-4cd3-b5e9-3b0b9c5bc80c/scratchpad/b1
cd /home/user/bolt-b1
V=build-atfe/variants
export BASE=atfe BOLT_FUNC=bolt_bench_stair_kernel BOLT_PROFILE_MODE=edges
export SOURCE_REPLAY=/home/user/r29/replay/replay.json
bash "$R1/refusals.sh" "$V/b2_stair_lto.elf" out/b2_stair_lto.skips.txt | tail -1
SKIP=$(cat out/b2_stair_lto.skips.txt)
cp "$S/b2_stair_lto.lkperf.samples" "$S/b2_stair_lto.lkperf.samples.manifest.json" "$V/"
python3 scripts/samples_to_fdata.py "$V/b2_stair_lto.elf" "$V/b2_stair_lto.lkperf.samples" \
  -o "$V/b2_stair_lto.lkperf.fdata" --toolchain build-atfe/bin --functions bolt_bench_stair_kernel \
  --skip-funcs "$SKIP" --patch-dir /home/user/bolt-aarch32/overlay/llvm/patches/atfe 2>/dev/null | tail -1 \
  || python3 scripts/samples_to_fdata.py "$V/b2_stair_lto.elf" "$V/b2_stair_lto.lkperf.samples" \
       -o "$V/b2_stair_lto.lkperf.fdata" --toolchain build-atfe/bin --functions bolt_bench_stair_kernel \
       --skip-funcs "$SKIP" | tail -1
echo "lk-perf fdata: $(($(wc -l < "$V/b2_stair_lto.lkperf.fdata") - 1)) locations, $(awk 'NR>1{s+=$4} END{print s}' "$V/b2_stair_lto.lkperf.fdata") samples in the kernel"
BOLT_OUT_SUFFIX=_bolt_instr ./scripts/bolt-variant.sh optimize b2_stair_lto "$V/b2_stair_lto.counters.bin" | tail -1
cp "$V/b2_stair_lto.fdata" "$V/b2_stair_lto.instr.fdata"
echo "instr fdata: $(wc -l < "$V/b2_stair_lto.instr.fdata") edges"
BOLT_FDATA="$V/b2_stair_lto.lkperf.fdata" BOLT_OUT_SUFFIX=_bolt_lkperf ./scripts/bolt-variant.sh optimize b2_stair_lto | tail -1
for s in _bolt_instr _bolt_lkperf; do
  echo "== b2_stair_lto$s"
  grep -E "BOLT-INFO: .*(profile quality|modified layout|Inserted)" "$V/b2_stair_lto$s.log" | head -3
done
mkdir -p "$S/img"
for v in b2_stair_o2 b2_stair_lto b2_stair_lto_bolt_instr b2_stair_lto_bolt_lkperf; do cp "$V/$v.bin" "$S/img/"; done
