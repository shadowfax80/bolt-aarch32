# Supported AArch32 instrumentation contract

Follow-up 2026-10-03: overlay 0039 closes the 0038 unnamed interior-entry
reservation bypass for decoded original code. Every decoded acquisition is
analyzed independently of entry metadata; unanalyzed stores reject. Other
ISA/entry/runtime caveats below remain. See
[evidence](results/correctness_interior_reservations_20261003.json).

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
runtime properties. Genuine shared-object inputs, call/indirect-call profiling
and process/fork options have rejection tests. Static PIE is a freshly reproduced
exception: it is admitted while generated absolute pointers lack rebasing
relocations. Treat it as unsupported until the fixed-load/PIE boundary is fixed.
For the LK wrapper, set:

```sh
BASE=atfe ARCH=arm32 ARM_INSTRUMENTATION_CONTRACT=privileged-single-core-no-fiq scripts/instrument-lk-bolt.sh
```

Establish the environment before acknowledging it. The isolated Pi count
fixture checks CPSR, MPIDR and stack alignment before/after every measured
call. Its loader parks secondary cores. MPIDR proves the executing core's
identity; it does not independently prove that other cores are parked.

The current hardware matrix runs quiet, with IRQ/FIQ disabled. Quiet nested
Thumb calls and recursion are verified; active ISR and mixed-ISA nested state,
concurrent resets and live snapshots remain open. Overlay 0037 rejects selected
exclusive functions; local overlay 0038 requires reservations in decoded skipped
callers to stay within their function, rejecting live calls/exits and unmodeled
boundaries before instrumentation. Known multiple entries reject conservatively.
The 0038 review reproduced an unnamed interior-entry bypass in skipped exclusive
code; 0039's acquisition-rooted gate now rejects those inputs. General ISA/entry/symbol admission remains
open. Thumb-entry instrumentation also crashes; ARMv6 input receives unsupported
generated instructions. Both host modes pass the scoped
boundary tests; supported Pi fixture bytes match previous execution evidence.
No new hardware reservation-failure reproduction is claimed. See
[cross-function evidence](results/correctness_cross_function_exclusive_20261002.json).

See [current caveats](CORRECTNESS_REVIEW_0038.md) and
[ordered closure tasks](CORRECTNESS_PRIORITY_TODO.md) before broader use.
No supported SMP/FIQ/userspace claim follows from supplying the contract flag.

See [evidence](results/correctness_instrumentation_scope_20261002.json).
