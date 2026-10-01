#!/usr/bin/env bash
# Whole-image emission with explicit, scoped redirects; not a hardware pass.
# Usage: full_image_wsl.sh OUTDIR --redirect-functions NAME[,NAME...] [--input ELF]
#        [--toolchain DIR] [-- extra llvm-bolt options]
# Follow with full_image_verify.py on the Pi host. Outputs stay in OUTDIR.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
exec python3 "$HERE/full_image_build.py" "$@"
