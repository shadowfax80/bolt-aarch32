# ATFE correctness checkpoint — 2026-10-01

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
