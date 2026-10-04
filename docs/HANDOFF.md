# Claude ↔ Codex handoff

Two agents work on this repo: **Claude** (Claude Code) and **Codex**. This file
is the single source of truth for who owns what. Read it before starting work,
and update it before stopping. `AGENTS.md` and `CLAUDE.md` point here.

## Rules

1. **One writer per live tree.** The WSL ATFE source
   (`/home/user/bolt-aarch32/third_party/llvm-project-atfe`) and its build
   (`build-atfe`) are shared. Only the agent named in *Live-tree lock* may edit
   or rebuild them. Take the lock by committing a change to this file first;
   release it the same way.
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

## Live-tree lock

| Holder | Since | Purpose |
|---|---|---|
| — (free) | 2026-10-04 | Released by Claude after overlay 0053 |

## Claims (consolidated TODO)

One shared list. Review items (R*) come from the 2026-10-04 Claude review
([details](CORRECTNESS_REVIEW_CLAUDE_0E616EB.md)); certification items
(6a–14) keep their closure criteria in
[CORRECTNESS_PRIORITY_TODO.md](CORRECTNESS_PRIORITY_TODO.md). "Part of"
links an R item to the certification item it contributes to; closing the R
item does not close that item. *Owner* is empty until someone claims it.

### Open (unclaimed — anyone may take), in resume order

Take items in the order below; groups reflect dependencies, not ownership.

**A. Unblockers (first)**

| Order | ID | Item | Priority | Owner | Status | Part of | Notes |
|---|---|---|---|---|---|---|---|
| 1 | R11 | Skip-and-report admission mode | P1 | — | Open | — | Replaces the multi-round coverage scan; needed by R17 |
| 2 | R17 | Synthesized edge-case test image (`bolt_edge`), stage 1 (~40 cases) | P1 | — | Open | 7, 8, 11, 12 | Generator emits sources + admission manifest + independent checksums; QEMU + Pi; stage 2 randomized generator later |

**B. P0 certification (finish)**

| Order | ID | Item | Priority | Owner | Status | Part of | Notes |
|---|---|---|---|---|---|---|---|
| 3 | 6a | Every gate proves execution: close G1 (fixed-path intermediates), G2 (seal profile chain in QEMU certificate), G3 (contracts for QEMU LK builds) | P0 | — | Partial | — | Pi sealed chain certified; G3 needs user review; "both assertion modes" needs a second toolchain build |
| 4 | 6c | Legacy/manual hook admission | P0 | — | Partial | — | R9 done; includes R13 |
| 5 | 6d | Durable receipts on every certification route | P0 | — | Partial | — | Pi gate + coverage report receipts exist |
| 6 | 6b | Oracle contracts for further configurations (Thumb workloads, `bolt_edge` images) | P0 | — | Partial | — | Full-LK `pi4` contract active; each new contract needs user review |

**C. Correctness defects (small)**

| Order | ID | Item | Priority | Owner | Status | Part of | Notes |
|---|---|---|---|---|---|---|---|
| 7 | R8 | r12 clobbered by local-branch LongJmp stubs | P1 | — | Open | 13 | Liveness check or rejection |
| 8 | R15 | Full-LK instrumentation blocked by `arch_spin_trylock` guard (false positive) | P1 | — | Open | exclusive guards (0038/0039) | Keep must-reject tests for real cross-function pairs |
| 9 | R12 | ADR to an inline TBB/TBH table (`vsnprintf`) | P2 | — | Open | 12 | Last coverage item |
| 10 | R13 | Redirect functions starting with a 16-bit instruction | P2 | — | Open | 6c | If not done under 6c |

**D. P1 certification matrices (as capacity allows)**

| Order | ID | Item | Priority | Owner | Status | Notes |
|---|---|---|---|---|---|---|
| 11 | 8 | CFG and mutation invariants | P1 | — | Partial | R4–R6 done |
| 12 | 7 | Relocation/literal/veneer matrix | P1 | — | Partial | R1–R3, R7, R14 done |
| 13 | 11 | Entries/symbols/reference routes | P1 | — | Partial | R9 done |
| 14 | 12 | Tables and inline data | P1 | — | Partial | R12 pending |
| 15 | 13 | Actual pass combinations | P1 | — | Partial | R7 done; R8 pending |
| 16 | 9 | Interrupt/reentrancy/reset boundaries | P1 | — | Partial | |
| 17 | 10 | Sampling/PMU ownership | P1 | — | Open | |
| 18 | 14 | Clean build/content provenance | P1 | — | Partial | Overlay replay only |

**Needs the user:** new oracle contracts (6a G3, 6b, each `bolt_edge` image).

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

## Coverage goal

Raise BOLT coverage of the full LK test binary, measured only by
`scripts/lk_coverage_report.py` ([LK_COVERAGE.md](LK_COVERAGE.md)).

| Step | Item | LK functions recovered | Coverage after (functions) |
|---|---|---|---|
| Baseline 2026-10-04 | — | — | 273/417 (65.5%); 79.1% of code bytes |
| 1 | R4 conditional tail calls (crash) — **done, 0051** | 3 | 276/417 (66.2%); 79.2% of code bytes |
| 2 | R5 noreturn calls at function end — **done, 0052** | 78 | 354/417 (84.9%); 92.6% of code bytes |
| 3 | R6 predicated returns and calls in IT blocks — **done, 0053** | 45 | 399/417 (95.7%); 97.9% of code bytes |
| 4 | R12 ADR to inline switch table | 1 | ~96% |
| 5 | R15 try-lock reservation guard | instrumentation of the image | — |

**Target:** everything except the 9 functions that must stay in place
(7 PC-writing vectors and early setup, `arm_reset`, `arm_secondary_entry`),
plus genuine fallthrough such as `bzero`: about 98% of functions.

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
