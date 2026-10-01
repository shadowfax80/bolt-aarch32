# Correctness fixes

## Full-image execution gate and redirect bounds (2026-10-01)

`full_image_wsl.sh` now delegates to `full_image_build.py`, requires an explicit
redirect set and keeps outputs in a fresh output directory. It no longer silently
loads a nearby profile. It checks restoration byte-for-byte with exact addresses
and sizes, and records original/emitted/not-emitted/redirected coverage plus image,
map, tool and patch hashes. Emission reports execution as unverified.

Redirects use the ELF function's Thumb bit, require matching input/output symbols,
bounded source/body ranges, alignment, preserved original bytes and nonoverlapping
entries. An all-missing explicit selection now fails instead of redirecting the
whole map. A late failure leaves the ELF unchanged. Prologue equality remains a
conservative restriction; this does not close all alias/secondary-entry cases.

`full_image_verify.py` verifies hashes and independently decodes each redirect
branch in the ELF/uploaded binary, checks all 18 baseline/candidate results and
requires checksum-verified samples of the correct ISA inside named rewritten
bodies. Missing/saturated/corrupt samples fail. Results are scoped to required
functions, not every emitted function. It saves complete logs and a verification
manifest in a fresh evidence directory.

Validation: 13/13 host tests. Whole-image ATFE emission: 417 input functions,
411 emitted, four redirected. One Pi repetition correctly failed when interworking
had no sampled PC. Ten repetitions passed all 18 results with 33,848 samples:
rewritten IT 2,506, interworking 27 and memcpy 16; far-call 0. The sampled bodies
are Thumb/ARM/Thumb respectively. See
[manifest](results/correctness_full_gate_20261001.json) and
[usage](PI_FULL_IMAGE_VERIFICATION.md). Profile identity, every other optimization
gate, graph consistency, broader fixtures and clean replay remain under #12.

## Complete workload gates and profile input validation (2026-10-01)

`passes_check.py` now requires the explicit 18-workload result set, rejects
conflicting duplicates, reported workload failures and nonzero child exits, and
can save complete attempt logs. A matching one-workload baseline/candidate pair
can no longer pass. Counter conversion checks dump addresses, declared counter
array lengths, metadata bounds and referenced counters/locations before publishing
buffered output. A later invalid descriptor cannot overwrite an existing profile
with partial output. Sample conversion rejects empty or partial PC words and stages
perf2bolt output so a failed child cannot overwrite an existing profile.

Validation: 10/10 host negative/positive tests in
`scripts/tests/test_profile_validation.py`; real WSL ATFE perf2bolt converted three
synthetic PCs from the existing baseline ELF; the new counter converter processed
existing instrumentation metadata with 61 synthetic counters (3,520 output bytes).
These are input/conversion checks, not new hardware profiling evidence. Full graph
consistency, exact image identity and full-image execution proof remain open in #12.
Ignored detailed logs are in `out/correctness/validation-fix/`.

## Independent Pi workload results (2026-10-01)

Memcpy initializes nonzero source data and a different destination, validates
every destination byte and publishes its FNV checksum. Far-call consumes a
callee return value; Thumb IT publishes its conditional-loop result (ARM builds
publish an explicit unavailable marker); interworking publishes its accumulator.
These workloads no longer inherit the previous workload's shared result.

An isolated snapshot of the existing LK source built successfully using ATFE.
Baseline and an ext-tsp ATFE image redirecting the four workloads both completed
all 18 workloads on Pi with matching results. The new values also match independent
calculations: memcpy `5acd3dc5`, far_call `b7082fa9`, it_cond `021e8480`, interwork
`2fb21555`. This fixture executes Thumb IT and explicit ARM/Thumb callees; the
ARM-only IT skip path and multiple inputs/pass combinations remain unverified.

The redirected image sampled PCs while running all workloads, then dumped the
512 KiB buffer with per-chunk checksum verification. All 3,390 kept/taken samples
were present, with observed PCs inside rewritten IT (250), interworking (2) and
memcpy (2). Far-call was redirected and returned the expected value but no sampled
PC landed inside its short body. Four functions were selected/emitted/redirected;
only three have independent sampled execution evidence. This does not validate
the full-image script's 403/411 emission claim. Image, map, benchmark source and
log hashes, results and scoped coverage are recorded in
[the manifest](results/correctness_validation_20261001.json).

## Thumb entry and moved symbols (2026-10-01)

ATFE overlay 0021 normalizes the Thumb state bit before looking up ARM function
addresses and retains it in a moved ELF entry. Moved Thumb `STT_FUNC` symbols
now resolve to their rewritten functions, while `$t` mapping symbols retain even
byte addresses and zero size. The valid Thumb-entry fixture that previously
asserted now emits `e_entry=0x22001`, moved `_start`, `probe` and `probe_nz`
symbols, and `$t=0x22000`.

Validation: assertions-enabled ATFE rebuild; 32/32 focused BOLT ARM and JITLink
AArch32 tests; full QEMU-LK image emission. A rebuilt Pi image redirected
`app_start_by_name` and `strtoul`; original and rewritten images booted and
completed seven benchmark commands with matching shared-result dumps. That Pi
image has an ARM entry, so hardware did not execute the synthetic odd-entry
fixture. Aliases, skipped functions, code/data transitions and pointer targets
remain open under item #9. Patch reverse-apply check passed against live ATFE.

## CBZ/CBNZ flags and long-range branches (2026-10-01)

ATFE overlay 0020 replaces the Thumb compare-and-branch expansion that used
`CMP; Bcc`. The original CBZ/CBNZ preserves NZCV, whereas CMP overwrote it.
An inverted CBZ/CBNZ now skips one 4-byte wide unconditional branch to the
original target. Both instructions preserve NZCV; the short skip is always in
range and the wide branch handles layout changes. A fixture with flags consumed
on both successor paths checks emitted instructions for both opcodes.

Validation: ATFE rebuilt; BOLT ARM and JITLink AArch32 focused suites passed
31/31 combined, including the new test; full QEMU-LK image emission passed.
On the Pi, `app_start_by_name` and `strtoul` were rewritten and redirected.
The output code was decoded and confirmed to contain the new sequences. Original
and rewritten images both completed seven benchmark commands with matching
shared-result dumps: hot_loop e0e64a6a, hot_cold 00000000, branch_chain
00517a00, memcpy 00517a00, spill_ret a0804950, litpool e096b516,
interwork e096b516. Memcpy and interwork do not update this shared variable,
so those comparisons alone are not independent checksums. The synthetic
flag-sensitive paths were checked at the emitted-instruction level; a dedicated
Pi execution check for both paths remains on the TODO list.

The patch was exported from the live ATFE tree and `git apply --reverse --check`
passed against that tree. The dirty parent/source checkout still needs a clean
replay/provenance check under item #12.

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
