//===- instr_baremetal.cpp - BOLT instrumentation runtime for bare metal --===//
//
// Freestanding stand-in for bolt/runtime/instr.cpp. Upstream's runtime is
// Linux-only: it mmaps MAP_FIXED over the counter pages, finds its own binary
// through /proc/self/map_files, and writes .fdata with open/write from a
// DT_FINI hook. LK has no syscalls, no /proc and no filesystem, so none of
// that survives the port.
//
// This library keeps only the symbol contract that llvm-bolt links against:
// RewriteInstance::linkRuntime() validates __bolt_instr_start and
// __bolt_instr_fini, redirects e_entry to the former and hooks the latter into
// DT_FINI. Counters stay in .bolt.instr.counters where BOLT emitted them,
// which on a bare-metal image is already loaded read-write, so setup has
// nothing to remap.
//
// Profile extraction happens off-target: scripts/dump-bolt-counters.py reads
// __bolt_instr_locations out of the running guest over the QEMU monitor. That
// keeps this file small enough to audit against the instrumentation pass.
// Serializing .fdata on-target (upstream's writeFunctionProfile path, with
// UART instead of a file descriptor) is the next step; see
// docs/aarch64-bare-metal.md.
//
//===----------------------------------------------------------------------===//

#if !defined(__aarch64__)
#error "the bare-metal BOLT runtime is AArch64-only"
#endif

#include <stdint.h>

// Emitted into the instrumented binary by InstrumentationRuntimeLibrary.
extern "C" uint64_t __bolt_instr_locations[];
extern "C" uint32_t __bolt_num_counters;

// Injected by Instrumentation::createAuxiliaryFunctions. The trampolines hold
// the original entry point and DT_FINI target.
extern "C" void __bolt_start_trampoline();
extern "C" void __bolt_fini_trampoline();

// Mirrors bolt/runtime/sys_aarch64.h. The instrumented binary reaches us
// through plain branches, not a call boundary, so every register and NZCV has
// to survive the detour.
#define SAVE_ALL                                                               \
  "stp x0, x1, [sp, #-16]!\n"                                                  \
  "stp x2, x3, [sp, #-16]!\n"                                                   \
  "stp x4, x5, [sp, #-16]!\n"                                                   \
  "stp x6, x7, [sp, #-16]!\n"                                                   \
  "stp x8, x9, [sp, #-16]!\n"                                                   \
  "stp x10, x11, [sp, #-16]!\n"                                                 \
  "stp x12, x13, [sp, #-16]!\n"                                                 \
  "stp x14, x15, [sp, #-16]!\n"                                                 \
  "stp x16, x17, [sp, #-16]!\n"                                                 \
  "stp x18, x19, [sp, #-16]!\n"                                                 \
  "stp x20, x21, [sp, #-16]!\n"                                                 \
  "stp x22, x23, [sp, #-16]!\n"                                                 \
  "stp x24, x25, [sp, #-16]!\n"                                                 \
  "stp x26, x27, [sp, #-16]!\n"                                                 \
  "stp x28, x29, [sp, #-16]!\n"                                                 \
  "mrs x29, nzcv\n"                                                            \
  "stp x29, x30, [sp, #-16]!\n"

#define RESTORE_ALL                                                            \
  "ldp x29, x30, [sp], #16\n"                                                  \
  "msr nzcv, x29\n"                                                            \
  "ldp x28, x29, [sp], #16\n"                                                  \
  "ldp x26, x27, [sp], #16\n"                                                  \
  "ldp x24, x25, [sp], #16\n"                                                  \
  "ldp x22, x23, [sp], #16\n"                                                  \
  "ldp x20, x21, [sp], #16\n"                                                  \
  "ldp x18, x19, [sp], #16\n"                                                  \
  "ldp x16, x17, [sp], #16\n"                                                  \
  "ldp x14, x15, [sp], #16\n"                                                  \
  "ldp x12, x13, [sp], #16\n"                                                  \
  "ldp x10, x11, [sp], #16\n"                                                  \
  "ldp x8, x9, [sp], #16\n"                                                    \
  "ldp x6, x7, [sp], #16\n"                                                    \
  "ldp x4, x5, [sp], #16\n"                                                    \
  "ldp x2, x3, [sp], #16\n"                                                    \
  "ldp x0, x1, [sp], #16\n"

extern "C" void __bolt_instr_setup() {
  // Upstream mmaps anonymous read-write pages MAP_FIXED over the counter array
  // so that forked children can share them. A bare-metal image loads
  // .bolt.instr.counters as ordinary writable data and there is no second
  // process, so the array is usable as linked.
}

// e_entry points here. Run setup with the boot state intact, then fall through
// to the entry point BOLT displaced.
extern "C" __attribute__((naked)) void __bolt_instr_start() {
  __asm__ __volatile__(SAVE_ALL "bl __bolt_instr_setup\n" RESTORE_ALL
                       "adrp x16, __bolt_start_trampoline\n"
                       "add x16, x16, #:lo12:__bolt_start_trampoline\n"
                       "br x16\n" :::);
}

// LK never runs DT_FINI, so this exists to satisfy the link and to keep the
// original fini reachable if the harness ever calls it. Upstream would dump
// the profile here; on bare metal the dump is triggered explicitly instead.
extern "C" __attribute__((naked)) void __bolt_instr_fini() {
  __asm__ __volatile__("adrp x16, __bolt_fini_trampoline\n"
                       "add x16, x16, #:lo12:__bolt_fini_trampoline\n"
                       "br x16\n" :::);
}

extern "C" void __bolt_instr_clear_counters() {
  for (uint32_t I = 0; I < __bolt_num_counters; ++I)
    __bolt_instr_locations[I] = 0;
}

// Kept as a debugger-callable no-op: the host reads the counter array directly.
extern "C" void __bolt_instr_data_dump() {}

// Only reachable when the binary is instrumented with call counting. The
// handler stubs BOLT generates push their arguments and restore the stack
// themselves, so returning immediately leaves indirect calls uncounted but
// correct. Build with --instrument-calls=false to drop the stubs entirely.
extern "C" __attribute__((naked)) void __bolt_instr_indirect_call() {
  __asm__ __volatile__("ret\n" :::);
}

extern "C" __attribute__((naked)) void __bolt_instr_indirect_tailcall() {
  __asm__ __volatile__("ret\n" :::);
}
