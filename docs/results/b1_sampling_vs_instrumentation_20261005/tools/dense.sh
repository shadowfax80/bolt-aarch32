#!/usr/bin/env bash
set -euo pipefail
S=/mnt/c/Users/User/AppData/Local/Temp/claude/C--Users-User-CURSOR-ClaudeProjects-BOLT-AARCH32/f74ad4de-0e6e-4cd3-b5e9-3b0b9c5bc80c/scratchpad/b1/whole
cd /home/user/bolt-b1
V=build-atfe/variants; TC=build-atfe/bin
cp "$S/whole_a.dense.samples" "$S/whole_a.dense.samples.manifest.json" "$V/"
python3 scripts/samples_to_fdata.py "$V/whole_a.elf" "$V/whole_a.dense.samples" -o "$V/whole_a.dense.fdata" \
  --toolchain "$TC" --functions bolt_bench_composite --skip-funcs "$(cat out/whole_a.skips.txt)" | tail -1
echo "dense composite: $(($(wc -l < "$V/whole_a.dense.fdata") - 1)) locations, $(awk 'NR>1{s+=$4} END{print s}' "$V/whole_a.dense.fdata") samples"
rm -rf out/whole/r2d_dense
BOLT_WORKSPACE=/home/user/bolt-b1 python3 scripts/pi4/full_image_build.py out/whole/r2d_dense --input "$V/whole_a.elf" \
  --toolchain "$TC" --profile "$V/whole_a.dense.fdata" --redirect-functions bolt_bench_composite \
  -- -skip-funcs="$(cat out/whole_a.skips.txt)" | tail -1
cp out/whole/r2d_dense/baseline_full.bin "$S/img/r2d_lkperf_dense.bin"
