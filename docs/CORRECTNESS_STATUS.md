# Twelve-item correctness work

Last updated: 2026-10-01. Verification details: [CORRECTNESS_FIXES.md](CORRECTNESS_FIXES.md).

Fresh source review at `bbae817`: [CORRECTNESS_REVIEW_BBAE817.md](CORRECTNESS_REVIEW_BBAE817.md).
Actionable subitems and closure criteria: [CORRECTNESS_TODO.md](CORRECTNESS_TODO.md).

Active scope: ATFE only, as requested. Upstream work is stopped and excluded
from completion criteria. Three items are complete within this scope (2, 8, 10).

| # | Work | Status | Remaining work |
|---|---|---|---|
| 1 | Relocation matrix and literal loads | Partial | THM_JUMP19 and splitting now supported; complete signed range, alignment, BLX H-bit, addend and unsupported-path coverage |
| 2 | EHABI exidx/extab | Complete via rejection | Unsupported unwind information is rejected; full unwind rewriting remains unsupported |
| 3 | Pseudo/CFG invariants | Partial | ARM B pseudo root cause fixed; debug-only recovery remains and assertions-on/off parity is unverified |
| 4 | Control flow and return semantics | Partial | CBZ flags, ARM Bcc and tail calls improved; conditional returns, wider PC writes, live flags, IT and inlining boundaries remain |
| 5 | Instrumentation correctness | Partial validation | Low-word-only counter update confirmed; carry, registers/flags/IT and exact edge counts remain |
| 6 | Instrumentation scope | Open | Enforce privilege/single-core/IRQ-FIQ contract and reject placeholder indirect-call profiling |
| 7 | ISA/profile/endianness | Pending | Enforce the supported target feature boundary |
| 8 | FK_Data_8 / ABS32 mismatch | Complete | ATFE host and Pi checks passed; symbolic 64-bit relocations rejected; resolved values and map width corrected |
| 9 | Entry points and symbols | Partial | Entry, split symbols, mapping and mixed-ISA marking improved; aliases, skipped functions, secondary entries, pointer targets and redirects remain |
| 10 | Deterministic stubs | Complete | Stable visitation and layout, mixed-stub alignment fixed; repeated links and Pi checks passed |
| 11 | Rewrite coverage | Partial | TBB/TBH and generic passes implemented; full-image emitted coverage is not execution proof; table/pass boundaries and excluded ELF constructs remain |
| 12 | Verification and artifact integrity | Partial | Bound sampling/execution pass on Pi; isolated replay exposes four unexported source changes; counter binding, core ownership, other gates, broader inputs and content stamps remain |

Hardware takes priority for execution verification; QEMU is a supplemental
debugging tool. Pi checks use serial reboot where possible. A halted shell may
still require a physical power cycle. Host tests and hardware tests are recorded
separately; passing a single workload does not close the entire correctness audit.

Review validation at bbae817: 36/36 focused ARM tests passed. Isolated emission
confirmed full-image postprocessing restores original code/entry; a partial-result
Pi gate and truncated-counter converter incorrectly accept their negative fixtures.
The negative probes describe the reviewed bbae817 baseline. Local validation fixes now
pass 10 host tests plus real ATFE sample conversion and 61-counter metadata conversion.
Independent benchmark changes built in an isolated LK snapshot. Pi baseline and
four-function redirected ATFE image match on all 18 workloads; the four new values
match independent calculations. Checksum-verified PC samples observe rewritten IT,
interworking and memcpy (not the brief far-call). This is scoped execution proof,
not full-image coverage. Manifest: results/correctness_validation_20261001.json.
Existing hardware reports retain their documented scope.
Next order: #12 execution/results/profiles, #5/#6 instrumentation, #3/#4 CFG/control
flow, #1 relocations, #9 symbols and #7/#11 admission/coverage. #2/#8/#10 remain gates.

The local monitor is started with `python3 scripts/correctness-monitor.py`.
It refreshes `out/correctness/progress-monitor.json` every 30 seconds. Its log
records changes and heartbeats; it watches recorded status and does not execute
corrective work or automatically send chat messages.
