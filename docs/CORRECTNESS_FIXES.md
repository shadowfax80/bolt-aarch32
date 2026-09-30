# Correctness fixes

## A32 literal loads (2026-09-30)

The upstream 0008 and ATFE 0014 overlays correct backward literal-load
offsets, subtract-zero decoding, and symbolic MC operands. JITLink now handles
R_ARM_LDR_PC_G0 with signed imm12 range checks while preserving predicate and
register bits. Regression tests cover forward/backward loads, nonzero addends,
ordinary register-based loads, and positive/negative range boundaries.

Validation on the ATFE assertions-enabled Release build:

- BOLT ARM suite passed (13/13 before the separate unwind change).
- LLVM JITLink AArch32 suite passed (13/13).
- Full LK image emission passed, replacing the previous unsupported-fixup errors.
- Postprocessed QEMU image completed four workloads. Postprocessing restores
  original sections, so this does not prove that every rewritten function ran.

The upstream overlay applied cleanly to its pinned base plus patches 0001-0007;
the upstream build has not been tested. The Pi passed baseline serial/upload,
checksum, and benchmark sanity checks, but the modified BOLT output has not yet
been verified on hardware. These fixes do not close the full relocation audit.

## EHABI rejection boundary

The upstream 0009 and ATFE 0015 overlays reject nonempty `.ARM.extab`,
malformed exidx record lengths, and exidx descriptors other than CANTUNWIND.
Genuine EHABI unwinding needs index relocation and sorting before it can be
supported safely. The rejection regression passed on ATFE; the complete BOLT
ARM suite passed 14/14 and JITLink AArch32 passed 13/13. Full LK emission passed.
The upstream overlay applied cleanly but has not been build-tested.

## Pi verification and failure propagation (2026-10-01)

Using the modified ATFE build, stair edge instrumentation ran on the Pi and
returned a complete checksum-verified 85,165-byte counter dump. That hardware
profile produced an ext-tsp optimized image and a no-reordering control image.
The original entry was redirected into the emitted stair function, moving it
from 0x80008e0a to 0x80061000. The original and both rewritten variants completed
two runs each on the Pi; all six checksums were 0x5b19056f. This verifies this
Thumb workload and pipeline, not every A32 literal-load case or full-image
rewrite. No speed claim is made from this small correctness sample.

`verify-all-wsl.sh` now returns failure if any child gate fails while continuing
to run later gates. `pi4_compare.py` returns failure for mismatched or missing
workload checksums instead of printing an error and returning success.
Run `python3 scripts/tests/check-verification-failures.py` under Linux/WSL to
check all-pass, failed-child, later-gate execution, and checksum failure paths
without requiring hardware. Real serial observations are mocked for this
failure-path test; hardware verification above used the actual Pi.

## Data fixup width

Upstream 0010 and ATFE 0016 remove the FK_Data_8-to-R_ARM_ABS32 substitution.
Unresolved 64-bit symbolic ARM ELF data now reports an error. Resolved 64-bit
expressions write all eight bytes instead of silently becoming zero or losing
the high word. Tests cover high-word values and both byte orders. BOLT address
maps retain 64-bit records but use target-width symbolic relocations with
explicit zero extension, avoiding unsupported relocations on ELF32.

ATFE validation passed: 32 selected ARM MC relocation tests, BOLT ARM 14/14,
JITLink AArch32 13/13, and full LK image emission. Rebuilding the optimized and
no-reordering stair images with this fix and comparing against the original on
the Pi again produced checksum 0x5b19056f in all six runs. This is hardware
validation of the pipeline, not a claim that the Pi exercises big-endian data.
The upstream patch applied cleanly; upstream compilation remains pending.

## ATFE return terminators and BLX link bit

Work after this point is ATFE only, per the requested scope. ATFE 0017 fixes
BLX-to-BL conversion when JITLink redirects an ARM call to an ARM stub. Bit 24
is the BLX H bit but the BL link bit; failing to set it converted H=0 calls
into plain branches, losing LR. The new regression checks that the emitted
instruction remains BL and that a jump remains B.

ATFE 0018 recognizes unconditional returns as terminators, including the
existing POP/updated-LDM return forms. Code after a return now becomes an
unreachable block instead of remaining in the returning block. Predicated
returns retain their fallthrough instructions; separate conditional-return
CFG modeling is not implemented. The regression covers ARM POP, non-PC POP,
predicated POP, narrow Thumb POP, and wide Thumb POP.

Validation: BOLT ARM 15/15; JITLink AArch32 14/14; full LK emission passed.
Seven original entries were redirected to rewritten functions on the Pi:
hot_loop, hot_cold, branch_chain, memcpy, spill_ret, litpool, and interwork.
All returned to the shell. Result-variable dumps after each workload matched
the original image. Memcpy and interwork do not update that shared variable,
so their dump comparison alone is not an independent output checksum.
The initial interwork run aborted before the BLX fix; baseline recovery and
the fixed run passed. Dedicated BLX H-bit and alignment cases remain open.

## Deterministic stubs and mixed instruction-set alignment

ATFE 0019 visits original blocks in section/address order and assigns distinct
ordering addresses to generated stubs. It also aligns generated stub sections
for every contained block and preserves block alignment when BOLT remaps their
addresses. Previously five identical LK links produced five different text
hashes. Stable stub order exposed two padding inconsistencies on the Pi;
those candidates were not pushed. The final candidate passed seven redirected
workloads with result-variable dumps matching the original.

The regression links a mixed ARM/Thumb fixture eight times, compares text and
stub bytes, and verifies that ARM calls land on physical ARM stub starts.
Five LK links also produce identical text hashes. BOLT ARM passed 16/16,
JITLink AArch32 passed 14/14, and full LK emission passed. Whole ELF files can
still differ in informational notes containing output paths; this check covers
generated code/stubs rather than those invocation-specific notes.
