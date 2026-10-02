# Twelve-item correctness work

Last updated: 2026-10-02. Verification details: [CORRECTNESS_FIXES.md](CORRECTNESS_FIXES.md).

Work resumed by user on 2026-10-02; WSL is running. Overlay 0027 is pushed as
`be09efb`, nested verification as `b732798`, and runtime reset as `edfa3d7`.
The #6 admission boundary is pushed as `e9cd3b3` and passes 40 focused host tests
and 372 Pi cases per mode, plus reset-fault detection. #3 CFG/assertion parity is
active: overlays 0029/0030 reject pseudo-count mismatches, function fallthrough
and invalid postprocessed CFG in both build modes. Decoded single-register
POP-to-PC returns pass the full Pi state matrix in both modes. Next is #4's
conditional-return/PC-write and pass-safety audit. Broader
#5/#6 coverage stays open. #12 remains separately paused. See CORRECTNESS_RESUME.md.

Fresh source review at `bbae817`: [CORRECTNESS_REVIEW_BBAE817.md](CORRECTNESS_REVIEW_BBAE817.md).
Actionable subitems and closure criteria: [CORRECTNESS_TODO.md](CORRECTNESS_TODO.md).

Active scope: ATFE only, as requested. Upstream work is stopped and excluded
from completion criteria. Three items are complete within this scope (2, 8, 10).

| # | Work | Status | Remaining work |
|---|---|---|---|
| 1 | Relocation matrix and literal loads | Partial | THM_JUMP19 and splitting now supported; complete signed range, alignment, BLX H-bit, addend and unsupported-path coverage |
| 2 | EHABI exidx/extab | Complete via rejection | Unsupported unwind information is rejected; full unwind rewriting remains unsupported |
| 3 | Pseudo/CFG invariants | Partial | Pseudo-count and fallthrough rejection verified in both build modes; worker fatal errors exit after join; wider CFG audit open |
| 4 | Control flow and return semantics | Partial; active | Single-register POP-to-PC decoded and verified on Pi; conditional returns, wider PC writes, live flags and pass/inlining boundaries remain |
| 5 | Instrumentation correctness | Partial; operating scope next | Carry, CPU-state, IT, nested Thumb/recursion and real runtime clear pass on Pi; mixed-ISA nested state, active interrupts and live snapshots remain |
| 6 | Instrumentation scope | Partial | Explicit privileged/single-core/no-FIQ contract and call/process/dynamic rejection pass; audit exclusive-memory and active ISR boundaries |
| 7 | ISA/profile/endianness | Pending | Enforce the supported target feature boundary |
| 8 | FK_Data_8 / ABS32 mismatch | Complete | ATFE host and Pi checks passed; symbolic 64-bit relocations rejected; resolved values and map width corrected |
| 9 | Entry points and symbols | Partial | Entry, split symbols, mapping and mixed-ISA marking improved; aliases, skipped functions, secondary entries, pointer targets and redirects remain |
| 10 | Deterministic stubs | Complete | Stable visitation and layout, mixed-stub alignment fixed; repeated links and Pi checks passed |
| 11 | Rewrite coverage | Partial | TBB/TBH and generic passes implemented; full-image emitted coverage is not execution proof; table/pass boundaries and excluded ELF constructs remain |
| 12 | Verification and artifact integrity | Paused by user, partial | Verified fixes pushed as 43c9e16; resume counter binding, core ownership, other gates, broader inputs, content stamps and clean provenance after the next items |

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
