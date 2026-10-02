# Correctness fixes

## AArch32 instrumentation operating contract (2026-10-02)

Overlay 0028 requires an explicit privileged/single-core/no-FIQ caller contract
and rejects default or explicit call profiling, shared/dynamic inputs and
process/fork options before transformation. Reset and snapshots require
quiescence. The LK wrapper requires explicit contract configuration; isolated
Pi builders acknowledge the environment established by their firmware/loader.
Eight rejected combinations and an accepted direct invocation pass within the
40-test focused suite. The Pi again passes all 372 cases in four modes plus
reset-fault detection, with runtime checks for privileged mode, masked IRQ/FIQ,
core zero and aligned stack. Nine result-gate tests pass. This does not certify
active ISR/SMP operation or exclusive-memory insertion. #6 remains partial.
See [contract](PI_INSTRUMENTATION_SCOPE.md) and
[evidence](results/correctness_instrumentation_scope_20261002.json).

## Real runtime clear at quiescent boundaries (2026-10-02)

The 50-function Pi fixture calls the actual linked
`__bolt_instr_clear_counters` before each of 372 seeded cases per image. Both
words of every slot must become zero before reseeding. Baseline and all three
instrumented layouts pass; an otherwise identical image with the clear entry
replaced by BX LR fails at the exact first uncleared word. All five images
watchdog-return to the loader. Eight host gate tests pass. Runtime linker-local
symbols are bound through BOLT's checked clear-address diagnostic, and the
function pointer/image bytes are validated before upload. This checks quiet
reset/read boundaries; concurrent reset and live snapshots remain unsupported.
See [evidence](results/correctness_runtime_clear_20261002.json).

## Nested Thumb calls and recursion counts (2026-10-02)

The optional `build_it_counts.py --nested` matrix passes 372 Pi cases each in
baseline/normal/reverse/conservative modes (1,488 total). It adds two caller
levels and recursion through 65 frames at eight inputs; return values and
all 85/85/73 counter slots match independent cross-function path models with
zero/carry/wrap seeds. Every image watchdog-returns to the loader. Six host
gate tests pass. No additional backend fix was required. This checks quiet
Thumb nested calls, without full register/flag-state or active ISR coverage.
See [evidence](results/correctness_nested_counts_20261002.json).

## Terminal IT branches and exact IT counts (2026-10-02)

Overlay 0027 fixes a confirmed silent corruption: LLVM decodes an IT-predicated
direct branch as tB/t2B, whose descriptor is unconditional. CFG construction
removed reachable loop code, then instrumentation split the IT group. The fix
converts supported terminal direct branches to explicit t2Bcc before analysis
and shortens/replaces their IT header. Unsupported control transfers, nested or
truncated groups, mapped data and branches into IT bodies fail explicitly.

All 39 focused ARM/JITLink tests pass, including seven rejection boundaries.
The Pi passes 300 cases each in baseline, normal, reverse-layout and conservative
modes. Forty-seven selected functions cover all fifteen IT data masks,
narrow/wide terminal branches and loops. Return values and every 81/81/71
counter slot match independent expected paths under zero/carry/wrap seeds;
each case resets counters. All four images watchdog-return to the loader.
Five host parser/group checks pass. Nested execution, active interrupts, other
conditions/pass combinations and snapshot boundaries remain open.
See [workflow](PI_IT_COUNTS.md) and
[evidence](results/correctness_it_counts_20261002.json).

## Dedicated ARM/Thumb counter-state checks (2026-10-02)

The Pi fixture executes actual generated leaf bodies through two explicit
redirects. Baseline and instrumented firmware each pass 512 cases covering
R0-R12, LR/SP, full CPSR equality, all NZCV/Q patterns, sixteen GE patterns,
enabled/pre-disabled IRQ and four seeds including full uint64 wrap. Both
complete emitted bodies match independent assembly. Three deliberately broken
images prove detection of lost high-word carry, missing IRQ restoration and R0
clobbering. Six host result-parser tests reject partial/contradictory output.

Every image watchdog-reboots back to the serial loader; software reboot from LK
also succeeded. The run uses privileged HYP mode on COM5, a private aligned
stack and parked secondary cores. No active interrupt handler is invoked and
FIQ stays disabled. IT, nested execution, broader count/reset/snapshot cases and
the enforced operating contract still remain. Item #5 is partial and #12 remains
paused. See [workflow](PI_COUNTER_STATE.md) and
[hardware evidence](results/correctness_counter_state_20261002.json).

## Full-width ARM/Thumb counters (2026-10-02)

Overlay 0026 replaces the low-word-only increment with ADDS on the low word and
ADC on the high word. It preserves R0-R3 in a 16-byte stack frame and restores
both NZCV and the saved IRQ state with CPSR_fc. The emitter operand orders and
complete bytes are checked against independent ARM/Thumb assembly. The sequence
still requires privileged execution; IRQ masking does not enforce an SMP/FIQ
operating contract. Item #6 remains open.

All 38 focused ARM/JITLink lit tests pass, including the portable runtime-symbol
fixture. The patch reverse-checks against the tested live source. Pi validation
compares original, zero-counter and near-overflow images with explicit redirects
into Thumb IT and ARM interwork instrumented bodies. All 18 workload outputs
match. All eight final seeded values equal `0x00000007fffffff0` plus the zero-run
counts; the hot Thumb and ARM slots cross `0xffffffff` with increments of 999,999
and 9,999 respectively. Full dumps/log hashes and per-function counter attribution
are recorded in [evidence](results/correctness_counter_carry_20261002.json).

This completes the counter-width subitem. The dedicated leaf state checks above
also pass; IT masks, nested execution and wider exact CFG-count tests remain
under #5. User paused #12 and moved #5 to the active position.

## ATFE attributes and kept-code export (2026-10-02)

Overlay 0025 exports the four unrecorded live source changes. Input build features
reach both ARM and Thumb subtargets; the emitted ARM/Thumb UDIV and ERET bytes are
checked. This propagates features and does not enforce the ISA/ABI admission
contract. Malformed/missing attribute handling still belongs to #7.

For `--use-old-text`, ignored functions retain their original bytes and reserve
their text range. Kept A32 branches receive early opcode, alignment and target-ISA
checks, bounded little-endian writes and stream-position preservation. The prior
malformed-relocation and hot-at-end assertion probes now fail with diagnostics.
Insufficient text, unsupported hot-at-end and unmappable interior references are
rejected; late failures remove partial output. The scoped full-image builder
rejects text-placement overrides because its restoration path is separate.

Validation: twelve real linked-ELF probes, 37/37 focused ARM/JITLink lit tests,
25/25 profile/replay tests and 14/14 execution-gate tests. All 25 ATFE patches now
replay to the exact live source, with no uncovered changes. Original source
preimages and the initial failed replay remain preserved. Privileged ERET and
kept-code Pi execution are not certified by these host results. Content stamps,
clean build provenance and the remaining #12 validation tasks stay open.

The fresh candidate built with this ATFE tool emits 411/417 functions and redirects
four benchmark entries. After physical power cycling, Pi verification on COM5
passes all 18 outputs across ten repetitions, with 33,850 kept/taken samples.
Rewritten IT/interworking/memcpy have 2,507/30/14 sampled PCs; far-call remains
unobserved. This gate uses the regular full-image restoration/redirect path, not
`--use-old-text`. See [durable evidence](results/correctness_atfe_0025_20261002.json).

## ATFE source replay guard (2026-10-02)

The isolated verifier exports patch-touched files from the pinned ATFE base,
applies the complete series in a separate Git directory and compares source
contents without changing live files. It rejects changed patch contents,
uncovered source changes, unsafe paths and live mutations. Existing evidence
directories are preserved. Host validation: 25 profile/replay tests pass, including
changed-patch detection and source preservation.

All 24 real ATFE patches apply, but four live files differ due to unexported
ARM attribute-feature and kept-code handling. The diff was preserved; the audit
correctly refuses source-equality certification. This is a validation guard,
not a completed clean replay or build provenance claim. Review/export and focused
tests for the unrecorded changes, content stamps and a clean build remain open.
See [replay workflow](ATFE_OVERLAY_REPLAY.md) and
[audit evidence](results/correctness_atfe_replay_20261002.json).

## Sampling artifact identity (2026-10-01)

The Pi sampling path now requires an ELF/binary pair sealed before collection.
A portable ELF32 reader checks uploaded section bytes and records the source
function table and buffer. Isolated session copies prevent an in-progress build
from silently changing the upload. The collector checks workload repetitions,
sample count/saturation, dump range/completion/checksums and PMU/core reports,
then saves the full log and capture identity. Failed children preserve prior outputs.

Conversion requires the capture payload and ELF hashes plus the sealed perf2bolt
digest, checks named offsets against unambiguous source function ranges, and
publishes a profile sidecar. The ARM no-LBR wrapper and explicit full-image
`--profile` path reject absent/stale/unbound profiles. Debug synthetic conversion
remains available but its output cannot pass the optimization identity gate.
See [workflow and limits](PI_PROFILE_IDENTITY.md).

Validation: 23 profile tests and 14 execution-gate tests, including stale payloads,
wrong source ranges, changed tools, incomplete/saturated captures, failed children
and late-failure preservation. The actual independent LK fixture ELF/binary seals
against ATFE tool/patch digests; real perf2bolt synthetic diagnostics validate source
locations. Existing 61-counter/3,520-byte conversion remains green. Synthetic
samples/counters do not certify hardware semantics.

The initial Pi attempt failed on COM5. After power cycling, Windows assigned COM6.
A host repetition bug exposed by composite/stair's duplicate acc/sink observations
was fixed and regression-tested, then a fresh capture passed: 6,772 samples and
two repetitions of all 18 workloads. Unbounded arch_idle locations fail strict
conversion; an explicit four-function projection records all excluded counts.
Real ATFE conversion and negative stale-payload/wrong-ELF checks pass, preserving
the previous profile and sidecar on failure. The profile-guided whole-image
candidate emits 411/417 functions with four explicit redirects. Ten Pi repetitions
match all 18 baseline results; 33,850 samples observe rewritten IT/interworking/
memcpy (2,506/24/16 PCs), while far-call remains unobserved. See the
[bound-profile hardware manifest](results/correctness_sampling_bound_pi_20261002.json).
#12 remains open for counter binding,
single-core sampling ownership, other execution gates, broader fixtures and clean
overlay replay. Recorded patch hashes alone do not prove build-source provenance.

## Profile graph consistency (2026-10-01)

The counter converter validates every descriptor, including cold graphs. It rejects
duplicate CFG edges/nodes/counter assignments, missing counter coverage, inferred
cycles or multiple parents, unmeasured inferred exits/calls, contradictory measured
leaf/call counts and negative inferred edges. It no longer clamps invalid inferred
counts to zero. Sparse node IDs are mapped to compact indices, so metadata cannot
request an allocation proportional to a huge node ID. Function string offsets must
start at a nonempty, whitespace-free string; one descriptor cannot mix source names
or contain unsupported cross-function CFG edges.

Leaf-only descriptors without source locations are rejected: assigning the first
string or trusting an unbound positional --funcs list could label counts as the
wrong function. This is an explicit profile-format boundary, not newly implemented
leaf profiling. Names/offsets still need binding to the exact source ELF under #12.

Validation: 14/14 profile tests, including a valid inferred tree with sparse IDs,
zero counters, cycles, multiple parents, unmeasured exits, negative flow and string
boundary/identity failures. Existing real ATFE conservative metadata with 61 counters
still converts to a 3,520-byte profile. Counter values in that conversion are
synthetic; it does not certify instrumentation counter semantics under #5.

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
# 2026-10-02: ARM pseudo-count invariants in both build modes

Overlay 0029 removes the debug-only ARM count repair/ignored-function fallback.
Stale pseudo bookkeeping now produces a fatal diagnostic with assertions on or
off. Accounted replacement passes; two deliberately unaccounted mutations are
rejected. Both full CoreTests runs pass 52 with 31 expected skips. Focused lit
passes 40 assertions-on and 39 assertions-off, with one debug-only alignment
skip whose ARM/Thumb semantic checks pass separately. Independent assertion-off
BOLT/JITLink builds share host compiler/assembler/linker/test helpers.

Both Pi builds pass 372 cases per baseline/normal/reverse/conservative image and
detect the reset fault. All five payloads are byte-identical between build modes
and return to the serial loader. Evidence: [CFG pseudo counts](results/correctness_cfg_pseudos_20261002.json).
#3 remains partial: function-fallthrough, synthesized Thumb returns and other
CFG recovery paths remain under review. #12 remains paused.
# 2026-10-02: function fallthrough and decoded POP-to-PC

Overlay 0030 rejects reachable residual function fallthrough before CFG repair,
uses the function's ARM/Thumb builder, removes invalid-CFG ignore recovery and
exits fatal ARM CFG admission after workers join. It prevents conditional-edge
erasure, unmodeled final-call continuations and A32 returns inside Thumb output.
The exact standard SP/+4 single-register POP-to-PC is recognized from real
decoder bytes; general LDR-to-PC and conditional-exit modeling remain open.

Twenty unsafe admissions reject with status 1 and no output; eighteen safe
return/tail/padding/POP admissions pass. Both modes pass 53 unit tests with 31
expected skips; lit passes 41 assertions-on and 40 with one debug-only skip off.
Both Pi POP-state builds pass 512 baseline/512 generated cases and detect all
three faults, with identical payloads. An exact existing A32 absolute veneer is
admitted before its later removal pass; broader veneer matching remains to audit.
The host veneer fixture now ends with an explicit loop if its SVC returns.
Evidence: [CFG fallthrough](results/correctness_cfg_fallthrough_20261002.json).
