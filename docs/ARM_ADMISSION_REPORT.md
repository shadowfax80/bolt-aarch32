# AArch32 admission diagnostics — R11, overlay 0054

`llvm-bolt INPUT -o /dev/null --arm-admission-report=REPORT.json` collects
recoverable local disassembly/CFG admission rejections in one run. It stops
before optimization, instrumentation, emission and certification. Normal BOLT
continues to reject these functions fatally unless the caller explicitly skips
them. Global ISA/ABI/fixed-load guards and unknown/internal errors stay fatal.

The option requires ARM input, `/dev/null` output and no profile,
instrumentation, aggregation or analysis mode. The report cannot replace the
input. Failed scans/publication preserve an existing report; successful reports
are published by sibling temporary file and rename. Function-bound symbolizers
are cleared on early disassembly exits so a rejected function cannot leave a
dangling symbolizer for the next one. Diagnostic CFG collection is sequential.

Schema 1 binds the report to the input SHA-256 and records normalized function
address, primary name, size, ISA and status. `admitted` means local decoding/CFG
admission, `rejected` carries stage/reason, and `not-analyzed` covers excluded
or otherwise unprocessed bodies. Aliases are represented by one primary body.
`complete: true` means this diagnostic scan completed; `execution_verified`
is always false. Neither admission nor completeness proves safe transformation,
reference repair, instrumentation, pass combinations or execution.

`scripts/lk_coverage_report.py` validates the schema, input identity, distinct
names/addresses and totals before using rejected names as explicit skips in a
second, normal fatal BOLT run. Coverage comes from that run's actual function
map. `--legacy-scan` explicitly selects the older multi-run scan; failure of
the new scan does not silently fall back.

## Corrective status after the Astra review

R11 is **Partial, unclaimed**. A truncated ITT/ITE leaves mutable predicate
state in the shared Thumb decoder and falsely rejects the next independent
`bx lr` for fallthrough. Earlier successful receipts remain valid within their
tested scope; complete diagnostic JSON is not proof of order-independent
classification. Fix independent decoder-state isolation and add both-mode
rejection-followed-by-valid-function regressions. See the
[reconciled review and preserved probe evidence](CORRECTNESS_REVIEW_ASTRA_0057.md).

## Historical verification of overlay 0054, 2026-10-04

Both Release toolchains were rebuilt from the same live source with assertions
ON/OFF. The OFF configuration uses its own BOLT and runtime; its configured
fixture compiler/linker are shared with the ON build.

| Check | Assertions ON | Assertions OFF |
|---|---|---|
| New admission lit regression | 41 checks; eight local exclusions in each scan | Same |
| ARM + JITLink AArch32 lit | 61 passed | 60 passed; `ELF_data_alignment.s` requires assertions |
| BOLT CoreTests | 58 passed; 31 target-inapplicable skips | Same |
| Full-LK diagnostic | 12 rejected primary bodies, 403 admitted, 2 not analyzed; one run | Same |
| Strict emission coverage | 399/417 functions; 124166/126834 code bytes (97.9%) | Same |
| Pi, approved input, watchdog | 18/18 independent results; 10 repetitions; both selected redirects sampled | Same |

The host Python suite ran 145 tests successfully with four Linux process-test
skips on Windows. The new parser tests cover malformed reports/rows, unknown
statuses, false certificates, wrong input, duplicate identities and totals.
Lit covers ARM/Thumb PC reads/writes, fallthrough, truncated/entered IT groups,
aliases, deterministic layouts, fatal default, output/map preservation,
explicit strict skips, incompatible modes, global guards and failed publication.

The 0053 scanner needed 12 rounds. The 0054 scanner needs one, with unchanged
coverage and admission policy. The 12 rejected primary bodies include an alias
representative that is not an extra symbol row; the coverage table has 11
rejected symbol rows. No body is newly admitted by R11. Full-LK instrumentation
still fails the `arch_spin_trylock` reservation guard (R15).

All 54 overlays replay exactly, with no uncovered or mismatched files. Source
identity: `484c5825e2f75d120d71078f8c2a2728a73c77fa16ae103bbacd8fb321b3d383`.
This verifies source contents against the pinned base, not a clean build.

Both Pi candidates emit 400 function-map bodies and redirect exactly
`bolt_bench_interwork` and `bolt_bench_memcpy`. The ON run captured 33849 PCs
(27 interwork, 15 memcpy); OFF captured 33848 (10, 11). The approved input is
`424606a869c34b5be5f3c97f66a9cec8ea16844ac788c14c77839edcfef2459b`.
Hardware claims cover these two selected bodies and the 18 workload results,
not execution of all emitted functions, IRQ/state preservation or general
backend correctness. Build and verification receipts bind the pre-publication
repository revision `0b2b320`, patch hashes, script hashes, tools and artifacts.

## No-FPU checker caveat

The approved input passes `scripts/check-no-fpu.sh` with zero FP/NEON
instructions. Applying that input-oriented checker directly to the candidate
produces false positives because output ELF mapping symbols do not describe
all original/restored and emitted ISA transitions. Restored Thumb code is
decoded as ARM. Even after excluding restored code in a diagnostic copy,
four matches remain: A32 `bxeq lr` at `0x800f3a08` and `0x800f3b04`, `bx lr`
at `0x800f3b68`, and a generated A32 veneer `bx r12` at `0x800f5d60` are decoded
as Thumb SIMD. Their raw words were independently decoded with ARM llvm-mc.
The uploaded candidates were not changed by this investigation.

The automatic candidate scan is therefore not a full no-FPU certificate.
ISA-aware output metadata/scanning, including veneers and restored code,
remains under work item 14. R11 does not change emitted instruction generation.

## Durable evidence

- [Summary](results/r11_completion_20261004.json), [overlay replay](results/r11_overlay_replay_20261004.json).
- [ON coverage](results/lk_coverage_20261004_r11.json), [OFF coverage](results/lk_coverage_20261004_r11_off.json).
- [ON diagnostic](results/r11_admission_on_20261004.json), [OFF diagnostic](results/r11_admission_off_20261004.json).
- [ON checks](results/r11_admission_checks_on_20261004.json), [OFF checks](results/r11_admission_checks_off_20261004.json).
- [ON Pi certificate](results/r11_pi_on_certified_20261004.json), [OFF Pi certificate](results/r11_pi_off_certified_20261004.json).
- [ON build manifest](results/r11_pi_on_build_manifest_20261004.json), [OFF build manifest](results/r11_pi_off_build_manifest_20261004.json).

Raw build/lit/Core/Pi logs and immutable uploaded copies remain under `out/`.
The live tree and earlier evidence/preimages are preserved. Current work order is in HANDOFF.md;
new image/configuration oracle contracts require user review before certification.

## Historical pickup state at e5ef4f3

Last observed at the R11 milestone: the live-tree lock was released. WSL Ubuntu
was running, with the root repo synced to the published milestone and both
toolchains built through 0054. The dirty ATFE tree is intentional and matches
the full overlay series; do not reset or reapply it. The Windows Codex/Claude
checkouts and local Claude project memory have the same handoff state.

At that milestone the Pi was restored to the approved baseline LK image.
Baseline binary SHA-256:
`ee9982ba422fa5e40854f0c21c298b20c4be02eb349413eefe7fdcf53bedd612`.
The console responded on COM5 at 3000000 baud. Sampling was stopped, the watchdog
was off, and the serial port was closed. Restore log: `out/r11-pi-pickup.log`.
Use the repo venv `out/correctness/pi-venv/Scripts/python.exe` for Windows serial
scripts and `--reboot` with the hot-loaded fast loader for future uploads.

These observations predate later Claude work. Read the current remote handoff,
reserve resources and verify current state before use.
