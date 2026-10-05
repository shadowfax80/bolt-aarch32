# B1: BOLT on the Pi from an lk-perf sampling profile vs an instrumentation profile (2026-10-05)

Question (user): with lk-perf (sampling) and bolt-aarch32 (instrumentation)
both able to produce BOLT profiles, how much real benefit does each deliver on
hardware? Two workloads: a showcase built to need BOLT, and the whole LK image
running apps that already exist.

All numbers are from the Raspberry Pi 4B (Cortex-A72, AArch32, Non-secure SVC,
600 MHz). Each image was booted fresh for every run; image order rotated
between rounds. Every app's result value was identical in every run of every
image. This is a measurement, not a certification: no oracle contract was
changed, and the full-image gate was not rerun on these images.

## Results

### Showcase: `bolt_bench stair`, ThinLTO, 512 sites (3 rounds x 2 runs, interleaved)

ThinLTO inlines a cross-TU helper into every site: the kernel grows from
18 KB to 134 KB and stops fitting the 48 KB L1I. That is the BOLT input.

| Image | Cycles | vs ThinLTO input | vs -O2 | L1I refills |
|---|---|---|---|---|
| -O2 (reference) | 11.328M | | | 3 |
| ThinLTO (BOLT input) | 32.602M | | +187.8% | 2,094,053 |
| **BOLT, instrumentation profile** | **9.196M** | **-71.8%** | -18.8% | 76,795 |
| **BOLT, lk-perf sampling profile** | **9.226M** | **-71.7%** | -18.6% | 89,390 |

Run-to-run spread is below 0.02%. **The sampled profile recovers 99.9% of the
gain** of the exact-edge profile (23.376M vs 23.406M cycles saved); the 0.3%
difference shows up as 16% more L1I refills, the cost of edges inferred from
samples (BOLT reports 54.6% weighted CFG flow imbalance for the sampled
profile, 0% for instrumentation). 39,515 samples landed in the kernel.

### Whole LK image, existing apps (6 rounds x 1 suite pass)

Input: the normal -O2 image (`bolt_bench` in ARM mode, see below) with
lk-perf's profiler. Apps: `bolt_bench` composite, multi, pgo_lab (pl_a..pl_d),
stair; lk-perf bench, nest, memtest, schedtest, smp. bolt_bench apps report
their own cycles; lk-perf apps are timed with `profiler stat` (all cores).

| App | input | R1 instrumentation | R2 lk-perf, same scope | R3 lk-perf, whole image |
|---|---|---|---|---|
| composite | 6.105M | +0.02% | **+16.40%** | **+16.39%** |
| multi | 43.358M | **-45.59%** | **-45.77%** | **-45.65%** |
| pl_a / pl_b / pl_c / pl_d | 25.3 / 32.9 / 22.3 / 14.1M | 0.00% | 0.00% | 0.00 to +0.09% |
| stair (640 sites, -O2) | 14.151M | +0.54% | +1.44% | +1.41% |
| bench / nest / smp | 16.2 / 3.2 / 12.3M | 0.00% | 0.00% | 0.00% |
| memtest | 167.0M | +0.16% ±0.62 | -0.31% ±0.57 | +0.14% ±0.67 |
| schedtest | 80.8M | +0.02% | +0.02% | +0.07% |
| **suite total** | 437.85M | **-4.43%** | **-4.37%** | **-4.18%** |

- R1: instrumentation can only cover `bolt_bench_*` code (project policy: kernel
  and platform code must not be instrumented); 11 functions, 1,015 exact edges,
  11 entries redirected.
- R2: lk-perf samples restricted to the same 11 functions (3,321 samples).
- R3: lk-perf samples over everything sampling sees and BOLT can rewrite: 49
  functions (scheduler, threads, mutexes, timers, wait queues, vfprintf,
  uart_putc, lk-perf workloads, pgo_lab), 12,681 samples, 46 entries
  redirected (3 left unredirected because BOLT changed their prologue).

**Composite regression and sample density** (3 rounds x 2 runs):

| Profile for `bolt_bench_composite` | Samples in function | Cycles vs input |
|---|---|---|
| instrumentation (R1) | (2.0M exact counts) | +0.02% |
| lk-perf, suite capture (R2) | 245 at 3 PCs | **+16.39%** |
| lk-perf, dense capture (R2d) | 13,647 at 8 PCs | **+0.01%** |

Composite runs for ~10 ms per suite pass, so the suite capture gave it 245
samples. Without branch records BOLT infers edges from block counts, so blocks
that ran but drew no sample looked dead and were moved off the hot path. With
enough samples the sampled profile matches instrumentation exactly.

### What this says

1. **When BOLT has something to fix, a good sampling profile is as good as
   instrumentation**: -71.7% vs -71.8% on the showcase; -45.8% vs -45.6% on
   `multi` (six 7-11 KB functions laid out contiguously).
2. **Sampling needs enough samples per hot function.** 245 samples made a 16%
   regression; 13,647 made none. A sampling profile should be collected per
   workload or long enough that every hot function gets thousands of samples.
3. **Sampling reaches code instrumentation may not touch** (kernel, libc,
   drivers, pgo_lab's `pl_*`, lk-perf apps), but on the stock LK image that
   code fits the caches: rewriting 49 such functions changed nothing
   measurable (R3 vs R2). The A72's 48 KB L1I and 1 MB L2 hold LK's hot paths;
   BOLT pays off only where the hot code footprint is large.
4. **BOLT without a layout problem costs a little**: stair at -O2 (fits in L1I)
   got 0.5-1.4% slower in every variant.
5. Whole-image sampling exercised rewritten code that the instrumentable scope
   never runs, and found a backend bug (R28, below).

## How the sampling profile was made

lk-perf's `app/profiler` and its kernel overlays were added to this repo's LK
(bolt-aarch32 LK overlays 0001-0011 at LK 79d2f560, plus lk-perf overlays
0001-0003, 0005, 0009, 0010, 0012-0016; `gic_v2.c` merged by hand so both IRQ
hooks run: `tools/merge_lkperf.py`). Built with the ATFE clang in a separate
root (`~/bolt-b1`, shared toolchain read only; the certified shared LK tree was
not touched).

- **Sampler:** lk-perf timer mode (K10: per-core virtual timer, one sample at a
  random point of each period), not PMU mode: `bolt_bench` reprograms the PMU
  for its own measurements and overrode overflow sampling (2 samples instead
  of ~60).
- **Pseudo-NMI** (`profiler nmion`, K12): `bolt_bench` runs timed regions with
  IRQs masked, so without it only 2.1% of samples reached the stair kernel;
  with it 24.1% (all of the workload core's time).
- **Collector:** `scripts/pi4/pi4_lkperf_profile.py` (new). It seals the image
  first (`profile_identity.py seal-samples`), runs clear/sample/dump cycles
  (`--per-command` keeps a long suite from wrapping the per-core ring), checks
  every lk-perf record checksum, dump footer and image hash, and writes
  Thumb-tagged PCs with a `pi-pc-capture` manifest. From there the existing
  verified route is unchanged: `samples_to_fdata.py` (perf2bolt `-nl`) and
  `profile_identity.py check-profile`.
- Instrumentation used the existing route (`bolt-variant.sh instrument`,
  `--conservative-instrumentation`, privileged-smp-no-fiq contract,
  `pi4_bolt_profile.py`, now with `--command` for a command suite), sealed
  against a fresh overlay replay of 0001-0069 (0 mismatched files).
- Measurement: `scripts/pi4/pi4_compare.py` (showcase)
  and `scripts/pi4/pi4_suite_measure.py` (new; whole image), watchdog armed.

## Findings and fixes along the way

| Item | What | Status |
|---|---|---|
| **R28** (new, bolt-aarch32) | BOLT sets the Thumb bit on code addresses in an ARM-mode function's inline `add rX, pc; ldr pc, [rX, rY, lsl #2]` table ("0 functions had jump tables": the table is kept as inline data and its R_ARM_ABS32 entries are re-emitted with bit 0 set). In ARMv7, `ldr pc` with bit 0 set switches to Thumb: the rewritten `pl_b` data-aborted on the Pi (`r28/crash_r3_pl_b.log`). Workaround here: `pl_b/1`, `bolt_bench_switch_pick/1`, `arch_sync_cache_range` kept original. | Open (HANDOFF) |
| **R29** (new, fails safe) | Thumb code hit the R8 refusal "local branch ... needs an r12 stub but r12 is live": ext-tsp reordering of the 120 KB Thumb ThinLTO stair kernel, and edge instrumentation of Thumb `bolt_bench_stair` and even the 756-byte `bolt_bench_multi`. BOLT refuses, so no wrong code; the ARM-mode builds of the same functions pass. Cause not analysed (Thumb narrow-branch relaxation itself is probed and works, R27/V7). Workaround here: `bolt_bench` built in ARM mode (`BOLT_BENCH_ISA=arm`). | Open (HANDOFF) |
| lk-perf K14 | lk-perf's mask accounting read the PC as data (`mov rX, pc`) in every inlined `arch_disable_ints()`; BOLT refused 44 kernel functions. Fixed in lk-perf overlay 0016: 2 refusals left (hand-written assembly). | Fixed (lk-perf 58c3daf) |
| lk-perf K13 | lk-perf's host image hash failed on an ELF with a 2-byte gap between load segments (ARM-mode build). | Fixed (lk-perf 30c90d6) |
| lk-perf K15 | lk-perf `profiler stat` left the cycle counter disabled, so `bolt_bench` read 0 cycles in any later suite pass; the whole-image measurement therefore uses one pass per boot. | Fixed (lk-perf a547f94), verified on the Pi |
| no-FPU scan | `check-no-fpu.sh` flags `vnmls.f32` in BOLT outputs at restored ARM code (`arch_disable_cache`): bytes identical to the input, decoded as Thumb because the output drops the `$a` mapping symbol. Known item 14; inputs scan clean. | Existing item 14 |
| Local symbols | `-skip-funcs` and `--funcs-file` need BOLT's local names (`pl_b/1`); a plain `pl_b` silently matches nothing (the first R28 workaround did not take and the Pi crashed again). | Noted |

## Limits

- One A72 board; the A55 target is in-order with different caches (T4).
- Profiles were collected on the measured inputs (no held-out input).
- No certification gate was run on these images; correctness evidence is the
  identical app results in every run (288 + 24 measurements) and no crash
  after the R28 workaround.
- R3 redirects 46 kernel/app entries; that is broader than any certified
  scope.

## Artifacts

| | SHA-256 |
|---|---|
| stair -O2 | `96fd68ce…` |
| stair ThinLTO input | `368f087c…` |
| stair BOLT instrumentation | `e6b0c7c8…` |
| stair BOLT lk-perf | `8dad6c57…` |
| whole input | `c7e9e0d2…` |
| whole R1 / R2 / R2d / R3 | `3a8f5b76…` / `b89888f0…` / `d94b37df…` / `2f0ea758…` |

Profiles (`*.fdata`) and their identity manifests, measurement CSVs and
summaries, BOLT's full-image stats, the R3 scope and skip lists, the R28 crash
log, and the exact helper scripts (`tools/`, written for this session's
scratch paths) are in this directory.
