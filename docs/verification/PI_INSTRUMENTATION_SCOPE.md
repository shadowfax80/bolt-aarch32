# Supported AArch32 instrumentation contract

Current declared contracts (see [HANDOFF.md](../HANDOFF.md)):

| Option value | Participating cores | Counter path |
|---|---|---|
| `privileged-single-core-no-fiq` | One | Original inline full-width increment |
| `privileged-smp-no-fiq` | Multiple | Overlay 0060's A32 LDREXD/STREXD helper |

Both require privileged execution, no FIQ and `--instrument-calls=false`.
Reset and snapshot require quiescence; neither flag establishes it. The SMP
receipt covers the declared four-core Pi workload/counter model. Active IRQ
reentrancy, wider entry/runtime matrices and clean provenance remain bounded
by HANDOFF's open items. User mode and FIQ are unsupported.

Conditional returns (0073/R35) now have explicit return and continuation
blocks for uniform, flag-invariant Thumb IT groups and safe predecessor-based
A32 shapes. [R35 evidence](../results/r35_conditional_returns_20261006/README.md)
verifies the C1 Thumb CSPGO kernel's exact counters on the Pi. The A32 return
variants have build and user-QEMU state/semantic checks; this is not a new
general A32/IRQ/SMP instrumentation certificate. Mixed/flag-changing Thumb
groups and A32 entry/targeted/after-control-transfer returns keep the refusal
guard (R36).

## Historical single-core contract and evidence through 0039

The older observations below are preserved as dated evidence. Subsequent
overlays fix Thumb startup (0040), ISA/ABI admission (0041/0058), fixed-load ELF
admission (0042), and try-lock instrumentation (0059). Their old open/unsupported
statements are not the current work queue.

Follow-up 2026-10-03: overlay 0039 closes the 0038 unnamed interior-entry
reservation bypass for decoded original code. Every decoded acquisition is
analyzed independently of entry metadata; unanalyzed stores reject. Other
ISA/entry/runtime caveats below remain. See
[evidence](../results/correctness_interior_reservations_20261003.json).

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
[cross-function evidence](../results/correctness_cross_function_exclusive_20261002.json).

See [current caveats](../reviews/CORRECTNESS_REVIEW_0038.md) and
[ordered closure tasks](../HANDOFF.md#claims-consolidated-todo) before broader use.
No supported SMP/FIQ/userspace claim follows from supplying the contract flag.

See [evidence](../results/correctness_instrumentation_scope_20261002.json).
