# Shared CMake cache for building LLVM + Clang + LLD + BOLT from third_party/llvm-project.
# Usage:
#   cmake -G Ninja -S third_party/llvm-project/llvm -B build -C cmake/llvm-bolt.cmake

set(LLVM_ENABLE_PROJECTS "clang;bolt;lld" CACHE STRING "" FORCE)
set(LLVM_TARGETS_TO_BUILD "X86;AArch64;ARM" CACHE STRING "" FORCE)
set(CMAKE_BUILD_TYPE "Release" CACHE STRING "" FORCE)
set(LLVM_ENABLE_ASSERTIONS ON CACHE BOOL "" FORCE)
set(LLVM_USE_LINKER "lld" CACHE STRING "" FORCE)
set(LLVM_CCACHE_BUILD ON CACHE BOOL "" FORCE)
set(LLVM_BUILD_TOOLS ON CACHE BOOL "" FORCE)
