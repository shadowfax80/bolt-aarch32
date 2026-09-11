# Phase 1: BOLT on LK AArch64 (QEMU)

## Goal

Prove BOLT instrumentation and re-optimization on **Little Kernel** running bare-metal in QEMU `virt`, with profile data collected **in RAM** (not via Linux `perf`).

## Pipeline

1. Build LK `qemu-virt-arm64-test` with `--emit-relocs` (`-Wl,-q`)
2. `llvm-bolt lk.elf -instrument -o lk.instr.elf` (use `--no-lse-atomics` for QEMU `cortex-a53`)
3. Place instrumentation counters in a linker-script RAM section (`overlay/lk/patches/`)
4. Boot in QEMU, run workload, dump counter region → host `.fdata`
5. `llvm-bolt lk.elf -o lk.bolt.elf -data=prof.fdata ...`
6. Boot optimized LK and verify

## Why not stock bolt-rt?

`bolt/runtime/instr.cpp` writes `/tmp/prof.fdata` using Linux syscalls. LK has no filesystem. Overlay patches will redirect profile emission to a fixed RAM buffer.
