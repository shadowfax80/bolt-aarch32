# Twelve-item correctness work

Last updated: 2026-10-01. Verification details: [CORRECTNESS_FIXES.md](CORRECTNESS_FIXES.md).

| # | Work | Status | Remaining work |
|---|---|---|---|
| 1 | Relocation matrix and literal loads | Partial | THM_JUMP19 and remaining relocation paths; upstream build; dedicated A32 hardware cases |
| 2 | EHABI exidx/extab | Partial | Rejection boundary tested; upstream build; full unwind rewriting unsupported |
| 3 | Pseudo/CFG invariants | Investigating | Reproduce failures and enforce safe behavior with assertions disabled |
| 4 | POP/LDM terminators | Investigating | CFG regression and hardware checks before enabling dynamic terminators |
| 5 | Instrumentation correctness | Partial validation | Stair edge collection passed on Pi; register/flags/IT and other edge cases remain |
| 6 | Instrumentation scope | Pending | Enforce privileged single-core boundary and reject unsupported cases |
| 7 | ISA/profile/endianness | Pending | Enforce the supported target feature boundary |
| 8 | FK_Data_8 / ABS32 mismatch | Fix implemented | ATFE host and Pi checks passed; upstream build pending |
| 9 | Mapping symbols and dropped functions | Pending | Audit odd Thumb mapping symbols and preservation of skipped functions |
| 10 | Deterministic stubs | Pending | Repeat-link comparison and deterministic allocation |
| 11 | Rewrite coverage | Pending | Unsupported jump tables/GOT/TLS/veneers and explicit rejection policy |
| 12 | Verification failures and coverage | Partial | Failure propagation fixed and tested; broader regression/hardware coverage remains |

Hardware takes priority for execution verification; QEMU is a supplemental
debugging tool. Pi checks use serial reboot where possible. A halted shell may
still require a physical power cycle. Host tests and hardware tests are recorded
separately; passing a single workload does not close the entire correctness audit.
