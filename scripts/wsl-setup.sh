#!/usr/bin/env bash
# Build the whole BOLT-on-Pi toolchain inside WSL2 (Ubuntu), for when RunPod has
# no CPU capacity. Run as the normal WSL user; the apt step uses `wsl -u root`
# from the Windows side (see below) because that user has no passwordless sudo.
#
#   wsl -d Ubuntu -u root -- bash /mnt/c/.../scripts/wsl-setup.sh deps
#   wsl -d Ubuntu          -- bash /mnt/c/.../scripts/wsl-setup.sh build
#
# `build` rsyncs the Windows checkout (uncommitted changes included) into
# ~/bolt-aarch32 on WSL's native filesystem -- building on /mnt/c is several times
# slower -- then fetches ATFE + LK, applies the overlay patches, and builds clang,
# lld, llvm-profdata, BOLT and the two bare-metal runtimes into ~/bolt-aarch32/build-atfe.
set -euo pipefail

SRC="$(cd "$(dirname "$0")/.." && pwd)"
# WSL_DEST overrides the build location (e.g. a from-scratch reproduction next to the
# everyday tree).
DEST="${WSL_DEST:-$HOME/bolt-aarch32}"

case "${1:-}" in
deps)
  export DEBIAN_FRONTEND=noninteractive
  apt-get update -qq
  apt-get install -y -qq build-essential cmake ninja-build python3 python3-venv git ccache \
    zlib1g-dev libxml2-dev libedit-dev libcurl4-openssl-dev lld clang curl ca-certificates \
    jq rsync qemu-system-arm libnewlib-arm-none-eabi
  echo "deps installed"
  ;;
build)
  mkdir -p "$DEST"
  # third_party and build outputs stay on the WSL side; they are gitignored anyway.
  rsync -a --delete --exclude build/ --exclude 'build-*/' --exclude third_party/ \
    --exclude legacy-archives/ --exclude __pycache__/ "$SRC"/ "$DEST"/
  cd "$DEST"
  # The Windows checkout can have CRLF line endings (git autocrlf); `git am` then
  # cannot match patch context and shell scripts break. Normalize the WSL copy only.
  find overlay scripts cmake docs -type f \( -name '*.patch' -o -name '*.sh' -o -name '*.py' \
    -o -name '*.mk' -o -name '*.c' -o -name '*.h' -o -name '*.cmake' -o -name '*.md' \) \
    -exec sed -i 's/\r$//' {} +
  export BASE=atfe CC=clang CXX=clang++
  ./scripts/fetch-sources.sh
  ./scripts/apply-overlays.sh
  source ./scripts/resolve-base.sh
  if [[ ! -f "$BUILD_DIR/build.ninja" ]]; then
    # 11-12 GB of RAM: cap concurrent links, they are the memory peak.
    cmake -G Ninja -S "$LLVM_DIR/llvm" -B "$BUILD_DIR" -C cmake/llvm-bolt.cmake \
      -DLLVM_PARALLEL_LINK_JOBS=2
  fi
  JOBS="${JOBS:-12}" ./scripts/build-llvm-bolt.sh
  ninja -C "$BUILD_DIR" -j"${JOBS:-12}" llvm-profdata
  ./scripts/build-bolt-rt-baremetal.sh
  ARCH=arm32 ./scripts/build-bolt-rt-baremetal.sh
  ./scripts/build-pgo-rt-baremetal.sh
  echo "WSL TOOLCHAIN BUILD COMPLETE"
  ;;
sync)
  # Push the current Windows checkout (edited overlay files, scripts) into the WSL
  # copy and re-install the overlay into third_party/lk. Cheap; no rebuild.
  rsync -a --delete --exclude build/ --exclude 'build-*/' --exclude third_party/ \
    --exclude legacy-archives/ --exclude __pycache__/ "$SRC"/ "$DEST"/
  cd "$DEST"
  find overlay scripts cmake docs -type f \( -name '*.patch' -o -name '*.sh' -o -name '*.py' \
    -o -name '*.mk' -o -name '*.c' -o -name '*.h' -o -name '*.cmake' -o -name '*.md' \) \
    -exec sed -i 's/\r$//' {} +
  BASE=atfe ./scripts/apply-overlays.sh >/dev/null
  echo "synced"
  ;;
*)
  echo "usage: $0 deps|build|sync" >&2
  exit 2
  ;;
esac
