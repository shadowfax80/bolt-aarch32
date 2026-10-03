# Pi far-call execution contract

`scripts/pi4/build_far_safety.py` builds a bare-metal ARM harness and all four
ARM/Thumb caller/callee pairs. Each pair runs five independently computed
inputs (`0`, `1`, `17`, `0x7fffffff`, `0xffffffff`) and returns/stores input + 7
modulo 2^32. Normal and reverse BOLT layouts remove the four explicit supported
ARM literal veneers and emit far-call stubs. Decoding verifies the call, the
stub's owning ISA, MOVW/MOVT/BX IP target, Thumb bit and displacement outside
the corresponding direct-call range.

The padded ELF files exceed the resident loader's contiguous upload boundary.
A small bootstrap copies the original harness and complete nonzero emitted
code pages into RAM, synchronizes instruction fetch and enters the original
ARM `_start` at 1 MiB. No padded zero gap is written. Destination checks exclude
the stack reserve (7–9 MiB), relocated loader reserve (32–33 MiB), overlaps and
addresses outside 1–256 MiB. Uploads remain below 1 MiB. The C harness disables
unaligned accesses because it runs with MMU/caches off.

`scripts/pi4/verify_far_safety.py` reconstructs the actual bootstrap copy table
and source bytes from the uploaded binary. It checks every original allocated
byte, with only the declared case-entry metadata edits, and every emitted
nonzero page. The executed code hash includes deterministic fault mutations.
Protected destinations, unexplained extents, source mismatches or missing
pages reject before serial upload.

Caller and callee MOV-PC instructions store their live PCs; a second caller
witness records the return path. Their expected values derive from actual
instructions and the ISA's PC bias. Callee entry also stores incoming R12:
baseline literal veneers preserve the sentinel; emitted far stubs supply the
exact callee address with its Thumb bit. These witnesses distinguish original
and emitted functions even when they return identical arithmetic results.
The gate checks all twenty ordered cases, result/memory, preserved NZCV and
aligned unchanged SP. Thumb MRS is not treated as proof of the CPSR T bit.

Three executable negative controls change arithmetic, change flags and point
the generated stub at the retained original callee. The last preserves the
correct arithmetic result but must fail the live callee-PC check. Each image
must complete with exactly the expected records and return to `SBOOT?` through
the watchdog. Missing output, duplicate/contradictory records and timeout reject.

Receipts bind producer tool/options/script identities, source manifests, exact
upload/loader snapshots, verification dependencies, repository revision,
decoded routes, live records and serial logs. Artifacts and dependencies are
checked again before publishing a successful receipt. These checks establish
identity and bounded execution; they do not establish clean compiler provenance.

The scope is Pi 4 core 0 in HYP mode, IRQ/FIQ masked, MMU and caches disabled.
It excludes interrupts, PMU ownership, whole-LK admission, automatic v7 linker
thunks, near-range boundaries, split/cold layouts and wider stub-sharing cases.
Item 6 and original #12 remain active. See the [queue](CORRECTNESS_PRIORITY_TODO.md)
and [four-ISA source fix](AARCH32_FAR_INTERWORK.md).

## Verified milestone, 2026-10-03

Both assertion modes pass baseline, normal and reverse images: 80 transformed
cases and 40 baseline cases overall. All six negative controls fail at their
expected fields, and all twelve images return to the loader. Uploads are 4,812
bytes for baseline and 21,692 bytes for the other variants. All 98 Python tests
pass. The first prototype's incomplete baseline is preserved as a rejected
harness diagnostic; the final fixtures disable unaligned C accesses.
See [published evidence](results/correctness_pi_far_20261003.json).
