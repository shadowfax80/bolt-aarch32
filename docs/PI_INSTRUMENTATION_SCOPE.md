# Supported AArch32 instrumentation contract

Direct ARM32 instrumentation must pass:

```text
--arm-instrumentation-contract=privileged-single-core-no-fiq
--instrument-calls=false
```

The contract acknowledges privileged execution, one participating core and
FIQ disabled throughout measured execution. Inline updates use privileged
CPSID/MSR, mask IRQ across the full-width increment and restore the original
CPSR. They are not multicore atomic operations. Reset and counter reads must
occur while all measured execution is quiescent; the clear routine itself
does not establish quiescence. There is no automatic profile writer in the
bare-metal runtime. The sleep-time option remains a linker requirement for
static input, and does not start a bare-metal periodic writer.

The compiler requires caller acknowledgement; ELF metadata cannot prove these
runtime properties. Shared/dynamic inputs, call/indirect-call profiling and
process/fork options are rejected before output. For the LK wrapper, set:

```sh
BASE=atfe ARCH=arm32 ARM_INSTRUMENTATION_CONTRACT=privileged-single-core-no-fiq scripts/instrument-lk-bolt.sh
```

Establish the environment before acknowledging it. The isolated Pi count
fixture checks CPSR, MPIDR and stack alignment before/after every measured
call. Its loader parks secondary cores. MPIDR proves the executing core's
identity; it does not independently prove that other cores are parked.

The current hardware matrix runs quiet, with IRQ/FIQ disabled. Quiet nested
Thumb calls and recursion are verified; active ISR and mixed-ISA nested state,
exclusive-memory insertion, concurrent resets and live snapshots remain open.
No supported SMP/FIQ/userspace claim follows from supplying the contract flag.

See [evidence](results/correctness_instrumentation_scope_20261002.json).
