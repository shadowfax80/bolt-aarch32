#!/usr/bin/env bash
# Build the Secure-SVC armstub for the Pi 4 (32-bit, GIC), same defines and
# link address as upstream's armstub8-32-gic.bin. No FPU/NEON instructions.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
TC="${TOOLCHAIN_BIN:-/home/user/bolt-aarch32/build-atfe/bin}"
OUT="$HERE/out"; mkdir -p "$OUT"
"$TC/clang" --target=armv7a-none-eabi -mfpu=none -DGIC=1 -DBCM2710=1 -DBCM2711=1 \
  -c "$HERE/armstub7-secure.S" -o "$OUT/armstub7-secure.o"
"$TC/ld.lld" --image-base=0 --section-start=.init=0 "$OUT/armstub7-secure.o" -o "$OUT/armstub7-secure.elf"
"$TC/llvm-objcopy" -O binary "$OUT/armstub7-secure.elf" "$OUT/armstub8-32-gic-secure.bin"
NOFPU_TOOLCHAIN="$TC" bash "$HERE/../../scripts/check-no-fpu.sh" "$OUT/armstub7-secure.elf"
sha256sum "$OUT/armstub8-32-gic-secure.bin"
