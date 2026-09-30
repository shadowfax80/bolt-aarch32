#!/usr/bin/env bash
# Build the chainloader images with the ATFE clang (run inside WSL):
#   kernel7l_fast.img        real Pi 4B chainloader with the 3 Mbaud fast mode (the deliverable)
#   kernel7l_orig.img        lk-perf's unmodified chainloader built with the same toolchain
#                            (a sanity check of the toolchain, not for the SD card)
#   kernel7l_fast_qemu.elf   fast-mode variant for QEMU raspi2b (protocol test only)
# No FPU/NEON: -mfpu=none, verified with scripts/check-no-fpu.sh.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
TC="${TOOLCHAIN:-$HOME/bolt-aarch32/build-atfe/bin}"
OUT="${OUT:-$HERE/out}"
mkdir -p "$OUT"
python3 "$HERE/patch_main.py" >/dev/null

CF=(--target=arm-none-eabi -mcpu=cortex-a72 -marm -mfpu=none -mfloat-abi=soft
    -ffreestanding -nostdlib -fno-builtin -fno-unwind-tables -fno-asynchronous-unwind-tables
    -O2 -Wall -Wextra)

build() { # name main.c extra-flags...
  local name="$1" src="$2"; shift 2
  "$TC/clang" "${CF[@]}" "$@" -c "$HERE/start.S" -o "$OUT/$name.start.o"
  "$TC/clang" "${CF[@]}" "$@" -x c -c "$src" -o "$OUT/$name.main.o"
  "$TC/ld.lld" -T "$HERE/linker.ld" "$OUT/$name.start.o" "$OUT/$name.main.o" -o "$OUT/$name.elf"
  "$TC/llvm-objcopy" -O binary "$OUT/$name.elf" "$OUT/$name.img"
}

build kernel7l_fast "$HERE/main.c"
build kernel7l_orig "$HERE/main.c.orig"
build kernel7l_fast_qemu "$HERE/main.c" -DPLATFORM_QEMU_RPI2

"$ROOT/scripts/check-no-fpu.sh" "$OUT/kernel7l_fast.elf" "$OUT/kernel7l_orig.elf"
ls -l "$OUT"/*.img "$OUT/kernel7l_fast_qemu.elf"
