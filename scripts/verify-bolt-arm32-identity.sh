#!/usr/bin/env bash
# Scoped identity rewrite of selected bolt_bench functions in QEMU.
#
# With a reviewed qemu-virt oracle contract for the input image this runs the
# certifying route (qemu_rewrite_build.py: fresh evidence, live entry-pair
# traces, independent sinks). QEMU is a debug aid (6a, user decision
# 2026-10-04) and no such contract exists by default, so otherwise it runs a
# labelled DIAGNOSTIC: rewrite + redirect in a fresh directory, then
# baseline/candidate output consistency. Certification is Pi-only
# (scripts/pi4/full_image_verify.py, scripts/pi4/smp_verify.py).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TOOLCHAIN="${TOOLCHAIN:-$ROOT/build-${BASE:-upstream}/bin}"
LK_PROJECT="${LK_PROJECT:-qemu-virt-arm32-bolt-test}"
ELF="${ELF:-$ROOT/third_party/lk/build-$LK_PROJECT/lk.elf}"
QEMU="${QEMU:-qemu-system-arm}"
OUT_DIR="${OUT_DIR:-$ROOT/out/arm32-identity}"
BOLT_BENCH_FUNCS="${BOLT_BENCH_FUNCS:-bolt_bench_hot_loop,bolt_bench_hot_cold,bolt_bench_branch_chain,bolt_bench_memcpy}"
if [[ "${BOOT_REWRITTEN:-1}" != 1 || "${BENCH_CMDLINE:-lk.bolt_bench=all}" != lk.bolt_bench=all ]]; then
  echo "error: identity execution gate requires live boot and the complete workload" >&2
  exit 1
fi
# Never rebuild by default: build-lk-aarch32.sh re-applies overlays, which must
# not run on a dirty live tree.
if [[ "${REBUILD_LK:-0}" == 1 || ! -f "$ELF" ]]; then
  BOLT_BENCH_ISA="${BOLT_BENCH_ISA:-}" "$ROOT/scripts/build-lk-aarch32.sh"
fi

if python3 - "$ELF" "$ROOT/scripts" <<'PY'
import hashlib, sys
sys.path.insert(0, sys.argv[2])
from qemu_bench_oracle import CONTRACTS
h = hashlib.sha256(open(sys.argv[1], 'rb').read()).hexdigest()
sys.exit(0 if CONTRACTS.get(h, {}).get('platform') == 'qemu-virt' else 1)
PY
then
  python3 "$ROOT/scripts/qemu_rewrite_build.py" --elf "$ELF" --toolchain "$TOOLCHAIN" \
    --funcs "$BOLT_BENCH_FUNCS" --qemu "$QEMU" --out "$OUT_DIR" --timeout 120
  exit 0
fi

# BOLT's new code must land in memory LK never reuses. Without a linked,
# protected window it is placed after _end and LK's heap overwrites it at
# runtime (seen: "unhandled syscall" inside the rewritten copy). Fail closed.
if ! "$TOOLCHAIN/llvm-nm" "$ELF" | grep -q ' __bolt_reserved_start$'; then
  echo "error: $ELF has no protected BOLT window (__bolt_reserved_start/end);" >&2
  echo "       rewritten code would be overwritten at runtime. Use the Pi route" >&2
  echo "       (scripts/pi4/full_image_build.py + full_image_verify.py)." >&2
  exit 1
fi
mkdir -p "$OUT_DIR"
RUN="$(mktemp -d "$OUT_DIR/diag-XXXXXX")"
RUN="$(cd "$RUN" && pwd)"
echo "run directory: $RUN (no qemu-virt contract for this image: diagnostic route)"
cp "$ELF" "$RUN/original.elf"
"$TOOLCHAIN/llvm-bolt" "$RUN/original.elf" --funcs="$BOLT_BENCH_FUNCS" --no-huge-pages \
  --emit-function-map="$RUN/functions.map" -o "$RUN/candidate.elf" > "$RUN/bolt.log" 2>&1
python3 "$ROOT/scripts/fix-kernel-elf-sections.py" "$RUN/candidate.elf" --original "$RUN/original.elf" \
  --readelf "$TOOLCHAIN/llvm-readelf" > "$RUN/fix.log" 2>&1
python3 "$ROOT/scripts/redirect-bolt-entries.py" "$RUN/candidate.elf" --original "$RUN/original.elf" \
  --map "$RUN/functions.map" --func "$BOLT_BENCH_FUNCS" --toolchain "$TOOLCHAIN" \
  --report "$RUN/redirect.json" > "$RUN/redirect.log" 2>&1
python3 "$ROOT/scripts/qemu_workload_gate.py" --diagnostic --elf "$RUN/original.elf" \
  --candidate "$RUN/candidate.elf" --qemu "$QEMU" --out "$RUN/run" --timeout 120
echo "DIAGNOSTIC ONLY: identity rewrite output consistency in QEMU; not a certificate."
echo "Certification is Pi-only (scripts/pi4/full_image_verify.py, scripts/pi4/smp_verify.py)."
