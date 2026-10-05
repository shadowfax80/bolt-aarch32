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
   and watchdog state before publishing the release. The table below is
   **board-wide**: lk-perf work reserves the same Pi here too (see
   [lk-perf HANDOFF](https://github.com/shadowfax80/lk-perf/blob/main/docs/HANDOFF.md)).

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
- **Design and state:** [architecture](AARCH32_BACKEND_ARCHITECTURE.md),
  [limitations](KNOWN_LIMITATIONS.md), [coverage](LK_COVERAGE.md),
  [latest review](reviews/CORRECTNESS_REVIEW_CLAUDE_0069.md), and the
  [documentation map](README.md) for gate contracts, reviews and history.
- **Certified input image:** `fixtures/lk-rpi4-bolt-test-424606a8.elf`
  (see `fixtures/README.md`); the skip list is in
  `docs/results/lk_coverage_r15_20261004.json` (`skip_funcs`).
- **Backend source:** overlays `overlay/llvm/patches/atfe/0001–0069`; the WSL
  live tree must replay them exactly (`scripts/verify-atfe-overlays.py`).
  Do not run `scripts/apply-overlays.sh` on the dirty live tree.
- **Commands:**
  - Coverage: `python3 scripts/lk_coverage_report.py --elf fixtures/lk-rpi4-bolt-test-424606a8.elf --toolchain /home/user/bolt-aarch32/build-atfe/bin --out <fresh dir> --doc docs/LK_COVERAGE.md --json docs/results/lk_coverage_<date>.json`
  - Raw re-patch check: `python3 scripts/check_raw_original_text.py --input <elf> --raw <llvm-bolt output> --toolchain <bin>`
  - Certified Pi run: `scripts/pi4/full_image_build.py` then
    `py -3.12 scripts/pi4/full_image_verify.py <dir> --require-executed <redirects> --repeat 10 --port COM5 --fast-loader tools/pi4-serialboot-fast/kernel7l_fast.img`
  - Sealed profile chain: `profile_identity.py seal-samples` →
    `pi4/pi4_sample_profile.py` → `samples_to_fdata.py --skip-funcs …` →
    `full_image_build.py --profile …` (see `docs/verification/PI_PROFILE_IDENTITY.md`).
- **Environment notes:** use a Windows Python with pyserial (`py -3.12` or
  the Codex venv `out/correctness/pi-venv/Scripts/python.exe`); Pi on
  COM5; sample captures occasionally fail chunk validation (USB corruption),
  retry; never `git stash` from WSL on the Windows checkout.
- **Build versions:** ON is `build-atfe`; current OFF is `build-atfe-noassert`,
  tested through 0069 (ARM lit 58/58, 2026-10-05). The older OFF build
  `out/correctness/build-atfe-noasserts-20261002` is 0054 evidence. ON 0060–0061
  checks do not establish OFF parity for those overlays; recheck build hashes.
  Preserve both older receipts and dirty live source.

## Target platform (user, 2026-10-04) and gap to it

The product target is **Cortex-A55, SMP, AArch32 bare-metal LK, always Non-secure SVC (the same state as the Pi), no FPU and no NEON**. Testing here uses Pi 4B A72 cores only;
the user will port and perform final validation on the real A55 target from
this repo. Keep build recipes, LK/backend overlays and approved contracts
portable. Pi evidence covers the executed A72-compatible instructions and
workloads; A55 timing and target-platform behavior require target evidence.

| Aspect | Implemented / verified | Remaining gap |
|---|---|---|
| ARMv8-A AArch32 | T1 Done: 0058 accepts v8-A attributes and decodes v8 integer instructions; LK patch 0011 adds `cortex-a55`; approved A55-built Pi fixtures certified | No A55-only instruction or target-hardware claim; keep the A72-compatible subset explicit |
| SMP execution | T2 Done: declared rewritten workloads run on all four Pi cores with independent sinks and per-core PC evidence | Wider runtime/IRQ matrix 9 and PMU/loss matrix 10 remain Partial |
| SMP counters | T2b Done: 0060 privileged-SMP-no-FIQ helper; all 74 selected counters match the scoped Pi model | Reset/snapshot require quiescence; broader instrumentation matrix and OFF checks for 0060 remain open |
| No FPU / NEON | Inputs guarded with `-mfpu=none`; scanner fail-closed since 000a8a4; runtime integer-only | Item 14: candidate ISA metadata/scanner still misdecodes restored original code; keep input and emitted-code checks scoped |
| Privileged SVC | Declared Pi routes run in SVC | Broader entry/state/interrupt preservation remains in the certification matrices |
| Security state | The target runs Non-secure SVC, the same state as every Pi run | None. Secure-SVC parity (T3) closed as not needed (user, 2026-10-05) |
| IRQ / PMU | IRQ sampling hook and scoped rewritten IRQ evidence; per-core watch ranges available | Active IRQ/reentrancy, per-sample core attribution and loss/saturation accounting remain open; GICv3 target needs the equivalent platform hook |
| Performance / real target | Pi is out-of-order A72; target A55 is in-order | T4 P2 belongs to the user on target hardware; Pi gains do not transfer |

T1/T2 and the declared P0 routes are complete; T3 is closed (not needed). New
image/configuration oracle contracts still require user review.

## Live-tree lock

| Holder | Since | Purpose |
|---|---|---|
| Claude | 2026-10-05 | R28 (ARM ldr-pc table Thumb bit), R29 (Thumb r12-stub refusals): ATFE source and builds |

## Pi reservation

Board-wide: shared by bolt-aarch32 and lk-perf (one Pi 4B on COM5).

| Holder | Since | Purpose / last observation |
|---|---|---|
| Claude | 2026-10-05 | R28/R29 hardware checks (Thumb showcase and Thumb instrumentation on the Pi) |

## Claims (consolidated TODO)

One shared list. Review items (R*) come from the 2026-10-04 Claude review
([details](reviews/CORRECTNESS_REVIEW_CLAUDE_0E616EB.md)) and the
[recovered Astra review](reviews/CORRECTNESS_REVIEW_ASTRA_0057.md); certification items
(6a–14) keep their closure criteria in
[history/CORRECTNESS_PRIORITY_TODO_0045_HISTORY.md](history/CORRECTNESS_PRIORITY_TODO_0045_HISTORY.md)
and [history/CORRECTNESS_WORKSTREAMS_HISTORY.md](history/CORRECTNESS_WORKSTREAMS_HISTORY.md). "Part of"
links an R item to the certification item it contributes to; closing the R
item does not close that item. *Owner* is empty until someone claims it.

### Remaining shared work, in resume order

Take items in the order below; groups reflect dependencies, not ownership.

**C. Correctness defects and target items** (declared group B P0 milestones are complete)

| Order | ID | Item | Priority | Owner | Status | Part of | Notes |
|---|---|---|---|---|---|---|---|
| 10a | R28 | ARM-mode inline `ldr pc, [rX, rY, lsl #2]` table re-emitted with the Thumb bit on every entry; the rewritten function data-aborts when it runs | P0 | Claude | In progress | 12 | Found by B1 on the Pi (`pl_b`), see [B1](results/b1_sampling_vs_instrumentation_20261005/README.md); 0057 models the table shape, so this is a mis-emission inside a supported shape; check the R25 (0068) data-pointer path. Workaround: keep such functions original |
| 10b | R29 | Thumb code hits the R8 r12-stub refusal on reordering (120 KB ThinLTO stair kernel) and instrumentation (`bolt_bench_multi`, 756 bytes; `bolt_bench_stair`); fails safe | P1 | Claude | In progress | 7 | Found by B1; ARM-mode builds pass; cause not analysed (narrow-branch relaxation itself is probed, R27/V7) |
| 10c | T4 | Performance and final validation on the real A55 target (A72 gains not transferable) | P2 | User | Out of scope here | — | Done by the user in the office environment, from this repo |


**D. P1 certification matrices (as capacity allows)**

| Order | ID | Item | Priority | Owner | Status | Notes |
|---|---|---|---|---|---|---|
| 11 | 8 | CFG and mutation invariants | P1 | — | Partial | R4–R6, R19, R11, R23 done |
| 12 | 7 | Relocation/literal/veneer matrix | P1 | — | Partial | R1–R3, R7, R14, R25 done |
| 13 | 11 | Entries/symbols/reference routes | P1 | — | Partial | R9 done |
| 14 | 12 | Tables and inline data | P1 | — | Partial | R18, R22, R24, R12, R21, R26 done |
| 15 | 13 | Actual pass combinations | P1 | — | Partial | R7, R8, R20, R27 (probe: split/ICF/instrument/reverse on edge shapes) done |
| 16 | 9 | Interrupt/reentrancy/reset boundaries | P1 | — | Partial | T2/T2b (SMP execution and counters) done; active-IRQ fixtures still open |
| 17 | 10 | Sampling/PMU ownership | P1 | — | Partial | Per-core PC watch ranges (T2) done; per-sample core attribution and loss/saturation accounting open |
| 18 | 14 | Clean build/content provenance | P1 | — | Partial | Overlay replay + assertions-off build (6a); clean full build and OFF parity for 0060–0061 still open; no-FPU guard misreads BOLT outputs (no input $t in original .text) |

**Needs the user:** new oracle contracts for new configurations.

### Done

Completed items with patches and evidence: [history/HANDOFF_DONE.md](history/HANDOFF_DONE.md) (newest first; add new rows there). Latest: B1, M2, T3 (closed), R27, R25, R26, R21, R12, R24, R23.

## Coverage goal

Raise BOLT coverage of the full LK test binary, measured only by
`scripts/lk_coverage_report.py` ([LK_COVERAGE.md](LK_COVERAGE.md)).

Progress by item: [history/HANDOFF_DONE.md](history/HANDOFF_DONE.md#full-lk-coverage-progression).

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

### 2026-10-05 — Claude: B1 done (BOLT from lk-perf sampling vs instrumentation); R28, R29 opened; lock and Pi released

- User asked for the real hardware benefit of BOLT from a sampling profile
  (lk-perf) vs an instrumentation profile, on a showcase and on the whole LK
  image running existing apps. Results and method:
  [B1 results](results/b1_sampling_vs_instrumentation_20261005/README.md).
- Showcase (stair, ThinLTO 512 sites, 32.60M cycles, 2.09M L1I refills):
  BOLT from instrumentation 9.196M (-71.8%), from lk-perf samples 9.226M
  (-71.7%): sampling recovers 99.9% of the gain.
- Whole image, 9 apps: total -4.43% (instrumentation), -4.37% (lk-perf, same
  11-function scope), -4.18% (lk-perf, 49 functions incl. kernel); all from
  `multi` (-45.6/-45.8/-45.7%). Sparse samples (245 in composite) gave
  +16.4%; a dense capture (13,647) gave +0.01%, equal to instrumentation.
  Kernel/libc/driver rewriting changed nothing measurable (fits in cache).
- New scripts: `scripts/pi4/pi4_lkperf_profile.py` (lk-perf capture into the
  verified sampling route), `scripts/pi4/pi4_suite_measure.py` (whole-image
  app suite); `pi4_bolt_profile.py --command`. No backend/overlay change;
  coverage not regenerated (no backend or LK test-image change).
- Bugs found: R28 (ARM ldr-pc table entries get the Thumb bit; the Pi
  data-aborted), R29 (Thumb r12-stub refusals). lk-perf side fixed in
  lk-perf K13-K15 (segment-gap hash, PC-read site capture that blocked 44
  kernel functions, stat leaving the cycle counter off).
- Build root `~/bolt-b1` (clone at e0dc130, LK 79d2f560 + bolt overlays +
  lk-perf overlays, shared toolchain read only); the shared LK tree was not
  touched. Next: R28 first (P0, wrong code).

### 2026-10-05 — Codex: shared Pi released after lk-perf demonstration

- Reserved Pi with pushed claim `9d8cdaa`. Previous LK shell responded at
  3 Mbaud; software reboot reached the serial chainloader and CRC-verified
  upload loaded the existing lk-perf image (console now 6 Mbaud).
- Ran four-core `profiler smp 400000000` with PMU CPU cycles, period 1000000.
  Retained 3200 samples, 800/core. Both samplers stopped before dump; a
  lightweight second dump recovered all records after first-dump serial loss.
- FlameGraph and Perfetto CLI import/SQL analysis verified in lk-perf;
  evidence and replay: `shadowfax80/lk-perf`,
  `docs/results/lk_perf_demo_20261005/README.md`.
- Pi left at lk-perf shell, both samplers stopped, samples retained, COM5
  closed. No watchdog command issued by lk-perf; reset replaced BOLT payload.
  No BOLT source, overlay, shared build or LK test-image change; published
  BOLT coverage unchanged. Live-tree lock remains free.
- Next agent: reserve Pi and recheck baud/state. Reboot the current image
  at 6000000 baud to return to loader; do not use the old 3 Mbaud snapshot.

### 2026-10-05 — Claude: M2 documentation consolidation; target corrected to Non-secure SVC (T3 closed)

- **Target correction (user):** the A55 target runs **Non-secure SVC**, the
  same state as every Pi run. T3 (Secure-SVC parity) is closed as not needed;
  the unused `tools/pi4-armstub-secure/` was removed (still in Git history).
  Updated HANDOFF, KNOWN_LIMITATIONS (V1), architecture doc, README, the two
  reviews that mentioned it (dated correction notes) and the published page;
  older log entries keep their wording under a correction banner.
- **Docs:** 60 top-level files → 6 current docs plus `docs/README.md` (the map).
  Moved with history: `verification/` (22 gate/contract pages), `reviews/`
  (8), `upstream/` (RFC, readiness review, and the U/D/L audit split out of
  KNOWN_LIMITATIONS), `history/` (17, including `HANDOFF_DONE.md` = the Done
  table and coverage progression moved out of this file). Removed the five
  pointer-only stubs (TODO, CORRECTNESS_TODO/STATUS/PRIORITY_TODO/RESUME).
  HANDOFF keeps the newest three log entries; older ones are at the top of
  `history/HANDOFF_HISTORY.md`. README rewritten for the current state.
- Links rewritten everywhere; overlays, receipts and `docs/bolt_edge`
  evidence untouched. `repo_health.py` now checks that no current doc other
  than HANDOFF carries work-item rows (replaces the stub check). Health clean;
  host tests 167 run / 12 skipped, no failures.
- Lock free, Pi unreserved (unchanged). Next: P1 matrices; T4 user.

### 2026-10-05 — Claude: R27 done (probe extension, no defect); lock released

- `scripts/review/edge_probe.py`: +3 cases, +3 option sets (`split`,
  `split-fill`, `instrument`; the padded split variants were dropped, see
  below). 26 × 7 = 182 runs: 158 OK, 24 known rejections (table base read,
  svc-exit noreturn, instrumentation contract), 0 wrong
  (`docs/results/edge_probe_r27_20261005.json`).
- Verified in the outputs, not just by matching results: `t.cold.0` exists
  under split; `t.cold.0` is 1.1 MB from `t` under split-fill; a backward
  `cbz` became `cbnz` + `b.w`; ICF folded both twin pairs with correct ISA bits in
  `.data`.
- `--pad-funcs-before` with `--split-functions` aborts in JITLink (the
  emitter pads each fragment, LongJmp only the first): debug-option artifact,
  recorded as KNOWN_LIMITATIONS V9; cross-fragment beyond ±16 MB unprobed (V10).
- No backend change, so no overlay, coverage regeneration or Pi run. Lock
  free, Pi unreserved (unchanged since R26). Next: P1 matrices; T3 deferred,
  T4 user.

### 2026-10-05 — Claude: deep edge-case review; R25 (0068) and R26 (0069) fixed; limitations re-baselined; lock and Pi released

- New differential harness `scripts/review/edge_probe.py`: 23 small programs
  × 4 BOLT option sets (default, reversed blocks, ICF + random function
  order, far padding), original vs BOLT output under qemu-user (diagnostic).
  First run on 0067: 6 WRONG. Final on 0069: 80 OK, 12 safe rejections, 0
  WRONG (`docs/results/edge_probe_r26_20261005.json`).
- R25 (P0, 0068): Thumb function pointers and interior-entry pointers in
  `.data` came out even (call entered ARM state). Masked in LK because the
  pipeline restores data sections. `arm-thumb-data-pointer.test`.
- R26 (P0, 0069): a re-pointed table base (0057/0066/0067) read in a case
  gave layout-dependent results; tables now need the base dead at every case
  target. `arm-table-base-liveness.test`. No coverage loss (vsnprintf still
  admitted).
- Verified: ON/OFF ARM lit 58/58; BOLT lit known AArch64 failure only;
  0001–0069 replay exactly (`f47e50ee…`); coverage LK 401/417, edge 561, A55
  400 (unchanged); certified Pi gate on `424606a8` PASS (10 reps, 18/18).
- Docs: [review](reviews/CORRECTNESS_REVIEW_CLAUDE_0069.md);
  [KNOWN_LIMITATIONS.md](KNOWN_LIMITATIONS.md) has a new current section
  (scope S1–S5, rejected shapes N1–N5, assumptions A1–A3, verification gaps
  V1–V8); U1/U5 marked superseded for ATFE.
- Next: R27 (probe extension) or the P1 matrices; T3 deferred, T4 user. Lock
  free, Pi unreserved, WSL live tree = 0001–0069.

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

Earlier implementation/session entries are in
[HANDOFF_HISTORY.md](history/HANDOFF_HISTORY.md). Historical ownership and work-order
statements there do not override the current Claims and reservation tables.
