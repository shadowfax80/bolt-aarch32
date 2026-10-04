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

## Resuming (no session context needed)

Everything needed to continue is in this repo:

- **What to do next:** *Claims* below, Open tables in resume order.
- **Findings and plans:** [CORRECTNESS_REVIEW_CLAUDE_0E616EB.md](CORRECTNESS_REVIEW_CLAUDE_0E616EB.md),
  [R17_BOLT_EDGE_PLAN.md](R17_BOLT_EDGE_PLAN.md), [LK_COVERAGE.md](LK_COVERAGE.md),
  [PI4_ORACLE_CONTRACT_DRAFT.md](PI4_ORACLE_CONTRACT_DRAFT.md) (approved).
- **Certified input image:** `fixtures/lk-rpi4-bolt-test-424606a8.elf`
  (see `fixtures/README.md`); the skip list is in
  `docs/results/lk_coverage_20261004_r6.json` (`skip_funcs`).
- **Backend source:** overlays `overlay/llvm/patches/atfe/0001–0053`; the WSL
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
- **Environment notes:** Windows Python with pyserial is `py -3.12`; Pi on
  COM5; sample captures occasionally fail chunk validation (USB corruption),
  retry; never `git stash` from WSL on the Windows checkout.

## Target platform (user, 2026-10-04) and gap to it

The product target is **Arm Cortex-A55, multi-core (SMP), AArch32, bare-metal
LK, always privileged SVC, mostly Secure state, no FPU and no NEON**. The Pi 4B
(Cortex-A72, run as ARMv7-A Cortex-A15 code, Non-secure SVC) is the
verification stand-in. Completeness against that target:

| Aspect | Target | Implemented / verified today | Gap |
|---|---|---|---|
| Architecture | ARMv8.2-A, AArch32 state (A32/T32) | Admission (0041) accepts **only ARMv7-A** attributes and decodes with v7 features; `armv8a` is a must-reject test case | **T1 (P0): an A55-built image is rejected outright.** Needs v8-A AArch32 admission + decode (LDA/STL, LDAEX/STLEX, `dmb ishld`, `sevl`, v8 IT restrictions), lit tests, and a Pi image built for v8-A AArch32 (the A72 runs it) |
| No FPU / no NEON | none at all | Enforced: `-mfpu=none` everywhere, `check-no-fpu.sh` (fail-closed since 000a8a4), BOLT runtime NEON-free; certified fixtures 0 VFP/NEON | None, keep the guard on every new build (incl. v8 images) |
| Privileged SVC only | always SVC | Matches the instrumentation contract (privileged); all Pi runs in SVC | None for rewriting |
| SMP | multi-core | Pi LK runs `WITH_SMP` (4 cores) but rewritten code is only exercised on the boot core; instrumentation contract is `single-core-no-fiq` (counter reset/snapshot need quiescence); exclusive-pair guards know LDREX/STREX and LDAEX/STLEX | **T2 (P0): concurrent execution of rewritten code on all cores not verified; SMP instrumentation not admitted.** Pi has 4 cores, so this is testable |
| Secure state | Secure SVC only; PMU sampling interrupts are IRQ (user) | Pi runs Non-secure SVC; Secure-SVC Pi bring-up plan on hold (user). Rewriting is Secure/Non-secure agnostic; IRQ-based PMU sampling is compatible with the `no-fiq` instrumentation contract; no SMC/monitor calls in target LK | **T3 (P2, optional):** a Secure-SVC confirmation run on the Pi, only when the user asks |
| Interrupts | IRQ active (incl. PMU sampling); no FIQ | Rewritten IRQ handler verified on the Pi (676 IRQs, R4); quiet fixtures otherwise | Matrix 9 (interrupts/reentrancy) and 10 (PMU ownership) remain open |
| Performance numbers | in-order A55, small caches | Measured on out-of-order A72 | **T4 (P2):** layout gains are not transferable; final measurements belong on target hardware |

Bottom line: within the declared boundary the backend is functional and Pi-verified
for ARMv7-A, single-core-exercised code. For the actual target it is **not yet
applicable** (T1 blocks any A55-built image) and SMP execution is unverified (T2).
T1 and T2 lead the resume order.

## Live-tree lock

| Holder | Since | Purpose |
|---|---|---|
| — (free) | 2026-10-04 | Released by Claude after overlay 0057 |

## Claims (consolidated TODO)

One shared list. Review items (R*) come from the 2026-10-04 Claude review
([details](CORRECTNESS_REVIEW_CLAUDE_0E616EB.md)); certification items
(6a–14) keep their closure criteria in
[CORRECTNESS_PRIORITY_TODO.md](CORRECTNESS_PRIORITY_TODO.md). "Part of"
links an R item to the certification item it contributes to; closing the R
item does not close that item. *Owner* is empty until someone claims it.

### Remaining shared work, in resume order

Take items in the order below; groups reflect dependencies, not ownership.

**B. P0 certification (first)**

| Order | ID | Item | Priority | Owner | Status | Part of | Notes |
|---|---|---|---|---|---|---|---|
| 2a | T1 | ARMv8-A AArch32 (Cortex-A55) admission and decode: accept v8-A build attributes, decode v8 AArch32 integer instructions (LDA/STL, LDAEX/STLEX, `dmb ishld`, `sevl`), keep rejecting FP/NEON; lit tests; Pi image built for v8-A AArch32, coverage + certified gate | P0 | — | Open | 6b, 7, 11 | Target is A55; 0041 rejects `armv8a` today (must-reject test); A72 on the Pi executes v8 AArch32 |
| 2b | T2 | SMP: run rewritten functions concurrently on all Pi cores (results + execution per core); decide SMP instrumentation contract (counters are LDREX/STREX; reset/snapshot quiescence) | P0 | — | Open | 9, 10 | Pi LK already runs `WITH_SMP` (4 cores); today only the boot core executes rewritten code |
| 3 | 6a | Every gate proves execution: close G1 (fixed-path intermediates), G2 (seal profile chain in QEMU certificate), G3 (contracts for QEMU LK builds) | P0 | — | Partial: G1/G2 done; QEMU route diagnostic (user), runs to instrumentation, then blocked by R15 | — | Pi sealed chain certified; G3 needs user review; 0054 ON/OFF builds and scoped Pi runs verified, remaining gate routes still open |
| 4 | 6c | Legacy/manual hook admission | P0 | — | Partial | — | R9 done; includes R13 |
| 5 | 6d | Durable receipts on every certification route | P0 | — | Partial | — | Pi gate + coverage report receipts exist |
| 6 | 6b | Oracle contracts for further configurations (Thumb workloads, future `bolt_edge` seeds) | P0 | — | Partial | — | Active `pi4` contracts: full LK (`424606a8…`), bolt_edge stage 1 (`0895d7bc…`), 1b (`439dfd7c…`) and 2 (`ce8dd005…`); each new contract needs user review |

**C. Correctness defects (small)**

| Order | ID | Item | Priority | Owner | Status | Part of | Notes |
|---|---|---|---|---|---|---|---|
| 7 | R8 | r12 clobbered by local-branch LongJmp stubs | P1 | — | Open | 13 | Liveness check or rejection |
| 8 | R15 | Full-LK instrumentation blocked by `arch_spin_trylock` guard (false positive) | P1 | — | Open | exclusive guards (0038/0039) | Keep must-reject tests for real cross-function pairs |
| 9 | R12 | ADR to an inline TBB/TBH table (`vsnprintf`) | P2 | — | Open | 12 | Last coverage item |
| 10 | R13 | Redirect functions starting with a 16-bit instruction | P2 | — | Open | 6c | If not done under 6c |
| 10a | R21 | A32 `-O0` load-then-jump tables (`add rB, pc, #k; ldr rX, [rB, rI, lsl #2]; mov pc, rX` / `bx rX`) still rejected as PC read | P2 | — | Open | 12 | Found by R17 after R18 (`c_switch_arm_o0`, `c_switch_marm_o0`); extend 0057's table model to a register jump |
| 10b | T3 | Secure-SVC confirmation run on the Pi (rewriting is state-agnostic; PMU sampling is IRQ, so no FIQ conflict; no SMC calls) | P2 | — | Optional | 9 | Only when the user asks (Pi Secure SVC on hold) |
| 10c | T4 | Performance on target hardware: A72 gains are not transferable to the in-order A55 | P2 | — | Open | — | Needs target hardware access |


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
| 18 | 14 | Clean build/content provenance | P1 | — | Partial | Overlay replay only; ISA-aware no-FPU output scanning/metadata needed (0054 audit) |

**Needs the user:** new oracle contracts (6b, T1 v8-A image); target hardware for T4; go-ahead for Secure-SVC on the Pi (T3, optional).

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
| R11 | Skip-and-report admission mode | P1 | Codex | — | 0054; [diagnostic contract/evidence](ARM_ADMISSION_REPORT.md); one scan, same 399/417 coverage; both assertion modes + scoped Pi |

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
  timeout-feature test unsupported. CoreTests: 58 passed/31 target skips each.
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
