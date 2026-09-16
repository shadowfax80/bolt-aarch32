# Shared CMake cache for building LLVM + Clang + LLD + BOLT from third_party/llvm-project.
# Usage:
#   cmake -G Ninja -S third_party/llvm-project/llvm -B build -C cmake/llvm-bolt.cmake

set(LLVM_ENABLE_PROJECTS "clang;bolt;lld" CACHE STRING "" FORCE)

# ARM: clang/lld target AArch32; BOLT backend enabled via overlay patches
# (0003–0007) adding ARM to BOLT_TARGETS_TO_BUILD. Every BOLT_TARGETS_TO_BUILD
# entry must also be in LLVM_TARGETS_TO_BUILD (bolt/CMakeLists.txt enforces
# this) -- RISCV was listed here without being enabled above; this project
# never builds or exercises a RISCV BOLT target, so dropped rather than
# added (found 2026-09-15: the existing cache predated this line and never
# hit the check until a from-scratch reconfigure during the bolt-aarch32 /
# atfe-bolt-aarch32 repo merge).
set(LLVM_TARGETS_TO_BUILD "X86;AArch64;ARM" CACHE STRING "" FORCE)
set(BOLT_TARGETS_TO_BUILD "AArch64;ARM;X86" CACHE STRING "" FORCE)

set(CMAKE_BUILD_TYPE "Release" CACHE STRING "" FORCE)

# Assertions ON: every llvm-bolt built and verified this project's whole
# history (per `llvm-bolt --version` => "Optimized build with assertions")
# has had them on -- this project's own defect-hunting (D1/D2/D4/D6 etc.)
# has repeatedly relied on an assertion firing rather than silently
# miscompiling. Keep them on despite the build-time/runtime cost.
set(LLVM_ENABLE_ASSERTIONS ON CACHE BOOL "" FORCE)

set(LLVM_USE_LINKER "lld" CACHE STRING "" FORCE)
set(LLVM_CCACHE_BUILD ON CACHE BOOL "" FORCE)
set(LLVM_BUILD_TOOLS ON CACHE BOOL "" FORCE)

# Builds libbolt_rt_instr.a for the HOST architecture only (x86_64 here). It cannot
# instrument AArch64 binaries; upstream cross-build support is still unmerged
# (llvm/llvm-project#187308). Phase 2 supplies its own bare-metal runtime via
# llvm-bolt --runtime-instrumentation-lib=. See docs/aarch64-bare-metal.md.
set(BOLT_ENABLE_RUNTIME ON CACHE BOOL "" FORCE)
