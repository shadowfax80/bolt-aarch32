# ATFE correctness checkpoint - 2026-10-02

## Latest: resumed by user; #5 active

Actual linked runtime reset now passes the 372-case matrix in all four modes.
The bad-reset image fails at case 0/seed 0/field 2000, actual 0x12345678, proving
that clear was not replaced by fixture-side zeroing. All five images return to
the loader. Eight host gate tests pass. Evidence: it-counts-pi/build-oxagizx9/
pi-verify-0qqt43k2 and correctness_runtime_clear_20261002.json.
Next enforce the instrumentation operating boundary under #6; #5 remains
partial for live snapshots, active interrupts and mixed-ISA nested state.
Preimages for #6 are preserved in out/correctness/instrumentation-scope/before
and before-manifest.json. No scope source edits have been made at this point.

Overlay 0027 is pushed as be09efb. The expanded fixture adds nested Thumb calls
and recursion (two caller levels; n=0,1,2,3,8,17,33,64, maximum 65 frames).
All four Pi images pass 372 cases each, including original IT cases plus 72
nested/recursive seeded cases. All 85/85/73 slots match independent cross-function
path counts, and all images return to the loader. Six host gate tests pass.
Evidence: it-counts-pi/build-i6hc3l6i/pi-verify-j59k8mxz and the tracked
correctness_nested_counts_20261002.json. Run build_it_counts.py --nested to
reproduce. No backend change was required. Next validate actual runtime clear
and define snapshot/quiescence boundaries, then enforce #6. Active interrupts
and mixed-ISA nested state are still open; #12 remains separately paused.

WSL is running. Overlay 0027 normalizes terminal direct IT branches before CFG
construction and rejects unsupported IT control transfers/interior entries.
All 39 focused ARM/JITLink tests pass; the new lit test covers seven rejection
boundaries. The Pi passes 300 cases each for baseline/normal/reverse/conservative
images (1,200 total), all fifteen IT data masks, narrow/wide terminal branches,
loops, per-case reset, low carry and uint64 wrap. Counts are checked against
independent path models, with 81/81/71 measured slots. All four images returned
automatically to the loader on COM5. Evidence: it-counts-pi/build-9q43m0w3/
pi-verify-0b960t99 and results/correctness_it_counts_20261002.json.
Reusable build/verify scripts are scripts/pi4/build_it_counts.py and
verify_it_counts.py. The tracked builder's fresh build-gqwkbnr0 also passes
host modeling. Exact preimages/postimages remain in it-branch-fix.

Three original items are complete (#2/#8/#10); #5 stays partial. Next: remaining
reset/snapshot/CFG cases and operating contract #6.
#12 stays explicitly paused. Order remains #5, #6, #3, #4, #1, #9, #7, #11, #12.
The host-only test also reproduced the existing odd Thumb entry instrumentation
assertion (Instrumentation::createAuxiliaryFunctions Start lookup); retain that
negative evidence in it-branch-fix/patch-before-test-revision.patch and earlier
logs for #9. Do not infer it is fixed by the IT patch.
ATFE only; preserve dirty WSL source and unrelated Microsoft/. Older stop and
priority instructions below are historical and superseded by this checkpoint.

## Previous: overall work stopped by user

User requested stopping and resuming in a new session. Do not resume until asked.
WSL inspection reports no running distributions; do not restart it merely to
make the pause checkpoint. No build, test or serial process is currently known
to be running. Pi last returned to the serial loader after the state tests.

Latest verified GitHub implementation/tests: `c2b9b5c` (counter-state tests).
Three original items are complete: #2, #8 and #10. #5 is partial and paused with
the overall work; #12 remains separately paused by user. Resume order is
#5, #6, #3, #4, #1, #9, #7, #11, then #12. ATFE only; no upstream work.

Unfinished #5 work found a confirmed terminal-IT branch defect. Before the fix,
IT-predicated `t2B` was treated as unconditional, reachable loop code was removed
and a counter was emitted inside IT. Original evidence is
`out/correctness/it-probe-1ha37uvl`. A local fix normalizes terminal direct IT
branches to explicit conditional branches, shortens/replaces their IT header,
and rejects unsupported IT control transfers and branches into IT bodies.
The assertions-enabled ATFE build passed; the small normal/reverse/conservative
host probe now retains the loop. Evidence: `out/correctness/it-probe-s6enm8m7`.
This fix is **not fully verified, exported, committed or pushed**. No Pi run or
full lit run has been performed for it. Preserve the dirty live ATFE source.

The three changed files are `bolt/include/bolt/Core/MCPlusBuilder.h`,
`bolt/lib/Target/ARM/ARMMCPlusBuilder.cpp` and `bolt/lib/Core/BinaryFunction.cpp`.
Exact preimages/prepared postimages, hashes and successful build log are saved
under `out/correctness/it-branch-fix/{before,after}`, `source-change.json` and
`build.log`. `out/correctness/apply-it-branch-fix.py` already applied the edits;
do not rerun it against modified live files. Audit and probe scripts are retained.

The unfinished wider fixture has 47 functions: all fifteen data IT masks,
fifteen terminal-branch masks in both widths, and narrow/wide loops. Its driver
is `out/correctness/build-it-counts-pi.py`; new untracked firmware source is
`scripts/pi4/fixtures/it-counts/main.c`. Fresh failed attempts are preserved in
`out/correctness/it-counts-pi`. The driver currently stops while constructing
the narrow-loop expected-count model (`target not modeled`, offset 26). Its
post-link narrow branch plus NOP creates a separate fallthrough block before
the original loop exit; model that block explicitly rather than changing the
backend to fit the test. Earlier global trace labels accidentally became
secondary entries; they were replaced with temporary object-only labels.

Next on explicit resumption: repair the fixture path model, validate every
selected emitted function/IT group and exact counter assignment, add negative
IT tests, run focused lit and Pi checks, then export/review/push the verified
fix. Nested execution and wider reset/snapshot/CFG cases still remain under #5.
The Windows unrelated untracked `Microsoft/` directory is untouched. All scratch
evidence and WIP scripts are local and ignored by Git; retain this workspace.

## Active implementation after review

User explicitly paused item #12 on 2026-10-02 and requested moving to the next
items. #5 is now active. Overlay 0026 fixes full-width carry and restores flags
as well as IRQ state; R0-R3 use a 16-byte frame. 38/38 focused host tests pass,
including independent ARM/Thumb assembly-byte checks. Pi baseline/zero/seeded
images match all 18 outputs and all eight counters satisfy seed plus measured
count. Metadata attributes overflow slots to Thumb IT (index 1, 999999) and
ARM interwork (index 4, 9999). Evidence: counter-carry-pi/pi-verify-sj3t6e_m and
docs/results/correctness_counter_carry_20261002.json. Source preimages are in
instrumentation-audit/source and counter-carry-fix/before.cpp; zero-run snippets
before the fix are preserved in counter-carry-before. The dirty LK source was
not changed; hardware images derive from the existing independent baseline ELF.
Dedicated leaf state cases now pass on Pi: 512 baseline and 512 instrumented
ARM/Thumb cases preserve R0-R12, LR/SP and full CPSR, with all NZCV/Q patterns,
sixteen GE patterns, both IRQ masks and four seeds including uint64 wrap.
Three faulty images fail at expected checks; all five images watchdog-return
to the loader. Six host parser tests pass. Evidence is counter-state-pi/
build-ro6zv3x6/pi-verify-haiq1khs and the tracked counter-state result JSON.
The new build/verify scripts and fixtures are in scripts/pi4; no backend changes
were needed beyond 0026. Next: IT, nested execution and wider exact-count
coverage. Continue #6, #3, #4, #1, #9, #7 and #11 before
returning to #12. This supersedes the older instruction to finish #12 first.
Verified #12 work is pushed as 43c9e16. The unfinished content-state prototype is
saved in out/correctness/atfe-content-stamp-wip.py and .patch; it is untested,
not installed in WSL and not committed. The tracked verifier was restored to
the pushed version. Preserve this checkpoint for #12 resumption.

Latest work: overlay 0025 exports the four unrecorded ARM attribute/kept-code
changes and fixes the kept A32 write/rejection boundary. Source preimages are
preserved in out/correctness/kept-arm-fix/before*, and the original audit diff
remains untouched. All 25 patches reproduce live source exactly in
out/correctness/atfe-clean-replay-0025-final-20261002 (source identity c390d7d0...).
37/37 focused lit, twelve linked-ELF probes, 25/25 profile/replay and 14/14 execution
gate tests pass. The final fresh candidate is out/correctness/full-gate-0025-final;
its Pi check passes on COM5 after a physical power cycle: all 18 workload outputs,
ten repetitions, 33,850 kept/taken PCs and rewritten IT/interwork/memcpy samples
(2,507/30/14). The COM6-missing and COM5 reboot-timeout attempts are retained.
Evidence: docs/results/correctness_atfe_0025_20261002.json and
full-gate-0025-final/pi-verify-58wpzrs6. Do not claim Pi execution of
--use-old-text or privileged ERET from the regular full-image gate. The builder
now rejects text-placement overrides. #12 remains active; next finish content
stamps/clean provenance, counter identity, core ownership and the other gates
before advancing to #5. WSL remains running and the dirty parent is preserved.

The paragraphs below retain historical checkpoints and evidence. Their older
priority/pause instructions are superseded by the active checkpoint above.

Sampling identity fixes and bound-profile Pi evidence are pushed as bf69f15.
The next #12 replay audit applies all 24 ATFE patches in an isolated file tree,
but finds source-content differences in RewriteInstance.h, BinaryContext.cpp,
BinaryFunction.cpp and RewriteInstance.cpp. Live additions include ARM attribute
feature propagation and ignored-code/branch handling for -use-old-text; these
are absent from the GitHub overlays. The source was preserved, and the full diff
is saved in out/correctness/atfe-clean-replay-20261002/unexported-source.diff.
No uncovered source files were found. The verifier's changed-content/preservation
regressions pass (25 profile/replay tests total). Review/export those existing
changes with focused tests, then obtain successful replay and migrate content
stamps; do not overwrite live code or infer clean binary provenance from patch hashes.
See ATFE_OVERLAY_REPLAY.md and results/correctness_atfe_replay_20261002.json.

Latest local work adds sampling build/capture/profile identity and a pure ARM
ELF32 parser in scripts/profile_identity.py. The collector uploads isolated
session copies and checks workload repetitions, buffer/count/saturation and
PMU/core reports. Conversion validates source-function offsets and tool identity;
debug-unbound outputs cannot pass the optimization profile gate. The ARM no-LBR
wrapper and explicit full-image --profile path consume sidecars. Counter profiles
remain unbound; do not claim #12 closed or advance to #5 yet.

Twenty-three profile host tests and fourteen execution-gate tests pass. The independent
lk.elf/lk.bin fixture seals against actual ATFE tool/patch hashes. Real perf2bolt
synthetic diagnostics and the 61-counter/3520-byte conversion pass; synthetic
samples are explicitly unbound. Power cycling recovered the Pi on reassigned COM6.
Fresh bound capture passes with 6,772 samples/two workload repetitions. A duplicate
acc/sink repetition bug was fixed; strict conversion rejects unbounded arch_idle,
while explicit benchmark projection records exclusions. Real scoped conversion,
wrong-payload/ELF negative gates and failure preservation pass. Its full-image
candidate (411/417 emitted, four redirects) passes ten repetitions/all 18 outputs;
33,850 PCs observe rewritten IT/interworking/memcpy (2,506/24/16), far-call zero.
Evidence: out/correctness/sampling-bound and full-gate-bound; tracked summary
docs/results/correctness_sampling_bound_pi_20261002.json. WSL is running; dirty
source and unrelated Microsoft/ were preserved. Next finish counter identity,
clean replay/content stamps and the other #12 gates before advancing to #5.

User authorized proceeding in the updated priority order. #12 complete-result and
truncated-profile fixes pass 10/10 host tests plus real ATFE sample/61-counter
conversion checks. See CORRECTNESS_FIXES.md. The independent memcpy/far_call/
it_cond/interwork results have been added and built in an isolated LK snapshot at
WSL `out/correctness/lk-oracles`; original WSL source/images remain untouched.
Pi baseline and redirected images match on all 18 workloads; the four new values
match independent calculations. PC samples observe rewritten IT/interworking/memcpy;
far-call has no sampled PC. Current evidence is Windows
`out/correctness/validation-fix/` and the tracked
`docs/results/correctness_validation_20261001.json`. WSL was restarted for these checks.

The corrected full-image builder emits 411/417 functions and explicitly redirects
four. Its Pi gate passed 18 workload results across ten repetitions and observed
rewritten IT/interworking/memcpy (2,506/27/16 PCs). Far-call remains unobserved.
Thirteen host gate tests pass. Evidence: out/correctness/full-gate and tracked
docs/results/correctness_full_gate_20261001.json. Complete #12 before advancing:
profile/image binding, graph consistency, other execution gates, broader input/pass
coverage and clean overlay replay. User explicitly requested #12 completion first.
The reviewed bbae817 full-image script restored originals without redirects; its
replacement has explicit redirects and scoped hardware verification. Upstream
work remains stopped; preserve dirty WSL checkouts and unrelated Microsoft/ folder.

## Latest checkpoint: GitHub bbae817 re-evaluation

The Windows checkout was fast-forwarded from ff7d544 to bbae817. The current
review is CORRECTNESS_REVIEW_BBAE817.md, and the original twelve-item status/TODO
files have been updated. This task reviewed correctness; it did not implement
new backend fixes. Do not resume from the older priority order below.

Fresh host validation: 36/36 BOLT ARM + JITLink AArch32 tests pass. Overlay 0024
reverse-checks against the live WSL source. The dirty WSL parent still reports
eab1e71 and ATFE base bcc088849; both were preserved. No broad WSL sync/reset was
run. Review source snapshots, isolated ELF output and negative-probe logs are
saved in Windows out/correctness/review-bbae817; compact results are tracked in
docs/results/correctness_bbae817_review.json. No new Pi run was performed.

First work on resumption: #12 execution proof and complete independent results.
Full-image postprocessing reproduces original text, entry and pointer-bearing
sections without redirecting execution; 403/411 emitted symbols is not runtime
coverage. The Pi pass gate accepts a one-workload baseline, and truncated counter
dumps still become [7, 0]. Then follow CORRECTNESS_TODO.md's updated order.

WSL access was obtained through scoped approvals for inspection, tests and
isolated repros. `wsl --shutdown` completed successfully, and `wsl --list --running`
confirmed no running distributions at the end of this review. Restart with `wsl -d Ubuntu --cd
/home/user/bolt-aarch32` when work is resumed.

## Earlier implementation checkpoint (before external work)

The user requested a graceful pause. Do not resume work until asked. Scope is
ATFE only; do not work on upstream LLVM. Hardware has priority over QEMU.

Windows checkout: `C:\Users\User\CURSOR\CodexProjects\BOLT_AARCH32` on `main`.
WSL checkout: Ubuntu `/home/user/bolt-aarch32`; ATFE source at
`third_party/llvm-project-atfe`, build at `build-atfe`. The WSL parent and ATFE
checkouts contain preexisting dirty overlay changes: preserve them and do not
reset or stash. Windows has an unrelated untracked `Microsoft/` directory:
leave it untouched. WSL can be restarted with `wsl -d Ubuntu --cd
/home/user/bolt-aarch32` after the deliberate `wsl --shutdown` at this pause.

Verified changes: overlay 0020 fixes CBZ/CBNZ long branches without changing
NZCV and was pushed as `10afe0c`. Overlay 0021 handles odd Thumb `e_entry`,
moved Thumb function symbols, and even `$t` mapping symbols. Its focused
regression checks entry, moved `_start`/`probe`/`probe_nz`, and `$t`; the 32-test
BOLT ARM + JITLink AArch32 run passed. Full LK emission passed. The rebuilt
Pi image redirected `app_start_by_name` and `strtoul`; both original and
rewritten images booted and ran seven benchmark commands with matching dumps.
The Pi LK image uses an ARM entry, so this does not execute the synthetic odd
Thumb entry. `docs/CORRECTNESS_FIXES.md` has details and coverage limits.

Evidence is in ignored `out/correctness/` and WSL
`/home/user/bolt-aarch32/out/correctness/`: Pi logs/JSON, the fixture ELF and
function map, and the full LK output. The scratch script
`out/correctness/check-review-delivery.py` still expects the old Thumb-entry
assertion and must be updated before using it again. Overlay 0021 was exported
from the live tree and passed `git apply --reverse --check` there.

Next: finish item #9 for aliases, skipped functions, secondary symbols,
code/data transitions and pointer targets. Then #12 artifact/profile integrity,
#1 relocation matrix, and #3 CFG invariants. Item #4 still needs conditional
return/PC-load work and dedicated Pi execution of both flag-sensitive paths.
See `docs/CORRECTNESS_STATUS.md` and `docs/CORRECTNESS_TODO.md` for all 12 items.

Before further WSL shutdowns, allow builds/tests to finish, save patches and
results to durable files, and run `wsl --shutdown` from Windows. Confirm no
distribution remains in `wsl --list --running`.
