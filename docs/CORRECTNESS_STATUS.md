# Twelve-item correctness work

## Follow-up: execution gate hardening, item 6 active (2026-10-03)

Item 6's first execution/result gate hardening stage is verified; item 6
remains active. Complete ordered workload repetitions, strict dump framing,
every-selected-redirect PC coverage, immutable upload/manifest/loader snapshots,
stable tool/script/revision receipts and watchdog-cleanup failure propagation are
enforced. Unsafe legacy ARM/Thumb counter hooks reject; section restoration is
exact and bounded. Generic comparisons explicitly claim output consistency only.
All five reproduced admissions reject, 80 Python tests pass, and the transport
matrix passes 7 admissions/80 rejections. Real ARM/Thumb host artifact builds pass
both modes. Fresh Pi pass matrices pass 420 positive cases and two expected faults
per build, with all eight images returning to the loader. The whole-LK attempt
still rejects an unsupported transfer in arm_reset; no whole-LK or rewritten
far-call execution is claimed. No LLVM source changes were made (overlay 0043).
Next is the remaining item 6 execution/oracle/legacy-path work; #12 stays active.
See [gate scope and remaining work](AARCH32_EXECUTION_GATES.md),
[evidence](results/correctness_execution_integrity_20261003.json) and
[status table](CORRECTNESS_PRIORITY_TODO.md).

## Follow-up: exact profile/artifact identity (2026-10-03)

Consolidated queue item 5 is scoped verified in overlay 0043 for the sealed
ARM counter and PC-sampling pipelines. Instrumentation records exact source-input
SHA-256 and descriptor owners; seals bind ELFs, map, image, tools and patch/source
identity. Capture, conversion and consumption reject stale artifacts and invalid
source offsets. Publication stages output bundles and rolls back caught errors;
crash/power-loss atomicity is not claimed. Both builds pass 300 cases each
(12 admissions, 288 rejections), focused suites 51/50 and CoreTests 58/31 skips.
All 65 Python tests and four wrapper rejection checks pass. All 43 overlays replay
exactly; fresh supported Pi bytes equal the executed 0041 payloads. Captures in
this milestone are synthetic host fixtures; no fresh hardware execution is claimed.
Legacy unsealed captures are excluded from verified optimization. Item 6 is next;
original #12 remains active, including PMU and clean-build provenance work.
See [the identity contract](AARCH32_PROFILE_IDENTITY.md),
[evidence](results/correctness_profile_identity_20261003.json) and
[status table](CORRECTNESS_PRIORITY_TODO.md).

## Follow-up: fixed-load ELF boundary (2026-10-03)

Consolidated queue item 4 is scoped verified in overlay 0042. Both ordinary
rewriting and instrumentation now reject PIE/shared inputs and unsupported
dynamic/TLS/GOT/PLT machinery, validate fixed LOAD/section mappings, and exclude
nonempty loaded sections at zero before the reproduced relocation assertion.
Both builds pass 192 cases (12 admissions, 180 rejections), focused suites 51/50
(one expected skip off) and CoreTests 58/31 skips. The 358-case ISA matrix remains
green. Runtime and counter pointers are checked at three fixed VMAs; nonzero
bias is unsupported. Fresh supported Pi payloads equal the exact executed 0041
bytes; no new Pi execution is claimed. All 42 overlays replay exactly.
Next is queue item 5, profile/artifact identity. Original #12 remains active;
no additional whole original workstream closes. See the
[fixed-load contract](AARCH32_FIXED_LOAD_CONTRACT.md),
[evidence](results/correctness_fixed_load_20261003.json) and
[status table](CORRECTNESS_PRIORITY_TODO.md).

## Follow-up: ISA/ABI boundary (2026-10-03)

Consolidated queue item 3 is verified within the initial conservative ISA/ABI
contract in overlay 0041. Both builds pass 358 admission cases (32 admitted,
326 rejected), focused suites 50/49 (one expected skip off) and CoreTests 58/31
skips. Generic ARMv7-A integer-only runtime, generated-form minimum-profile checks,
fresh Pi startup and 372-case IT/nested/reset matrices pass in both builds.
Static PIE remains admitted; queue item 4 is next. Automatic v7 thunk recognition
and retained-target routes remain open in items 7/11. #12 remains active;
no additional whole original workstream is closed. See the
[contract](AARCH32_ISA_ABI_CONTRACT.md),
[evidence](results/correctness_isa_contract_20261003.json) and
[status table](CORRECTNESS_PRIORITY_TODO.md).

Last updated: 2026-10-03. Verification details: [CORRECTNESS_FIXES.md](CORRECTNESS_FIXES.md).

Consolidated queue items 1/2 have scoped fixes in 0039/0040. Item 2 fixes Thumb
startup crashes: both builds pass 40 cases, 49/48 focused tests and 58 CoreTests
with 31 skips. Fresh Pi baseline/normal/reverse runs pass per build, following
actual runtime/trampoline/rewritten Thumb entry and checking exact count/state.
Static finalization remains a dummy return; dynamic hooks and PIE policy stay
open. See [0040 evidence](results/correctness_thumb_startup_20261003.json) and
[14-item status table](CORRECTNESS_PRIORITY_TODO.md). Next is queue item 3,
ISA/profile/ABI admission. #12 remains active; no whole original item newly closes.

Earlier review evidence: [review through 0038](CORRECTNESS_REVIEW_0038.md) and
[fresh priority queue](CORRECTNESS_PRIORITY_TODO.md). At that checkpoint focused suites
passed (48/47), both CoreTests runs pass 58/31 skips, and the complete 38-overlay
source replay matches. The review reproduced skipped unnamed
interior-entry reservation admission, Thumb instrumentation SIGABRT/SIGSEGV,
ARMv6 inputs receiving unsupported synthesized instructions and static PIE with
unrelocated absolute counter pointers. General backend correctness is not
established. Overlay 0038 and its scoped evidence are published with this review;
no backend fix or new Pi execution was performed during the review. The user
reactivated #12; its remaining validation/provenance work is in the consolidated
queue. Three original items remain complete; nine remain open.

Earlier milestone:

Work stopped at the user-requested next milestone on 2026-10-02. Local overlay
0038 rejects cross-function exclusive reservations in decoded original code,
including skipped/unselected callers and known secondary entries. Both build
modes pass 133 new cases (98 rejections, 35 admissions), 48/47 focused tests
(one expected debug-only skip off), and 58 CoreTests/31 skips. Fresh supported
Pi payloads match executed 0036 bytes; no new Pi execution is claimed. Overlay
0038 is exported and reverse-apply checked, not committed/pushed. Last pushed
production fix is 5049da5/0037. Active ISR scope remains open; #12 stays paused.
See [evidence](results/correctness_cross_function_exclusive_20261002.json) and
[resume checkpoint](CORRECTNESS_RESUME.md).

Earlier checkpoints: overlay 0027 is pushed as
`be09efb`, nested verification as `b732798`, and runtime reset as `edfa3d7`.
The #6 admission boundary is pushed as `e9cd3b3` and passes 40 focused host tests
and 372 Pi cases per mode, plus reset-fault detection. #3 CFG/assertion parity has
verified boundaries: overlays 0029/0030 reject pseudo-count mismatches, function fallthrough
and invalid postprocessed CFG in both build modes. Decoded single-register
POP-to-PC returns pass the full Pi state matrix in both modes. Next is #4's
conditional-return/PC-write and pass-safety audit. Overlay 0031 additionally
preserves flag-writing/PC-writing self-moves and fixes
the 0030 Thumb NOP worker-annotation regression. Host and Pi state checks pass
in both modes. #4 is active: overlay 0032 makes ARM inlining safety mandatory
even with --force-inline and recognizes the decoder's implicit-LR BX_RET.
Host and Pi tests pass in both build modes: 55 baseline/normal/reverse cases
per mode, with result and CBZ-flag faults detected. Overlay 0032 is pushed as
66f1df1. The next PC-write audit confirms MOV PC,PC corruption on Pi;
0033 rejects unsupported PC writes and noncanonical LDM returns. Both build
modes pass their tests and reject the exact hardware input without output;
all five supported Pi payloads match the previously executed bytes. Broader
#5/#6 coverage stays open. Overlay 0033 is pushed as 796083d. Overlay 0034
extends the inlining host gate to 92 emitted cases and four IT-call rejections
per build mode. The expanded Pi matrix passes 840 positive cases across six
configurations in both modes, detects four fault runs and watchdog-returns
all sixteen images. Predicated, indirect and mixed-ISA calls remain intact;
automatic and size-based inlining preserve the tested safety boundary.
Overlay 0035 closes the exception-return admission gap: ARM/Thumb RFE,
decoded ERET and Thumb exception SUBS reject before transformation. Both modes
pass 56 negative cases plus attribute-decoded ERET rejection, 14 real decoder
cases, the ERET descriptor gate and full focused/unit suites. Fresh supported
Pi payloads match all eight executed 0034 images in each mode. #4 remains
partial for wider predicated exits, other special transfers and profile-driven
pass combinations. Overlay 0036 additionally rejects instrumentation of
unmodeled conditional returns while preserving ordinary relocation. Both
host builds pass twelve rejections/six admissions; fresh nested/IT Pi checks
pass 2,976 positive cases, two reset faults and ten watchdog returns.
#6's exclusive-memory boundary has a verified function-local exclusion in 0037:
104 rejection cases, 52 relocation admissions and 38 actual decoder cases pass
in each build. Fresh supported Pi payloads match executed 0036 images. Overlay
0038 adds the decoded cross-function boundary described above; active ISR
coverage remains open. A
separate Thumb ELF-entry assertion is recorded for #9. #12 remains separately paused.
See CORRECTNESS_RESUME.md.

Fresh source review at `bbae817`: [CORRECTNESS_REVIEW_BBAE817.md](CORRECTNESS_REVIEW_BBAE817.md).
Actionable subitems and closure criteria: [CORRECTNESS_TODO.md](CORRECTNESS_TODO.md).

Active scope: ATFE only, as requested. Upstream work is stopped and excluded
from completion criteria. Three items are complete within this scope (2, 8, 10).

| # | Work | Status | Remaining work |
|---|---|---|---|
| 1 | Relocation matrix and literal loads | Partial | THM_JUMP19 and splitting now supported; complete signed range, alignment, BLX H-bit, addend and unsupported-path coverage |
| 2 | EHABI exidx/extab | Complete via rejection | Unsupported unwind information is rejected; full unwind rewriting remains unsupported |
| 3 | Pseudo/CFG invariants | Partial | Pseudo-count and fallthrough rejection verified in both build modes; worker fatal errors exit after join; wider CFG audit open |
| 4 | Control flow and return semantics | Partial; checkpoint verified | POP-to-PC, flags, CBZ/CBNZ and inlining verified; unsupported PC writes/exception returns/IT calls reject; conditional-return instrumentation rejects; general exit model and broader pass combinations remain |
| 5 | Instrumentation correctness | Partial; operating scope next | Carry, CPU-state, IT, nested Thumb/recursion and real runtime clear pass on Pi; mixed-ISA nested state, active interrupts and live snapshots remain |
| 6 | Instrumentation scope | Partial; decoded F1 boundary fixed | 0039 analyzes every decoded acquisition and rejects unanalyzed stores; active ISR and general ISA/entry coverage remain |
| 7 | ISA/profile/endianness | Open; P0 admission violations reproduced | Enforce generated-feature/ISA and fixed-load boundaries; ARMv6, static PIE, missing attributes and BE8 probes admitted |
| 8 | FK_Data_8 / ABS32 mismatch | Complete | ATFE host and Pi checks passed; symbolic 64-bit relocations rejected; resolved values and map width corrected |
| 9 | Entry points and symbols | Partial; P0 crashes/routes reproduced | Thumb instrumentation aborts with assertions and segfaults without; skipped unnamed interior routes evade discovery; aliases/pointers/redirect coverage remains |
| 10 | Deterministic stubs | Complete | Stable visitation and layout, mixed-stub alignment fixed; repeated links and Pi checks passed |
| 11 | Rewrite coverage | Partial | TBB/TBH and generic passes implemented; full-image emitted coverage is not execution proof; table/pass boundaries and excluded ELF constructs remain |
| 12 | Verification and artifact integrity | Active, partial | Exact counter/artifact identity and execution gates now P0 queue items; PMU ownership, broader inputs/manifests and clean build/content provenance also active |

Hardware takes priority for execution verification; QEMU is a supplemental
debugging tool. Pi checks use serial reboot where possible. A halted shell may
still require a physical power cycle. Host tests and hardware tests are recorded
separately; passing a single workload does not close the entire correctness audit.

Overlay 0025 exports the previously unrecorded ARM attribute/kept-code changes,
checks kept A32 opcode/alignment/ISA, writes bounded little-endian bytes and
preserves the stream position. Unsupported hot-at-end, insufficient space and
unmappable interior-reference cases fail. Host validation: 37/37 focused lit tests,
twelve linked-ELF probes and 14/14 execution-gate tests. All 25 overlays replay to
the exact live source contents. This does not certify privileged ERET execution,
general ISA/ABI admission or `--use-old-text` execution on Pi. The scoped full-image
builder rejects text-placement overrides.
The fresh regular full-image candidate also passes Pi verification on COM5:
all 18 results, ten repetitions, and sampled execution in the required rewritten
IT/interworking/memcpy bodies. Far-call remains unobserved. See
[overlay 0025 evidence](results/correctness_atfe_0025_20261002.json).

Overlay 0026 fixes the low-word-only counter increment. All 38 focused host tests
pass. On Pi, zero/near-overflow instrumented images preserve all 18 workload
outputs and all eight slots satisfy seed plus measured count. Counter 1 in Thumb
IT and counter 4 in ARM interwork cross the 32-bit boundary correctly. Dedicated
IT, nested and scope tests remain open; see
[counter carry evidence](results/correctness_counter_carry_20261002.json).

The dedicated state fixture also passes on Pi: 512 baseline and 512 generated
ARM/Thumb leaf cases preserve R0-R12, LR/SP and the complete CPSR across all
NZCV/Q patterns and both IRQ-mask states. Six host parser tests pass; three
deliberately broken images fail at their specified checks. Every payload returns
to the serial loader through the watchdog. This quiet HYP-mode fixture does not
exercise active IRQ/FIQ, nested execution, IT or SMP. See
[state evidence](results/correctness_counter_state_20261002.json).

Review validation at bbae817: 36/36 focused ARM tests passed. Isolated emission
confirmed full-image postprocessing restores original code/entry; a partial-result
Pi gate and truncated-counter converter incorrectly accept their negative fixtures.
The negative probes describe the reviewed bbae817 baseline. Local validation fixes now
pass 10 host tests plus real ATFE sample conversion and 61-counter metadata conversion.
Independent benchmark changes built in an isolated LK snapshot. Pi baseline and
four-function redirected ATFE image match on all 18 workloads; the four new values
match independent calculations. Checksum-verified PC samples observe rewritten IT,
interworking and memcpy (not the brief far-call). This is scoped execution proof,
not full-image coverage. Manifest: results/correctness_validation_20261001.json.
Existing hardware reports retain their documented scope.
User changed the order on 2026-10-02: #5/#6 instrumentation, #3/#4 CFG/control
flow, #1 relocations, #9 symbols and #7/#11 admission/coverage, then return to #12.
#12 is paused explicitly; #2/#8/#10 remain regression gates.

The local monitor is started with `python3 scripts/correctness-monitor.py`.
It refreshes `out/correctness/progress-monitor.json` every 30 seconds. Its log
records changes and heartbeats; it watches recorded status and does not execute
corrective work or automatically send chat messages.
