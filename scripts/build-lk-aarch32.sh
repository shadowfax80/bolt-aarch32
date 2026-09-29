#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
CLANG_BINDIR="${CLANG_BINDIR:-${TOOLCHAIN:-$ROOT/build-${BASE:-upstream}/bin}}"
LK_PROJECT="${LK_PROJECT:-qemu-virt-arm32-test}"

if [[ ! -x "$CLANG_BINDIR/clang" ]]; then
  echo "error: build toolchain first ($CLANG_BINDIR/clang missing)" >&2
  exit 1
fi

"$ROOT/scripts/ensure-lk-source.sh"
"$ROOT/scripts/apply-overlays.sh"

cd "$ROOT/third_party/lk"

export TOOLCHAIN=clang
export CLANG_BINDIR
export LD=ld.lld
export PATH="$CLANG_BINDIR:$PATH"

MAKE_ARGS=()
if [[ -n "${BOLT_BENCH_ISA:-}" ]]; then
  MAKE_ARGS+=("BOLT_BENCH_ISA=$BOLT_BENCH_ISA")
fi
if [[ "${WITH_BOLT_PGO:-}" == "true" ]]; then
  MAKE_ARGS+=("WITH_BOLT_PGO=true")
  PGO_RT_LIB="${PGO_RT_LIB:-$ROOT/build-${BASE:-upstream}/pgo-rt-baremetal-arm/libpgo_rt_baremetal.a}"
  if [[ ! -f "$PGO_RT_LIB" ]]; then
    echo "error: $PGO_RT_LIB not found — run scripts/build-pgo-rt-baremetal.sh first" >&2
    exit 1
  fi
  MAKE_ARGS+=("EXTRA_OBJS=$PGO_RT_LIB")
fi
# LK's build.mk resolves SIZE via TOOLCHAIN_PREFIX (arm-eabi-size) even under
# TOOLCHAIN=clang, unlike its other post-link tools. No arm-eabi- binutils are
# installed here (this project only uses clang/lld), so default to the host's
# generic `size` — it reads any ELF's section headers fine regardless of arch.
MAKE_ARGS+=("SIZE=${SIZE:-size}")

make "$LK_PROJECT" "${MAKE_ARGS[@]}" -j"${JOBS:-$(nproc)}"

echo "LK ARM32 build complete: build-$LK_PROJECT/lk.elf"
