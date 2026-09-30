# Real-hardware (Pi 4B) BOLT verification

**Goal:** verify BOLT's AArch32 backend on real Pi 4B PMU counters, not just
QEMU's cycle counts (QEMU models no i-cache — exactly what BOLT optimizes).
Staged comparison: baseline → +PGO → +PGO+ThinLTO → +PGO+ThinLTO+BOLT, all on
the ATFE toolchain. Full step list: see the plan this work follows (10 steps,
recorded at conversation time; steps below track progress against it).

Hardware setup is shared with the [lk-perf](https://github.com/shadowfax80/lk-perf)
project: same Pi 4B, same USB-serial adapter (COM5 on the dev machine), same
`experiments/pi4-serialboot` chainloader already on the SD card (generic,
payload-agnostic — no reflash needed for this project's own images).

## Status

| Step | What | Status |
|------|------|--------|
| 1 | Recreate RunPod env, build ATFE LLVM+BOLT, bare-metal runtime, LK, QEMU gate | **Done** — `verify-bolt-workloads.sh` (ARCH=arm32) green |
| 2 | Port lk-perf's rpi4 hardware patches (BCM2711, UART baud, watchdog-reboot) | **Done** — `overlay/lk/patches/0002-0004`, `target/rpi4/`, `project/rpi4-bolt-test.mk` |
| 3 | Boot plain baseline on real Pi, confirm all `bolt_bench` workloads run | **Done** — all 16 workloads ran, real cycle counts (see below) |
| 4 | Replace QEMU's memory-dump mechanism with a UART one | **Done** — QEMU cross-check + real Pi trial both pass |
| 5 | Add a two-file composite benchmark (cross-TU, for ThinLTO to have something to do) | **Done** — verified under QEMU |
| 6 | Compile-time PGO support | **Done** — profile collected on the real Pi, applied via `-fprofile-instr-use` |
| 7 | ThinLTO on top of PGO | **Done** — scoped to the bolt_bench module; relocations preserved for BOLT |
| 8 | BOLT on top of PGO+ThinLTO | **Done** — runs correctly on the Pi; no measurable gain (see below for why) |
| 9 | PMU counter reading in `bolt_bench.c` (cycles + cache misses) | **Done** — cycles + L1I/L1D refills, instructions retired, branch mispredicts |
| 10 | Full staged comparison, real Pi, several runs each | **Done** — 80 runs, see below |

## Step 1 — environment

New network volume `3g114i4sby` (150 GB, EU-RO-1), replacing the deleted
`j1d9e6wq5l`. `BASE=atfe` build of LLVM+BOLT (clang/lld/llvm-bolt), the
bare-metal BOLT runtime (`libbolt_rt_baremetal.a`, arm-none-eabi/cortex-a15),
and LK (`qemu-virt-arm32-test`) all built clean. `verify-bolt-workloads.sh`
passed: 6/6 instrumentation counters non-zero, BOLT optimize pass ran,
`BOLT arm32 workload verification OK`.

Dynamic pod sizing used throughout: 8 vCPU only for the actual `ninja`
compile, 2 vCPU for everything else (checkout, patch work, LK builds, QEMU
verify) — matching the project's established cost-optimization pattern.

## Step 2 — rpi4 hardware patches

Ported three of lk-perf's overlay patches (skipping its sampling/SMP/FPU
patches — not needed for a benchmark harness, not a profiler):

- `0002-bcm28xx-add-rpi4.patch` — BCM2711 platform: peripheral base/GIC-400
  address windows, `platform.c` GIC init + DTB memory-size parsing,
  `TARGET=rpi4` in `platform/bcm28xx/rules.mk` (Hyp-mode drop, SMP on).
- `0003-bcm2711-uart-baud.patch` — LK requests its own UART clock at boot
  (IBRD=1/FBRD=0 against the chainloader's 48MHz clock = exactly 3,000,000
  baud), instead of inheriting the chainloader's 115200.
- `0004-bcm28xx-watchdog-reboot.patch` — PM-block watchdog reset backing
  `platform_halt()`, so a running LK image can reboot itself back to the
  SD-card chainloader via the `reboot` shell command — no physical
  power-cycle needed between two of *our own* LK images (still needed the
  first time, or whenever a non-LK payload — e.g. a bare test image — is
  currently running, since only LK's shell listens for the command).

New `target/rpi4/rules.mk` and `project/rpi4-bolt-test.mk` (this project's
own analog of lk-perf's `project/rpi4-test.mk`, with `app/bolt_bench`
instead of `app/profiler`, and `project/virtual/test.mk` deliberately
excluded — it pulls in `lib/libm`, which uses hardware VFP unconditionally;
the real hardware PoC target has no FPU/NEON at all).

**Idempotency fix (`scripts/apply-overlays.sh`):** the existing
"already applied?" check (`git apply --check --reverse`) breaks once more
than one sequential patch touches adjacent context in the same file —
checking patch N's reverse-apply in isolation fails when patch N+1's text
already occupies the exact spot N's hunk expects as its boundary, even
though nothing is actually wrong. Replaced with a stamp file
(`third_party/lk/.applied-overlay-patches`, gitignored, tracks applied
patch filenames directly), falling back to the old reverse-check only once,
for patches applied before the stamp file existed. Verified: full clean
checkout → `apply-overlays.sh` → re-run `apply-overlays.sh` (idempotent,
all patches skip correctly) → rebuild, still green.

## TODO: reflash chainloader to a faster upload baud

Image uploads (the initial serial transfer before LK boots) run at the
chainloader's fixed 115200 baud — confirmed by matching throughput
(~11 KiB/s ≈ 115200 8N1 raw byte rate exactly). The 3M-baud UART patch only
speeds up LK's *own* post-boot interactive shell (it requests its own
clock after the chainloader has already handed off), not the upload itself.
A BOLT-instrumented image is ~6.27 MB (mostly BOLT's reserved hot-text
padding for a handful of tiny benchmark functions), so at 115200 baud this
upload takes ~9-10 minutes per iteration.

Fix: reflash the SD card's chainloader itself to also transfer at 3M (or
6M) baud — the actual reflash lk-perf's own baud work deliberately avoided
needing. **User decision (2026-09-29): do this at the next opportunity, not
now.** Tracked here as a definite TODO, not a someday-maybe.

## Step 3 — real hardware boot

`BASE=atfe LK_PROJECT=rpi4-bolt-test ./scripts/build-lk-aarch32.sh` on the
pod, `lk.bin` (75,644 bytes) downloaded to the dev machine, sent over serial
via `scripts/pi4/pi4_run.py` (vendored from lk-perf, unmodified).

All 16 `bolt_bench` workloads ran to completion on the real Pi:

```
bolt_bench: hot_loop done (9 cycles)
bolt_bench: hot_cold done (9 cycles)
bolt_bench: branch_chain done (9270596 cycles)
bolt_bench: memcpy done (621545 cycles)
bolt_bench: far_call done
bolt_bench: it_cond done (5001032 cycles)
bolt_bench: interwork done (100104 cycles)
bolt_bench: switch done (13002425 cycles)
bolt_bench: spill_ret done (1050101 cycles)
bolt_bench: litpool done (2001371 cycles)
bolt_bench: indirect_call done (252133 cycles)
bolt_bench: interwork_tail done (200088 cycles)
bolt_bench: regpressure done (280075 cycles)
bolt_bench: hotcold_split done (3321862 cycles)
bolt_bench: icf done (200065 cycles)
bolt_bench: shrinkwrap done (5033016 cycles)
```

Note: `hot_loop`/`hot_cold` reporting 9 cycles (vs. millions for everything
else) is suspicious for a 1,000,000-iteration loop and needs investigation —
either `arch_cycle_count()` isn't reading a real free-running counter on this
platform, or LLVM folded the `sum += i` accumulation into a closed-form
formula (a well-known compiler idiom for a compile-time-constant-trip-count
linear induction variable), which would mean the compiled binary no longer
contains an actual hot loop to bench at all. Not chased down yet — these
first runs were only scoped to prove boot + execution end-to-end. Worth
resolving before Step 9 (real PMU counter reading) is trusted, and worth
checking the disassembly either way once a pod is up again.

## Step 4 — UART memory dump, done

Added `bolt_dump <addr_hex> <size_hex>` to `bolt_bench.c`: chunked (64
bytes/line) memory dump over UART, each chunk carrying a seq number and an
FNV-1a checksum (same algorithm family as lk-perf's
`profiler_sample_checksum`, applied to a raw byte range instead of typed
fields) — carries lk-perf's seq/crc integrity discipline forward, since a
dump that just trusted whatever arrived would reproduce the same silent
corruption bug lk-perf found on this exact link.

Host side: `scripts/bolt_dump_reassemble.py` (transport-agnostic parser,
shared by both the QEMU cross-check and the real Pi path — reassembles
`BOLT_DUMP_BEGIN/BOLT_DUMP/BOLT_DUMP_END` text lines back into raw bytes,
verifying each chunk's checksum and reporting any gaps) and
`scripts/qemu_bolt_dump.py` (the cross-check driver: boots an instrumented
image under QEMU with a TCP-socket serial chardev instead of QMP, runs the
workload, dumps via the new command).

**Cross-check (QEMU, zero hardware risk):** dumped the same instrumented
`qemu-virt-arm32-test` image (`.bolt.instr.counters`, 10074 bytes at
`0x80601000`) both ways — via the existing QMP `memsave` method
(`dump-bolt-counters.py`) and via the new UART command
(`qemu_bolt_dump.py`). The two raw dumps were **byte-for-byte identical**
(`cmp` reported no difference), and running both through
`ram-dump-to-fdata.py` produced **identical `.fdata`** output. Confirms the
UART method is a drop-in replacement — the existing `.fdata` conversion
script needed zero changes, as planned.

**Real Pi trial:** instrumented `rpi4-bolt-test` the same way (same
counter section address/size, since `KERNEL_BASE` happens to match
`qemu-virt-arm32-test`'s). Converted the instrumented ELF to a raw binary
via `llvm-objcopy -O binary` — 6.27 MB, mostly BOLT's reserved hot-text
padding for the ~14 tiny instrumented functions (real content is a small
fraction of that). Sent over serial, booted, ran `bolt_bench all`, then
`bolt_dump 80601000 275a`: all 158 chunks arrived correct on the first try
(zero bad checksums this run — lk-perf's corruption was real but
intermittent, not guaranteed every transfer), reassembled to exactly 10074
bytes, and converted cleanly to `.fdata` with all 14 instrumented
functions' real branch/call structure present.

One real bug caught along the way: the first Pi attempt instrumented a
*stale* `rpi4-bolt-test` build from before `bolt_dump` was added (only
`qemu-virt-arm32-test` had been rebuilt after the code change) — resulted
in `bolt_dump: command not found` on-device, after a needless ~10-minute
image transfer. Rebuilt `rpi4-bolt-test` fresh and retried successfully.

**Note:** the `hot_loop`/`hot_cold` cycle-count anomaly above was later
resolved (see below): the compiler folded those loops to constants.

## Step 5 — composite cross-TU benchmark, done

Every other `bolt_bench` workload is single-file, so ThinLTO would have
nothing cross-module to actually optimize — everything a single `clang
-O2` invocation can already see doesn't need LTO. Added `composite.c`
(new second translation unit in `app/bolt_bench/`) with a hot path
(`composite_process`, called every iteration) and a cold path
(`composite_report_cold`, called every 262144th iteration) that
`bolt_bench.c`'s new `bolt_bench_composite()` calls into across the
TU boundary.

Verified under QEMU:
- Confirmed via disassembly the calls are real `bl` instructions to
  `composite_process`/`composite_report_cold`, not already inlined by the
  single-TU compile (`llvm-objdump -d`, `bolt_bench_composite`'s body).
- Standalone (`lk.bolt_bench=composite`): hot path ran, cold path fired
  exactly 3 times (`1000000 / 262144 = 3`, matches the `0x3FFFF` mask),
  completed in 16.3M cycles.
- As part of `all` (17 workloads now): all ran cleanly, no regressions to
  the existing 16.

Same anomaly as above showed up in a different form here: this QEMU run's
`hot_loop`/`hot_cold` read 3530/2500 cycles (not the real Pi's suspicious
9) — worth keeping in mind when finally chasing that down, since QEMU and
real hardware disagree on more than just absolute scale.

## Step 6 — PGO profile generation, done (use-side pending)

ATFE's compiler-rt already has a real `COMPILER_RT_PROFILE_BAREMETAL` mode
(minimal profile runtime: no filesystem, no init hook, no malloc/value
profiling) -- reused rather than writing a runtime. `scripts/build-pgo-rt-baremetal.sh`
compiles that source set directly with clang for arm-none-eabi/cortex-a15
(against apt's `libnewlib-arm-none-eabi` headers for string.h/stdint.h --
new pod dependency, added to `install-deps.sh`/`bootstrap-pod.sh`) into
`libpgo_rt_baremetal.a`. `WITH_BOLT_PGO=true` builds the `bolt_bench` module
(only, not all of LK) with `-fprofile-instr-generate` and links that archive
via LK's `EXTRA_OBJS`. New `bolt_pgo_dump` shell command calls
`__llvm_profile_write_buffer()` to serialize a complete, valid raw instrprof
file into a buffer and prints its address/size; the existing generic
`bolt_dump` (Step 4) reads it out over UART -- no new transport.

Verified on the real Pi (no QEMU): `bolt_bench composite` then `bolt_pgo_dump`
then `bolt_dump 8002a080 e98` -> 3736 bytes, all chunks checksum-clean.
`llvm-profdata` (built from the matching ATFE tree -- a distro one would
mismatch the raw-format version) accepts it: `composite_process` and
`composite_transform` 1,000,000 calls each, `composite_report_cold` 3,
driver-loop blocks `[1000000, 3]` -- exactly the expected counts. Merged to
an indexed `.profdata` (kept on the volume at `build-atfe/pgo/`).

Note: the same build on the `qemu-virt-arm32-test` project failed to link
(`lk_symtab_*` undefined -- that project's `lib/symtab` two-stage generation
step); abandoned rather than debugged, since verification is Pi-only now and
`rpi4-bolt-test` (no `lib/symtab`) links cleanly.

## Steps 6-7 — variants built and first measured on the real Pi

`scripts/build-variants.sh` builds each named variant from a clean LK build
dir with the same overlay source (`baseline`, `pgo-collect`, `pgo`,
`pgo_thinlto`), so differences between them are flags only.
`scripts/pi4/pi4_pgo_collect.py` collects the profile (two boots: learn the
buffer size, then dump it). ThinLTO is scoped to the `bolt_bench` module only
(not all of LK, whose global `LTO_MODE` would confound the comparison) via
overlay patch `0005-module-lto-optin.patch`, a per-module `MODULE_LTO` opt-in in
LK's `module.mk`.

**Benchmark bug caught along the way:** `composite_process`/`composite_transform`
were first marked `noinline` (copied from the other benches, which need that
to stay distinct BOLT-instrumentable symbols). That blocks exactly the
cross-TU inlining this benchmark exists to measure — the ThinLTO build was
bitcode but still `bl composite_process`. Fixed (hot path inlinable, cold path
`composite_report_cold` stays out of line) and every variant plus the profile
rebuilt from the corrected source.

Confirmed by disassembly of `bolt_bench_composite`: baseline and +PGO still
`bl composite_process` (PGO cannot inline across a TU boundary); +PGO+ThinLTO
inlines it.

**First measurement, real Pi 4B, `bolt_bench composite`, 5 runs per variant
(one boot each), cycles from the PMU cycle counter:**

| Variant | cycles (5 runs) | vs. baseline |
|---|---|---|
| baseline | 6,102,285 – 6,102,728 | — |
| +PGO | 6,102,070 – 6,102,725 | no change (within noise) |
| +PGO+ThinLTO | 4,201,101 – 4,201,322 | **-31%** |

PGO alone does nothing here: the loop has no branch worth reordering and the
call crosses a TU boundary it cannot see through. ThinLTO's cross-TU inlining
removes ~1.9 cycles/iteration. Run-to-run spread is ~0.01%, so these are not
noise. This is a first look (one boot per variant), not the Step 10 result.

## `hot_loop` / `hot_cold` anomaly: resolved

`arch_cycle_count()` is a direct read of the PMU cycle counter
(`mrc p15,0,r0,c9,c13,0`) and it is live — `composite` measures ~6M cycles
for 1M iterations. `hot_loop`/`hot_cold` report ~9 cycles because LLVM folded
the loop into a closed-form constant (`sum += i` over a compile-time-constant
trip count becomes a `movw`/`movt` of the result); the 9 cycles is just two
back-to-back counter reads. Those two workloads contain no loop for BOLT to
optimize; Step 9 is not blocked on the counter. (The 3530/2500 QEMU figures
were QEMU's counter emulation, not comparable.)

## Step 8 — BOLT on top of PGO+ThinLTO, on the real Pi

Reproducible via `scripts/bolt-variant.sh instrument|optimize <variant>` (build
host) plus `scripts/pi4/pi4_bolt_profile.py` (dev machine, real Pi). Getting a
BOLT-optimized image to *actually execute on hardware* took five fixes, none
of which the existing QEMU-era scripts had needed:

1. **Image size.** llvm-bolt force-enables "hot text" mode when instrumenting
   (and when reordering functions without an explicit `-hot-text`), aligning
   new code to 2MB huge-page boundaries — a Linux feature. Result: a ~148KB
   image becomes ~6.27MB, a ~10 minute upload at the chainloader's fixed
   115200 baud. `--no-huge-pages` (BOLT's `PageAlign = 4KB`) gives 148-156KB,
   a ~13 second upload. The chainloader-reflash TODO above is therefore much
   less urgent, though still worthwhile.
2. **LK's page array landed on BOLT's segments.** Without huge-page padding,
   BOLT places its new segments (instrumentation stubs, counters, relocated
   code, runtime) at the first page boundary after the original image's `_end`
   — exactly where LK's boot allocator starts, and where `pmm_add_arena()`
   carves its `vm_page` array (12-byte nodes, ~3MB for 1GB RAM). The dumped
   "counters" were a free list. Not a tool bug: the old 2MB-away layout only
   survived by distance. First attempt (`pmm_alloc_range` after the arena was
   added) changed nothing, because the array was already built there; the fix
   is claiming the window with `boot_alloc_mem()` *before* `pmm_add_arena()`
   (overlay patch `0006-bcm2711-reserve-bolt-window.patch`, 1MB). Verified: the
   counter region now matches the ELF's initial bytes exactly.
3. **ThinLTO silently defeats function selection.** ThinLTO internalizes
   `bolt_bench_composite` (only same-module `run_one` references it) into a
   LOCAL symbol; BOLT names it `bolt_bench_composite/1`, so the exact-name
   `--funcs-file` and hook lookups match nothing and BOLT instruments **zero**
   functions without erroring (`Number of function descriptors: 0`). Fixed with
   `--undefined=bolt_bench_composite` in the ThinLTO variant so it stays a
   global entry point; `bolt-variant.sh instrument` now fails loudly if no hook
   was installed.
4. **The profile has no edge frequencies.** On the ARM path the image restores
   the original text and installs a single *entry* hook that bumps all of a
   function's counters once per call, so every edge in the `.fdata` reads 1
   (the loop ran 1,000,000 times; cold path 3). BOLT's block layout has nothing
   to work with beyond function-level counts.
5. **The optimized code never ran.** `optimize-lk-bolt.sh` ends with
   `fix-kernel-elf-sections.py`, which restores the original text and only knows
   how to install *instrumentation* hooks — nothing branches into BOLT's
   optimized copy. The image booted and looked fine while executing
   byte-for-byte the same code as its input (0 differing bytes). This means the
   earlier QEMU "optimize OK" gates only proved the image stayed bootable, not
   that optimized code ran. New `scripts/redirect-bolt-entries.py` patches the
   original entry with a Thumb `b.w` to the optimized copy (valid only when a
   single function is rewritten; refuses otherwise). Proved on the Pi: with the
   original body overwritten by `0xff` bytes the image still runs correctly, so
   BOLT's copy is what executes.

**Result, real Pi 4B, `bolt_bench composite`, 5 runs per variant:**

| Variant | cycles | vs. baseline |
|---|---|---|
| baseline | ~6,102,4xx | — |
| +PGO | ~6,102,4xx | no change |
| +PGO+ThinLTO | ~4,201,2xx | -31% |
| +PGO+ThinLTO+BOLT | ~4,201,2xx | -31% (no change vs. ThinLTO) |

BOLT's output is functionally identical (same accumulator values on every cold
report) and exactly as fast. That is the expected outcome, not a pipeline
failure: PGO already placed the cold `composite_report_cold` call out of line,
so the hot path is 10 instructions with a single taken backward branch — there
is nothing left for block reordering to improve, and the entry-only profile
could not have told BOLT anything more anyway. A workload with real layout
headroom (a large working set / many hot functions) plus edge-level profiling
on ARM would be needed to show a BOLT gain.

## Step 9 — PMU event counters

`bolt_bench composite` now prints, after each run, instructions retired, L1I and
L1D refills and branch mispredicts (Cortex-A72 architectural events 0x08, 0x01,
0x03, 0x10) next to the cycle count. Two things that cost time:

- The PMU is **banked per core** and the shell thread can run on any core. Arming
  only the core that ran the first command left every later run on another core
  reading zeros while the cycle counter (enabled per core by LK) kept counting.
  Fixed by arming all cores with `mp_sync_exec()` and pinning the measured region
  to one core (`thread_set_pinned_cpu`); a run that migrates is reported INVALID
  instead of printing wrong numbers.
- Programming it that way exposed the NEON panic below.

## Step 10 — final staged comparison (real Pi 4B)

`scripts/pi4/pi4_compare.py`: 5 rounds x 4 variants x 4 runs per boot = 80 runs,
variants interleaved across rounds (so slow drift cannot favor one), every run
kept in `docs/results/step10_rpi4_composite.csv`. Workload: `bolt_bench composite`
(1,000,000 iterations; hot path `composite_process`, cold path every 262,144th).

| Variant | cycles (mean, [min..max], sd) | instructions | L1I refill | br mispredict | cycles vs. baseline |
|---|---|---|---|---|---|
| baseline | 6,102,662 [6,102,369 .. 6,102,950] sd 143 | 15.007M | 12.6 | 89 | — |
| +PGO | 6,102,791 [6,102,558 .. 6,103,015] sd 127 | 15.007M | 12.7 | 112 | +0.00% |
| +PGO+ThinLTO | 4,101,541 [4,101,413 .. 4,101,674] sd 78 | 10.007M | 3.0 | 89 | **-32.79%** |
| +PGO+ThinLTO+BOLT | 4,101,564 [4,101,377 .. 4,101,708] sd 99 | 10.007M | 5.2 | 87 | -32.79% |

(These supersede the preliminary numbers in the Step 6-7 and 8 sections above,
taken on an earlier revision of the source before the PMU code was added.)

What the counters say, not just the cycles:

- **PGO alone: nothing.** Same instructions, same cycles. The loop has no branch
  worth reordering and the hot call crosses a TU boundary PGO cannot see through.
- **ThinLTO: -32.8%, and it is entirely fewer instructions.** 15 -> 10 per
  iteration (inlining `composite_process` removes the call, its push/pop and
  the return); IPC is unchanged (~2.45), so cycles fell in proportion.
- **BOLT: no change, correctly.** The image is functionally identical (same
  accumulator values on every cold report) and the optimized copy provably runs
  (see Step 8). L1I refills are ~0-13 in every variant — the whole loop lives in
  the L1I — so there is no instruction-cache effect for BOLT to improve; PGO had
  already left the hot path with one taken backward branch; and the entry-hook
  profile carries no edge frequencies anyway. Differences between the ThinLTO and
  BOLT rows are inside the run-to-run spread (sd ~100 cycles on 4.1M).

To show a BOLT gain you would need a workload with real layout headroom (a large
hot working set spread across many functions that overflows the L1I) and
edge-level profiling on ARM.

## TODO: multi-function BOLT support in the Pi pipeline

Definite TODO (not a someday-maybe). `scripts/redirect-bolt-entries.py` can only
make the optimized image run BOLT's code when exactly ONE function was rewritten:
LK boots from the original text with the MMU off, BOLT drops the moved function's
symbol, so the tool takes the new entry from the start of the output `.text` and
patches a single `b.w` at the original entry. To support `--reorder-functions` and
several optimized functions it needs to recover each function's new address (e.g.
BOLT's address map, `--enable-bat`, or body matching), patch every original entry,
and handle entries hit from outside BOLT's copies (vectors, function pointers).
Until then the Pi results only cover single-function block layout.

**Status 2026-09-30: mechanics done, performance not yet shown.** Overlay patch
`0013-bolt-emit-function-map` adds `llvm-bolt --emit-function-map=FILE` (one
`<name> <in> <out> <size>` line per emitted function; the symbol table is not
reliable for this, e.g. two moved functions shared one address). 
`redirect-bolt-entries.py --map FILE` patches every original entry (Thumb `b.w` or
ARM `b`), and accepts entries in `.text.cold` (where BOLT puts a function with no
profile). Verified on the Pi with two functions (`bolt_bench_stair_kernel`,
`bolt_bench_stair_step`): both redirected, checksum unchanged. In that run the
stair function's edge counters read zero, so BOLT only had a profile for the
helper and the result (+0.05% vs baseline) says nothing about performance. Several
profiled functions with `--reorder-functions`, ARM-mode functions and
function-pointer entries are still untested.

**Zero edge counters: root-caused and fixed (2026-09-30).** Not a hardware or dump
problem. BOLT's default edge instrumentation counts only the edges off a spanning
tree and infers the rest from flow conservation, which needs each function's entry
count; that count comes from call-site counters, which `instrument-lk-bolt.sh`
disables (`--instrument-calls=false`). For the stair function the tree took every
hot edge, the only counters sat on cold edges that never ran (disassembly: each
counter block is on the not-taken side of its guard), and a function called 1600
times dumped all zeros. Edges mode now adds `--conservative-instrumentation` (a
counter on every edge): the same image then profiles as 672 edges, each exactly
1600. **Consequence:** every earlier edges-mode profile was partial -- counts only
on edges that happened to be off the tree, nothing inferred -- including the one
behind the 448-site BOLT result (-9.9% vs baseline). That measurement is real, but
BOLT laid the code out from incomplete data; it has to be redone.

## Follow-up: no-FPU build and a workload that can show BOLT (in progress)

**No FPU/NEON (done).** The target is a Cortex-A55 with no FP/SIMD, so the rpi4
build now matches: overlay patches `0007-rpi4-no-fpu-neon` and
`0008-rpi4-compile-no-fpu` (`-mfpu=none` for the whole rpi4 build). Verified by
disassembling the full `lk.elf`: 0 FP/NEON instructions in 20,176.

**Showing a BOLT gain (shown, see "BOLT on the stair workload" below).** Findings on the way, all on the real Pi:

- The first "layout headroom" kernels measured compiler if-conversion, not layout:
  PGO and hot blocks became Thumb-2 IT-predicated runs (`itttt mi`), a compile-time
  decision BOLT cannot undo. An empty `asm volatile` in each block makes it
  unpredicable, so the blocks stay real branches (verified: 0 IT blocks).
- With one shared accumulator the kernel ran at IPC ~1, latency-bound, which hides
  any layout effect. The blocks must be independent so the kernel is front-end bound.
- BOLT needs edge-level profiling to see layout: `BOLT_PROFILE_MODE=edges`
  (`instrument-lk-bolt.sh` with `BOLT_INSTR_EDGES=1`, no entry hook). Edge counts
  were verified real and the checksums unchanged.
- The `stair` workload (`bolt_bench stair`) stages the three techniques in one
  kernel: cold guards (PGO), a cross-TU helper call (ThinLTO), a per-site-biased
  branch inside the helper (BOLT). v1 on the Pi, 18 interleaved runs
  (`build/stair1b`): baseline 10.64M cycles, PGO 10.64M (+0.01%), PGO+ThinLTO
  4.92M (**-53.8%**, 21.4M -> 11.2M instructions). PGO and BOLT do not move cycles:
  a predicted taken branch is almost free on the A72, so removing a few is too
  small to measure. The real BOLT lever is instruction-fetch footprint.
- v2 (written, not yet measured): 640 sites with two ~70-byte helper arms, so the
  interleaved layout exceeds the 48 KB L1I and BOLT's packing should fit it. Adds a
  second PMU set (`bolt_bench stair 1`: `stall_fe`, `stall_be`, `l1i_acc`, `br_ret`,
  `itlb_refill`), warm-up, interrupts off in the window, and a `taken` counter
  (PC_WRITE_RETIRED). Each stage has a predicted counter signature; a stage counts
  as demonstrated only if that counter moves. The BOLT stage also needs a
  no-reorder control to separate "code moved" from "code reordered".

Tooling fix found on the way: `pgo_cycle.sh` piped the remote build through
`tail`, which hid a failed `pgo-collect` build, so training ran on a stale image
and the profile-using variants silently ignored it (PGO looked like a 0% no-op).
The remote commands now run with `pipefail`.

## BOLT on the stair workload (2026-09-30, real Pi 4B)

`scripts/pi4/bolt_stage.sh <M>` runs one complete point from scratch: PGO training
on the Pi, builds of baseline / +PGO / +PGO+ThinLTO in WSL, BOLT edge profile
(every edge counted, see above) on the Pi, BOLT optimize twice from the same
profile, and a 3-round x 2-run interleaved measurement of five images with a
checksum check. `<M>` is the number of 64-site units (448 / 512 / 640 sites below).
The control image is BOLT with `-reorder-blocks=none`: the function is rewritten
and moved to the new `.text`, but keeps its block order, which separates "code
moved" from "code reordered". Raw runs and BOLT's profile report:
`docs/results/stair_bolt_stage_<sites>sites*.{csv,txt}`. The checksum is identical
in all 30 runs of every point.

| Sites | baseline | +PGO | +PGO+ThinLTO | BOLT control (no reorder) | **+BOLT** |
|---|---|---|---|---|---|
| 448 | 9.191M | +0.29% | +3.73% (145.6k L1I refills) | +5.84% (167.1k) | **-10.08%** (5.6k) |
| 512 | 10.498M | +0.32% | +38.92% (606.6k) | +46.75% (649.8k) | **-8.95%** (26.0k) |
| 640 | 13.103M | +0.43% | +84.44% (1,414k) | +88.97% (1,445k) | **-6.37%** (107.7k) |

(Cycles are the baseline's mean; every other cell is the change against it. Run to
run spread is under 0.01% everywhere.)

What it shows:

- **BOLT's gain is real and is the block reordering.** The control, which moves the
  function without reordering it, is *worse* than ThinLTO alone at every size
  (+2 to +6% more cycles), so the layout change is the whole effect. The profile is
  complete (448 sites: 1,569 edges, hottest count 1,600 = one per call, 0% CFG
  discontinuity in BOLT's report); BOLT modified the layout of exactly 1 function,
  100% of the profiled code.
- **The mechanism is instruction-cache footprint.** ThinLTO removes ~23% of the
  instructions but inlines the helper into every site; past ~384 sites the hot path no
  longer fits the 48 KB L1I, refills go from ~2 to 10^5-10^6 and IPC falls from 2.2
  to 0.9-1.7. BOLT packs each site's hot arm and moves the cold arm away: refills
  drop 26x (448), 23x (512), 13x (640) and IPC recovers to 1.8-1.9. Instructions
  barely change (-1% at 448).
- **The gain shrinks as the function grows** (-10.1% / -9.0% / -6.4%): the more code,
  the more misses remain after BOLT (5.6k / 26k / 108k refills).
- **PGO does nothing at any size** (+0.3 to +0.4%, instructions unchanged), and
  ThinLTO is a net loss above ~384 sites (below that it is a clean -11%). So the
  workload does not show "PGO first, then ThinLTO, then BOLT" as three separate
  wins: it shows BOLT recovering, and beating baseline after, a ThinLTO
  regression caused by code growth.
- **Limits:** one workload, one core, one profile per size; the profile is collected
  on the same input the measurement runs (no held-out input); only one function is
  rewritten per point.

## Where PGO pays off: the pgo_lab kernels (2026-09-30, real Pi 4B)

PGO was ~0% on every stair point, so the first question was which decisions a
profile changes that matter on a Cortex-A72. `bolt_bench pgo_lab` runs four
independent kernels (`pl_a`..`pl_d`), each isolating one mechanism, each with its
own PMU window; every input is opaque to the compiler and the kernels have
independent lanes so instruction-count effects show. Baseline vs +PGO (PGO trained
on composite + stair + pgo_lab together, ATFE clang), 3 rounds x 2 runs interleaved
by `scripts/pi4/pgo_lab_measure.py`, checksums identical for both images
(`docs/results/pgo_lab.csv`):

| Kernel | Mechanism | baseline cycles | +PGO | instructions | IPC | mispredicts |
|---|---|---|---|---|---|---|
| `pl_a` | hot call-site inlining (callee over -O2's threshold) | 25.68M | **-2.80%** | -6.0% | 1.01 -> 0.97 | ~0 |
| **`pl_b`** | **skewed switch (92% case 0)** | 29.81M | **-35.40%** | -15.6% | 1.49 -> 1.95 | -38% (287k -> 177k) |
| `pl_c` | spill placement around a cold call | 18.82M | -0.35% | +6.4% | 2.47 -> 2.64 | 22 |
| `pl_d` | loop trip count (2..5 iterations) | 14.12M | -0.01% | 0 | 1.11 | -1% |

- **The clear PGO win is switch-dispatch lowering.** With the profile the hot case's
  body sits inline on the loop's fall-through path; only the other 8% go through the
  jump table. That removes ~7M instructions and ~110k indirect-branch mispredicts on
  the hot path: IPC rises 1.49 -> 1.95, cycles -35%.
- **Hot-callsite inlining works but is worth little here** (-2.8%). Disassembly:
  `pl_a` has 5 `bl pl_mix` in the baseline and 1 (the cold site) with PGO; the function
  grows 46 -> 443 instructions. The callee is ~80 instructions, so the call and return
  are a small part of each call.
- **Spill placement and trip-count unrolling did nothing measurable.** `pl_c` executes
  more instructions with PGO (+6.4%) at a higher IPC and ends up flat; `pl_d` is
  identical to the instruction.
- **Limit:** the profile is trained on the same input the measurement runs, as in a
  normal PGO build; there is no held-out input. The branch skew (92%) is a property of
  the data table, so the size of the win depends on it.

So PGO can show a large, mechanism-confirmed gain on this core, but from dispatch
lowering, not from block layout. The stair workload (where PGO stays ~0%) has no
skewed switch; combining the two into one staged workload is the next step.

## Bugs found on the way (debugged with QEMU and the Pi interchangeably)

Each of these blocked BOLT/PGO on real hardware, and none had shown up in the
QEMU-era gates:

1. **Instrumented code panics in interrupt context** — clang vectorizes the
   64-bit profile-counter increments into NEON (`vld1.64`), and LK panics on
   "floating point code in irq context" when that runs from an IPI handler (the
   PMU arming does). On the Pi the two cores' panic messages interleave into
   unreadable text; under QEMU the same message reads cleanly, which is what made
   it diagnosable. Fix: `-mfpu=none` on the instrumented module.
2. **BOLT's ARM builder could not reverse `cbz`/`cbnz`** —
   `llvm_unreachable("cannot reverse branch condition")` aborted `llvm-bolt` when
   instrumenting any function containing a compare-and-branch (they have no
   condition code; reversing one is swapping the opcode). Overlay patch
   `0011-bolt-arm-reverse-cbz.patch`.
3. **JITLink stub padding vs. call sites** — the Thumb v7 stub is 10 bytes but
   was built with 4-byte block alignment, and BOLT's integration disagreed with
   itself about the padding: call sites resolved to a packed 10-byte stride while
   the emitted section used 12. Call N landed N*2 bytes into the stub area: the
   first call hit exactly, the second landed on padding and fell through by luck
   (which is why an earlier two-stub build worked), later calls landed mid-stub
   and jumped through a stale `r12` to address 0. Overlay patch
   `0012-jitlink-arm-thumb-stub-alignment.patch` (Thumb stubs align 2).
4. (Step 8) LK's PMM page array landing on BOLT's segments, ThinLTO
   internalizing the function BOLT selects by name, and the optimized copy never
   being entered — see the Step 8 section.

Patches 0011 and 0012 are in the ATFE overlay only; the upstream-based series has
not been given them yet.

QEMU tooling for this: `scripts/qemu_console.py` (boot, type commands, print the
transcript), `scripts/qemu_bolt_profile.py`, and the QEMU twin project
`qemu-virt-arm32-bolt-test` (same `bolt_bench` module, SMP, PMU path; needs
`BOLT_EXTRA_ARGS=""` because that platform lacks the rpi4 reserve-window patch).
QEMU's own cycle and PMU numbers are not real and are never reported.
