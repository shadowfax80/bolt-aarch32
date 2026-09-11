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
// __bolt_instr_locations out of the running guest over the QEMU monitor.
//===----------------------------------------------------------------------===//

#if !defined(__aarch64__)
#error "the bare-metal BOLT runtime is AArch64-only"
#endif

#include <stdint.h>

extern "C" uint64_t __bolt_instr_locations[];
extern "C" uint32_t __bolt_num_counters;

extern "C" void __bolt_start_trampoline();
extern "C" void __bolt_fini_trampoline();

extern "C" void __bolt_instr_setup() {
  // Upstream mmaps anonymous read-write pages MAP_FIXED over the counter array
  // so that forked children can share them. A bare-metal image loads
  // .bolt.instr.counters as ordinary writable data and there is no second
  // process, so the array is usable as linked.
}

// e_entry points here. A kernel image reaches us at reset, before any stack
// exists, so spilling the register file the way the Linux runtime does would
// fault on the first stp. Setup is empty on bare metal, so this is a tail
// call to the entry point BOLT displaced.
extern "C" __attribute__((naked)) void __bolt_instr_start() {
  __asm__ __volatile__("adrp x16, __bolt_start_trampoline\n"
                       "add x16, x16, #:lo12:__bolt_start_trampoline\n"
                       "br x16\n" :::);
}

extern "C" __attribute__((naked)) void __bolt_instr_fini() {
  __asm__ __volatile__("adrp x16, __bolt_fini_trampoline\n"
                       "add x16, x16, #:lo12:__bolt_fini_trampoline\n"
                       "br x16\n" :::);
}

extern "C" void __bolt_instr_clear_counters() {
  for (uint32_t I = 0; I < __bolt_num_counters; ++I)
    __bolt_instr_locations[I] = 0;
}

extern "C" void __bolt_instr_data_dump() {}

extern "C" __attribute__((naked)) void __bolt_instr_indirect_call() {
  __asm__ __volatile__("ret\n" :::);
}

extern "C" __attribute__((naked)) void __bolt_instr_indirect_tailcall() {
  __asm__ __volatile__("ret\n" :::);
}
