# Twelve-item correctness work

Last updated: 2026-10-01. Verification details: [CORRECTNESS_FIXES.md](CORRECTNESS_FIXES.md).

Fresh source review: [CORRECTNESS_REVIEW.md](CORRECTNESS_REVIEW.md).
Actionable subitems and closure criteria: [CORRECTNESS_TODO.md](CORRECTNESS_TODO.md).

Active scope: ATFE only, as requested. Upstream work is stopped and excluded
from completion criteria. Three items are complete within this scope (2, 8, 10).

| # | Work | Status | Remaining work |
|---|---|---|---|
| 1 | Relocation matrix and literal loads | Partial | Literal and BLX link-bit fixes verified; THM_JUMP19, H-bit/alignment cases, and remaining relocation paths open |
| 2 | EHABI exidx/extab | Complete via rejection | Unsupported unwind information is rejected; full unwind rewriting remains unsupported |
| 3 | Pseudo/CFG invariants | Open | Debug-only pseudo recovery confirmed; fix mutation causes and verify assertions-on/off parity |
| 4 | Control flow and return semantics | Partial | CBZ/CBNZ flag clobber confirmed in emitted bytes; conditional returns and wider load-to-PC forms remain |
| 5 | Instrumentation correctness | Partial validation | Low-word-only counter update confirmed; carry, registers/flags/IT and exact edge counts remain |
| 6 | Instrumentation scope | Open | Enforce privilege/single-core/IRQ-FIQ contract and reject placeholder indirect-call profiling |
| 7 | ISA/profile/endianness | Pending | Enforce the supported target feature boundary |
| 8 | FK_Data_8 / ABS32 mismatch | Complete | ATFE host and Pi checks passed; symbolic 64-bit relocations rejected; resolved values and map width corrected |
| 9 | Entry points and symbols | Open | Thumb e_entry assertion, odd mapping symbol and missing moved function symbol reproduced; preserve aliases and skipped functions |
| 10 | Deterministic stubs | Complete | Stable visitation and layout, mixed-stub alignment fixed; repeated links and Pi checks passed |
| 11 | Rewrite coverage | Open | Unsupported jump tables/GOT/TLS/veneers; explicit rejection and selected/emitted/executed coverage |
| 12 | Verification and artifact integrity | Partial | Truncated dump silently becomes zero counter; enforce image/profile identity, execution proof, independent outputs and clean replay |

Hardware takes priority for execution verification; QEMU is a supplemental
debugging tool. Pi checks use serial reboot where possible. A halted shell may
still require a physical power cycle. Host tests and hardware tests are recorded
separately; passing a single workload does not close the entire correctness audit.

Review validation: 30/30 focused ARM tests and failure-propagation tests passed.
Small host repros confirmed gaps above; no new Pi run was performed in this review.
Next order: #4 flags, #9 entry, #12 integrity, #1 relocations, #3 CFG, then
#5/#6 instrumentation and #7/#11 admission/coverage. #2/#8/#10 remain regression gates.

The local monitor is started with `python3 scripts/correctness-monitor.py`.
It refreshes `out/correctness/progress-monitor.json` every 30 seconds. Its log
records changes and heartbeats; it watches recorded status and does not execute
corrective work or automatically send chat messages.
