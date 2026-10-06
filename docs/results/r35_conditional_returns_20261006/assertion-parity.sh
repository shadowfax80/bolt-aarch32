#!/usr/bin/env bash
set -euo pipefail
ROOT=/mnt/c/Users/User/CURSOR/CodexProjects/BOLT_AARCH32
V="$ROOT/out/r35/counter-off"
mkdir -p "$V"
cp "$ROOT/out/r35/counter/cspgo_thinlto."{elf,bin} "$V/"
export BASE=atfe TOOLCHAIN=/home/user/bolt-aarch32/build-atfe-noassert/bin
export VARIANTS_DIR="$V" BOLT_FUNC=bolt_bench_stair_kernel BOLT_PROFILE_MODE=edges
export BOLT_RT_LIB=/home/user/bolt-aarch32/build-atfe/bolt-rt-baremetal-arm/libbolt_rt_baremetal.a
export ARM_INSTRUMENTATION_CONTRACT=privileged-single-core-no-fiq
bash "$ROOT/scripts/bolt-variant.sh" instrument cspgo_thinlto
export BOLT_FDATA="$ROOT/out/r35/counter/cspgo_thinlto.fdata"
bash "$ROOT/scripts/bolt-variant.sh" optimize cspgo_thinlto
for job in instr _bolt; do
  if [ "$job" = instr ]; then STEM=cspgo_thinlto.instr; else STEM=cspgo_thinlto_bolt; fi
  cmp "$ROOT/out/r35/counter/$STEM.bin" "$V/$STEM.bin"
  "$TOOLCHAIN/llvm-objcopy" --remove-section=.note.bolt_info "$ROOT/out/r35/counter/$STEM.elf" "$V/$STEM.on.nonote"
  "$TOOLCHAIN/llvm-objcopy" --remove-section=.note.bolt_info "$V/$STEM.elf" "$V/$STEM.off.nonote"
  cmp "$V/$STEM.on.nonote" "$V/$STEM.off.nonote"
  bash "$ROOT/scripts/check-no-fpu.sh" "$V/$STEM.elf"
done
for mode in on off; do
  "$TOOLCHAIN/llvm-objcopy" --remove-section=.note.bolt_info "$ROOT/out/r35/full-$mode/baseline_full.elf" "$ROOT/out/r35/full-$mode/baseline_full.nonote"
  bash "$ROOT/scripts/check-no-fpu.sh" "$ROOT/out/r35/full-$mode/baseline_full.elf"
done
cmp "$ROOT/out/r35/full-on/baseline_full.nonote" "$ROOT/out/r35/full-off/baseline_full.nonote"
cmp "$ROOT/out/r35/full-on/baseline_full.bin" "$ROOT/out/r35/full-off/baseline_full.bin"
echo 'PASS: ON/OFF CSPGO instrumentation, counter optimization and certified-image outputs match (ELF excludes command-line .note.bolt_info only); all no-FPU scans pass'
