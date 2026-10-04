# Shared correctness TODO — Claude / Codex

Updated 2026-10-04 through overlay 0061 after the recovered Astra review.
[HANDOFF.md](HANDOFF.md#claims-consolidated-todo) is authoritative for status,
ownership and resource reservations. Fetch it before claiming an unowned item;
publish the claim and required locks before implementation.

The declared P0 milestones are Done. The first corrective work is **R22 → R11
→ R23**, followed by R24/R12/R21 and the remaining matrices. T3's SD-card
install and Secure re-runs remain Deferred by the user; T4 belongs to the user.
No implementation item is claimed. Original workstream #12 remains covered by
the open certification matrices; a scoped milestone does not close all routes.

Published v7 emission coverage is **400/417 functions**, **124282/126834 bytes
(98.0%)**. See the [reconciled review](CORRECTNESS_REVIEW_ASTRA_0057.md) and
[R11 evidence/corrective status](ARM_ADMISSION_REPORT.md). Existing Pi receipts
retain their specific execution scope. The historical material below preserves
closure criteria; its old statuses and stop instructions are superseded.

### Remaining shared work, in resume order

Take items in the order below; groups reflect dependencies, not ownership.

**C. Correctness defects and target items** (declared group B P0 milestones are complete)

| Order | ID | Item | Priority | Owner | Status | Part of | Notes |
|---|---|---|---|---|---|---|---|
| 7a | R22 | Privileged LDM overwrites an inline-table base without rejection | P1 | — | Open | 12 (R18 follow-up) | Host probe accepts `ldmia r4,{r3,r5}^` that clobbers r3; ordinary LDM control rejects. Model register-list definitions or reject conservatively; both-mode must-reject tests. Fix before relying on expanded table admission. |
| 7b | R11 | Isolate Thumb decoder IT state between independent admission scans | P1 | — | Partial (reopened) | 8, 6d | 0054 report mode remains implemented, but truncated ITT/ITE falsely rejects the following valid `bx lr`. Preserve prior receipts; fix symbolic/plain decoder isolation and add both-mode order-independence regressions. |
| 7c | R23 | Noreturn absolute-thunk traversal bypasses cycle detection | P1 | — | Open | 8 (R19 follow-up) | A→B→A MOVW/MOVT/BX thunk chain times out at 8 s; self-cycle rejects, acyclic chain succeeds. Put traversal inside the cache/visited guard; both-mode A32/T32 regressions. |
| 8a | R24 | Decode A32 rotated immediates when computing inline-table bases | P2 | — | Open | 12 (R18 follow-up) | #256 ADD table fixture falsely rejects while #8 control succeeds; ADDri/SUBri MC operand is encoded mod_imm. Test rotated ADD/SUB and malformed table addresses. |
| 9 | R12 | ADR to an inline TBB/TBH table (`vsnprintf`) | P2 | — | Open (analysed, see log) | 12 | Pattern: `adr.w r2, <table>; tbh [pc, r4, lsl #1]; <table>` (424606a8: 0x80030c04). Plan: treat the ADR right before TBB/TBH that addresses that table as a table reference; re-emit it against the emitted table label (reuse 0057's ADR-base mechanism with 0024's TBH model; relax 0045's PC-read rejection only for this shape) |
| 10a | R21 | A32 `-O0` load-then-jump tables (`add rB, pc, #k; ldr rX, [rB, rI, lsl #2]; mov pc, rX` / `bx rX`) still rejected as PC read | P2 | — | Open | 12 | Found by R17 after R18 (`c_switch_arm_o0`, `c_switch_marm_o0`); extend 0057's table model to a register jump |
| 10b | T3 | Secure-SVC parity on the Pi | P2 | — | Deferred TODO (user, 2026-10-04): Secure armstub is built (`tools/pi4-armstub-secure/`, sha `af4a5512…`, install/rollback in its README) but not installed; the SD-card step and the Secure re-runs wait until the user asks | 9 | All Pi results so far are Non-secure SVC; BOLT rewriting is state-agnostic, so T3 is a parity confirmation |
| 10c | T4 | Performance and final validation on the real A55 target (A72 gains not transferable) | P2 | User | Out of scope here | — | Done by the user in the office environment, from this repo |


**D. P1 certification matrices (as capacity allows)**

| Order | ID | Item | Priority | Owner | Status | Notes |
|---|---|---|---|---|---|---|
| 11 | 8 | CFG and mutation invariants | P1 | — | Partial | R4–R6, R19 milestones done; R11, R23 pending |
| 12 | 7 | Relocation/literal/veneer matrix | P1 | — | Partial | R1–R3, R7, R14 done |
| 13 | 11 | Entries/symbols/reference routes | P1 | — | Partial | R9 done |
| 14 | 12 | Tables and inline data | P1 | — | Partial | R18 milestone done; R22, R24, R12, R21 pending |
| 15 | 13 | Actual pass combinations | P1 | — | Partial | R7, R8, R20 done |
| 16 | 9 | Interrupt/reentrancy/reset boundaries | P1 | — | Partial | T2/T2b (SMP execution and counters) done; active-IRQ fixtures still open |
| 17 | 10 | Sampling/PMU ownership | P1 | — | Partial | Per-core PC watch ranges (T2) done; per-sample core attribution and loss/saturation accounting open |
| 18 | 14 | Clean build/content provenance | P1 | — | Partial | Overlay replay + assertions-off build (6a); clean full build and OFF parity for 0060–0061 still open; no-FPU guard misreads BOLT outputs (no input $t in original .text) |

**Needs the user:** new oracle contracts for new configurations; T3 SD-card install only when the user decides (deferred).

### Done

| ID | Item | Priority | Owner | Part of | Patch / evidence |
|---|---|---|---|---|---|
| R1 | Thumb `blx` re-patched as `bl` to ARM targets (61 LK sites) | P0 | Claude | 7 | 0046; `arm-external-branch-repatch.test`; LK raw output 61 → 0 |
| R2 | ARM `B`/`BL`/`BLX` re-patch drops condition; PC+8 | P0 | Claude | 7 | 0046 |
| R3 | Thumb narrow/conditional fixup → relocation mapping | P1 | Claude | 7 | 0046 |
| R14 | RISC-V 64 relocations dispatched to ARM helpers | P1 | Claude | 7 | 0047 (untested: RISC-V not built here) |
| R9 | PatchEntries emits ARM patches into Thumb entries | P1 | Claude | 6c, 11 | 0048; `arm-patch-entries.test` |
| R7 | Far tail call through LongJmp stub becomes `BL` | P1 | Claude | 7, 13 | 0049; `arm-far-tail-call.test` |
| R10 | Global ARM builder in Thumb functions; NOP as trap fill | P2 | Claude | — | 0050; `arm-trap-fill.test` |
| R16 | Full-image coverage report | P1 | Claude | 6d | `scripts/lk_coverage_report.py`, [LK_COVERAGE.md](LK_COVERAGE.md) |
| R4 | Conditional tail calls crash | P1 | Claude | 8 | 0051; Pi: 676 IRQs via rewritten `platform_irq` |
| R5 | Noreturn calls at function end | P1 | Claude | 8 | 0052; LK 276 → 354 functions |
| R6 | Predicated returns and calls in IT blocks | P1 | Claude | 8 | 0053; LK 354 → 399 functions |
| R19 | `mov lr, pc; b X` call idiom (clang ARM-mode) | P1 | Claude | 8 | 0055; `arm-mov-lr-pc-call.test`; edge image: all `c_noret` ARM functions admitted; LK 399 → 400 |
| R20 | ICF aborted on A32 MOVW/MOVT `:lower16:/:upper16:` operands (found while testing R19) | P1 | Claude | 13 | 0056; `arm-icf-movw-movt.test`; ICF now folds such functions (edge image 7 → 26 folded) |
| R18 | A32 inline `ldr pc` jump tables (clang ARM-mode switch / function-pointer tables) | P1 | Claude | 12 | 0057; `arm-ldr-pc-table.test`; edge image: all 6 such functions admitted and run correctly on the Pi |
| R17 | Synthesized edge-case image `bolt_edge`: 146 cases (hand-written A32/T32, C at O0/O2/Os in attribute and whole-module `-marm`/`-mthumb`, 48 seeded random functions) | P1 | Claude | 7, 8, 11, 12 | [Plan](R17_BOLT_EDGE_PLAN.md); contracts `0895d7bc`, `439dfd7c`, `ce8dd005` certified; `docs/results/bolt_edge_*_20261004.json`; optional tuning: more conditional tail calls |
| R13 | Redirect functions whose first instruction is 16-bit followed by a 32-bit one (split prefix) | P1 | Claude | 6c | `redirect-bolt-entries.py`: allowed when no branch, data word or symbol outside the function references the split bytes; unit tests; A55 image 31 redirects (7 split) pass on 4 cores; certified gate on `47c73bc0` with `it_cond` + `branch_chain` executed (`docs/results/r13_split_prefix_certified_20261004.json`) |
| R15 | Full-LK instrumentation blocked by the `arch_spin_trylock` exclusive-reservation guard | P1 | Claude | exclusive guards (0038/0039) | 0059: a return with a live reservation (abandoned, e.g. try-lock failure) is admitted only when a raw scan finds no exclusive store outside analyzed functions; calls/branches out stay rejected; new must-reject cases (caller store, orphan store). Full-LK instrumentation now succeeds on `424606a8` and `47c73bc0` (`docs/results/lk_coverage*_r15_20261004.json`) |
| T2 | SMP: rewritten code on all 4 cores (Cortex-A55-built LK) | P0 | Claude | 9, 10 | `bolt_bench smp` (per-core sink; per-core and concurrent phases), `bolt_sample watch` (per-core PC evidence), `scripts/pi4/smp_verify.py`; contract `e1139981` (smp); certified: SMP gate (72 + 480 sinks on original and rewritten, every core sampled in every required rewritten function) and standard gate (10 reps, 18/18) — `docs/results/t2_*_certified_20261004.json`. Instrumentation part split out as T2b |
| 6c | Legacy/manual hook admission | P0 | Claude | 9, 11, 12 | Manual counter hooks rejected (existing); R13 split prefixes; new `scripts/tests/test_redirect_routes.py` (real ELFs: map route ARM/Thumb, legacy no-map, short, secondary entry, PC-relative prologue, referenced/unreferenced split prefix, unknown function; every refusal leaves the ELF byte-identical) + existing restoration/preservation/late-failure tests. Found and fixed: the split-prefix scan missed unpadded (<8-digit) addresses |
| 6d | Durable receipts on every certification route | P0 | Claude | 12 | Certification routes are `full_image_verify.py` (already complete) and `smp_verify.py` (now: tool/script/patch/option identities, manifest + loader hashes, emitted/redirected sets, expected and observed per-core sinks, log hashes; atomic publication). Tests: `test_smp_gate.py` (checker rejections; preflight refusals before upload, no evidence dir). QEMU routes are labelled diagnostics. Receipt: `docs/results/t2_smp_certified_20261004.json` |
| 6b | Oracle contracts for the declared configurations | P0 | Claude + user | — | Active `pi4` contracts: full LK v7 (`424606a8`), bolt_edge 1/1b/2, A55 (`47c73bc0`), A55 SMP (`e1139981`), A55 whole-module `-marm` SMP (`00d9c42d`); all certified. Contract descriptions corrected (workloads are the default Thumb module; erratum in the draft). New configurations still need the user's review |
| 6a | Every gate proves execution | P0 | Claude | — | Pi gates certify (full_image_verify, smp_verify); QEMU routes are labelled diagnostics that fail closed (G1/G2 done, G3 n/a by user decision); wrappers audited; overlays 0001–0059 pass in both assertion modes (assertions-off `build-atfe-noassert`: ARM lit 50/50, BOLT lit 719 + 110 unsupported asserts-only + the known AArch64 failure) |
| T1 | ARMv8-A AArch32 (Cortex-A55) admission and decode; v8-A Pi image, coverage and certified gate | P0 | Claude | 6b, 7, 11 | Done and certified: contract `47c73bc0` approved (d3c8253); certified gate 10 reps, 18/18, both redirects executed; Image `lk-rpi4-bolt-test-a55-47c73bc0.elf`: 406/416 admitted, rewritten image 2x18 on the Pi; evidence `docs/results/t1_a55_20261004.json`. Build: `make rpi4-bolt-test RPI4_ARM_CPU=cortex-a55` |
| T2b | SMP instrumentation | P1 | Claude | 9, 10 | 0060: `--arm-instrumentation-contract=privileged-smp-no-fiq` routes every counter through an injected A32 LDREXD/STREXD helper (single-core snippet unchanged); injected ARM functions get $a/$t mapping symbols; `arm-counter-smp.test`. Pi (A55 SMP image, 4 cores): all 74 moved counters exact, while the old snippet loses up to ~1.9M increments on 9 hot counters (`scripts/pi4/smp_counter_check.py`, logs `docs/results/t2b_*_counters_pi_20261004.log`). Also fixed: `instrument-lk-bolt.sh` now passes `--no-huge-pages` (instrumented code landed outside LK's reserved window and crashed) |
| R8 | r12 clobbered by local-branch LongJmp stubs | P1 | Claude | 13 | 0061: before stubbing a local branch on ARM, LongJmp computes r12 liveness at the target block (backward CFG fixpoint; calls kill, returns dead) and fails with a clear error when live; `arm-r12-local-stub.test` (ARM+Thumb: live rejected, dead splits with real r12 stubs) |

## Historical 0045 certification closure criteria and evidence

The material below preserves the original closure criteria and milestone
references. Its status, resume-order, oracle-availability and stop statements
are historical snapshots, superseded by the current handoff and tables above.
The earlier R1–R9 labels refer to the Codex 0045 review, not Claude's R1–R17 IDs.

### Archived review through 0045

Updated 2026-10-04 after the [deep review](CORRECTNESS_REVIEW_0045.md).
ATFE only. This is the fresh prioritized list for later work. Original twelve
workstream IDs remain stable in [CORRECTNESS_TODO.md](CORRECTNESS_TODO.md).
Original #12 is included throughout; it is **open**, not excluded or paused.

**Stop at the next verified milestone and publish this list**, as requested.
That instruction supersedes the earlier requirement to finish all P0 before
stopping. Consolidated P0 item 6 remains open. “Verified scoped” below means the
stated contract, not general backend correctness. See the
[milestone contract](AARCH32_ORACLE_MILESTONE.md) for final validation evidence.

## Prioritized work-item table

| Order | Priority | Work item / original IDs | Status at stop | Remaining work and closure criteria |
|---|---|---|---|---|
| 1 | P0 | Skipped interior-entry reservation bypass — #6/#9 | Verified scoped, 0039 | Decoded acquisitions and unpaired stores reject unsafe cross-function routes; retain both-mode regressions. General entry discovery is item 11. |
| 2 | P0 | Thumb instrumentation startup — #3/#9 | Verified scoped, 0040 | Static startup/runtime-to-Thumb execution verified; dynamic hooks and real finalization remain excluded. Retain startup/counter tests. |
| 3 | P0 | ISA/profile/ABI admission — #6/#7 | Verified scoped, 0041 | LE v7-A/Thumb-2, EABI5/base-AAPCS and runtime feature admission enforced. Broader ISA/ABI features require implementation or rejection and both-mode tests. |
| 4 | P0 | Fixed-load ELF boundary — #6/#7/#11 | Verified scoped, 0042 | Fixed ET_EXEC enforced; PIE/dynamic/TLS/GOT/PLT excluded. Preserve mapping/extent/zero-address and no-output rejection controls. |
| 5 | P0 | Exact profile/artifact identity — #12 | Verified sealed scope, 0043; #12 open | Sealed input/map/tool/profile identity verified. Actual end-to-end capture and clean compiler provenance remain in 6a/10/14. |
| 6a | P0 | Every optimization gate proves execution — #11/#12; review R1 | **Open; next task** | Validate complete sealed profile → optimize → exact-map redirect → boot pipeline in both modes. Audit identity/P4/workload/milestone/Pi/measurement wrappers and diagnostic modes; disabled boot, omitted functions, stale artifacts and late failures must never produce a certificate. |
| 6b | P0 | Independent output/state oracles — #11/#12; R2 | Partial; one exact QEMU contract verified | Eighteen independent sinks and four integer ARM entries verified. Add reviewed contracts and selected execution for the next declared supported configuration/Thumb/Pi scope, or enforce exclusion. No approved whole-LK Pi contract exists. Shared-wrong baseline/candidate, flags, memory, return and timeout controls must reject. |
| 6c | P0 | Legacy/manual hook admission — #9/#11/#12; R3 | Partial; whole Thumb prefix guarded; manual counter hooks rejected | Exercise real wrapper routes for sections/maps/legacy no-map redirects, short and interior targets, PC-relative prologues, restoration sizes, scratch limits, existing-artifact preservation and hard failure propagation. Support only with full semantics; otherwise reject before publication. |
| 6d | P0 | Durable coverage receipts — #12; R4 | Partial; fresh bounded QEMU/Pi receipts verified | Extend source/tool/profile/options identities, selected/emitted/redirected/executed sets, independent expected/observed results and logs to every certification route. Test complete receipt CLI construction and late publication failures. Bounded fixture receipts do not close #12. |
| 7 | P1 | Relocation/literal/veneer matrix — #1; R6 | Partial | Document extraction → MC → JITLink → pending/kept writes for each admitted relocation. Execute endpoints/addends/alignment/BLX/Thumb/predicates/split-cold routes; validate veneer opcode/name/size controls and automatic retained v7 thunk targets. Original NEON memcpy/ADR remains excluded. |
| 8 | P1 | CFG and mutation invariants — #3/#4; R5 | Partial; predicated-return gap remains | Model taken return + fallthrough, or reject every affected pass/input. Audit indirect/tail/trap/system transfers, per-function ISA builders and failure-before-publication; verify live LR/SP/NZCV/results in both modes. |
| 9 | P1 | Interrupt/reentrancy/reset boundaries — #5/#6; R8 | Partial; quiet fixtures only | Enforce quiet privilege/core contract or validate active IRQ/exception and monitor interactions. Cover nested interworking/recursion, concurrent clear/read and exact counts; FIQ/SMP/userspace remain excluded without proof. |
| 10 | P1 | Sampling/PMU ownership — #12; R8 | Open; parser/association hardened | Runtime arms all cores. Establish sample/core/PMU ownership, loss/saturation, workload completion and exclusions; preserve IRQ-masked blind spots and distinguish samples from exact edge counts. Wrong ownership/count/completion must fail. |
| 11 | P1 | Entries/symbols/reference routes — #9/#11; R7 | Partial; selected main-entry scope verified | Preserve aliases, secondary/unnamed entries, pointers, mapping transitions, kept callees and in-place references. Validate short/overwritten-interior redirects and exact input/map/ISA identity with actual indirect/original-entry execution. |
| 12 | P1 | Tables and inline data — #1/#11; R7 | Partial | Bound TBB/TBH reach, ambiguous/shared islands and reverse/split/instrumentation interactions. Support or reject ARM tables and unresolved data-to-code routes; ignored code must retain correct references. |
| 13 | P1 | Actual pass combinations — #4/#11; R9 | Partial | Prove that profile-driven reorder/split/peephole/inlining changed code safely; audit ICF/address identity, tail duplication, generic hooks and debug/DWARF. Record each real transformation; no-op success is not coverage. |
| 14 | P1 | Clean build/content provenance — #12; R9 | Partial; exact 45-overlay source replay only | Isolate a clean full build of assessed overlays, bind exact source/config/tools, compare both modes, audit export/modes and preserve live dirty ATFE/LK. Source replay and binary version banners are insufficient. |

## Milestone and caveats

The independent QEMU oracle and compatible BL/LR Pi witnesses improve item 6.
The wider Pi matrix uses nine edge seeds per ISA pair, including signed overflow
and wraparound, independent NZCV checks, and result/flag/retained-callee/hang
controls. These proofs remain bounded; consult the milestone evidence for exact
successful run counts and all failed diagnostics.

Whole-LK rewriting, original NEON memcpy, active interrupts/SMP, automatic v7
retained-thunk routes, arbitrary entries and clean compiler provenance are not
certified. Conservative rejection is retained where implemented. A source risk
or missing evidence is not presented as a freshly reproduced backend failure.

Only original #2 (EHABI rejection), #8 (data widths) and #10 (deterministic mixed
stubs) remain complete within their original bounded scope; nine original
workstreams remain open. Keep their tests green. Resume later with **6a**; do not
close #12 from one fixture or advance to P1 while claiming P0 is complete.

The [previous queue and checkpoints](CORRECTNESS_PRIORITY_TODO_0038_HISTORY.md)
are preserved as history; their earlier “continue”/“stop all P0” instructions and
pending-oracle/MOV-PC statements are superseded by this table and milestone.
