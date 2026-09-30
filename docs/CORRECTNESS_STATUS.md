# Twelve-item correctness work

Last updated: 2026-10-01. Verification details: [CORRECTNESS_FIXES.md](CORRECTNESS_FIXES.md).

Active scope: ATFE only, as requested. Upstream work is stopped and excluded
from completion criteria. Two items are complete within this scope (2 and 8).

| # | Work | Status | Remaining work |
|---|---|---|---|
| 1 | Relocation matrix and literal loads | Partial | Literal and BLX link-bit fixes verified; THM_JUMP19, H-bit/alignment cases, and remaining relocation paths open |
| 2 | EHABI exidx/extab | Complete via rejection | Unsupported unwind information is rejected; full unwind rewriting remains unsupported |
| 3 | Pseudo/CFG invariants | Investigating | Reproduce failures and enforce safe behavior with assertions disabled |
| 4 | POP/LDM terminators | Partial | Unconditional POP/updated-LDM terminators fixed and Pi checked; wider load-to-PC forms and conditional-return CFG remain open |
| 5 | Instrumentation correctness | Partial validation | Stair edge collection passed on Pi; register/flags/IT and other edge cases remain |
| 6 | Instrumentation scope | Pending | Enforce privileged single-core boundary and reject unsupported cases |
| 7 | ISA/profile/endianness | Pending | Enforce the supported target feature boundary |
| 8 | FK_Data_8 / ABS32 mismatch | Complete | ATFE host and Pi checks passed; symbolic 64-bit relocations rejected; resolved values and map width corrected |
| 9 | Mapping symbols and dropped functions | Pending | Audit odd Thumb mapping symbols and preservation of skipped functions |
| 10 | Deterministic stubs | Pending | Repeat-link comparison and deterministic allocation |
| 11 | Rewrite coverage | Pending | Unsupported jump tables/GOT/TLS/veneers and explicit rejection policy |
| 12 | Verification failures and coverage | Partial | Failure propagation fixed and tested; broader regression/hardware coverage remains |

Hardware takes priority for execution verification; QEMU is a supplemental
debugging tool. Pi checks use serial reboot where possible. A halted shell may
still require a physical power cycle. Host tests and hardware tests are recorded
separately; passing a single workload does not close the entire correctness audit.

The local monitor is started with `python3 scripts/correctness-monitor.py`.
It refreshes `out/correctness/progress-monitor.json` every 30 seconds. Its log
records changes and heartbeats; it watches recorded status and does not execute
corrective work or automatically send chat messages.
