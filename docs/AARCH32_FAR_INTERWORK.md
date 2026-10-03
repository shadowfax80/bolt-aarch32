# ARM/Thumb far-call execution — overlay 0044, item 6

Overlay 0044 fixes a reproduced Thumb far-call construction failure. The four
caller/callee ISA pairs now have bounded QEMU execution witnesses in both
assertion modes and normal/reverse layouts. Item 6 and original #12 remain active.

## Reproduced failure and fix

Both Thumb-to-ARM and Thumb-to-Thumb fixtures run successfully before BOLT, but
overlay 0043 fails linking their rewritten output in both assertion modes and
layouts: `Invalid opcode [ 0xe300, 0xc000 ] ... Thumb_MovwAbsNC`. Stub relaxation
used the context's default ARM builder, producing ARM MOVW bytes for Thumb code.
The preserved eight failures are build failures, not successful corrupted
hardware execution. ARM-to-Thumb probes also remain preserved as controls.

The LongJmp pass now selects builders using the function owning the stub for
creation, relaxation, range queries and target replacement. Calls to a local
stub use that stub's ISA. Global stub lookup refuses to reuse a stub owned by
a function in the other ISA. Range parameters are no longer cached from the
first builder, and instruction/frontier offsets use actual instruction sizes
instead of assuming every Thumb instruction has four bytes.

Separate executable grouping fixtures check both directions: same-ISA callers
share one stub; ARM/Thumb callers get two. In both assertion modes the produced
code executes the two original inputs 1 and 8, returns the independently
expected final result 15, and preserves the caller's stack.

## Bounded execution certificate

Run `scripts/verify_far_interwork.py --toolchain <bin> --out <evidence-parent>`
under WSL. QEMU is mandatory. Each invocation builds all four ARM/Thumb caller
and callee pairs with the explicit supported A32 literal veneer, then checks
normal and reverse layouts in fresh directories. This extends the earlier
[A32 gate](AARCH32_FAR_EXECUTION.md); the older P5 wrapper retains its A32 scope.

The verifier decodes the actual A32 or T32 BL, MOVW/MOVT/BX stub, exact target
and Thumb bit, function ISA symbols and ELF entry. It requires the callee to
lie outside the corresponding direct-call range. ARM and Thumb stub byte
encodings are checked independently; an ARM opcode cannot pass as a Thumb stub.

Five inputs (`0`, `1`, `17`, `0x7fffffff`, `0xffffffff`) have independently
computed return/memory results `(input + 7) mod 2^32`. The candidate preserves
the expected table and data layout. The fixture checks the result, memory,
NZCV and SP, plus a callee-written ISA tag. The checker is itself rewritten
and is tested with executable mutations; it is not a proof of every instruction.

QEMU CPU traces provide the actual ISA state separately from the fixture tag.
Each trace block must have matching guest PC, registers and a complete user-mode
PSR record. Caller, stub, callee and return must have the expected ARM/Thumb
states. The stub, callee and return each occur five times; actual callee R0
inputs and returned R0 outputs must match the complete ordered seed table, with
unchanged SP. Reading CPSR through a Thumb MRS alias does not expose the T bit
in this user-mode fixture; that value is not used as an ISA-state witness.

Each layout rejects eight executable faults: wrong arithmetic result, removed
store, changed NZCV, changed SP, wrong callee tag, bypassed call, one-input loop
that still exits 42, and an infinite-loop timeout. CPU-state admission tests
add wrong ISA tags/PSR, wrong guest-PC association, missing state, wrong input/
return values and stack changes. Timeout or incomplete output cannot certify.

Receipts bind tools, verifier dependencies, repository revision, QEMU, input/
output images, maps and logs. Executed bytes and source artifacts must stay
stable. Selected, emitted, eliminated and executed routes, expected/actual
values, CPU states, options and fault outcomes are durable. The manifests are
identity checks, not signatures or clean compiler-build provenance.

## Verification and limits

Both builds pass 40 transformed inputs and 64 rejected faults each: 80 positive
transformed inputs and 128 rejected faults overall. Baselines add 40 input
cases overall. The eight grouping fixtures execute correctly. All 89 Python
tests pass; both builds pass all 37 ARM lit tests and 58 CoreTests with 31 skips.
All 44 overlays replay exactly from the pinned base without altering live
source. Source replay does not certify a clean full build.

No new Pi execution is claimed. These padded ELF images exceed the current
contiguous serial loader's payload boundary, which protects the loader's
relocated memory. Hardware needs a bounded sparse/staged fixture rather than
sending these Linux user-mode images directly. The automatic v7 linker-thunk
retained-target caveat remains under items 7/11. Near-range boundaries, split/
cold layouts and wider sharing combinations still require their own matrix.
Whole-LK `arm_reset` admission, interrupts/PMU and clean-build provenance remain
open. No guard was weakened to obtain execution.

Next within item 6: hardware far-call witnesses, remaining raw-grep/comparison/
legacy gate audits, and durable coverage/oracle receipts for the remaining
supported gates. See [evidence](results/correctness_far_interwork_20261003.json)
and [the active queue](CORRECTNESS_PRIORITY_TODO.md).
