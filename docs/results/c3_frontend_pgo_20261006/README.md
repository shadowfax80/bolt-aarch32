# C3: fresh frontend-PGO verification on 0073

The FE verification gap is closed for **FE-PGO + module ThinLTO + sampled
or instrumented BOLT** on the declared stair kernel. This fresh cycle began
2026-10-06 and finished 2026-10-07. It uses new frontend feedback, not an old
FE or IR/CSPGO profile. No backend or LK source change was needed.

Use the [frontend recipe](../../verification/FRONTEND_PGO_PIPELINE.md) and
[four-route matrix](../../verification/CSPGO_PIPELINE.md#two-compiler-paths-two-bolt-profile-modes).
The default remains IR-PGO/ThinLTO/CSPGO. Verification covers the low-level
explicit FE variants in an isolated checkout; the legacy `--frontend`
launcher's shared synchronization and fixed output locations were not rerun.

## Input and build identity

- Repository claim revision: `6e0a5d3`; LLVM pin
  `bcc08884995ff3cbee70749524621803b9bd258a` plus overlays 0001–0073.
- [Exact replay](replay.json) source identity:
  `8dcc651c86e7f6370035c07efce6eaa064fef18ea0a5aa12410af01d6cf5476d`.
- Fresh LK source pin `79d2f56096fa32365846ceaba8b4a9d1c6b75cf0`, plus
  repository LK overlays, `rpi4-bolt-test`, `STAIR_M=8`, Thumb workload,
  `-mfpu=none`. Hardware: Pi 4B A72, AArch32 Non-secure SVC.
- [Identity](identity.json) binds 4,412 LK source files, 21 compiler artifacts,
  nine tools, both profiling runtimes, frontend-use module configuration and
  actual ThinLTO module bitcode. [Final identity](identity-final.json) equals
  the initial identity: sources/tools/compiler outputs did not change.
- Compiler profiling/ThinLTO cover `app/bolt_bench`; BOLT selects only
  `bolt_bench_stair_kernel`. This fresh image differs from C1/R35. Comparisons
  within C3 hold source/configuration fixed; C1/R35 figures are separate runs,
  not a controlled FE-versus-CSPGO comparison.

## Verification

| Check | Result |
|---|---|
| Fresh FE feedback | Pi raw profile **12,480 bytes**, **93 Front-end function records**, maximum count **409,600**; [collection](frontend-collection.json), [kind validation](frontend-profile.json) |
| FE use and ThinLTO | Explicit `pgo` and `pgo_thinlto` variants; `-fprofile-instr-use` recorded, final module object is LLVM IR bitcode |
| Exact BOLT feedback | **2,561 counters**, 1,600 entries and exits, all internal nodes conserve flow; accepted binding/CRC/layout/command-frame/checksum audit; [flow](counter-flow.json) |
| Sampled BOLT feedback | **26,835 samples kept/taken**, 2,959 distinct PCs, period 20,000, 32 workload repetitions; capture bound to the same final FE ELF |
| Both assertion modes | Instrumented and both optimized load binaries byte-identical; ELFs identical after excluding command-line `.note.bolt_info` only; [parity](assertion-parity.log) |
| No FPU/NEON | Every compiler image, training image and both optimized outputs pass; both BOLT assertion modes checked |
| Output consistency | **Seven images agree on all 18 workload results**: baseline, FE training, FE use, FE+ThinLTO, BOLT training, counter BOLT and sampled BOLT; [comparison](result-consistency.json) |
| Rewritten execution | Positive PC-watch hits inside all three rewritten kernel bodies; see below and [receipt](rewritten-pc.json) |
| Measurement binding | **24 accepted boots / 48 complete records**; exact uploaded image/loader hashes, raw command frames and all metrics match CSVs; [audit](evidence-audit.json) |
| Publication | [Repository health](repo-health.log) passes; [staged-byte audit](staged-byte-audit.log) confirms Git preserves archive members and recorded receipt/profile/CSV/PC hashes |
| Certified fixture coverage | Regenerated, unchanged **401/417 functions**, **126164/126834 code bytes (99.5%)**; instrumentation scan succeeds; [report](../lk_coverage_c3_20261006.json) |

The validator's `--showcs` view of the frontend profile also reports
**Front-end**; it does not prove CS records. Counter mode is conservative edge
profiling, no call instrumentation, `privileged-single-core-no-fiq`, sequential
training and quiescent snapshots. BOLT reports 0% CFG flow gap; its 100%
call-graph gap is expected for one function without call profiling.

| Image | Rewritten range | Core | Observed hits |
|---|---|---|---|
| Instrumented | `[0x800e2000,0x80123b18)` | 2 | 26,939 |
| Counter BOLT | `[0x800e2000,0x800f2cce)` | 1 | 1,024 |
| Sampled BOLT | `[0x800e2000,0x800f2d14)` | 3 | 1,030 |

PC checks run with sampling enabled; those cycles are excluded from timing
comparisons. The watch logs bind each exact image/ELF. All runs arm a watchdog.
Output equality is not an independent algorithmic oracle. This receipt does
not certify a new whole-image oracle, IRQ/SMP instrumentation matrix, or A55
target. The new FE coverage scan emits 411 functions, folds five, and aliases
two out of 427; nine rows reject. That admission scan is not an execution gate.
The unchanged 0073 certified-image hardware gate and 62/62 ARM lit in both
modes are R35 evidence, not fresh C3 runs. Clean-build provenance remains the
item-14 receipt for 0001–0072; C3 adds output parity, not a new clean build.

## Measured gains and regressions

Both compiler and BOLT profiles train on input 0. Timing stops profiling and
uses normal workload IRQ masking. Each comparison has two interleaved boot
rounds and two runs per image per boot (four observations/image). Every row
has the expected checksum and all six metrics. Lower cycles are better.

| Input | FE+ThinLTO mean cycles | Counter BOLT | Change | Sampled BOLT | Change |
|---|---|---|---|---|---|
| 0, training | 15,175,210 | 9,509,362 | **−37.336%** | 9,586,338 | **−36.829%** |
| 1, held out | 15,176,236 | 9,516,161 | **−37.296%** | 9,583,454 | **−36.852%** |
| 2, shifted selectors | 14,439,062 | 16,528,768 | **+14.473%** | 15,220,554 | **+5.412%** |

| Compiler, input 0 | Mean cycles | Change versus baseline |
|---|---|---|
| Fresh baseline | 10,495,449 | — |
| FE-PGO | 10,532,391 | **+0.352%** |
| FE-PGO + ThinLTO | 15,175,571 | **+44.592%** |

The FE pipeline works, but neither compiler profiling nor BOLT guarantees a
gain. FE+ThinLTO has far more L1I refills on input 0 despite fewer instructions;
this is evidence consistent with a layout/footprint problem, not proof of its
cause. BOLT improves that input but both profile modes lose on input 2.
**C4** in [HANDOFF](../../HANDOFF.md) retains this performance investigation.
The baseline-versus-BOLT numbers come from separate comparison blocks; no
single interleaved baseline/FE/BOLT matrix or controlled CSPGO comparison is
claimed. Within-boot runs share cache/predictor state. Intervals in
[summary](summary.json) describe repeatability with a small boot count,
not independent population sampling or representative/A55 performance.

## Portable evidence and pickup

[evidence.tar.xz](evidence.tar.xz) contains **268 files**, **2,083,068 bytes**.
SHA-256: `a961bff0bafa9814ce038a45cc7718cd63b96fc11ae90afa8fe8f0758b53ccb9`.
[Integrity catalog](integrity.json) hashes every member and published receipt;
all member bytes and JSON readability were checked after compression. It retains
compiler ELFs/images, raw/indexed FE profile, module configuration/bitcode,
counter/sample dumps and seals, BOLT outputs/maps in both modes, build/no-FPU
logs, full UART captures, immutable seven-image uploads and measurement
uploads/receipts, PC logs, source/tool inventory, exact replay, helpers and CSVs.
Historical absolute paths in manifests identify the original capture;
portable files are under archive-relative `c3-fe/`. Tools are hash-identified
and rebuildable from the pin/overlays, not bundled executable toolchains.

Failed attempts are retained and excluded from the accepted statistics:
initial FE collection build lacked `PGO_RT_LIB`; initial sampled optimization
used the wrapper's destination as its copy source; one measurement attempt
found COM5 busy because it overlapped the final parity boot. Accepted rebuild/
optimization/timing logs are distinct. The failed timing CSV has no data rows;
its failed boot is `measure-rkswmrja`, with no measurement receipt.

WSL shared LLVM source remains intentionally dirty with overlays 0001–0073;
do not reapply overlays or reset it. New isolated LK/builds are in
`/home/user/bolt-fe-20261006`, compiler `build-atfe/c3-fe-thumb`, BOLT
`build-atfe/c3-counter`, `c3-sample`, `c3-counter-off`, `c3-sample-off`.
C1/R35 outputs are preserved. Windows raw evidence remains `out/c3-fe`.
Final Pi observation: sampled-BOLT FE shell, sampler stopped, watch ranges
cleared, watchdog off and COM5 closed. Resource release is published in
HANDOFF. Next normal shared item remains R32; C4 is open, not started.
