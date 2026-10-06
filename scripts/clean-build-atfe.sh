#!/usr/bin/env bash
# Clean, isolated full build of the ATFE overlay series (HANDOFF item 14).
#
#   scripts/clean-build-atfe.sh <out-dir> [on|off ...]     (default: on off)
#
# Never touches the live tree (third_party/llvm-project-atfe, build-atfe*):
#   1. fetches the pinned ATFE commit from its remote into <out-dir>/src;
#   2. applies overlay/llvm/patches/atfe/*.patch in order with `git apply`;
#   3. records the git tree hash of the result (full source identity);
#   4. configures each mode from cmake/llvm-bolt.cmake with the host
#      compilers (CC/CXX, default clang/clang++), the only mode override
#      being LLVM_ENABLE_ASSERTIONS=OFF for `off`; ccache is bypassed
#      (CCACHE_DISABLE=1) so no object comes from an earlier build;
#   5. builds the targets of build-llvm-bolt.sh plus bolt-test-depends and
#      the bare-metal ARM BOLT runtime, and runs the ARM BOLT lit suite.
# scripts/build-provenance.py then binds source, config, tools and outputs.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT="${1:?usage: clean-build-atfe.sh <out-dir> [on|off ...]}"
shift
MODES=("$@")
[[ ${#MODES[@]} -gt 0 ]] || MODES=(on off)
BASE=atfe
source "$ROOT/scripts/resolve-base.sh"
JOBS="${JOBS:-$(nproc)}"
SRC="$OUT/src"
mkdir -p "$OUT"
OUT="$(cd "$OUT" && pwd)"
SRC="$OUT/src"
case "$OUT/" in "$ROOT/"*) echo "error: <out-dir> must be outside $ROOT" >&2; exit 2;; esac

if [[ ! -f "$OUT/source-tree.txt" ]]; then
  rm -rf "$SRC"   # an interrupted fetch or apply starts over
  git init -q "$SRC"
  git -C "$SRC" remote add origin "$LLVM_REMOTE"
  git -C "$SRC" fetch -q --depth=1 origin "$LLVM_COMMIT"
  git -C "$SRC" checkout -q --detach FETCH_HEAD
  [[ "$(git -C "$SRC" rev-parse HEAD)" == "$LLVM_COMMIT" ]] || { echo "error: fetched HEAD is not the pin" >&2; exit 1; }
  for p in "$PATCH_DIR"/*.patch; do
    git -C "$SRC" apply --whitespace=nowarn "$p" || { echo "error: $p does not apply" >&2; exit 1; }
  done
  git -C "$SRC" add -A
  git -C "$SRC" write-tree > "$OUT/source-tree.txt"
fi
echo "source tree: $(cat "$OUT/source-tree.txt")"

for mode in "${MODES[@]}"; do
  case "$mode" in on) assert=ON;; off) assert=OFF;; *) echo "error: mode $mode" >&2; exit 2;; esac
  B="$OUT/build-$mode"
  if [[ ! -f "$B/build.ninja" ]]; then
    # cmake/llvm-bolt.cmake does not choose the host compiler; the live
    # builds were configured with clang/clang++, so name them explicitly.
    cmake -G Ninja -S "$SRC/llvm" -B "$B" -C "$ROOT/cmake/llvm-bolt.cmake" \
      -DCMAKE_C_COMPILER="$(command -v "${CC:-clang}")" \
      -DCMAKE_CXX_COMPILER="$(command -v "${CXX:-clang++}")" \
      -DLLVM_ENABLE_ASSERTIONS=$assert -DLLVM_PARALLEL_LINK_JOBS=2 > "$OUT/configure-$mode.log"
  fi
  CCACHE_DISABLE=1 ninja -C "$B" -j"$JOBS" \
    clang lld bolt bolt_rt \
    llvm-objdump llvm-readelf llvm-objcopy llvm-nm llvm-strip llvm-ar llvm-cxxfilt \
    bolt-test-depends > "$OUT/build-$mode.log"
  # The ARM instrumentation tests link the bare-metal runtime, built here
  # with this build's own clang.
  ARCH=arm32 TOOLCHAIN="$B/bin" OUT_DIR="$B/bolt-rt-baremetal-arm" \
    "$ROOT/scripts/build-bolt-rt-baremetal.sh" >> "$OUT/build-$mode.log"
  "$B/bin/llvm-lit" -sv "$B/tools/bolt/test/ARM" > "$OUT/lit-$mode.log" 2>&1 || true
  tail -3 "$OUT/lit-$mode.log"
done
