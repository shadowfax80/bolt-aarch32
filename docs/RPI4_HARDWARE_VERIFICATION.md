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
| 4 | Replace QEMU's memory-dump mechanism with a UART one | Not started |
| 5 | Add a two-file composite benchmark (cross-TU, for ThinLTO to have something to do) | Not started |
| 6 | Compile-time PGO support | Not started |
| 7 | ThinLTO on top of PGO | Not started |
| 8 | BOLT on top of PGO+ThinLTO | Not started |
| 9 | PMU counter reading in `bolt_bench.c` (cycles + cache misses) | Not started |
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
