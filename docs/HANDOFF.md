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
  [PI4_ORACLE_CONTRACT_DRAFT.md](PI4_ORACLE_CONTRACT_DRAFT.md) (approved),
  [earlier implementation handoffs](HANDOFF_HISTORY.md).
- **Certified input image:** `fixtures/lk-rpi4-bolt-test-424606a8.elf`
  (see `fixtures/README.md`); the skip list is in
  `docs/results/lk_coverage_r15_20261004.json` (`skip_funcs`).
- **Backend source:** overlays `overlay/llvm/patches/atfe/0001–0067`; the WSL
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
  tested through 0067 (ARM lit 56/56, 2026-10-05). The older OFF build
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
| Claude | 2026-10-05 | R25 (data Thumb pointers) and R26 (table base read in cases): overlays 0068+ |

## Pi reservation

| Holder | Since | Purpose / last observation |
|---|---|---|
| Claude | 2026-10-05 | R25/R26 (0068/0069): certified full-image gate on `424606a8` with the 0069 toolchain |

## Claims (consolidated TODO)

One shared list. Review items (R*) come from the 2026-10-04 Claude review
([details](CORRECTNESS_REVIEW_CLAUDE_0E616EB.md)) and the
[recovered Astra review](CORRECTNESS_REVIEW_ASTRA_0057.md); certification items
(6a–14) keep their closure criteria in
[CORRECTNESS_PRIORITY_TODO.md](CORRECTNESS_PRIORITY_TODO.md). "Part of"
links an R item to the certification item it contributes to; closing the R
item does not close that item. *Owner* is empty until someone claims it.

### Remaining shared work, in resume order

Take items in the order below; groups reflect dependencies, not ownership.

**C. Correctness defects and target items** (declared group B P0 milestones are complete)

| Order | ID | Item | Priority | Owner | Status | Part of | Notes |
|---|---|---|---|---|---|---|---|
| 10d | R25 | Thumb code pointers in data words lose the Thumb bit (function-pointer tables, interior entry pointers in `.data`) | P0 | Claude | In progress (live tree) | 7 | Found by the 2026-10-05 deep review (`scripts/review/edge_probe.py`): output words point at the even address, so a `blx`/`bx` through them enters ARM state (SIGSEGV/SIGBUS). Masked in the LK pipeline only because `.data`/`.rodata`/`lk_init`/`commands` are restored and original entries redirect |
| 10e | R26 | Inline-table base register read as data in a case block (0057 A32 `ldr pc` tables, 0066 Thumb ADR base) | P0 | Claude | Claimed | 12 | Deep review: after re-pointing the base, a case that reads rB sees the new table address, so the result depends on layout (WRONG under `--reorder-blocks=reverse`). Fix: admit only when rB is dead at every case target, as R21 already requires for rX |
| 10b | T3 | Secure-SVC parity on the Pi | P2 | — | Deferred TODO (user, 2026-10-04): Secure armstub is built (`tools/pi4-armstub-secure/`, sha `af4a5512…`, install/rollback in its README) but not installed; the SD-card step and the Secure re-runs wait until the user asks | 9 | All Pi results so far are Non-secure SVC; BOLT rewriting is state-agnostic, so T3 is a parity confirmation |
| 10c | T4 | Performance and final validation on the real A55 target (A72 gains not transferable) | P2 | User | Out of scope here | — | Done by the user in the office environment, from this repo |


**D. P1 certification matrices (as capacity allows)**

| Order | ID | Item | Priority | Owner | Status | Notes |
|---|---|---|---|---|---|---|
| 11 | 8 | CFG and mutation invariants | P1 | — | Partial | R4–R6, R19, R11, R23 done |
| 12 | 7 | Relocation/literal/veneer matrix | P1 | — | Partial | R1–R3, R7, R14 done |
| 13 | 11 | Entries/symbols/reference routes | P1 | — | Partial | R9 done |
| 14 | 12 | Tables and inline data | P1 | — | Partial | R18, R22, R24, R12, R21 done |
| 15 | 13 | Actual pass combinations | P1 | — | Partial | R7, R8, R20 done |
| 16 | 9 | Interrupt/reentrancy/reset boundaries | P1 | — | Partial | T2/T2b (SMP execution and counters) done; active-IRQ fixtures still open |
| 17 | 10 | Sampling/PMU ownership | P1 | — | Partial | Per-core PC watch ranges (T2) done; per-sample core attribution and loss/saturation accounting open |
| 18 | 14 | Clean build/content provenance | P1 | — | Partial | Overlay replay + assertions-off build (6a); clean full build and OFF parity for 0060–0061 still open; no-FPU guard misreads BOLT outputs (no input $t in original .text) |

**Needs the user:** new oracle contracts for new configurations; T3 SD-card install only when the user decides (deferred).

### Done

| ID | Item | Priority | Owner | Part of | Patch / evidence |
|---|---|---|---|---|---|
| R22 | Privileged LDM overwrote an inline-table base without rejection | P1 | Claude | 12 | 0062: the R18 base-survival check also treats any register-list load naming the base as a redefinition (the privileged/user-bank `ldm ..^` does not mark its list as defs); `arm-ldr-pc-table.test` adds ordinary/user-bank/writeback LDM must-reject and a user-bank non-base control (12/12). ARM lit 52/52 in both assertion modes (OFF build now includes 0060–0062); coverage unchanged 400/417 (`lk_coverage_r22_20261005.json`) |
| R11 | Skip-and-report admission mode; Thumb IT-state isolation (reopened, fixed) | P1 | Codex + Claude | 8, 6d | 0054 report mode (Codex). Reopened by the Astra review: a truncated ITT/ITE leaked IT state into the next function. 0063: `MCDisassembler::resetState()` (ARM clears IT/VPT state); BOLT resets at every independent stream (function disassembly, noreturn/branch-fix scans, nested plain decode, padding/veneer scans, exclusive-reservation scan, every 0059 gap probe). `arm-it-isolation.test`: truncated ITT/ITE before and after clean functions, admission equals control. Unfixed OFF build reproduced the false rejection; fixed ON/OFF 53/53; LLVM ARM disassembler + JITLink AArch32 166 pass/1 XFAIL |
| R23 | Noreturn absolute-thunk traversal bypassed cycle detection | P1 | Claude | 8 | 0064: thunk following moved inside `isProvenNoReturnARM`'s in-progress cache guard, so A→B→A thunk cycles prove nothing and terminate; `arm-thunk-cycle.test` (A32+T32: cycle and self-cycle rejected promptly, acyclic chain still a proof). Unfixed OFF build reproduced the hang (timeout); fixed ON/OFF 54/54 |
| R24 | A32 rotated (modified) immediates in inline-table bases | P2 | Claude | 12 | 0065: `getPCRelativeBase` decodes the ADDri/SUBri operand as imm8 ror 2·rot instead of using the encoded value as a byte count; `arm-ldr-pc-table.test` adds `add r3, pc, #256` (admitted, base re-pointed at the re-emitted table, default + reversed). Unfixed OFF build rejected it; fixed ON/OFF 54/54 |
| R12 | ADR to an inline TBB/TBH table (`vsnprintf`) | P2 | Claude | 12 | 0066: Thumb `adr(.w) rB, <table>` directly before `tbb/tbh [pc,...]` is re-pointed at the re-emitted table (A32 table-base mechanism; ISA-aware builder in the emitter); still rejected when anything branches to the table branch or the adr is not adjacent. `arm-tbh-adr-base.test` (TBH/TBB default+reversed; branch-in and non-adjacent rejected); ON/OFF 55/55. Full LK 400 → 401/417 functions, 98.0% → 99.5% of code bytes. Pi: certified gate PASS with vsnprintf emitted (`r12_certified_20261005.json`); vsnprintf (boot-only, via snprintf) redirected: `threads` prints `idle 0-3` formatted by the rewritten copy, 18/18 (`r12_vsnprintf_threads_pi_20261005.log`) |
| R21 | A32 `-O0` load-then-jump tables | P2 | Claude | 12 | 0067: `add rB, pc, #k … ldr rX, [rB, rI, lsl #2]; mov pc, rX` (or `bx rX`) with the table right after the jump is modelled like 0057 (jump becomes the table branch, base re-pointed, table re-emitted); admitted only when every case block redefines rX before reading it; load not adjacent to the jump, clobbered base, or a case reading rX stay rejected. `arm-load-jump-table.test` 12/12; ON/OFF 56/56. Edge image: `c_switch_arm_o0`/`c_switch_marm_o0` admitted (`bolt_edge_coverage_r21_20261005.json`); with both redirected, 146 edge cases × 2 on the Pi, 0 mismatches; certified gate on `ce8dd005` PASS (`r21_edge_certified_20261005.json`) |
| M1 | Repository health and documentation consolidation | P2 | Codex | — | [Audit/changes](REPO_HEALTH.md); canonical HANDOFF queue, archived duplicate history, current monitor + offline integrity command; 167 host tests run/12 skipped, no failures; fixture/receipt hashes preserved |
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
| 5 | R12 ADR to inline switch table — **done, 0066** | 1 | 401/417 (96.2%); 99.5% of code bytes |
| 6 | R15 try-lock reservation guard — **done, 0059** | in-scope workload instrumentation | See `lk_coverage_r15_20261004.json` |

**Published v7 coverage:** 401/417 functions, 126164/126834 code bytes (99.5%).
Nine rejected symbol rows remain in the latest v7 receipt (`lk_coverage_r12_20261005.json`); admission of
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

### 2026-10-05 — Claude: R21 done (overlay 0067); group C correctness items complete; lock and Pi released

- A32 `-O0` switch lowering `add rB, pc, #k; ldr rX, [rB, rI, lsl #2];
  mov pc, rX` (or `bx rX`): the jump is now the table branch of 0057's model
  (base re-pointed, table re-emitted after the jump). Because rX keeps the new
  case address, the table is admitted only if every case block redefines rX
  before reading it. Non-adjacent load, clobbered base and a case reading rX
  stay rejected. `mov pc, rX` outside such a table is still a rejected PC
  write.
- Tests: `arm-load-jump-table.test` 12/12; ON/OFF ARM lit 56/56; BOLT lit
  750 + known AArch64 failure; 0001–0067 replay exactly (`361c833b`).
- Coverage: full LK unchanged at 401/417 (`lk_coverage_r21_20261005.json`);
  edge image now admits `c_switch_arm_o0`/`c_switch_marm_o0` (only the
  must-reject `a_add_pc_switch` remains among switch cases).
- Pi (reserved/released): edge candidate with both -O0 functions redirected,
  `bolt_edge all` × 2 = 146 × 2, 0 mismatches; certified gate on the approved
  `ce8dd005` contract PASS (10 reps, 18/18, edge 146/146).
- All group C correctness items are done (R22, R11, R23, R24, R12, R21).
  Remaining: T3 (deferred, user), T4 (user), P1 matrices. Lock free, Pi
  unreserved.

### 2026-10-05 — Claude: R12 done (overlay 0066); R21 claimed; Pi released

- `vsnprintf` used `adr.w r2, <table>` right before `tbh [pc, r4, lsl #1]`.
  0066 recognizes a Thumb `adr`/`adr.w` immediately followed by `tbb/tbh [pc]`
  whose inline table starts at the adr target, turns it into a table-base
  placeholder and the emitter points it at the re-emitted table (label
  emitted at the table start; ISA-aware builder). A branch into the table
  branch or a non-adjacent adr stays rejected.
- Tests: `arm-tbh-adr-base.test` 8/8; ON/OFF ARM lit 55/55; BOLT lit 749 +
  known AArch64 failure; 0001–0066 replay exactly (`9377a517`).
- Coverage (rule 6): full LK 400 → 401/417 functions, 124282 → 126164 of
  126834 code bytes (98.0% → 99.5%); 9 rejected rows remain
  (`lk_coverage_r12_20261005.json`).
- Pi (reserved/released per rule 8): certified gate on 424606a8 with
  vsnprintf emitted, 10 reps, 18/18, both redirects executed. vsnprintf only
  runs at boot (snprintf for idle-thread names), so the sampler cannot see it;
  with vsnprintf redirected the candidate boots, `threads` lists `idle 0..3`
  formatted by the rewritten copy, 18/18.
- Lock kept for R21 (claimed). Pi unreserved.

### 2026-10-05 — Claude: R24 done (overlay 0065); R12 claimed

- The A32 table-base matcher used the ADDri/SUBri operand (an encoded
  modified immediate) as a byte offset, so `add r3, pc, #256` (enc 0xF01) was
  rejected. It now decodes imm8 ror 2·rot (operands > 0xFFF refused).
- `arm-ldr-pc-table.test`: rotated #256 case admitted and rebased (default
  and reversed); the checker's address window widened for the longer
  function. Unfixed OFF build rejected it; fixed ON/OFF ARM lit 54/54; BOLT
  lit 748 + known AArch64 failure; 0001–0065 replay exactly (`81556541`).
  Coverage 400/417 unchanged (`lk_coverage_r24_20261005.json`).
- No Pi access. Lock kept for R12 (claimed).

### 2026-10-05 — Claude: R23 done (overlay 0064); R24 claimed

- `isProvenNoReturnARM` followed absolute MOVW/MOVT/BX thunks before its
  in-progress guard, so A→B→A recursed without end (self-cycles were caught
  by `F != this`). The thunk case now runs inside the guard.
- `arm-thunk-cycle.test` (A32 and T32): cycle and self-cycle reject with the
  normal fallthrough error; an acyclic chain to a looping function admits.
  Unfixed OFF build reproduced the hang; fixed ON/OFF ARM lit 54/54; BOLT lit
  748 + known AArch64 failure; 0001–0064 replay exactly (`6f0a8a0a`).
  Coverage 400/417 unchanged (`lk_coverage_r23_20261005.json`).
- No Pi access. Lock kept for R24 (claimed).

### 2026-10-05 — Claude: R11 done (overlay 0063); R23 claimed

- Shared Thumb disassemblers kept IT/VPT state across independent decodes.
  0063 adds `MCDisassembler::resetState()` (no-op default; ARM clears IT and
  VPT) and BOLT calls it at every independent stream start, including each
  probe of the 0059 executable-gap scan.
- `arm-it-isolation.test` (truncated ITT/ITE before/after clean functions;
  admission must equal the control image). Reproduced on the unfixed OFF build
  (`good_thumb` falsely rejected); fixed builds pass. ON/OFF ARM lit 53/53;
  BOLT lit 747 + known AArch64 failure; LLVM ARM disassembler and JITLink
  AArch32 166 pass + 1 XFAIL. 0001–0063 replay exactly (`8570e5c1`).
  Coverage 400/417 unchanged (`lk_coverage_r11b_20261005.json`).
- No Pi access. Lock kept for R23 (claimed).

### 2026-10-05 — Claude: R22 done (overlay 0062); R11 claimed

- R18's table-base survival check missed register-list loads whose list is
  not marked as definitions (privileged/user-bank `ldm ..^`). It now treats any
  variadic load naming the base in its list as a redefinition. Test: ordinary,
  user-bank and writeback LDM into the base reject (default + reversed
  layout); user-bank LDM not naming the base still admits.
- Both modes: ARM lit 52/52 ON and OFF (OFF rebuilt; now covers 0060–0062).
  BOLT lit 746 + the known AArch64 failure. 0001–0062 replay exactly
  (`88c0d473`). Coverage regenerated: 400/417 unchanged (tightening only).
- No Pi access. Lock kept for R11 (claimed).

### 2026-10-05 — Claude: reviewed Codex's M1/Astra update (ea23639); consolidated

- Synced Windows and WSL to `ea23639`. Reviewed the Astra consolidation and
  M1 cleanup: queue R22 → R11 (reopened) → R23 → R24 → R12 → R21 is
  consistent with Claude's last state (T1/T2/T2b/R8/R13/R15/6a–6d Done; T3
  deferred). New rules (pushed claims; separate Pi reservation) adopted.
- `py -3.12 scripts/repo_health.py`: no errors (7 fixtures, 61 overlays,
  42 work items, 11 R11 artifacts).
- Corrected the Pi reservation row to the last real observation (Claude ran a
  health check after 89dd17f): LK shell, A55 image, watchdog off, COM5 closed.
- No backend/LK change, no Pi access in this step. Live-tree lock free; no
  claims. Next agent: claim R22.

### 2026-10-04 — Codex: M1 repository health cleanup complete

- Consolidated current work/status in this file. Removed redundant queue copies,
  archived earlier checkpoints/criteria/logs, corrected stale README/contract/
  RunPod/WSL guidance, and refreshed LK_COVERAGE from the existing 0059 receipt
  (same 400/417 functions and 124282/126834 bytes, 98.0%; no new BOLT run).
- [Health audit](REPO_HEALTH.md): tracked JSON/Python syntax and local Markdown
  file targets pass; 61-overlay inventory, seven fixture hashes and 11 bound R11
  artifact hashes pass. Monitor reads this file instead of the retired twelve-row
  tracker. Host suite: 167 tests run, 12 platform/toolchain skips, no failures in
  the configured pyserial venv; four new malformed/duplicate/state regressions.
- Backend queue/status/ownership unchanged; M1 Done. No backend/LK mutation,
  rebuild, overlay application, Pi/COM5 access or hardware verification. Frozen
  generator copies, old receipts, dirty local trees and Microsoft/ preserved.
  Live-tree lock free; Pi state remains last observed. Project memory refreshed.
- Next implementation is still R22, then R11/R23. Use this table as authority;
  TODO/status gateways and local memories no longer maintain another live queue.

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

Earlier implementation/session entries are in
[HANDOFF_HISTORY.md](HANDOFF_HISTORY.md). Historical ownership and work-order
statements there do not override the current Claims and reservation tables.
