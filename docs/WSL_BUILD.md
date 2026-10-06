# Building and running everything locally (WSL2) with the real Pi

This is the current way to work on the project. Since 2026-09-30 nothing runs on
RunPod: EU-RO-1 had no CPU capacity for over an hour (every flavor, 2/4/8 vCPU), the work
moved to a local WSL2 Ubuntu, and the network volume `3g114i4sby` was deleted at the
owner's request. The older RunPod docs ([RUNPOD.md](history/RUNPOD.md), [RESUME.md](history/RESUME.md),
[VOLUME_RECREATION.md](history/VOLUME_RECREATION.md)) are kept as history.

## What you need

- Windows with WSL2 and an Ubuntu distro (developed on Ubuntu 26.04, kernel 6.18).
- The Pi 4B on a serial console (`COM5` here) with the LK chainloader on its SD card.
- RAM: give WSL **8 GB** in `%USERPROFILE%\.wslconfig` and no more on a 16 GB machine:

  ```
  [wsl2]
  memory=8GB
  processors=8
  swap=8GB
  ```

  With `memory=12GB` the machine ran short of memory during the LLVM build and the build
  was killed.

## Coordination before using shared resources

Read [HANDOFF.md](HANDOFF.md), publish the item claim/live-tree lock before
source or build mutations, and reserve the Pi separately before serial access.
The setup steps below are for a fresh tree. For an existing dirty live tree,
synchronize the repository with `git pull --ff-only`; do not reapply overlays.

## One-time setup

```
wsl -d Ubuntu -u root -- bash <repo>/scripts/wsl-setup.sh deps     # apt packages (root, no sudo password needed)
wsl -d Ubuntu          -- bash <repo>/scripts/wsl-setup.sh build    # ATFE clang/lld/BOLT/llvm-profdata + both bare-metal runtimes
```

`build` copies the Windows checkout (uncommitted changes included) into `~/bolt-aarch32`
on WSL's own filesystem, clones ATFE (`BASE=atfe`, LLVM 24.0.0git) and LK at their pins,
applies every overlay patch, and builds. It takes about an hour on 8 cores.
`JOBS=8 wsl-setup.sh build` caps the compile jobs.

`wsl-setup.sh sync` also re-installs LK overlay files, so it is a shared-source
mutation and requires the live-tree lock. It is not a routine repository-only
sync. Use `git pull --ff-only` in the WSL repo for published documentation/code
changes that do not require applying source overlays.

**Line endings:** a Windows checkout can have CRLF line endings, which makes `git am` fail on
the patches and breaks shell scripts. `wsl-setup.sh` normalizes the WSL copy to LF.

## Main compiler flow and Pi measurements

The normal optimized compiler image uses **ordinary IR-PGO and CSPGO together
with module ThinLTO**. Run `py -3.12 scripts/pi4/cspgo_cycle_wsl.py` from Windows
with `--wsl-root <isolated synced repo> --out <fresh output>`; it performs both
training rounds, merges ordinary+CS counts and builds `cspgo_thinlto`.
The [recipe](verification/CSPGO_PIPELINE.md) describes inputs and optional BOLT.
`build-variants.sh` defaults to this final image when no variant is named;
profiles must already exist. The IR-only build remains a comparison control.

Windows Git Bash entry points and measurement helpers:

| Script | What it does |
|---|---|
| `scripts/pi4/pgo_cycle_wsl.sh` | Main two-round IR-PGO/CSPGO cycle; same `--wsl-root`/`--out` options as the Python entry. Historical frontend cycle requires explicit `--frontend` |
| `scripts/pi4/bolt_stage.sh <M or M:X>` | Historical frontend-PGO staged comparison: PGO, ThinLTO, BOLT edge profile and no-reorder control; explicitly selects `--frontend`. For the main CSPGO pipeline use the recipe's sealed sampling route |
| `scripts/pi4/multi_stage.sh` | multi-function BOLT: six functions, spacing control |
| `scripts/pi4/stair_sweep.sh` | ThinLTO footprint sweep |
| `scripts/pi4/pgo_lab_measure.py`, `pi4_compare.py` | the interleaved measurement (checksum-checked, 95% confidence intervals via `stats_util.py`, one retry on a hung boot) |
| `scripts/verify-all-wsl.sh` (run inside WSL) | all five QEMU gates on `BASE=atfe`, PASS/FAIL summary, logs in `~/verify-logs/`. Last run 2026-09-30: harness, veneer, workloads PASS; milestones and identity FAIL at P1 (known U2 gap, see KNOWN_LIMITATIONS) |
| `bolt_bench pmu_probe <hex ev> ...` | which PMU events this core counts (Step 9 in the results doc) |

Runs use the LK watchdog `reboot` command for a software reset; a physical power cycle is
only needed if LK is hung or a non-LK payload was loaded (not needed so far).

## Rules and traps

- **No FPU, NEON or vector code anywhere** (the target core has none). Every ARM32 compile
  step needs `-mfpu=none -mfloat-abi=soft`; `scripts/check-no-fpu.sh <elf|obj|.a>...`
  fails on any `v*` mnemonic and runs before every profiling step.
- `wsl.exe` expands `$variables` in the Windows-side shell before they reach bash. Put the
  WSL-side steps in a script file (`multi_stage_wsl.sh`, `bolt_stage_wsl.sh`) instead of a
  quoted one-liner.
- If COM5 is busy, check the published Pi reservation and process ownership.
  Do not terminate another agent's serial session; stop only your own stale process.

Results are in [RPI4_HARDWARE_VERIFICATION.md](history/RPI4_HARDWARE_VERIFICATION.md).

## Historical fresh-clone verification (2026-09-30; not proof for later overlays)

A fresh `git clone` of this repo, a full toolchain build (`wsl-setup.sh build`, about 1.5 h with
4 jobs) and `scripts/repro-compare.sh <counters.bin>` produce the same results as the everyday
tree: 12 of 12 comparisons identical at commit 6bfec33+. Covered: patched LLVM and LK source
trees, the `baseline` and `pgo_thinlto` images, the BOLT edge-instrumented image, and BOLT's
`.fdata`, function map and optimized image from the same Pi counters. All `.bin` files are
byte-identical. `.elf` files are not byte-identical (each embeds its tree's absolute path in
debug info, and ThinLTO names promoted locals `foo.llvm.<path hash>`), so those are compared by
symbol table with the hash normalised.

The check found one real bug: 24 tracked `.sh` files were mode 100644 (Windows records no exec
bit), so `build-pgo-rt-baremetal.sh` failed with "Permission denied" on a Linux clone. Fixed in
6bfec33 with `git update-index --chmod=+x`; run that for any new script.

Other notes: `PI4_FAST_LOADER=<img>` (see `tools/pi4-serialboot-fast/`) hot-loads the 3 Mbaud
chainloader for every Pi script, no SD-card change needed. `scripts/mem-guard.sh` drops the
page cache when WSL memory runs low; run one heavy job at a time.
