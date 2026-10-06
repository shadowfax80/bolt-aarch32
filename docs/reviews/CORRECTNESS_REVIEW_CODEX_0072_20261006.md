# Codex correctness review at 0072 — 2026-10-06

Reviewed implementation baseline `d6aa4bb3e23c0afc70ac905a4bd5af9f42fe065c`,
overlays 0001–0072, together with lk-perf baseline
`a547f94a5a228b925f1182ee309f1ebfbb84eca5` (through K15).
CR1 is the review/documentation item. Implementation follow-ups belong to the
single [HANDOFF queue](../HANDOFF.md#claims-consolidated-todo), not this dated
review. No new backend overlay or hardware certification was produced.

## Assessment

No new wrong-code result was found in the exercised backend cases. The
current tools reproduce the known safe rejections and the fixes in
0070–0072 in both assertion modes. This is a bounded result: 99.5% emission
coverage, clean-build parity and a passing narrow redirect gate do not prove
all instructions, all pass combinations or all emitted functions correct.

The new concrete defects are in the evidence pipeline. The lk-perf collector
can publish a hash-bound profile despite an incomplete dump, and the suite
measurement tool can publish an apparently successful comparison despite
missing passes, metrics and result checks. Artifact binding and measurement
completeness are separate obligations. These require P1 follow-ups before
using the helpers as automated correctness/performance gates.

## Review and verification scope

Source inspection covered ARM instruction admission (PC reads/writes,
exception returns, exclusives and IT), table/base liveness, ISA-aware
relocations and linker targets, branch widening and r12 veneers, mapping
symbols, instrumentation contracts, full-image entry/redirection and retained
bytes, profile identity, capture/measurement parsers and clean provenance.
Existing 0069/Astra findings and the published G1/item-14/B1/B2 receipts were
reconciled against the later fixes. The paired lk-perf review covers the
capture producers and their analysis contracts.

| Check performed for this review | Result and limit |
|---|---|
| BOLT host unittest discovery | 167 tests, OK, 12 explicitly skipped; [log](../results/cr1_review_20261006/bolt-host-tests.txt) |
| `edge_probe.py`, current ON and OFF tools | Each: 26 shapes × 7 options = 182 outcomes, 158 matching results, 24 clean rejections, no crash/hang/wrong output |
| 0070 mixed-ISA `ldr pc` table checker | 6 combinations per assertion mode pass; case words even, Thumb function literal retains bit 0 |
| 0071 Thumb short branch checker | Both modes pass: widened conditional branch, CBZ + B.W, no unnecessary r12 stub; original/rewrite exit 4 |
| 0072 mapping-symbol checker | Both modes pass: kept original decode, split/ICF Thumb symbols, ARM/Thumb stubs, linked runtime marks |
| Tool/series identity | Four used tools per mode and all 72 overlay digests match the published item-14 receipt |
| Joint contract probes | Nine observations reproduced with real parsers; only serial transport replaced; [script/results](../results/cr1_review_20261006/README.md) |
| lk-perf host discovery/unwind checks | 56 tests OK, 1 optional consumer skipped; 7 separate unwind checks PASS |
| Actual Perfetto optional consumer | **Fails its stale K3 expectation:** actual `caller;no_cfi`, expected `no_cfi`; tracked in lk-perf K25 |

The edge harness checks original/rewrite hashes under qemu-user. Its options
cover default, reversed blocks, ICF/random function order, distant function
padding, splitting, splitting with a 1.1 MB filler, and instrumentation.
The 24 rejections are table bases read in case blocks, conditional-return
instrumentation, unprovable terminal noreturn calls, and exclusive-memory
instrumentation. They are expected safeguards, not failures to hide.

No full ARM lit rerun, clean rebuild, full coverage regeneration or Pi/A55
probe occurred here. Those operations would require ownership of shared
trees or the Pi; this review used read-only tools and independent outputs.
The existing 61/61 ON/OFF and four-build item-14 receipts remain historical
evidence. Current [coverage](../LK_COVERAGE.md) remains 401/417 functions and
126164/126834 code bytes; no emission changed.

## New follow-ups and closure criteria

These are findings at this baseline, not a second live queue.

| ID | Priority | Finding | Required closure |
|---|---|---|---|
| R31 | P1 | lk-perf collector accepts incomplete/inconsistent sessions | Fail closed on structural/session errors, mode/period mismatch, duplicate/reordered records and invalid per-core counts; bind parser dependency identity and stable ELF; preserve explicit quantified transfer loss; offline regressions plus a complete valid current-format capture |
| R32 | P1 | Suite measurement silently accepts missing/duplicate evidence | Declare expected command/metric/result sets and exact passes per image/round; validate one complete result per expected invocation; reject duplicates, omissions and asymmetric comparisons before CSV/summary publication; bind uploaded image snapshots/hashes; offline regression reproducing the false -50% comparison |
| R33 | P2 | Clean-build helper can reuse stale source/cache and conceal lit failure | Bind resume markers to pin/overlay/config/source identity, reject mismatches before build, propagate lit failures, and require an owned output directory before recursive cleanup; test safe interrupted/resumed and stale-output cases in fresh directories |
| R34 | P2 | B1/B2 raw evidence is not portable from GitHub | Archive hash-checked raw capture/measurement logs and required payload/ELF/profile inputs, or document a reproducible retention location accessible to the next worker; re-audit complete command/result frames without retroactively sealing old captures |

### R31: image matching does not imply a complete capture

[`pi4_lkperf_profile.py`](../../scripts/pi4/pi4_lkperf_profile.py) obtains
`session['problems']` but only stores them in the published manifest. It
does not reject them. A header and checksum-valid sample with no `DUMPEND`
pass the ELF/image checks; `sent` becomes zero and the final manifest says
`verified_binding=True`. The downstream `profile_identity.check_capture`
accepts it, because its checks concern hashes and function identities.

The reproduction seals a real assembled ARM ELF and matching binary with
the required 512 KiB sample buffer, uses real current lk-perf checksums and
parsers, and replaces only the serial subprocess. The collector returns 0,
publishes one sample, records the missing-footer problem, and prints
`-1 of 0 records lost`. Thus this is not an unverified mock of the binding
logic. Other related gaps include permissive duplicate/sequence handling,
unverified requested versus actual timer periods, mixed sources/configuration,
and an external parser whose digest is absent from collector provenance.
Use the strict host capture contract as a common component; do not reject
all quantified transport loss merely to repair structural validation.

### R32: omissions can manufacture a performance gain

[`pi4_suite_measure.py`](../../scripts/pi4/pi4_suite_measure.py) overwrites
duplicate metric names and collects result values in global sets. It checks
that observed values agree, but not that every expected invocation has a
value, metric or complete pass. Its totals sum whatever metrics each image
has. A probe requests two passes for each of two images, supplies one pass
each, omits all result checks, and omits metric `y` from the candidate. It
returns 0, reports identical results with **0 app results checked**, and a
**-50% total**. CSV publication happens before result disagreement checking.

The existing stricter measurement framing in
[`measurement_records.py`](../../scripts/pi4/measurement_records.py) is a
useful basis for consolidation. The new suite contract must also cover
profiler commands and stat totals; simply sharing regexes is insufficient.

### R33: standalone helper success is weaker than item-14 success

[`clean-build-atfe.sh`](../../scripts/clean-build-atfe.sh) skips source
construction whenever `source-tree.txt` exists; it does not compare that
marker with the current pin/overlay set. Existing `build.ninja` similarly
skips configuration. Its ARM lit command ends with `|| true`. An old output
directory can therefore rebuild an earlier source and a failed lit command
can still leave the helper successful. It also removes `<out>/src` when the
marker is absent without verifying ownership of that existing directory.
These are static workflow findings, not destructive experiments.

The published item-14 PASS remains valid within its recorded scope:
[`build_provenance.py`](../../scripts/build_provenance.py) independently
compares source/configuration and reruns lit with exit status checked. R33
hardens future helper use; it does not erase that stronger receipt.

### R34 and retrospective B1/B2 limits

The [archive audit](../results/cr1_review_20261006/archive-audit.json) finds
uniform existing whole-suite CSVs: 288 rows, 24 passes, 12 metrics per pass,
six passes per image, no duplicate metric rows, in both B1 and B2. Their stair
CSVs each contain six runs per variant and a single `acc` value. The four
published lk-perf manifests have no recorded session problems. Thus the new
probes do **not** demonstrate that the published B1/B2 gains were caused by
missing metrics or missing footers.

However, the capture manifests point to raw logs in Claude's local temporary
workspace, not tracked paths. Those logs are currently present locally;
their future retention is not assured. CSVs cannot prove every command's
result framing, and a permissive collector's empty `problems` list is not an
independent strict-record audit. Preserve the historical measurements and
their caveats, and close R34/R31/R32 before stronger reproducibility claims.

## Backend verification work retained

Do not duplicate the existing matrix items as new defect IDs. Their current
closure criteria still matter:

- **8 / CFG:** IT-final mutation, conditional returns/tails, instruction
  flag/state preservation, inter-function/interior-entry routes.
- **7 / relocation:** ARM/Thumb literals, anonymous/addend targets,
  retained external routes and cross-fragment B.W/BL beyond ±16 MB.
- **11 / entries:** aliases, interior/data references, split and ICF symbols,
  kept original text and redirects; keep 0072 checks in the matrix.
- **12 / tables:** case-boundary/liveness proofs, inline data, rotated bases,
  split/ICF/instrumentation combinations and declared AAPCS assumptions.
- **13 / passes:** actual combined transformations in both modes; distant
  hot/cold fragments, r12 live/dead cases and deterministic mapping symbols.
- **9 / IRQ/reset:** active IRQ reentrancy and reset boundaries remain
  outside the bounded SMP counter/execution evidence.
- **10 / sampling/PMU:** source/core/loss accounting and ownership; R31
  depends on lk-perf K18/K19/K20 rather than treating hash binding as proof.

Declared exclusions remain static non-PIC little-endian images with complete
relocations, no FPU/NEON, no rewritten exception unwinding, and privileged
instrumentation without FIQ. AAPCS table-base assumptions and odd words
pointing into Thumb code remain material caveats. No new A55 execution or
timing claim follows from A72 or QEMU results. Default IRQ sampling still
misses masked execution; lk-perf's opt-in pseudo-NMI mitigates masked thread
code, but IRQ handlers and other unsupported contexts remain blind.

## Cross-project pickup

The paired [lk-perf review](https://github.com/shadowfax80/lk-perf/blob/main/docs/reviews/CORRECTNESS_REVIEW_CODEX_K15_20261006.md)
records output protection, scheduler loss/boundary accounting, mixed-profile
weighting, lifecycle, PMU sharing and remaining measurement quality work.
R31 should consume the resulting shared strict capture contract rather than
create a third parser. Preserve both repositories' historical milestones;
claim open follow-ups from their own handoffs and reserve shared resources
only when implementation or hardware work actually needs them.
