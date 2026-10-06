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
  [latest review](reviews/CORRECTNESS_REVIEW_CODEX_0072_20261006.md), and the
  [documentation map](README.md) for gate contracts, reviews and history.
- **Certified input image:** `fixtures/lk-rpi4-bolt-test-424606a8.elf`
  (see `fixtures/README.md`); the skip list is in
  `docs/results/lk_coverage_r15_20261004.json` (`skip_funcs`).
- **Backend source:** overlays `overlay/llvm/patches/atfe/0001–0072`; the WSL
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
- **Build versions:** ON is `build-atfe`; OFF is `build-atfe-noassert`, both
  on 0001–0072 (ARM lit 61/61). Clean-build provenance (item 14): a clean
  build of the pin plus 0001–0072 in both modes gives byte-identical outputs
  to both live builds on the G1, SMP/single-core instrumentation and split
  jobs; clean OFF tools equal live OFF byte for byte
  ([receipt](results/item14_provenance_20261006/README.md)). Rerun `scripts/clean-build-atfe.sh` and
  `scripts/build_provenance.py` after backend changes that need a receipt.
  The older OFF build `out/correctness/build-atfe-noasserts-20261002` is 0054
  evidence. Preserve dirty live source.

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
| No FPU / NEON | Inputs guarded with `-mfpu=none`; scanner fail-closed since 000a8a4; runtime integer-only | None for decoding: BOLT outputs carry correct mapping symbols (0072, R30) and the guard refuses files whose marks are inconsistent |
| Privileged SVC | Declared Pi routes run in SVC | Broader entry/state/interrupt preservation remains in the certification matrices |
| Security state | The target runs Non-secure SVC, the same state as every Pi run | None. Secure-SVC parity (T3) closed as not needed (user, 2026-10-05) |
| IRQ / PMU | IRQ sampling hook and scoped rewritten IRQ evidence; per-core watch ranges available | Active IRQ/reentrancy, per-sample core attribution and loss/saturation accounting remain open; GICv3 target needs the equivalent platform hook |
| Performance / real target | Pi is out-of-order A72; target A55 is in-order | T4 P2 belongs to the user on target hardware; Pi gains do not transfer |

T1/T2 and the declared P0 routes are complete; T3 is closed (not needed). New
image/configuration oracle contracts still require user review.

## Live-tree lock

| Holder | Since | Purpose |
|---|---|---|
| Codex | 2026-10-06 | R35: safe conditional-return instrumentation, new per-item overlay/tests and both assertion-mode verification. Preserve dirty live source and existing evidence |

## Pi reservation

Board-wide: shared by bolt-aarch32 and lk-perf (one Pi 4B on COM5).

| Holder | Since | Purpose / last observation |
|---|---|---|
| Codex | 2026-10-06 | R35: sealed CSPGO stair counter capture, result/flow parity and rewritten-PC checks; watchdog armed for runs. Previous observation: CS+BOLT shell, sampler stopped/watch ranges cleared, watchdog off, COM5 closed |

## Claims (consolidated TODO)

One shared list. Review items (R*) come from the 2026-10-04 Claude review
([details](reviews/CORRECTNESS_REVIEW_CLAUDE_0E616EB.md)) and the
[recovered Astra review](reviews/CORRECTNESS_REVIEW_ASTRA_0057.md); certification items
(6a–14) keep their closure criteria in
[history/CORRECTNESS_PRIORITY_TODO_0045_HISTORY.md](history/CORRECTNESS_PRIORITY_TODO_0045_HISTORY.md)
and [history/CORRECTNESS_WORKSTREAMS_HISTORY.md](history/CORRECTNESS_WORKSTREAMS_HISTORY.md). "Part of"
links an R item to the certification item it contributes to; closing the R
item does not close that item. *Owner* is empty until someone claims it.

The [2026-10-06 joint review](reviews/CORRECTNESS_REVIEW_CODEX_0072_20261006.md)
adds R31–R34. These are follow-ups; historical B1/B2/G1/item-14 milestones
keep their scoped evidence. R31 depends on the strict capture contract in
lk-perf K18, and target guarantees also need K19/K20. No new backend P0
defect was reproduced; incomplete host evidence must still fail closed.

### Remaining shared work, in resume order

Take items in the order below; groups reflect dependencies, not ownership.

**C. Correctness defects and target items** (declared group B P0 milestones are complete)

| Order | ID | Item | Priority | Owner | Status | Part of | Notes |
|---|---|---|---|---|---|---|---|
| 1 | R32 | Complete, bound suite measurement and result frames | P1 | — | Open | — | Missing passes/results/metrics yield success and false -50% total; reject omissions/duplicates before publication, seal image identity; [closure criteria](reviews/CORRECTNESS_REVIEW_CODEX_0072_20261006.md#new-follow-ups-and-closure-criteria) |
| 2 | R31 | Fail-closed lk-perf PC-profile collection | P2 | — | Blocked (lk-perf K18) | 10 | Missing footer is accepted and downstream identity passes; require strict session/record/mode/period checks and parser provenance; start after lk-perf K18 (shared strict parser); P2: lk-perf profiles feed optimisation quality, not the certified (counter-based) pipeline; [closure criteria](reviews/CORRECTNESS_REVIEW_CODEX_0072_20261006.md#new-follow-ups-and-closure-criteria) |


**D. P1 certification matrices (as capacity allows)**

| Order | ID | Item | Priority | Owner | Status | Notes |
|---|---|---|---|---|---|---|
| 11 | 8 | CFG and mutation invariants | P1 | — | Partial | R4–R6, R19, R11, R23 done |
| 12 | 7 | Relocation/literal/veneer matrix | P1 | — | Partial | R1–R3, R7, R14, R25 done; include cross-fragment Thumb B.W/BL beyond ±16 MB (V10) |
| 13 | 11 | Entries/symbols/reference routes | P1 | — | Partial | R9 done |
| 14 | 12 | Tables and inline data | P1 | — | Partial | R18, R22, R24, R12, R21, R26 done |
| 15 | 13 | Actual pass combinations | P1 | — | Partial | R7, R8, R20, R27 done; 0072 joint review: 182 outcomes/mode, 158 matching +24 safe rejects; retain combined-pass/far-fragment and r12 live/dead matrix scope |
| 16 | 9 | Interrupt/reentrancy/reset boundaries | P1 | — | Partial | T2/T2b (SMP execution and counters) done; active-IRQ fixtures still open |
| 17 | 10 | Sampling/PMU ownership | P1 | — | Partial | Per-core PC watch ranges (T2) done; per-sample core attribution and loss/saturation accounting open |

**E. Workflow reproducibility and intended target**

| Order | ID | Item | Priority | Owner | Status | Part of | Notes |
|---|---|---|---|---|---|---|---|
| 18 | R33 | Safe, identity-checked clean-build resume and failure propagation | P2 | — | Open | 14 | Source marker/build cache can be stale; lit exit hidden by `\|\| true`; validate output ownership before cleanup. Item-14's independent PASS remains scoped; [closure](reviews/CORRECTNESS_REVIEW_CODEX_0072_20261006.md#new-follow-ups-and-closure-criteria) |
| 18a | R35 | Exact BOLT counter profiles for conditional-return compiler outputs | P2 | Codex | In progress | — | User requested next after C2. C1 CSPGO/ThinLTO stair hits 0036's safe conditional-return refusal; PC sampling works. Model function-exit counts and preserve predicates/IT, flags and stack state; test A32/T32, both assertion modes and Pi parity before relaxing the guard; do not treat this as general CSPGO incompatibility |
| 19 | R34 | Portable B1/B2 capture and measurement evidence | P2 | — | Open | — | Published CSVs have uniform metric/run sets; raw captures point into local temporary storage, not tracked paths; retain hash-bound logs/inputs and audit result frames; [closure](reviews/CORRECTNESS_REVIEW_CODEX_0072_20261006.md#new-follow-ups-and-closure-criteria) |
| 20 | T4 | Performance and final validation on the real A55 target (A72 gains not transferable) | P2 | User | Out of scope here | — | Done by the user in the office environment, from this repo |

**Needs the user:** new oracle contracts for new configurations.

### Done

Completed items with patches and evidence: [history/HANDOFF_DONE.md](history/HANDOFF_DONE.md) (newest first; add new rows there). Latest: C2 (compiler/BOLT route docs), C1 (compiler pipeline; R35 counter support remains open), CR1 (review/docs only), 14, R30, G1, B2, R28, R29, B1, M2, T3 (closed), R27, R25, R26, R21, R12, R24, R23.

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

### 2026-10-06 — Codex: C2 verified/documented two compiler paths and two BOLT profile modes

- Verified script wiring: `build-variants.sh` and LK `pgo.mk` retain FE-PGO+
  ThinLTO (`pgo_thinlto`) and default IR-PGO+ThinLTO+CSPGO (`cspgo_thinlto`).
  The latter has ordinary/late CS training rounds and final merged use with
  ThinLTO. FE is an alternative, not an extra stage before ordinary IR training.
- BOLT independently uses sampled or instrumented feedback for the exact
  final compiler ELF. Checked the generic `BOLT_FDATA`/counter conversion
  branches, sealed sampling collector, CS wrapper and historical FE staged
  scripts against Clang/BOLT primary documentation. Published the
  [four-combination route/status matrix](verification/CSPGO_PIPELINE.md#two-compiler-paths-two-bolt-profile-modes)
  and propagated it into root README, architecture, WSL guide and doc map.
- Evidence scope explicit: FE instrumented route has historical Pi results;
  FE sampled route is generic wiring, not a fresh measured C2 combination.
  C1 IR+CS sampled route is measured; the current stair kernel's counter
  route safely refuses conditional returns (0036/R35). No universal gain,
  all-four measured matrix or broadened instrumentation claim. Sampling and
  counters are profile acquisition modes of the same BOLT optimizer.
- Documentation only, no source/image/overlay/build changes or Pi access.
  Repository health and staged whitespace checks pass. Coverage unchanged
  401/417, 126164/126834 bytes (99.5%); no regeneration needed. Locks remain
  free, Pi last-observed C1 state unchanged; preserved `Microsoft/`.
  Next shared item remains R32; R35 Open P2. No new pending item from C2.

### 2026-10-06 — Codex: C1 compiler pipeline complete; R35 queued; resources released

- Added module IR-PGO and late CSPGO with ThinLTO, two-round collection and
  merged-profile validation/use; frontend PGO retained. LK overlay files and
  host build/collection tools changed, **no LLVM backend source change or new
  ATFE patch**. LK-only overlay installation avoids reapplying shared LLVM.
  [Recipe](verification/CSPGO_PIPELINE.md), [portable evidence/results](results/c1_cspgo_20261006/README.md).
- User requested normalization: the main flow is ordinary IR-PGO followed by
  late CSPGO, final merged use with ThinLTO. No-argument `build-variants.sh`
  selects `cspgo_thinlto`; `pgo_cycle_wsl.sh` defaults to the two-round workflow,
  legacy frontend requires `--frontend`. Historical staged/sweep callers now
  select it explicitly. Fresh default final ELF/bin equal the measured CS
  image byte for byte; no-FPU, shell syntax/dispatch and ten focused tests pass.
  Root README/WSL guide updated; frontend and IR collection modes distinguished.
  Frontend-use + IR-generation driver flags reject on the pin (retained probe);
  no third frontend feedback stage added. Archive round-trip/manifest and
  staged receipt byte checks pass; raw log bytes preserved via Git attributes.
- Pi: both profile levels trained (75 records each), four compiler builds;
  primary 36 measurements plus final current-workflow 12. CSPGO vs IR+ThinLTO:
  variants 0/1 -43.48/-43.46% cycles; variant 2 -0.01%, interval includes zero.
  Plain O2 sanity comparison is -11.93% (only two runs/image).
- Optional sealed PC sampling/BOLT comparison (48 records): IR+ThinLTO+BOLT
  -43.02% on variant 0; **CS+ThinLTO+BOLT +0.47/+0.43/+20.25%** on variants
  0/1/2 vs CS alone. Publish the shifted-input regression; no universal gain
  or A55 timing claim. Each exact compiler ELF has its own profile seal;
  failed UART capture rejected/preserved, accepted retry retained. Five
  final images have complete matching 18-workload results. Separate CS+BOLT
  watch observes 501 PCs in the rewritten kernel, sampler then stopped.
  No new oracle contract or certification derived from output agreement.
- Exact-counter instrumentation hits existing 0036 conditional-return refusal.
  This is fixable instruction-shape support, not CSPGO incompatibility.
  **R35 Open P2**: preserve exit predicates/IT/flags/registers/stack, model both
  paths, A32/T32 tests in both assertion modes and Pi parity before relaxing
  the guard. Sampling comparison does not establish exact-counter gains.
- Verification: 177 host tests run/12 skipped/no failures; ten new profile,
  transport and training-frame tests; shell syntax and all built-image
  no-FPU scans pass. Baseline/legacy collection compile and legacy profile
  validates (fresh legacy optimized cycle not run). Full overlays 0001–0072
  replay exactly with live source preserved. Certified fixture coverage
  before/after unchanged 401/417, 126164/126834 bytes (99.5%); regenerated
  [receipt](results/lk_coverage_c1_20261006.json). Compiler candidates 407/423
  emitted each are different images, not expanded certified coverage.
- WSL remains running and available. Isolated LK/build evidence is in
  `/home/user/bolt-cspgo`, pinned LK `79d2f560`; compiler/runtime used read-only
  from shared `build-atfe`. Shared LLVM source, assertion-mode builds and
  indices preserved on 0072; Windows `Microsoft/` preserved. Pi last observed
  CS+BOLT shell, sampler stopped/watch ranges cleared, watchdog off, COM5
  closed. Live-tree lock and board reservation released by this push.
- Next: claim **R32** in the shared pool; R31 still depends on lk-perf K18.
  R35 is a later P2 backend task. Complete images/profiles/logs/manifests are
  in the published 1.97 MB archive, avoiding dependence on local scratchpads.

### 2026-10-06 — Claude: CR1 follow-ups verified; R31 re-prioritised

- Reran Codex's `probe_contracts.py` on current trees: all nine observations
  reproduce (R31 missing footer accepted, R32 false -50%, lk-perf K16-K18,
  K21). Source check confirms R33 (clean-build helper) and R34 (B1/B2
  manifests point into a temporary scratchpad). All four items are accurate.
- Changes: R32 first; R31 P1 -> P2 and Blocked on lk-perf K18 (it reuses
  K18's strict parser, which was queued after R31). lk-perf priorities
  adjusted in its own handoff. Docs only, no code, build or Pi.

### 2026-10-06 — Codex: CR1 joint deep review complete; follow-ups published

- Reviewed BOLT `d6aa4bb` / overlays 0001–0072 and lk-perf `a547f94`
  through K15. Published [review](reviews/CORRECTNESS_REVIEW_CODEX_0072_20261006.md),
  [offline evidence](results/cr1_review_20261006/README.md), R31/R32 P1 and
  R33/R34 P2 closure criteria. Updated current documentation/limitations;
  existing historical milestones remain scoped. CR1 Done means review/docs,
  not closure of the newly identified implementation defects.
- BOLT host: 167 tests OK/12 skipped. Differential: each assertion mode
  158 matching +24 safe rejects (182), no wrong/crash/hang. Focused 0070,
  0071, 0072 checks pass ON/OFF; four used tool hashes/mode and overlay
  series match item 14. lk-perf: 56 tests OK/1 skipped, 7 unwind checks PASS;
  actual optional Perfetto consumer fails stale K3 expected stack (K25).
  Probes reproduce incomplete collector acceptance and false suite gain;
  B1/B2 CSV audit finds complete uniform published metric sets, not that
  failure. Raw logs are local temporary artifacts (R34).
- Tracked-file repository health PASS (72 overlays, fixture/R11 identities,
  Python/JSON and local documentation targets). Changed-document links,
  code fences and staged whitespace checks pass in both clones.
- No implementation/overlay/image changes, build, coverage regeneration or
  Pi use. Coverage unchanged 401/417 and 126164/126834 bytes (99.5%). Shared
  WSL source/build/index trees and Claude's checkouts untouched; locks free,
  Pi unreserved. Last observation remains Claude's G1 release (shell,
  watchdog disarmed, COM5 closed); no live probe. Preserved `Microsoft/`.
- Next: claim R31/R32; coordinate lk-perf K18 before creating another parser.
  Reserve live trees/Pi only if that work needs them. P1 matrices remain
  open; do not interpret current coverage as all-backend certification.

### 2026-10-06 — Codex: GitHub synchronization of both project checkouts

- Fast-forwarded the Codex BOLT checkout to `d6aa4bb` and the independent
  Codex lk-perf checkout to `a547f94`; read both current handoffs and claims.
  Imported the published 0070–0072 changes and G1/item-14 evidence. This
  sync did not independently rerun the reported tests or hardware gates.
- Git fast-forward checks passed; preserved the pre-existing untracked
  `Microsoft/` directory. No source edits, overlay application, rebuild,
  coverage regeneration, work-item claim or COM5 action during this sync.
  Published coverage stays as imported; shared WSL sources/builds and
  Claude's checkouts were not modified.
- Both live-tree locks remain free, Pi unreserved. Last board observation
  is Claude's G1 release in the reservation table, not a new live probe.
- Next: use the current shared queue and publish a claim/resource ownership
  before implementation. lk-perf has K11 blocked and T4 user-owned; BOLT
  retains its P1 certification matrices. Sync-only stop recorded here.

### 2026-10-06 — Claude: item 14 done (clean build provenance); lock and Pi released

- Clean full build of pin `bcc08884` + 0001–0072, fetched from the remote,
  both assertion modes, clang, no ccache (`scripts/clean-build-atfe.sh`).
  `scripts/build_provenance.py` PASS: source contents identical to the live
  tree (184,669 paths; 25 mode-bit-only differences), clean ON/OFF configs
  differ only in assertions, clean ON config = live ON, ARM lit 61/61 in all
  four builds, clean OFF tools byte-identical to live OFF, and the G1,
  SMP/single-core instrumentation and split jobs give identical, deterministic
  outputs in all four builds (`.bin` = certified `2181dffe…`). This also
  gives OFF parity for 0060/0061. [Item 14 results](results/item14_provenance_20261006/README.md).
- Audit findings recorded: host compiler not bound by the cache file (now
  explicit in the clean script); live OFF configured without the clang
  project; the bare-metal runtime is outside CMake.
- V6 resolved (0072 + guard). Pi not used for item 14 (byte parity with the
  certified image). Next: P1 matrices (items 8, 7, 11, 12, 13, 9, 10).

### 2026-10-06 — Claude: 0072 made deterministic (sorted linker marks)

- Item 14's first parity run: the flashed G1 `.bin` and the G1 ELF (without
  `.note.bolt_info`) are identical across clean/live ON/OFF builds, but the
  instrumented and split outputs differed even run to run: 0072 emitted
  stub marks in JITLink's pointer-hash order. 0072 now sorts them; three runs
  give identical outputs. ARM lit 61/61 both modes, replay exact.
- `.note.bolt_info` records the llvm-bolt path and command line, so parity
  compares outputs without it (raw hashes recorded too) and also runs each
  job twice. Clean build restarted on the fixed series.

### 2026-10-06 — Claude: R30 extended again (linked runtime library marks)

- Item 14's parity scenarios instrumented the LK input: the instrumentation
  runtime's `.text` (`.text.bolt.extra.1`, ARM) had no mapping symbols and
  decoded as Thumb (8 false FP hits per output). 0072 now also takes the
  linker's marks: JITLink keeps a linked object's own `$a`/`$t`/`$d` and each
  stub's ISA; the rewriter adds them for executable sections it does not
  mark itself.
- `arm-mapping-symbols.test` adds an instrumented run; fails on 0071 and on
  0072 as of bdcac1e, passes now. ARM lit 61/61 both modes, replay exact,
  coverage 401/417, G1 `.bin` identical (`2181dffe…`).

### 2026-10-06 — Claude: R30 extended (0072 updated: Thumb bit on fragment symbols)

- Item 14's stricter no-FPU guard (each STT_FUNC must start in the state its
  bit 0 gives) failed on a split build of the bolt_bench image: split
  `foo.cold.N` STT_FUNC symbols had bit 0 clear for Thumb fragments (also
  the non-relocation `foo.icf.0` alias). Same item, so 0072 was extended
  rather than a new overlay; nothing consumed the first 0072 (2a629c5).
- `arm-mapping-symbols.test` now adds a split Thumb function and an ICF pair;
  fails on 0071 and on the first 0072, passes now. ARM lit 61/61 in both
  assertion modes, replay 0001–0072 exact, coverage unchanged 401/417, G1
  `.bin` still identical. Guard: instrumented and split+ICF builds with 0072
  pass. [R30 results](results/r30_20261006/README.md).

### 2026-10-06 — Claude: R30 fixed (0072, output mapping symbols)

- Item 14's no-FPU guard flagged 1,943 FP/NEON "instructions" in the G1
  output: wrong mapping symbols, not code. BOLT marked new code only where
  the input had a mark at the entry (ARM functions that inherited `$a`
  followed Thumb code unmarked), put island "code resumes" marks on the next
  function's entry, dropped all marks of the kept original section, and left
  JITLink stubs unmarked. 0072 fixes all four.
- `arm-mapping-symbols.test` fails on 0071, passes on 0072; ARM lit 61/61 in
  both assertion modes; replay 0001–0072 exact; coverage unchanged 401/417
  (`lk_coverage_r30_20261006.json`). G1 image rebuilt on 0072: `.bin`
  identical (`2181dffe…`), so G1's Pi certification carries over; 0 of 417
  functions in the wrong state, original section decodes like the input
  except the 2 redirected entries. [R30 results](results/r30_20261006/README.md).
- WSL live tree: source = 0001–0072, `build-atfe` and `build-atfe-noassert`
  llvm-bolt rebuilt. Lock and Pi kept for item 14.

### 2026-10-06 — Claude: G1 passed (certified full-image gate on 0001–0071)

- `full_image_build.py` on `lk-rpi4-bolt-test-424606a8.elf` with the WSL
  `build-atfe` (0001–0071, llvm-bolt sha `e0d7e741…`): 417 input functions,
  402 emitted, 2 redirected (`bolt_bench_interwork`, `bolt_bench_memcpy`),
  0 stubs. Kept-code audit: 9 patched instructions, 0 changed shape.
- `full_image_verify.py --repeat 10` on the Pi, watchdog armed: PASS, 18
  workload results equal baseline and formulas, PC evidence for both
  redirected functions. Receipt: [`results/g1_certified_0071_20261006.json`](results/g1_certified_0071_20261006.json).
- Lock and Pi kept for item 14.

### 2026-10-05 — Claude: B2 done (B1 rerun on 0001–0071); lock and Pi released

- Thumb images, no R28 workaround, lk-perf with K13-K15, denser sampling.
  [B2 results](results/b2_sampling_vs_instrumentation_rerun_20261005/README.md).
- Showcase (Thumb ThinLTO stair 512): instrumentation -68.1%, lk-perf
  sampling -67.6% vs the input (99.3% of the gain).
- Whole image: -4.45% (instrumentation, 11 fns), -4.31% (lk-perf, same
  scope), -2.77% (lk-perf, 69 fns). Dense sampling fixed B1's composite
  regression; new: sampled layouts mispredict 5x more on stair at -O2
  (+10.3%, branch directions inferred from block counts), and a
  whole-image hfsort+ order splits multi's six functions (L1I refills
  52k -> 700k, -45% -> -34%). All app results identical; R28-affected
  code ran rewritten without fault.
- No source change. Next: P1 certification matrices.

### 2026-10-05 — Claude: R28 and R29 fixed (0070, 0071); lock and Pi released

- R28 (P0): BOLT's JITLink pre-prune pass flagged the section symbol Thumb
  whenever `.text` started inside a Thumb function, so every absolute word
  built from it (A32 `ldr pc` table entries) got bit 0. 0070 gives each such
  `Data_Pointer32` edge its own target with the parity from the addend.
  `arm-ldr-pc-table-mixed-isa.test` fails on 0069, passes on 0070. Pi:
  rewritten, redirected `pl_b` and `bolt_bench_switch` give identical
  results (data abort before).
- R29: LongJmp measured Thumb short branches by their short encodings and
  asked for r12 stubs (R8 refusal). 0071 widens B/B<c> in place
  (`MCPlusBuilder::widenBranch`) and measures CBZ/CBNZ as the B.W that
  prepareForEmission emits. `arm-thumb-short-branch-range.test` (qemu-arm
  run) fails on 0070, passes on 0071. Pi: Thumb ThinLTO stair BOLT -68.1%
  vs its input (refused before); Thumb whole-image instrumentation of 11
  functions and BOLT from it, all app results identical, multi -45.5%.
- ARM lit 60/60 in both assertion modes; replay 0001-0071 clean; LK coverage
  unchanged 401/417 (`lk_coverage_r29_20261005.json`). Evidence:
  [R28/R29 results](results/r28_r29_20261005/README.md).
- Process note: the first R28 Pi check ran while the Pi was still unreserved
  after B1 (no conflicting holder); the R29 checks ran under a published
  reservation (3d5564b).
- WSL live tree: source = 0001-0071, `build-atfe` and `build-atfe-noassert`
  rebuilt (llvm-bolt). Next: the P1 certification matrices (items 8, 7, 11,
  12, 13, 9, 10, 14).

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
