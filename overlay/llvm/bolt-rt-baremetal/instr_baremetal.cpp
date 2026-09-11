// e_entry points here. A kernel image reaches us at reset, before any
// stack exists, so spilling the register file the way the Linux runtime
// does would fault on the first stp. Setup is empty on bare metal (the
// counter array is already writable), so just transfer to the entry
// point BOLT displaced.
extern "C" __attribute__((naked)) void __bolt_instr_start() {
  __asm__ __volatile__("adrp x16, __bolt_start_trampoline\n"
                       "add x16, x16, #:lo12:__bolt_start_trampoline\n"
                       "br x16\n" :::);
}