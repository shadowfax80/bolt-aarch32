# ATFE correctness checkpoint - 2026-10-02

## Active implementation after review

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

The paragraphs below retain earlier checkpoints and evidence.

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
