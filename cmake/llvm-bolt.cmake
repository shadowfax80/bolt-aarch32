# Shared CMake cache for building LLVM + Clang + LLD + BOLT from third_party/llvm-project.
# Usage:
#   cmake -G Ninja -S third_party/llvm-project/llvm -B build -C cmake/llvm-bolt.cmake

set(LLVM_ENABLE_PROJECTS "clang;bolt;lld" CACHE STRING "" FORCE)

# ARM: clang/lld target AArch32; BOLT backend enabled via overlay patches
# (0003–0007) adding ARM to BOLT_TARGETS_TO_BUILD.
set(LLVM_TARGETS_TO_BUILD "X86;AArch64;ARM" CACHE STRING "" FORCE)
set(BOLT_TARGETS_TO_BUILD "AArch64;ARM;X86;RISCV" CACHE STRING "" FORCE)

set(CMAKE_BUILD_TYPE "Release" CACHE STRING "" FORCE)

# Assertions cost build time and slow llvm-bolt down. This is a consumed toolchain,
# not an LLVM development build; turn them on only when debugging BOLT itself.
set(LLVM_ENABLE_ASSERTIONS OFF CACHE BOOL "" FORCE)

set(LLVM_USE_LINKER "lld" CACHE STRING "" FORCE)
set(LLVM_CCACHE_BUILD ON CACHE BOOL "" FORCE)
set(LLVM_BUILD_TOOLS ON CACHE BOOL "" FORCE)

# Builds libbolt_rt_instr.a for the HOST architecture only (x86_64 here). It cannot
# instrument AArch64 binaries; upstream cross-build support is still unmerged
# (llvm/llvm-project#187308). Phase 2 supplies its own bare-metal runtime via
# llvm-bolt --runtime-instrumentation-lib=. See docs/aarch64-bare-metal.md.
set(BOLT_ENABLE_RUNTIME ON CACHE BOOL "" FORCE)
