#!/usr/bin/env bash
set -euo pipefail
ROOT=/mnt/c/Users/User/CURSOR/CodexProjects/BOLT_AARCH32
V=/home/user/bolt-cspgo/build-atfe/r35-counter-stair
mkdir -p "$V"
cp /home/user/bolt-cspgo/build-atfe/cspgo-runs/c148c605589f7b94/cspgo_thinlto.{elf,bin} "$V/"
export BASE=atfe TOOLCHAIN=/home/user/bolt-aarch32/build-atfe/bin
export VARIANTS_DIR="$V" BOLT_FUNC=bolt_bench_stair_kernel BOLT_PROFILE_MODE=edges
export BOLT_RT_LIB=/home/user/bolt-aarch32/build-atfe/bolt-rt-baremetal-arm/libbolt_rt_baremetal.a
export ARM_INSTRUMENTATION_CONTRACT=privileged-single-core-no-fiq
export SOURCE_REPLAY=/home/user/bolt-aarch32/out/r35-20261006/replay-final/replay.json
bash "$ROOT/scripts/bolt-variant.sh" instrument cspgo_thinlto
bash "$ROOT/scripts/check-no-fpu.sh" "$V/cspgo_thinlto.instr.elf" > "$V/nofpu-instrumented.log" 2>&1
python3 "$ROOT/scripts/profile_identity.py" seal-counters --original "$V/cspgo_thinlto.elf" --elf "$V/cspgo_thinlto.instr.elf" --map "$V/cspgo_thinlto.instr.funcmap" --image "$V/cspgo_thinlto.instr.bin" --toolchain "$TOOLCHAIN" --patch-dir "$ROOT/overlay/llvm/patches/atfe" --source-replay "$SOURCE_REPLAY"
cp "$V"/* "$ROOT/out/r35/counter/"
cp "$SOURCE_REPLAY" "$ROOT/out/r35/replay-final.json"
