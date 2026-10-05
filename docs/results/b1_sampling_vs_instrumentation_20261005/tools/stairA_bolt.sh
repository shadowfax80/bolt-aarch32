#!/usr/bin/env bash
# B1 stair showcase (ARM mode), WSL side: lk-perf samples -> fdata -> BOLT.
set -euo pipefail
S=/mnt/c/Users/User/AppData/Local/Temp/claude/C--Users-User-CURSOR-ClaudeProjects-BOLT-AARCH32/f74ad4de-0e6e-4cd3-b5e9-3b0b9c5bc80c/scratchpad/b1/stair
cd /home/user/bolt-b1
V=build-atfe/variants
export BASE=atfe BOLT_FUNC=bolt_bench_stair_kernel BOLT_PROFILE_MODE=edges
export SOURCE_REPLAY=out/b1-replay/replay.json
# perf2bolt skip list for this image: startup/vectors, bcopy/bzero, and every function
# the backend refuses (all from the inlined `mov rX, pc` of lk-perf's mask accounting)
SKIP=_start,arm_reset,arm_undefined,arm_swi,arm_prefetch_abort,arm_data_abort,arm_reserved,arm_irq,arm_fiq,platform_early_init,arch_early_init,bcopy,bzero
printf 'S 80008000 1\n' > /tmp/b1_probe.preagg
for i in $(seq 1 400); do
  out=$(build-atfe/bin/perf2bolt "$V/stairA_lto.elf" -nl -pa -p /tmp/b1_probe.preagg -o /tmp/b1_probe.fdata -skip-funcs="$SKIP" 2>&1 || true)
  f=$(grep -o "FATAL BOLT-ERROR: .* in [^ ]*" <<<"$out" | head -1 | sed 's/.* in \([^ (]*\).*/\1/' || true)
  [[ -z "$f" ]] && break
  SKIP="$SKIP,$f"
done
echo "$SKIP" > out/stairA_lto.skips.txt
echo "== perf2bolt skips $(tr , '\n' <<<"$SKIP" | wc -l) functions"
cp "$S/stairA_lto.lkperf.samples" "$S/stairA_lto.lkperf.samples.manifest.json" "$V/"
python3 scripts/samples_to_fdata.py "$V/stairA_lto.elf" "$V/stairA_lto.lkperf.samples" \
  -o "$V/stairA_lto.lkperf.fdata" --toolchain build-atfe/bin --functions bolt_bench_stair_kernel \
  --skip-funcs "$SKIP" | tail -1
echo "== lk-perf fdata: $(($(wc -l < "$V/stairA_lto.lkperf.fdata") - 1)) locations, $(awk 'NR>1{s+=$4} END{print s}' "$V/stairA_lto.lkperf.fdata") samples in scope"
cp "$V/stairA_lto.fdata" "$V/stairA_lto.instr.fdata"
echo "== instr fdata: $(wc -l < "$V/stairA_lto.instr.fdata") edges"
BOLT_FDATA="$V/stairA_lto.lkperf.fdata" BOLT_OUT_SUFFIX=_bolt_lkperf \
  ./scripts/bolt-variant.sh optimize stairA_lto | tail -1
for s in _bolt_instr _bolt_lkperf; do
  echo "== stairA_lto$s"
  grep -E "BOLT-INFO: .*(have non-empty execution profile|profile quality|modified layout)" "$V/stairA_lto$s.log" | head -4 || true
done
./scripts/check-no-fpu.sh "$V/stairA_lto_bolt_instr.elf" "$V/stairA_lto_bolt_lkperf.elf" | tail -2
mkdir -p "$S/img"
for v in stairA_o2 stairA_lto stairA_lto_bolt_instr stairA_lto_bolt_lkperf; do cp "$V/$v.bin" "$S/img/"; done
ls -la "$S/img" | awk '{print $5, $9}'
