#!/usr/bin/env bash
set -euo pipefail
ROOT=/mnt/c/Users/User/CURSOR/CodexProjects/BOLT_AARCH32
V=/home/user/bolt-cspgo/build-atfe/r35-counter-stair
cp "$ROOT/out/r35/counter/stair0.counters.bin"* "$V/"
export BASE=atfe TOOLCHAIN=/home/user/bolt-aarch32/build-atfe/bin
export VARIANTS_DIR="$V" BOLT_FUNC=bolt_bench_stair_kernel BOLT_PROFILE_MODE=edges
export SOURCE_REPLAY=/home/user/bolt-aarch32/out/r35-20261006/replay-final/replay.json
bash "$ROOT/scripts/bolt-variant.sh" optimize cspgo_thinlto "$V/stair0.counters.bin"
bash "$ROOT/scripts/check-no-fpu.sh" "$V/cspgo_thinlto_bolt.elf" > "$V/nofpu-optimized.log" 2>&1
cp "$V"/* "$ROOT/out/r35/counter/"
