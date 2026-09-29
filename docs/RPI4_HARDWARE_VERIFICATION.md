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
| 8 | BOLT on top of PGO+ThinLTO | Not started |
| 9 | PMU counter reading in `bolt_bench.c` (cycles + cache misses) | Not started (cycle counter already live; cache-miss events still to add) |
| 10 | Full staged comparison, real Pi, several runs each | Not started |

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
