# ATFE correctness checkpoint - 2026-10-01

## Active implementation after review

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

Next: enforce full-image execution evidence in the gate, then image/profile identity,
graph consistency and clean overlay replay. Broaden workload inputs/pass combinations.
The reviewed full-image script still restores originals without redirects. Upstream
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
