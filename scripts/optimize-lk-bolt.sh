#!/usr/bin/env bash
# Apply BOLT layout optimizations to LK using a host-generated .fdata profile.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TOOLCHAIN="${TOOLCHAIN:-$ROOT/build/bin}"
LK_DIR="${LK_DIR:-$ROOT/third_party/lk}"
ELF="${ELF:-$LK_DIR/build-qemu-virt-arm64-test/lk.elf}"
FDATA="${FDATA:-$ROOT/build/prof.fdata}"
OUT="${OUT:-$ROOT/build/lk.bolt.elf}"

if [[ ! -f "$ELF" ]]; then
  echo "error: $ELF not found — run scripts/build-lk-aarch64.sh" >&2
  exit 1
fi
if [[ ! -s "$FDATA" ]]; then
  echo "error: $FDATA missing or empty — run ram-dump-to-fdata first" >&2
  exit 1
fi

mkdir -p "$(dirname "$OUT")"

"$TOOLCHAIN/llvm-bolt" "$ELF" \
  -data="$FDATA" \
  -o "$OUT" \
  --no-lse-atomics \
  -reorder-blocks=ext-tsp \
  -reorder-functions=hfsort+ \
  "$@"

python3 "$ROOT/scripts/fix-kernel-elf-paddr.py" "$OUT"
python3 "$ROOT/scripts/fix-kernel-elf-entry.py" "$OUT" --original "$ELF" \
  --readelf "$TOOLCHAIN/llvm-readelf"
python3 "$ROOT/scripts/fix-kernel-elf-sections.py" "$OUT" --original "$ELF" \
  --readelf "$TOOLCHAIN/llvm-readelf"

echo "optimized image: $OUT"
