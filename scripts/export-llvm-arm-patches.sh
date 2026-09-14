#!/usr/bin/env bash
# Export the volume llvm-project ARM backend delta into overlay/llvm/patches/.
# Run on the pod from the overlay repo root.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
LLVM="${LLVM:-$ROOT/third_party/llvm-project}"
DEST="${DEST:-$ROOT/overlay/llvm/patches}"

if [[ ! -d "$LLVM/.git" ]]; then
  echo "error: $LLVM is not a git checkout" >&2
  exit 1
fi

export_one() {
  local name="$1"
  shift
  git -C "$LLVM" diff HEAD -- "$@" > "$DEST/$name"
  echo "wrote $DEST/$name ($(wc -l < "$DEST/$name") lines)"
}

export_one 0003-bolt-arm-elf32-and-target.patch \
  bolt/CMakeLists.txt \
  bolt/include/bolt/Core/BinaryContext.h \
  bolt/include/bolt/Core/BinaryFunction.h \
  bolt/lib/Core/BinaryContext.cpp \
  bolt/lib/Core/BinaryFunction.cpp

export_one 0004-bolt-arm-mcplusbuilder.patch \
  bolt/include/bolt/Core/MCPlusBuilder.h \
  bolt/lib/Target/ARM/ARMMCPlusBuilder.cpp \
  bolt/lib/Target/ARM/ARMMCSymbolizer.cpp \
  bolt/lib/Target/ARM/ARMMCSymbolizer.h \
  bolt/lib/Target/ARM/CMakeLists.txt

export_one 0005-bolt-arm-relocations.patch \
  bolt/lib/Core/Relocation.cpp

export_one 0006-bolt-arm-rewrite-dispatch.patch \
  bolt/include/bolt/Rewrite/RewriteInstance.h \
  bolt/lib/Rewrite/RewriteInstance.cpp

export_one 0007-bolt-arm-lit-tests.patch \
  bolt/test/ARM

export_one 0008-jitlink-arm-generic-archkind.patch \
  llvm/lib/ExecutionEngine/JITLink/ELF_aarch32.cpp

export_one 0009-bolt-arm-longjmp-veneers.patch \
  bolt/lib/Passes/LongJmp.cpp \
  bolt/lib/Passes/VeneerElimination.cpp \
  bolt/lib/Rewrite/BinaryPassManager.cpp

echo "ARM overlay patches refreshed from $LLVM"
