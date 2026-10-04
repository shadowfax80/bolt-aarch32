# Claude ↔ Codex handoff

Two agents work on this repo: **Claude** (Claude Code) and **Codex**. This file
is the single source of truth for who owns what. Read it before starting work,
and update it before stopping. `AGENTS.md` and `CLAUDE.md` point here.

## Rules

1. **One writer per live tree.** The shared WSL ATFE source
   (`/home/user/bolt-aarch32/third_party/llvm-project-atfe`), all assertion-mode
   builds, shared LK source and shared build outputs are covered by *Live-tree
   lock*. Only its holder may mutate or rebuild them. Acquire and release the
   lock by committing **and successfully pushing** the table update. A local
   commit alone grants no shared-resource ownership.
2. **Shared pool; claim before work.** Open items belong to no agent; either
   may take any of them, whatever its origin. Before starting, set *Owner* to
   yourself and *Status* to "In progress" in one commit and push it. Do not
   start an item the other agent has claimed; to take it over, ask the user
   and record it in the *Handoff log*. Done items keep their owner as a record.
3. **One overlay per item.** Each source change is exported as the next
   `overlay/llvm/patches/atfe/NNNN-*.patch` with its own lit/unit test. Before
   pushing, `scripts/verify-atfe-overlays.py` must replay the full series with
   no mismatched or uncovered files.
4. **Evidence, not claims.** A *done* status names the patch, the tests and the
   before/after measurement. Hardware claims come from the Pi only (watchdog
   armed); QEMU is for debugging.
5. **Hand off on stop.** Append a *Handoff log* entry (newest first) and push.
   The entry says what changed, what was verified, the live-tree state, and
   what the other agent should do next.
6. **Regenerate coverage on handoff.** After any change to the backend or
   the LK test image, rerun `scripts/lk_coverage_report.py` on the full LK
   test binary and commit [LK_COVERAGE.md](LK_COVERAGE.md) plus its
   `docs/results/lk_coverage_*.json`. Quote the before/after numbers in the
   log entry.
7. **Project rules still apply:** no FPU/NEON (`-mfpu=none`,
   `scripts/check-no-fpu.sh`); no oracle contract derived from Pi output
   without the user's review; keep admission guards conservative.
8. **Reserve the Pi separately.** Publish a *Pi reservation* before opening
   COM5 for probes, uploads, commands, sampling or watchdog changes. The source
   lock does not reserve the Pi. Close the port and record the board, sampler
   and watchdog state before publishing the release.

## Picking up shared work

Fetch and fast-forward a clean checkout, then read remote claims and resource
holders before claiming work. Preserve dirty trees and evidence; do not reset,
stash or reapply overlays to synchronize. Publish the item claim and required
reservations with a normal push before resource use. If the push is rejected,
fetch, re-read ownership and retry only for resources still free. Never resolve
a documentation conflict by overwriting another agent's winning claim.

Recorded WSL/Pi state is a **last-observed snapshot**, not a live guarantee.
Check current ownership and tool/input identities before use. Local memories
and historical log entries do not assign ownership.

## Resuming (no session context needed)

Everything needed to continue is in this repo:

- **What to do next:** *Claims* below, Open tables in resume order.
- **Findings and plans:** [Recovered Astra review, reconciled through 0061](CORRECTNESS_REVIEW_ASTRA_0057.md),
  [CORRECTNESS_REVIEW_CLAUDE_0E616EB.md](CORRECTNESS_REVIEW_CLAUDE_0E616EB.md),
  [R17_BOLT_EDGE_PLAN.md](R17_BOLT_EDGE_PLAN.md), [LK_COVERAGE.md](LK_COVERAGE.md),
  [PI4_ORACLE_CONTRACT_DRAFT.md](PI4_ORACLE_CONTRACT_DRAFT.md) (approved).
- **Certified input image:** `fixtures/lk-rpi4-bolt-test-424606a8.elf`
  (see `fixtures/README.md`); the skip list is in
  `docs/results/lk_coverage_r15_20261004.json` (`skip_funcs`).
- **Backend source:** overlays `overlay/llvm/patches/atfe/0001–0061`; the WSL
  live tree must replay them exactly (`scripts/verify-atfe-overlays.py`).
  Do not run `scripts/apply-overlays.sh` on the dirty live tree.
- **Commands:**
  - Coverage: `python3 scripts/lk_coverage_report.py --elf fixtures/lk-rpi4-bolt-test-424606a8.elf --toolchain /home/user/bolt-aarch32/build-atfe/bin --out <fresh dir> --doc docs/LK_COVERAGE.md --json docs/results/lk_coverage_<date>.json`
  - Raw re-patch check: `python3 scripts/check_raw_original_text.py --input <elf> --raw <llvm-bolt output> --toolchain <bin>`
  - Certified Pi run: `scripts/pi4/full_image_build.py` then
    `py -3.12 scripts/pi4/full_image_verify.py <dir> --require-executed <redirects> --repeat 10 --port COM5 --fast-loader tools/pi4-serialboot-fast/kernel7l_fast.img`
  - Sealed profile chain: `profile_identity.py seal-samples` →
    `pi4/pi4_sample_profile.py` → `samples_to_fdata.py --skip-funcs …` →
    `full_image_build.py --profile …` (see `docs/PI_PROFILE_IDENTITY.md`).
- **Environment notes:** use a Windows Python with pyserial (`py -3.12` or
  the Codex venv `out/correctness/pi-venv/Scripts/python.exe`); Pi on
  COM5; sample captures occasionally fail chunk validation (USB corruption),
  retry; never `git stash` from WSL on the Windows checkout.
- **Build versions:** ON is `build-atfe`; current OFF is `build-atfe-noassert`,
  last reported tested through 0059. The older OFF build
  `out/correctness/build-atfe-noasserts-20261002` is 0054 evidence. ON 0060–0061
  checks do not establish OFF parity for those overlays; recheck build hashes.
  Preserve both older receipts and dirty live source.

## Target platform (user, 2026-10-04) and gap to it

The product target is **Cortex-A55, SMP, AArch32 bare-metal LK, always SVC,
mostly Secure, no FPU and no NEON**. Testing here uses Pi 4B A72 cores only;
the user will port and perform final validation on the real A55 target from
this repo. Keep build recipes, LK/backend overlays and approved contracts
portable. Pi evidence covers the executed A72-compatible instructions and
workloads; A55 timing and target-platform behavior require target evidence.

| Aspect | Implemented / verified at 89dd17f | Remaining gap |
|---|---|---|
| ARMv8-A AArch32 | T1 Done: 0058 accepts v8-A attributes and decodes v8 integer instructions; LK patch 0011 adds `cortex-a55`; approved A55-built Pi fixtures certified | No A55-only instruction or target-hardware claim; keep the A72-compatible subset explicit |
| SMP execution | T2 Done: declared rewritten workloads run on all four Pi cores with independent sinks and per-core PC evidence | Wider runtime/IRQ matrix 9 and PMU/loss matrix 10 remain Partial |
| SMP counters | T2b Done: 0060 privileged-SMP-no-FIQ helper; all 74 selected counters match the scoped Pi model | Reset/snapshot require quiescence; broader instrumentation matrix and OFF checks for 0060 remain open |
| No FPU / NEON | Inputs guarded with `-mfpu=none`; scanner fail-closed since 000a8a4; runtime integer-only | Item 14: candidate ISA metadata/scanner still misdecodes restored original code; keep input and emitted-code checks scoped |
| Privileged SVC | Declared Pi routes run in SVC | Broader entry/state/interrupt preservation remains in the certification matrices |
| Secure state | Prepared Secure armstub in `tools/pi4-armstub-secure/`, uninstalled; all Pi evidence remains Non-secure SVC | T3 P2 Deferred TODO by latest user decision: wait for the user before SD-card install or Secure re-runs |
| IRQ / PMU | IRQ sampling hook and scoped rewritten IRQ evidence; per-core watch ranges available | Active IRQ/reentrancy, per-sample core attribution and loss/saturation accounting remain open; GICv3 target needs the equivalent platform hook |
| Performance / real target | Pi is out-of-order A72; target A55 is in-order | T4 P2 belongs to the user on target hardware; Pi gains do not transfer |

T1/T2 and the declared P0 routes are completed milestones. The recovered Astra
review predates them: use its reconciled findings, not its old target-blocker
summary. R22, R11 and R23 are the first corrective work below. T3 remains
deferred; new image/configuration oracle contracts still require user review.

## Live-tree lock

| Holder | Since | Purpose |
|---|---|---|
| — (free) | 2026-10-04 | Released by Claude after overlays 0060–0061 |

## Pi reservation

| Holder | Since | Purpose / last observation |
|---|---|---|
| — (unreserved) | 2026-10-04 | Latest Claude handoff reports Pi idle at 89dd17f. Codex/Sol has not opened COM5 or changed the board during this review; reserve and recheck before use. |

## Claims (consolidated TODO)

One shared list. Review items (R*) come from the 2026-10-04 Claude review
([details](CORRECTNESS_REVIEW_CLAUDE_0E616EB.md)) and the
[recovered Astra review](CORRECTNESS_REVIEW_ASTRA_0057.md); certification items
(6a–14) keep their closure criteria in
[CORRECTNESS_PRIORITY_TODO.md](CORRECTNESS_PRIORITY_TODO.md). "Part of"
links an R item to the certification item it contributes to; closing the R
item does not close that item. *Owner* is empty until someone claims it.

### Requested maintenance

| ID | Item | Priority | Owner | Status | Scope |
|---|---|---|---|---|---|
| M1 | Repository health and documentation consolidation (user request) | P2 | Codex | In progress | Docs/tooling only; no shared-source lock or Pi reservation needed |

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

## Coverage goal

Raise BOLT coverage of the full LK test binary, measured only by
`scripts/lk_coverage_report.py` ([LK_COVERAGE.md](LK_COVERAGE.md)).

| Step | Item | LK functions recovered | Coverage after (functions) |
|---|---|---|---|
| Baseline 2026-10-04 | — | — | 273/417 (65.5%); 79.1% of code bytes |
| 1 | R4 conditional tail calls (crash) — **done, 0051** | 3 | 276/417 (66.2%); 79.2% of code bytes |
| 2 | R5 noreturn calls at function end — **done, 0052** | 78 | 354/417 (84.9%); 92.6% of code bytes |
| 3 | R6 predicated returns and calls in IT blocks — **done, 0053** | 45 | 399/417 (95.7%); 97.9% of code bytes |
| 4 | R19 call idiom — **done, 0055** | 1 | 400/417 (95.9%); 98.0% of code bytes |
| 5 | R12 ADR to inline switch table | 1 expected | Pending |
| 6 | R15 try-lock reservation guard — **done, 0059** | in-scope workload instrumentation | See `lk_coverage_r15_20261004.json` |

**Published v7 coverage:** 400/417 functions, 124282/126834 code bytes (98.0%).
Ten rejected symbol rows remain in the latest v7 receipt; admission of
`arm_secondary_entry` does not authorize relocating or redirecting startup code.
Keep vectors/early setup in place and reject genuine fallthrough. Coverage is
emission coverage, not execution or whole-backend correctness.

**Done means, for each step:**

1. Admit the pattern only with a model that is correct in both assertion
   modes, with lit tests for the newly admitted shapes and for the shapes
   that must still reject. Never widen admission by skipping a check.
2. Regenerate the coverage report and quote before/after function and byte
   numbers in the handoff log.
3. Rebuild the full-image candidate (all newly admitted functions emitted)
   and run it on the Pi with the watchdog: all 18 results equal baseline and
   the reference formulas. Note which newly admitted functions executed.
4. Update the *Claims* table and LK_COVERAGE.md together.

## Handoff log

### 2026-10-04 — Codex claims M1 repository health cleanup

- User requested a repository health check and removal of redundant/stale
  information. M1 is claimed for documentation and repository-check tooling.
  Backend queue/ownership unchanged; live-tree lock free; no Pi access.
- Preserve historical receipts and dirty local trees. Consolidate active status
  in HANDOFF.md, retire contradictory entry points, and verify links, tracked
  artifacts and overlay inventory before publishing the cleanup.

### 2026-10-04 — Codex/Sol: recovered Astra review consolidated through 0061

- Synced to `89dd17f`, read Claude's newer milestones, recovered the completed
  Astra review and earlier host probes. Published
  [review](CORRECTNESS_REVIEW_ASTRA_0057.md) and
  [durable evidence](results/astra_review_20261004/evidence.json).
- R11 reopened Partial/unclaimed for leaked Thumb IT state. New shared items:
  R22 P1 privileged-LDM base-clobber admission, R23 P1 thunk-cycle analysis
  nontermination, R24 P2 encoded-immediate table-base rejection. Source through
  0061 still contains their causes. Original probes bind ON 0057 and OFF 0054
  (IT only); no new probe or both-mode 0061 claim is made.
- Kept T1/T2, T2b, R8/R13/R15 and declared 6a–6d milestones Done. R18/R19's
  positive milestones remain; new IDs track their edge cases. T3 stays Deferred
  under the latest user decision. Corrected stale target/skip-list/build guidance,
  synchronized TODO/resume views and local Claude memory, and added successful-
  push ownership plus separate Pi reservation rules.
- Review/docs only: no backend/image change, rebuild, upload, sampling or COM5
  access. Coverage unchanged: v7 400/417 functions, 124282/126834 bytes (98.0%);
  existing receipts preserved. No coverage rerun required. Dirty ATFE/LK,
  unrelated Microsoft/ and prior raw evidence are preserved. WSL executes reads;
  Pi idle is Claude's last observation, not a new access check.
- No implementation item claimed; live-tree lock remains free. Next agent:
  claim R22, then R11/R23, before resuming the P2 table work; export one overlay
  per item with both-mode regressions, replay and appropriate execution evidence.
  Use the next available overlay number, not the old R12 plan's reserved 0062.

### 2026-10-04 — Claude: R12 analysed; released (usage limit)

- `vsnprintf` (full LK `424606a8`, also the A55 builds) is rejected at
  `adr.w r2, #4` (0x80030c04), immediately followed by `tbh [pc, r4, lsl #1]`
  and the inline halfword table at 0x80030c0c: clang materialises the
  table base in r2 although TBH indexes from PC.
- Fix plan (one overlay, 0062): in the TBH model (0024), when the instruction
  right before TBB/TBH is `adr Rd, <table start>`, record it as the table's
  base and re-emit it against the emitted table label (the 0057 mechanism:
  `createInlineTableBase` / per-emission named labels); relax the 0045 PC-read
  rejection only for this exact shape. Keep rejecting an ADR to a table that
  is separated from the TBB/TBH or whose register is clobbered in between.
  Tests: Thumb lit fixture (ADR+TBH and ADR+TBB, default and reversed
  layout; separated/clobbered rejected), then full-LK coverage (expect
  401/417) and a Pi run.
- Lock free; R12 unclaimed. WSL synced, Pi idle.

### 2026-10-04 — Claude: T2b and R8 done (overlays 0060, 0061); lock released

- **T2b (0060):** new contract value `privileged-smp-no-fiq` (option moved to
  Passes/Instrumentation.cpp). Each probe saves r0-r3/r12/lr, keeps CPSR in
  r12, masks IRQ and calls the injected A32 `__bolt_instr_counter_incr`
  (`ldrexd/adds/adc/strexd` retry loop). The single-core snippet and its byte
  test are unchanged. Injected ARM functions now get `$a`/`$t` mapping
  symbols (the helper after a Thumb function was decoded as Thumb).
- **Pi proof** (`scripts/pi4/smp_counter_check.py`, A55 SMP fixture, 15
  concurrent-set workloads instrumented): single runs → dump C1, then
  `bolt_bench smp 4` → dump C2; exact model C2 = 5·C1 + 16·D (banner/quiet
  paths). SMP contract: 74/74 moved counters exact. Old snippet: 9 hot
  counters lose updates (e.g. 20,999,979 expected, 19,080,915 seen).
- **Found and fixed:** instrumented images crashed on the Pi (undefined abort
  in the first instrumented function): `instrument-lk-bolt.sh` used BOLT's
  huge-page layout (code 0x80400000, counters 0x80601000), outside the 1 MB
  window LK reserves after `_end` (patch 0006), so LK's page array overwrote
  them. The wrapper now passes `--no-huge-pages` (image 6.3 MB → 0.87 MB).
- **R8 (0061):** LongJmp checks r12 liveness before stubbing a local ARM
  branch and refuses when live (calls/tail calls exempt by AAPCS).
- Tests: ARM lit 52/52; BOLT lit 746 + the known AArch64 failure;
  0001–0061 replay exactly (`aa28c8df…`).
- Known tooling gap: `check-no-fpu.sh` on BOLT *output* images misreads the
  original `.text` (BOLT drops the input's `$t` symbols there) and reports
  false NEON; check inputs and new code, or decode with the input's mapping
  symbols. Next in order: R12.

### 2026-10-04 — Claude: T3 deferred (user)

- User: mark the SD-card part of T3 as TODO and defer it. The Secure armstub
  stays prepared in `tools/pi4-armstub-secure/` (not installed). Do not
  start the Secure re-runs or ask for the SD change until the user asks.
  All Pi results remain Non-secure SVC.
- State: lock free, no claims; WSL synced; Pi idle. Remaining open: T2b
  (SMP instrumentation), R8, R12, R21, P1 matrices, T3 (deferred), T4 (user).

### 2026-10-04 — Claude: 6a done (both assertion modes)

- New assertions-off build `build-atfe-noassert` (WSL; Release, bolt+lld,
  X86/AArch64/ARM). BOLT, llvm-mc, ld.lld, objdump/readelf/nm/objcopy,
  FileCheck and llvm-config are native assertions-off; helper tools it does
  not build (clang, llc, ...) are symlinked from `build-atfe`. Lit config: a
  copy of build-atfe's BOLT `lit.site.cfg.py` with obj/tools dirs pointed at
  the new build; `bolt-rt-baremetal-arm` copied next to it.
- ARM lit 50/50; full BOLT lit 719 passed, 110 unsupported (asserts-only
  tests), 1 failed (the known AArch64/constant_island_pie_update.s).
  Pitfall: with a symlinked assertions-on llvm-config, lit runs asserts-only
  tests and 16 fail spuriously; build the native llvm-config.

### 2026-10-04 — Claude: T3 prepared (Secure-SVC armstub); waiting on SD card

- `tools/pi4-armstub-secure/armstub7-secure.S`: Raspberry Pi's armstub7.S
  (downloaded unmodified as `armstub7.upstream.S`) with three marked changes:
  no switch to Non-secure HYP (kernel entered in Secure SVC); all interrupts
  kept in GIC Group 0 as IRQ (`FIQEn=0`); `CNTVOFF` zeroed from Monitor mode
  with `SCR.NS` set briefly. Built with `build.sh` (upstream defines and
  layout; 256 bytes; 0 FP/NEON; sha256 `af4a5512…`).
- Checked: LK `start.S` and the fast loader drop HYP→SVC only when entered in
  HYP; LK's GIC driver writes `GICD_CTLR=1`/`GICC_CTLR=1` (Group 0 enable in
  the Secure view) and never touches `IGROUPR`, so no LK GIC change.
- **Needs the user:** copy `out/armstub8-32-gic-secure.bin` to the SD boot
  partition and add `armstub=armstub8-32-gic-secure.bin` to `config.txt`
  (rollback: remove that line). Then: LK boot-time Secure check (entry mode +
  Secure-only register), and re-run full_image_verify / smp_verify /
  bolt_edge in Secure SVC.
- 6a: assertions-off rebuild (`build-atfe-noassert`) still compiling in WSL.

### 2026-10-04 — Claude: 6b done for the declared configurations

- Found and corrected: contract descriptions said bolt_bench was `-marm`; the
  approved images use LK's default Thumb module (39/44 functions Thumb, ARM
  ones via `target("arm")`). Hashes, oracle and results unaffected; erratum
  in `docs/PI4_ORACLE_CONTRACT_DRAFT.md`.
- New configuration: A55 full LK with `BOLT_BENCH_ISA=arm` (36 ARM / 8 Thumb
  workload functions), `fixtures/lk-rpi4-bolt-test-a55-marm-00d9c42d.elf`:
  original 18/18 + SMP; 406/416 admitted, instrumentation OK; rewritten (31
  redirects) 18/18 + SMP 72/480. User approved the SMP contract (a23d00a);
  certified: SMP gate and standard gate (receipts
  `docs/results/6b_a55_marm_*_certified_20261004.json`).
- Remaining before T3: 6a assertions-off re-check (build running in WSL:
  `build-atfe-noassert`).

### 2026-10-04 — Claude: 6d done

- `smp_verify.py` receipts now carry the same identity set as
  `full_image_verify.py` plus expected and observed per-core sinks, and are
  published atomically (`write_json`: staged + replace). Re-run on the
  certified SMP candidate: PASS, full receipt replaces
  `docs/results/t2_smp_certified_20261004.json`.
- New `scripts/tests/test_smp_gate.py` (7 tests): checker rejects missing,
  misplaced, wrong, duplicate, incomplete and repeated runs; `smp_verify.py`
  refuses unreviewed inputs, non-SMP contracts, uncovered or non-concurrent
  redirects and image/manifest mismatches before any Pi access and without
  creating an evidence directory.
- Remaining before T3: 6a assertions-off re-check (build running), 6b.

### 2026-10-04 — Claude: 6c done

- New `scripts/tests/test_redirect_routes.py` runs `redirect-bolt-entries.py`
  end to end on real llvm-mc/ld.lld/llvm-bolt images (needs TOOLCHAIN): map
  route ARM and Thumb, legacy no-map, short function, secondary entry in the
  prefix, PC-relative prologue, referenced and unreferenced split prefix,
  unknown function. Every refusal leaves the output ELF byte-identical.
- The test caught a real bug in R13's reference scan: it only matched 8-digit
  hex, so a branch to `f+2` printed as `0x800a` was missed. Fixed (any width);
  the LK A55 redirects are unchanged (identical image, 31 redirects, 7 split),
  so certified results stand. Script tests: 28 + 8 pass.

### 2026-10-04 — Claude: 6a wrapper audit (QEMU routes diagnostic, fail closed)

- `verify-bolt-arm32-harness.sh`: `--diagnostic`; `REBUILD_LK` defaults to 0
  (never re-applies overlays on the dirty live tree). Runs: DIAGNOSTIC
  COMPLETE WORKLOAD.
- `verify-bolt-arm32-milestones.sh`: all intermediates in a fresh
  `out/arm32-milestones/run-*` (no `/tmp` reuse); P0 diagnostic; P1 scoped to
  the selected functions (full-image rewrite correctly rejects startup code);
  P4 delegates to the identity wrapper. P0–P3 pass in QEMU.
- `verify-bolt-arm32-identity.sh`: certifies via `qemu_rewrite_build.py` only
  with a reviewed qemu-virt contract; otherwise a labelled diagnostic in a
  fresh directory. It refuses images without a protected BOLT window
  (`__bolt_reserved_*`): on the QEMU twin, BOLT's new code sits after `_end`
  and LK's heap overwrote it ("unhandled syscall" in the rewritten copy). So
  QEMU rewrite diagnostics need a reserved window in the QEMU project (like
  rpi4's LK patch 0006) — low priority, QEMU is a debug aid.
- Already audited and sound: `full_image_verify.py`, `smp_verify.py`,
  `qemu_rewrite_gate/build.py` (contract-bound), `qemu_workload_gate.py
  --check-log/--diagnostic`, `passes_check.py`, `measurement_records.py`
  (labelled, no execution claim).
- 6a left: re-check overlays 0055–0059 in an assertions-off build.

### 2026-10-04 — Claude: T2 certified (SMP); T2b split out

- `bolt_sample watch <lo> <hi>` counts samples per core inside a range;
  `scripts/pi4/smp_verify.py` runs `bolt_bench smp` on the original and the
  rewritten image and requires oracle-equal sinks on every core plus samples
  inside every required rewritten function on every core.
- User approved the SMP contract for `fixtures/lk-rpi4-bolt-test-a55-smp-e1139981.elf`
  (ed324be). Certified with redirects `interwork`, `spill_ret`, `it_cond`
  (split prefix): SMP gate PASS (per-core samples interwork 29/23/29/28,
  spill_ret 457/463/466/466, it_cond 2265/2267/2270/2272); standard gate
  PASS (10 reps, 18/18). Receipts `docs/results/t2_smp_certified_20261004.json`,
  `docs/results/t2_std_certified_20261004.json`.
- T2b (P1, open): SMP instrumentation needs a cross-core-atomic counter path.
- Next toward T3: 6a wrapper audit, 6c, 6d, 6b; then T3 (Secure SVC, approved).

### 2026-10-04 — Claude: R15 done (overlay 0059)

- The exclusive-reservation guard rejected `arch_spin_trylock` (`ldrex; cmp;
  strexeq; bx lr`): the failure path returns with the reservation open. An
  abandoned reservation can only be consumed by an exclusive store that has
  no local reservation, and every analyzed store must already be locally
  paired; so a live *return* is now admitted when a raw ARM+Thumb scan of
  executable bytes outside analyzed functions finds no exclusive store. Calls
  and branches out with a live reservation stay rejected. BOLT logs the
  admission (`reservation abandoned on return in arch_spin_trylock ...`).
- Tests: `arm-cross-function-exclusive.test` now admits `live_return`,
  `predicated_return`, `trylock`; new must-reject `live_return_caller_store`
  and `live_return_orphan_store` (ARM and Thumb). ARM lit 50/50; BOLT lit 744
  + the known AArch64 failure; 0001–0059 replay exactly (`ba5196d4…`).
- Full-LK instrumentation (bolt_bench functions, BOLT-generated per-edge
  counters) now succeeds on `424606a8` and the A55 `47c73bc0`.
  `lk_coverage_report.py` now uses `BOLT_INSTR_EDGES=1`; the legacy manual
  hook path stays rejected (6c). Instrumented images are not yet run on the
  Pi in this step.

### 2026-10-04 — Claude: R13 done (split-prefix redirects)

- `redirect-bolt-entries.py`: a 4-byte B.W over a 16-bit + 32-bit prefix is
  allowed when no reference from outside the function (branch/call target,
  ADR/literal comment, data word in the original `.text` disassembly) and no
  symbol points into the split bytes; otherwise it refuses and names the
  referencing address. Reports `split_prefix` per redirect. MOVW/MOVT-built
  addresses are not combined (documented limit; LK uses them for entries).
- A55 SMP image: 31 redirects (7 split, incl. branch_chain, far_call,
  it_cond) → `bolt_bench smp 8` + `all` pass on the Pi. Certified gate on the
  approved `47c73bc0` with `bolt_bench_it_cond` + `bolt_bench_branch_chain`
  (both split): 10 reps, 18/18, PC evidence for both. `far_call` is too short
  for PC sampling to observe (results still correct).
- Script tests 28/28 (`test_execution_gate.py`).

### 2026-10-04 — Claude: T2 milestone — rewritten code verified on all 4 cores; claim released

- **Harness:** `bolt_bench smp [reps]`. The sink is per core (a macro, so
  workload code is unchanged). Phase 1 runs the full suite on each core in
  turn (pinned thread, reports `arch_curr_cpu_num()`); phase 2 runs the 15
  workloads with no shared state other than the sink on all cores at once,
  `reps` times, rotated per core. memcpy, composite, stair stay out of
  phase 2 (shared buffers / PMU state). Checker:
  `scripts/bolt_bench_smp_check.py` (oracle values, core placement, counts).
- **Pi (A55-built LK, `e967850f`):** original 4 cores, seq 72 + conc 240
  sinks pass. Rewritten (403 emitted, 15 redirects): seq 72 + conc 480
  (8 reps) pass, no faults. Evidence `docs/results/t2_smp_20261004.json`.
- **Still open for T2:** per-core PC evidence (sampler cannot attribute PCs
  to cores, matrix 10); SMP instrumentation contract (also blocked on full LK
  by R15); a `pi4` contract for an image with the harness and a certified
  gate that runs `bolt_bench smp` (`full_image_verify.py` does not yet).
- bolt_bench source changed (sink macro + smp command), so future images get
  new source hashes; existing fixtures and contracts are unaffected. Lock
  free; T2 unclaimed.

### 2026-10-04 — Claude: T1 (ARMv8-A AArch32 / Cortex-A55) implemented; lock released

- **LK (overlay/lk/patches/0011):** `ARM_CPU=cortex-a55` (v7-A-compatible LK
  defines + `ARM_ISA_ARMv8`, `ARM_WITH_HYP`, `WITH_NO_FP`; `-mcpu=cortex-a55
  -mfpu=none`, no FP for float modules); `cores.h` recognises clang's
  `__ARM_ARCH_8_2A__`; rpi4 CPU selectable via `RPI4_ARM_CPU` (default stays
  cortex-a15, so existing fixtures rebuild unchanged). Secondary-core count
  uses LK's generic path (no A15 `L2CTLR`).
- **Backend (overlay 0058):** admission accepts `Tag_CPU_arch` v8-A (v9 and
  other profiles still rejected); decoding adds `v8.2a` (acquire/release,
  perfmon; no FP/NEON); a v8 runtime library needs a v8 input. Tests: new
  `arm-v8-aarch32.test` (A32+T32 `lda/stl/ldab/stlh/ldaex/stlex/sevl/dmb
  ishld` preserved in moved functions, default and reversed layout),
  `arm-isa-contract.test` now admits armv8a and checks v8-runtime/v8-input.
  ARM lit 50/50; BOLT lit 744 passed + the known AArch64 failure; CoreTests
  58; JITLink AArch32 15/15; 0001–0058 replay exactly (`6383f78d…`).
- **Pi (A72):** A55-built LK `lk-rpi4-bolt-test-a55-47c73bc0.elf` boots, 18/18 sinks equal the
  independent oracle. Admission 406/416 (same rejection classes as v7).
  Rewritten image (400 emitted, 15 redirects) 2 × 18 on the Pi, 0
  mismatches, no faults. ISA scan: only v8.0 instructions (`lda`, `stl`,
  `stlex`), so the A72 runs it.
- **Finding:** 16 bolt_bench Thumb functions, incl. `bolt_bench_memcpy`
  (a certified-gate redirect), start with a 16-bit instruction in the A55
  build → R13 raised to P1.
- **Certified:** user approved the `pi4` contract for `47c73bc0`
  (d3c8253). `full_image_verify.py` (10 reps): 18/18 against the independent
  oracle, PC evidence in both redirects (`bolt_bench_interwork`,
  `bolt_bench_spill_ret`; memcpy needs R13). Receipt:
  `docs/results/t1_a55_certified_20261004.json`.
- **Next:** T2 (SMP). Lock free.

### 2026-10-04 — Claude: Secure SVC on the Pi approved (T3)

- User approved Secure-SVC bring-up on the Pi for PoC parity; it follows T1
  (A55 build) and T2 (SMP). This lifts the earlier "Secure SVC only when the
  user asks" hold for T3. No code change; lock free.

### 2026-10-04 — Claude: target platform recorded; T1–T4 added

- User: target is Cortex-A55 SMP, AArch32 bare-metal LK, always SVC, mostly
  Secure, **no FPU and no NEON**. New section *Target platform* above.
- Main finding: 0041 admits only ARMv7-A attributes (`armv8a` is a must-reject
  test), so an A55-built image is rejected; SMP execution of rewritten code is
  unverified. Added T1 (v8-A AArch32, P0) and T2 (SMP, P0) at the head of
  group B, T3 (Secure-SVC confirmation run, now P2/optional) and T4 (target performance, P2) in group C.
- No code change; lock free.

### 2026-10-04 — Claude: 6a QEMU route + no-FPU guard fix; paused at R15

- **No-FPU guard was failing open (fixed).** `scripts/check-no-fpu.sh` took
  `TOOLCHAIN` as its bin dir; LK builds export `TOOLCHAIN=clang`, so
  `llvm-objdump` was not found, the error was hidden and every file passed.
  It now uses `NOFPU_TOOLCHAIN`/a real bin dir, exits 2 without objdump and
  fails on a disassembly error. Certified Pi fixtures re-checked directly:
  0 VFP/NEON in all of them.
- **The QEMU ARM32 image had 3,392 VFP/NEON instructions** (upstream
  `qemu-virt-arm32-test`: libm, gfx, benchmarks; no `-mfpu=none`). ARM32
  QEMU defaults (build, instrument, optimize, workload, harness, identity,
  milestones, verify-all, run-qemu) now use the twin
  `qemu-virt-arm32-bolt-test`, which sets `ARM_WITHOUT_VFP_NEON`,
  `-mfpu=none`, overrides LK's float-module flags and, via new LK patch
  `overlay/lk/patches/0010-qemu-virt-arm-optional-gpu.patch`
  (`BOLT_NO_VIRTIO_GPU`), drops the virtio GPU / PCI catch-all whose
  lib/gfx needs soft-float helpers. Result: 0 FP/NEON, boots, 18 workloads.
  Patch 0010 is applied in the WSL live LK tree.
- **Diagnostic mode:** `qemu_workload_gate.py --diagnostic` (no contract,
  baseline/candidate consistency only, receipt scope "DIAGNOSTIC");
  `verify-bolt-workloads.sh` uses it.
- **QEMU run (WSL):** `ARM_INSTRUMENTATION_CONTRACT=privileged-single-core-no-fiq
  BASE=atfe ARCH=arm32 REBUILD_LK=0 scripts/verify-bolt-workloads.sh`:
  baseline DIAGNOSTIC COMPLETE WORKLOAD; instrumentation then stops on R15
  (`arch_spin_trylock`: return with a live reservation). Next for 6a: R15
  (group C) unblocks the rest of this route; then audit the remaining
  wrappers (identity, P4, milestone, measurement).
- 13/13 script test modules pass; all scripts pass `bash -n`. WSL synced, no
  jobs; Pi idle. Lock free; 6a unclaimed.

### 2026-10-04 — Claude: 6a paused (usage limit); claim released

- **User decision:** QEMU is a diagnostic/debug route; certification is
  Pi-only (`full_image_build.py` + `full_image_verify.py`, already proven).
  G3 (QEMU contracts) is therefore not needed for 6a.
- **Done (scripts, unit-tested; 13/13 script test modules pass):**
  - G1: `verify-bolt-workloads.sh` writes every intermediate (instrumented
    ELF, counters, fdata, optimized ELF, serial log, evidence) to a fresh
    `out/workload-consistency/run-XXXXXX`; header and final message say
    DIAGNOSTIC ONLY; fdata uses `--debug-unbound`.
  - G2: `qemu_rewrite_gate.py` `--profile` (copied, `check_profile` against
    the input), `--optimizer-record`, `--bind NAME=PATH`; all hashed into
    `rewrite.json` (`bound`) and re-checked after capture.
    `optimize-lk-bolt.sh` keeps the funcs list (`OUT.funcs`) and writes
    `OUT.provenance.json` (input/profile/tool hashes, exact command,
    `profile_checked`); `BOLT_DIAGNOSTIC_PROFILE=1` skips check-profile and
    records `profile_checked: false`, which the rewrite gate rejects.
- **Left (next step):** the QEMU wrapper still stops at its first step: on
  ARM32, `qemu_workload_gate.py --elf` requires an oracle contract (fails
  closed). Add a labelled `--diagnostic` mode there (baseline vs candidate
  consistency only, no oracle, receipt scope says diagnostic), use it in
  the wrapper, then run `BASE=atfe ARCH=arm32 REBUILD_LK=0
  scripts/verify-bolt-workloads.sh` in WSL (never REBUILD_LK=1 on the dirty
  live tree). Then audit the remaining wrappers (identity, P4, milestone,
  measurement) and close 6a.
- WSL: synced to this commit, no jobs running. Pi: idle, not in use. Lock
  free.

### 2026-10-04 — Claude: R17 stage 2 done (random generator, 146 cases)

- New `scripts/bolt_edge/rand.py`: seeded random A32/T32 functions from a
  forward-only IR (ALU blocks; ret, branch, cmp+branch, IT / ARM-conditional
  groups incl. predicated returns, calls/tail calls across ISAs, conditional
  tail calls, TBB and `adr`+`ldr pc` switches). One IR yields both the asm and
  a Python model, so `gen.py` adds them to the same manifest (seed 17, 24 per
  ISA). Image `fixtures/lk-rpi4-bolt-edge-ce8dd005.elf`; generator and
  manifest frozen in `docs/bolt_edge/stage2/`.
- Pi baseline 146/146. Admission 153/155; only R21's two `-O0` tables
  remain; all 48 random functions admitted. Rewritten image (557 emitted, 67
  redirects, 26 random): 146 x 2 on the Pi, 0 mismatches, no faults.
  Evidence: `docs/results/bolt_edge_stage2_20261004.json`. Full LK unchanged
  (400/417; no backend change).
- **Contract:** user approved the `pi4` contract (83f2bc3; also hashes
  `rand.py` via new `edge_support_sha256`). Certified run (10 reps): 18/18
  bench + 146/146 edge on baseline and candidate, both sampled redirects
  executed. Receipt: `docs/results/bolt_edge_stage2_certified_20261004.json`.
  Same scope note as stage 1.
- **Left (tuning only):** only 4 conditional tail calls (44/48 functions
  get a frame), could bias toward frameless functions or more seeds.
- Lock free. R17 moved to Done. Next in resume order: group B (6a G1–G3, 6c/R13, 6d, 6b), then group C (R8, R15, R12, R13, R21).

### 2026-10-04 — Claude: R18 done (overlay 0057); lock released

- **Change:** A32 `add/sub/adr rB, pc, #k` that addresses a data island
  right after `ldr pc, [rB, rI, lsl #2]` is an inline absolute jump table.
  The base becomes `adr rB, <table>` (emission-time label, unique per
  emission like TBH), the LDR is an indirect branch with the table words as
  CFG successors (reuses 0024's inline-table model), and the emitter writes
  `.word <case label>` entries right after the LDR. Rejected: base clobbered,
  label/branch/call between base and LDR, invalid entries, a table branch
  without a recognized base. Mapping marks after such tables are `$a`.
- **Tests:** new `arm-ldr-pc-table.test` (default and reversed layout; base
  must address the re-emitted table, words must hit moved case blocks;
  clobbered base rejected). ARM lit 49/49; BOLT lit 859/860 (same unrelated
  AArch64 test); CoreTests 58; JITLink AArch32 15/15; overlays 0001–0057
  replay exactly (identity `b698cc7c…`).
- **Edge image:** admission 105/107; rewritten image with 41 redirected case
  entries (all six ARM table functions, attribute and `-marm`, O2/Os) passes
  98 × 2 on the Pi, no faults. Full LK unchanged at 400/417 (LK is Thumb).
- **Left:** `-O0` load-then-jump tables (new item R21); split functions with
  the base and the table in different fragments are unsupported (assembler
  error, not silent).

### 2026-10-04 — Claude: R19 + R20 done (overlays 0055–0056); lock released

- **R19 (0055):** A32 `mov lr, pc` (0xe1a0e00f) directly followed by an
  unconditional `b X` is disassembled as `nop; bl X` (same return address);
  a branch to the B alone is rejected. `isProvenNoReturnARM()` follows ld.lld
  absolute thunks (`movw/movt r12; bx r12`, A32 and T32) to their target.
- **R20 (0056):** ARM `equals(MCSpecifierExpr)` override (as AArch64); ICF
  previously aborted ("target-specific expressions are unsupported") once two
  identical functions with MOVW/MOVT symbol operands were compared.
- **Tests:** ARM lit 48/48; BOLT lit 858/859 (same unrelated AArch64 test);
  CoreTests 58 (rebuilt); JITLink AArch32 15/15; overlays 0001–0056 replay
  exactly (identity `86460b1b…`).
- **Edge image (`439dfd7c…`):** admission 99/107; only R18's 8 table
  functions remain. Rewritten image (501 emitted, 35 redirects incl.
  `c_noret_arm_o2/o0`): 98 × 2 runs on the Pi, 0 mismatches.
- **Full LK:** 399 → 400/417 functions, 98.0% of code bytes; the newly
  admitted function is `arm_secondary_entry` (its only PC read was the R19
  pair). **Caveat:** admission is not a placement decision. Startup and
  secondary-entry code runs before the MMU; never redirect it (the full-image
  pipeline only redirects explicitly selected functions).
- Next: R18 (ARM inline `ldr pc` tables), then R17 stage 2 and the open list.

### 2026-10-04 — Claude: bolt_edge stage-1b contract approved; certified

- User approved the `pi4` contract for `fixtures/lk-rpi4-bolt-edge-439dfd7c.elf`
  (bfd94e1), bound to frozen `docs/bolt_edge/stage1b/` manifest + generator.
- Certified `full_image_verify.py` run (10 repetitions): 18/18 bench and
  98/98 edge cases on baseline and candidate; execution observed in both
  sampled workload redirects. Receipt:
  `docs/results/bolt_edge_stage1b_certified_20261004.json`. Same scope note as
  stage 1 (restored `.rodata`; rewritten edge execution shown by the
  uncertified 33-redirect run, 98 × 2, 0 mismatches).

### 2026-10-04 — Claude: R17 stage 1b (whole-module -marm / -mthumb)

- `gen.py` now also emits submodules `app/bolt_edge/marm` and `mthumb`
  compiling the C cases with whole-module `-marm` / `-mthumb` at O2, Os
  (`minsize`) and O0 (`optnone`): 98 cases. Image
  `fixtures/lk-rpi4-bolt-edge-439dfd7c.elf` (0 FP/NEON).
- Pi baseline 98/98 equal to the models. Admission 95/107: whole-module
  `-mthumb` fully admitted; ARM-mode code (attribute or `-marm`, any level)
  hits R18 (8 functions) and R19 (4). Rewritten image (498 emitted, 33 case
  entries redirected, 8 from the flag modules): 98 × 2 runs, 0 mismatches.
  Evidence: `docs/results/bolt_edge_stage1b_20261004.json`.
- The approved stage-1 contract (`0895d7bc…`) now names frozen copies in
  `docs/bolt_edge/stage1/` (same hashes, re-verified); `check.py --manifest`
  selects a manifest. The 98-case image needs a new contract (user review).

### 2026-10-04 — Claude: bolt_edge contract approved; certified run

- The user approved the `pi4` contract for `fixtures/lk-rpi4-bolt-edge-0895d7bc.elf`
  (908753f): 18 bolt_bench sinks as for full LK, plus the 68 bolt_edge sinks
  bound by the manifest and generator hashes. `check_edge_results()` in
  `scripts/qemu_bench_oracle.py`; `full_image_verify.py` runs `bolt_edge all`
  on baseline and candidate when a contract binds a manifest (outside the
  sampled window). Gate unit tests pass; an altered sink is rejected.
- Certified run (`full_image_verify.py`, 478 emitted, 2 sampled workload
  redirects, 10 repetitions): 18/18 + 68/68 on baseline and candidate,
  33,847 samples, execution observed in both redirected workloads.
  Receipt: `docs/results/bolt_edge_certified_20261004.json`.
- **Scope:** the build restores `.rodata`, so non-redirected edge cases run
  their original code through the case table; the certificate proves correct
  results from the rewritten image, not rewritten edge-case execution. That
  is covered by the uncertified 25-redirect run (68 × 2, 0 mismatches). A
  gate mode that accepts redirect-plus-result evidence without PC samples
  for short functions would close this gap (record under 6a/6d).

### 2026-10-04 — Claude: R17 stage 1 done (68-case bolt_edge image)

- `scripts/bolt_edge/gen.py` generates `overlay/lk/files/app/bolt_edge/`, the
  `rpi4-bolt-edge` project and `docs/bolt_edge/manifest.json` (model-computed
  sinks + expected admission); `scripts/bolt_edge/check.py results|admission`
  compares runs and BOLT admission. Image: `fixtures/lk-rpi4-bolt-edge-0895d7bc.elf`
  (0 FP/NEON). Build: install the app/project into `third_party/lk` and run
  `make rpi4-bolt-edge` (TOOLCHAIN=clang, CLANG_BINDIR=build-atfe/bin,
  LD=ld.lld, SIZE=size). **Do not use `build-lk-aarch32.sh` on the dirty live
  tree:** it runs `apply-overlays.sh` (it stopped safely at 0014; replay
  re-verified clean).
- **Pi baseline:** 68/68 sinks equal the models. **Admission:** 72/77
  functions as designed; 5 real gaps in clang `-marm` output, new items R18
  (ARM inline `ldr pc` tables) and R19 (`mov lr, pc; b` call idiom).
- **Rewritten image on the Pi:** 478 emitted, 25 case entries redirected
  (interworking, ARM CTC and `bleq`, noreturn chains, TBB/TBH, carry, C
  variants): 68 cases × 2 runs, 0 mismatches, no faults. Uncertified until the
  user reviews the generator/models as an oracle contract (6b).
- Next: user review of `gen.py` models for a `pi4` contract on `0895d7bc…`;
  R18/R19; stage 2 (randomized generator).

### 2026-10-04 — Claude: session-independent handoff

- Added `fixtures/lk-rpi4-bolt-test-424606a8.elf` (certified input, was
  WSL-only), `scripts/check_raw_original_text.py` (raw re-patch checker that
  found R1; on the current toolchain: 20 patched sites, 0 changed),
  `docs/R17_BOLT_EDGE_PLAN.md`, and the *Resuming* section above. Pointers
  added to CORRECTNESS_RESUME.md and CORRECTNESS_PRIORITY_TODO.md.

### 2026-10-04 — Codex: R11 verified and published; lock released

- R11 done, overlay 0054: explicit report-only local admission collection;
  no emitted ELF/certificate, conservative fatal default and global guards
  preserved. Early symbolizer cleanup prevents stale function-bound state.
  Coverage now uses a validated input-bound report, then normal fatal BOLT
  with explicit skips; old scanner remains an explicit compatibility option.
- ON/OFF Release builds from the same source pass the new 41-check lit
  regression. ARM + AArch32 JITLink: ON 61 passed; OFF 60 passed, one
  `ELF_data_alignment.s` unsupported (`REQUIRES: asserts`), correcting the earlier timeout-feature description. CoreTests: 58 passed/31 target skips each.
  Windows host suite: 145 tests, four Linux process-test skips. Full 54-overlay
  replay has no mismatched/uncovered source files, identity `484c5825…`.
- Coverage before/after: **399/417 functions (95.7%)**, **124166/126834 code
  bytes (97.9%)**, unchanged in both modes. Rejection discovery: 12 rounds
  → one; 12 primary-body rejects, 403 diagnostic admits, two not analyzed.
  No newly admitted body. R15 instrumentation guard still rejects trylock.
- Pi watchdog runs: each candidate emits 400 bodies, redirects the two
  selected interwork/memcpy workloads, and passes 18/18 independent results
  over 10 repetitions. ON/OFF PC samples in those bodies: 27/15 and 10/11.
  Other emitted functions are not execution coverage. Receipts, manifests,
  diagnostic reports and scope are in [ARM_ADMISSION_REPORT.md](ARM_ADMISSION_REPORT.md).
- New audit caveat: the input passes the no-FPU check, but candidate ELF ISA
  mapping metadata causes false FP matches. The four matches in rewritten
  code were decoded as A32 BX instructions; restored Thumb code is also
  misdecoded. No candidate no-FPU certificate is claimed. ISA-aware scanning
  and metadata, including generated veneers, are recorded under item 14.
- Stop at the verified milestone. The lock is released; R17 is next and
  unclaimed. Prepare its generated cases, admission manifest and independent
  oracle for user review before new-image certification. P0 items and original
  #12 remain open. Windows/WSL trees and evidence/preimages are preserved;
  WSL remains running. The Pi is restored to the approved baseline LK shell
  (COM5, 3 Mbaud), sampling stopped, watchdog off, serial port closed.
  Baseline binary SHA-256 `ee9982ba422fa5e40854f0c21c298b20c4be02eb349413eefe7fdcf53bedd612`;
  pickup log: `out/r11-pi-pickup.log`. Repository resume/TODO records and the
  local Claude project-state/memory index are refreshed. Windows Codex/Claude
  checkouts and WSL are synced to the published milestone. No one-time helper reruns,
  resets, overlay reapplication or implicit ownership by origin.

### 2026-10-04 — Codex resumes R11 and reacquires the live-tree lock

- User requested resume. R11 is In progress under Codex; the shared ATFE lock
  is reacquired before backend changes. Continue the saved admission-handler
  inspection, preserving fatal default/global guards and all existing evidence.
- No other item is claimed. Baseline remains overlays 0001–0053 and recorded
  coverage 399/417 functions (95.7%), 97.9% function code bytes. R17 follows R11.

### 2026-10-04 — Codex paused R11 at the user's request; lock released

- The user requested pause for mobile remote control, then exit. R11 remains
  assigned to Codex and is Paused; the live-tree lock is released. Other items
  retain their owners/statuses. Reacquire the lock before implementation on resume.
- Claim commit: `46e8b1b`. Windows and WSL repos were synced to that claim.
  Read current disassembly/CFG admission handlers and coverage scanning code.
  The 53-overlay baseline replay passes with no uncovered/mismatched files:
  WSL `out/r11-baseline-replay-20261004/replay.json`, source identity
  `dfbf60c0e1c3c6c051dcfa3749b16652e904188e9276fb8f15f26a0ab54ecfdc`.
- No backend edits, overlay 0054, compiler rebuilds, test runs or Pi uploads
  have started. Read-only inspection helpers are under Windows `out/r11_*.py`.
  Existing dirty ATFE/LK, unrelated Microsoft/ and evidence are preserved.
  Recorded coverage is unchanged: 399/417 functions (95.7%); 97.9% code bytes.
- Resume R11 by reviewing `RewriteInstance::disassembleFunctions()` and
  `buildFunctionsCFG()` error handlers and BinaryFunction cleanup. Keep default
  fatal/global admission intact; diagnostic reports must not become correctness
  certificates. Add both-mode regressions, export 0054, replay and regenerate
  coverage before closure; R17 follows. WSL is left available; Pi serial is closed.

### 2026-10-04 — Codex claims R11 and takes the live-tree lock

- Starting in the user-approved A → B → C → D order. R11 is claimed by
  Codex; all other remaining items are unclaimed. Taking the shared ATFE
  source/build lock before implementation. Planned overlay: 0054.
- Implement an explicit diagnostic skip-and-report mode, retaining fatal
  admission by default and conservative input/global guards. Add regression
  tests, verify both assertion modes, replay the full overlay set and regenerate
  full-LK coverage before marking R11 done. Next item is R17.
- Starting recorded coverage: 399/417 functions (95.7%), 97.9% of function code
  bytes. No backend change or new execution evidence at claim time.

### 2026-10-04 — Codex: latest shared TODO tables published

- Published the current Claims tables (A → B → C → D) in
  [CORRECTNESS_PRIORITY_TODO.md](CORRECTNESS_PRIORITY_TODO.md): 18 remaining
  items (7 Open, 11 Partial), all unclaimed, and 11 completed review items.
  IDs, ownership, priorities, order and notes match this handoff. Preserved the
  0045 certification closure criteria as explicitly historical material;
  ownership/current status remain authoritative here. No TODO item claimed.
- Checked the generated rows against Claims: orders 1–18 and empty owners.
  Next requested implementation starts at R11, then R17. New oracle contracts
  still require user review as listed. Live-tree lock remains free.
- Documentation only: no backend/image change, build, test execution or Pi
  upload. Published coverage is unchanged at 399/417 functions (95.7%) and
  97.9% of function code bytes; coverage regeneration is not required. No new
  live-source or hardware correctness claim. WSL/Pi availability remains as
  recorded in the preceding access-check entry; unrelated Microsoft/ preserved.

### 2026-10-04 — Codex: repository sync and shared-pool handoff acknowledged

- Fast-forwarded the Windows checkout from `0e616eb` to `baa8bcd` and read
  `AGENTS.md`, `CLAUDE.md`, this protocol, the Claude review, coverage report,
  approved Pi contract and latest certification handoffs. Both agents may claim
  any unowned item; origin does not assign ownership. Current ownership and
  resume order come from *Claims* here, while the correctness queue retains
  certification closure criteria. Earlier 0045 checkpoints are historical
  where superseded by overlays 0046–0053 and the approved Pi contract.
- No TODO item claimed or started. No live-tree lock taken; it remains free.
  Next on a requested work resume: claim **R11**, commit and push the claim,
  and take the live-tree lock before editing/rebuilding shared ATFE; then R17
  and the remaining groups in the listed order. Recheck remote claims first.
- Documentation-only sync plus the user's requested access check: WSL Ubuntu
  starts and executes commands, and its repo is at `baa8bcd` (`third_party/`
  remains untracked). Pi serial access is available on COM5 at 3 Mbaud: `help`
  returns the LK command list and shell prompt; the port was closed afterward.
  No backend/image edits, builds, test runs or Pi uploads. WSL is now running.
  Live ATFE/build content is taken from Claude's preceding 0053 handoff, not
  revalidated in this turn. Unrelated
  `Microsoft/`, dirty live trees and raw evidence are preserved.
- Published coverage is unchanged: **399/417 functions (95.7%)**, **97.9% of
  function code bytes**. No regeneration is needed without backend or LK image
  changes. Claude's Pi and sealed-chain receipts were read, not rerun; remaining
  P0 gaps and the second assertion-mode build stay open as listed above.

### 2026-10-04 — Open list regrouped into resume order (user request)

- Groups: A unblockers (R11, R17) → B P0 certification (6a, 6c, 6d, 6b) →
  C small defects (R8, R15, R12, R13) → D P1 matrices (8, 7, 11, 12, 13, 9,
  10, 14). Resume at order 1 (R11). Baseline: main c519923, coverage
  399/417 (97.9%), full-LK `pi4` contract active, sealed Pi chain certified.

### 2026-10-04 — R17 added (user decision)

- New open item R17: synthesized edge-case test image (see the 2026-10-04
  evaluation in the session: interworking, IT masks, noreturn, far code, data
  in code, entries/symbols, must-reject guards, register/flag state, runtime
  context, compiler variety). R11 raised to P1 because R17 needs it.

### 2026-10-04 — Claude: 6a milestone (usage limit); P0 items released

**Milestone:** the complete sealed Pi chain is certified end to end on the
full LK image: seal (`profile_identity.py seal-samples`) → Pi PC capture
(6,772 samples) → `samples_to_fdata.py` + `check-profile` → `full_image_build
--profile` (manifest binds profile + sidecar hashes; 400 emitted) →
`full_image_verify.py` PASS (10 repetitions, 18/18 vs the approved contract,
execution observed in both required rewritten functions). Receipts:
`docs/results/sealed_chain_certified_20261004.json`,
`docs/results/sealed_chain_profile_manifest_20261004.json`.

**Fix (scripts only):** `samples_to_fdata.py --skip-funcs` passes the
optimizer's admission skip list to perf2bolt and records it in the sidecar
(`perf2bolt_skip_funcs`). Without it the sample-profile route failed on the
full image (`perf2bolt` stopped at `arm_reset`). All 12 script unit-test
modules pass.

**6a audit results:**
- Sound (no certificate without proof): `qemu_rewrite_gate.py` /
  `qemu_rewrite_build.py` (contract-bound input, fresh evidence dirs, live
  entry-pair traces, tool/script/revision re-checks); `full_image_verify.py`;
  `qemu_workload_gate.py --check-log` and Pi `passes_check.py` /
  `measurement_records.py` are labelled diagnostics (no execution claim).
- **G1 (open):** `verify-bolt-workloads.sh` reuses fixed-path intermediates
  (instrumented ELF, counters, fdata, optimized ELF, /tmp serial log) without
  clearing them first.
- **G2 (open):** that QEMU pipeline's certificate (`rewrite.json`) does not
  bind the profile/instrumented image/BOLT options; the Pi full-image route
  does (manifest `profile`).
- **G3 (open, fails closed):** default QEMU LK builds have no oracle contract,
  so the QEMU pipeline cannot currently certify.
- Not done: "both assertion modes" (needs a second, no-assertions ATFE build).

All P0 items are released (unclaimed); the lock is free.

### 2026-10-04 — Claude: 6b contract active; first certified full-image Pi run

- **6b:** the user approved the draft; `CONTRACTS['424606a8…']` (platform
  `pi4`) added in `scripts/qemu_bench_oracle.py` (6ff3f34). Gate unit tests
  (oracle, execution, rewrite, workload) pass.
- **6a:** `full_image_verify.py` certified the full-image candidate
  (`out/full-check-claude-6a`, 400 emitted, 12 skips, 2 redirects): 10
  repetitions, 18/18 against the independent contract, 33,849 PC samples,
  execution observed in both required rewritten functions (27 and 12
  samples). Receipt: `docs/results/full_image_certified_20261004.json`.
- **Remaining for 6a:** audit the other certification wrappers (identity,
  P4, workload, milestone, measurement) and their diagnostic modes; then
  6d receipts and 6c hook admission.

### 2026-10-04 — Claude claims the P0 items (user request)

- Order: 6b → 6a → 6d → 6c. 6b draft contract written
  ([PI4_ORACLE_CONTRACT_DRAFT.md](PI4_ORACLE_CONTRACT_DRAFT.md)); it is not
  active until the user approves it. The Pi input's bench sources equal the
  repo's (LF-normalized); 0 FP/NEON instructions.
- The live-tree lock stays free: 6b and 6a need no backend change so far.

### 2026-10-04 — List made a shared pool (user decision)

- The user decided items are not tied to the agent whose history they came
  from: open items are unclaimed and either agent may take any of them by
  claiming it first (rule 2). *Claims* now has an Open table (suggested
  order) and a Done table. No item is currently claimed; the lock is free.

### 2026-10-04 — Claude: R6 done (overlay 0053); lock released

- **Change:** a group-final predicated return (`bx<c> lr`, `pop<c> {…,pc}`)
  or predicated call (`bl<c>`, `blx<c>`) in a Thumb IT block now stays inside
  its block, the model A32 predicated returns already use; the IT group is
  emitted unchanged. `adjustCallForTargetMode()` now keeps the call's
  condition (it rebuilt every call as unconditional: T32 IT calls and A32
  `BL<c>` via LongJmp/veneer paths) and fails on a conditional A32 call that
  would need BLX. `BL_pred` is now symbolized: A32 `BL<c>` previously kept its
  input displacement after moving.
- **Codex tests changed (please review):** `check-arm-it-boundaries.py`: the
  `return` case now expects the fallthrough diagnostic (still rejected: the
  return ends the function), and the `call` case is a positive check that
  `it eq; bleq helper` is emitted unchanged. `check-arm-inline-safety.py`:
  the four IT-call modes now require success and that the call is kept, not
  inlined (the inliner's unpredicated-BL guard holds).
- **Tests:** new `arm-predicated-returns-calls.test` (IT returns, `itt`,
  `ite`, IT `bl`/`blx`, A32 `bleq`; default, reversed and far/LongJmp
  layouts). ARM lit 45/45; BOLT lit 855/856 (same unrelated AArch64 test);
  CoreTests 58; JITLink AArch32 15/15; overlays 0001–0053 replay exactly.
- **Coverage:** 354 → 399/417 functions; 92.6% → 97.9% of code bytes. Left:
  7 PC-write, `arm_reset`/`arm_secondary_entry`, `vsnprintf` (R12),
  `bcopy`/`bzero`.
- **Pi:** `out/full-check-claude-r6`, 400 emitted, 51 entries redirected
  (16 R6-recovered, incl. `io_write`, `io_read`, `cbuf_write_char`,
  `thread_resched`, `thread_timer_tick`): 3 repetitions, 18/18 equal baseline
  and the reference formulas; no faults. The console path that carried the
  results runs through the rewritten `io_write`/`io_read`.
- **Next for Codex:** 6a, R8, R11–R13, R15. The coverage goal is met except
  R12 (`vsnprintf`).

### 2026-10-04 — Claude: R5 done (overlay 0052); lock kept for R6

- **Change:** `BinaryFunction::isProvenNoReturnARM()` proves from input bytes
  that a function never returns: no return, indirect branch or computed PC
  write; branches out of it and its final call go to proven functions; it
  cannot run off its end. Unproven cases (recursion, size 0, interior
  entries) count as "may return". The fallthrough rejection is lifted only
  for a final unconditional direct call to a proven function's primary entry.
- **Tests:** `arm-noreturn-calls.test`: A32/T32 chains admitted in both
  layouts; may-return, indirect, conditional final call, tail branch to
  returning code and recursion still reject. ARM lit 44/44; BOLT lit 854/855
  (same unrelated AArch64 test); CoreTests 58; JITLink AArch32 15/15;
  overlays 0001–0052 replay exactly.
- **Coverage:** 276 → 354/417 functions; 79.2% → 92.6% of code bytes.
  Remaining fallthrough rejections: `bcopy`, `bzero` (real fallthrough).
- **Pi:** `out/full-check-claude-r5`, 355 emitted, 35 entries redirected to
  rewritten copies (33 R5-recovered functions on boot, timer, MMU, PMM/VMM
  and heap paths, plus platform_irq and two workloads). Booted to the shell;
  3 repetitions, 18/18 equal baseline and the reference formulas; no faults.
  PC samples (2027) only hit the workloads: the boot-path functions are
  shown executed by the redirect plus successful boot, not by sampling.
  `initial_thread_func` could not be redirected (PC-relative first BL).

### 2026-10-04 — Consolidated TODO; R6 reassigned to Claude

- *Claims* now holds one consolidated list: R items mapped to the Codex queue
  item they belong to. Closure criteria for 6a–14 stay in
  CORRECTNESS_PRIORITY_TODO.md.
- The user asked Claude to take R6 as well (after R5). Codex: start with 6a
  and R8/R11–R13/R15 when the lock is released.

### 2026-10-04 — R5 reassigned to Claude; Claude takes the lock

- The user asked Claude to take R5. Codex: coverage goal continues at R6
  once the lock is released.

### 2026-10-04 — Claude: R4 done (overlay 0051); lock released

- **Root cause:** not IT-specific. Any AArch32 conditional tail call
  (`b<c> f` to another function, with or without IT) crashed:
  `removeConditionalTailCalls()` retargets the branch to a local tail-call
  block via `convertTailCallToJmp()`, which ARM did not override, so the
  branch kept its tail-call annotation and `analyzeBranch()` ignored it.
  0051 adds the override (same as AArch64).
- **Tests:** new `arm-conditional-tail-call.test` (ARM, Thumb, IT with one
  and two instructions, default and reversed layout; the predicated ADD
  keeps its shortened IT). ARM lit 43/43; BOLT lit 853/854 (same unrelated
  AArch64 test); CoreTests 58 passed; JITLink AArch32 15/15; overlays
  0001–0051 replay exactly.
- **Coverage:** 273 → 276/417 functions, 79.1% → 79.2% of code bytes
  (`platform_irq`, `platform_fiq`, `arm_gic_init_percpu` now rewritten);
  CFG-crash class gone. [LK_COVERAGE.md](LK_COVERAGE.md),
  `docs/results/lk_coverage_20261004_r4.json`.
- **Pi:** full-image candidate (`out/full-check-claude-r4`, 277 emitted)
  with `platform_irq` and `arm_gic_init_percpu/1` redirected to their
  rewritten copies: 18/18 results equal baseline and the reference formulas;
  with the PMU sampler on, 676 interrupts went through the rewritten
  `platform_irq`. No faults.
- **Note:** a one-instruction IT around the branch leaves a harmless 2-byte
  `mov r0, r0` (existing 0027 behaviour).
- **Next for Codex:** coverage goal step 2 (R5). The lock is free.

### 2026-10-04 — R4 reassigned to Claude; Claude takes the lock

- The user asked Claude to take R4. Codex: start the coverage goal at R5 and
  wait for the lock to be released.

### 2026-10-04 — Claude: coverage goal assigned to Codex

- User asked that the Codex handoff also raise BOLT coverage. Added the
  *Coverage goal* section: order R4 → R5 → R6 → R12, then R15; target about
  98% of LK functions; per-step coverage report, tests and Pi run.

### 2026-10-04 — Claude: full-image coverage report (R16)

- `scripts/lk_coverage_report.py` classifies every FUNC symbol and every
  `.text` byte of the LK test binary (kernel, platform, libc, startup and
  vector assembly, bolt_bench workloads). Baseline on input `424606a8…` with
  overlays 0001–0050: **79.1% of function code bytes and 273/417 functions
  rewritten**; 138 rejected (fallthrough 80, IT transfer 46, PC write 7, CFG
  crash 3, PC read 2); 5 folded by ICF; 27.4% of `.text` is alignment filler.
  Instrumentation of the image fails on R15. See [LK_COVERAGE.md](LK_COVERAGE.md).
- It reruns llvm-bolt until no function is rejected (61 rounds, ~3 s). R11
  would replace that loop with one run.
- No live-tree changes; the lock stays free.

### 2026-10-04 — Claude releases the lock (overlays 0046–0050)

**Done:** R1–R3 (0046), R14 (0047), R9 (0048), R7 (0049), R10 (0050). Each
has its own lit test, except 0047. Evidence:
[claude_review_fixes_20261004.json](results/claude_review_fixes_20261004.json).

- **0046** goes beyond the review: the external-reference scan used the A32
  builder, disassembler symbolizer and STI for Thumb functions. Thumb `b.w` /
  `bne.w` to moved functions were overwritten with A32 encodings, and A32
  callers were never re-patched (the symbolizer had already replaced the
  operand). Branches are now re-encoded from the original word (condition,
  BL/BLX by target ISA, PC+8/PC+4). An out-of-range branch keeps its original
  target, with a warning (relocation mode only). With `--use-old-text`, A32
  sites are left to `patchKeptARMCodeReferences()` as before.
- **Verified:** ARM lit 42/42; BOLT lit 852/853; CoreTests 58 passed, 31
  skipped; JITLink AArch32 15/15. Overlays 0001–0050 replay exactly
  (`out/atfe-replay-claude-0050`). Pi (fast loader, watchdog): full-image LK
  candidate, all 18 results equal baseline and the reference formulas.
- **Not verified:** the one BOLT lit failure,
  `AArch64/constant_island_pie_update.s`, is not caused by these patches (all
  changes are ARM-gated), but it was not rerun on a pre-0046 binary. 0047
  is untested because RISC-V is not in `LLVM_TARGETS_TO_BUILD`. The Pi gate
  restores the original text, so it cannot exercise 0046 on hardware; that
  needs a pipeline mode that keeps BOLT's patched original code.
- **Live tree:** clean against overlays 0001–0050; `build-atfe` is built from
  it. The lock is free.
- **Next for Codex:** R4, then R5/R6 (coverage), then R8, R11–R13 and the
  existing queue. Re-run the LK skip-list scan after R4–R6 to measure coverage.

### 2026-10-04 — Claude takes the live-tree lock

- Synced Windows and WSL repos to `0e616eb`; the live ATFE tree replays
  exactly from overlays 0001–0045 (`out/atfe-replay-sync-20261004/replay.json`).
- Review published; items split as in *Claims*. Codex: start with R4 once
  Claude releases the lock; R5/R6 are the main coverage wins.
