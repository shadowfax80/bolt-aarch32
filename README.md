# bolt-aarch32

Working toward an **AArch32 (ARM/Thumb) backend for LLVM BOLT**, with a bare-metal **Little Kernel** harness that collects instrumentation profiles **in RAM** — no OS, no filesystem, no `perf`.

Upstream [llvm-project](https://github.com/llvm/llvm-project) and [lk](https://github.com/littlekernel/lk) are **not forked**. Only deltas live in `overlay/` on GitHub. **llvm, lk and the builds run in a local WSL2 Ubuntu, and measurements run on a real Raspberry Pi 4B** — see [docs/WSL_BUILD.md](docs/WSL_BUILD.md). (RunPod was used until 2026-09-30 and is no longer; its docs are kept as history.) Do not clone upstream on the Windows side.

## Documentation

| Doc | What |
|-----|------|
| [docs/TODO.md](docs/TODO.md) | Active ATFE correctness work and owner-deferred scope |
| [docs/CORRECTNESS_TODO.md](docs/CORRECTNESS_TODO.md) | Twelve correctness workstreams, priorities and completion criteria |
| [docs/CORRECTNESS_REVIEW_0038.md](docs/CORRECTNESS_REVIEW_0038.md) | Current review through overlay 0038: fresh defects, passing evidence and correctness limits |
| [docs/CORRECTNESS_PRIORITY_TODO.md](docs/CORRECTNESS_PRIORITY_TODO.md) | Fresh ordered work queue from the current correctness review |
| [docs/WSL_BUILD.md](docs/WSL_BUILD.md) | **Start here** — build the toolchain locally in WSL2 and measure on the Pi |
| [docs/RPI4_HARDWARE_VERIFICATION.md](docs/RPI4_HARDWARE_VERIFICATION.md) | Real Pi 4B results: staged PGO / ThinLTO / BOLT, multi-function BOLT, PGO lab, bugs found |
| [docs/VOLUME_RECREATION.md](docs/VOLUME_RECREATION.md) | Historical — recreating the RunPod volume (both volumes are now deleted) |
| [docs/RESUME.md](docs/RESUME.md) | Historical resume notes (RunPod era) |
| [docs/why-bolt.md](docs/why-bolt.md) | What BOLT does that PGO and LTO cannot, with examples |
| [docs/PROJECT_PLAN.md](docs/PROJECT_PLAN.md) | Checklist, status, decisions |
| [docs/architecture.md](docs/architecture.md) | End-to-end flow, overlay split, toolchain baseline |
| [docs/aarch64-bare-metal.md](docs/aarch64-bare-metal.md) | Delta vs stock BOLT; runtime library; LK workloads |
| [docs/aarch32-bolt.md](docs/aarch32-bolt.md) | ARM/Thumb design, edge cases, upstream merge path |
| [docs/BOLT_AARCH32_BACKEND.md](docs/BOLT_AARCH32_BACKEND.md) | Backend reference: design principles, interfaces, AArch64 diff, bare-metal user guide |
| [docs/KNOWN_LIMITATIONS.md](docs/KNOWN_LIMITATIONS.md) | **Before upstreaming** — open gaps, blockers, and deferred scope, with verification status |
| [docs/UPSTREAMING_REVIEW.md](docs/UPSTREAMING_REVIEW.md) | Submission-readiness review: what a BOLT maintainer sees on first open, what's already right, ranked fixes |

## Phases

| Phase | Focus | Status |
|-------|-------|--------|
| 0 | Repo, scripts | Done (RunPod until 2026-09-30, local WSL2 since) |
| 1 | LLVM + BOLT toolchain | Done — ATFE `BASE=atfe`, LLVM 24.0.0git, built locally in WSL2 |
| 2 | AArch64 in-RAM profiling + BOLT optimize on LK | **Done** — instrument → fdata → optimize boots |
| 3 | AArch32 backend → LLVM upstream | **P1 done** — patches `0003`–`0007` staged; upstream blockers deferred (see [KNOWN_LIMITATIONS](docs/KNOWN_LIMITATIONS.md)) |
| 4 | Real Raspberry Pi 4B verification | **Done** — staged PGO → ThinLTO → BOLT with the Pi's PMU, multi-function BOLT ([results](docs/RPI4_HARDWARE_VERIFICATION.md)) |

Phase 2 exists to prove bare-metal profiling on an architecture BOLT already supports, so that Phase 3 only has to solve the AArch32 problem.

## Quick start

**Builds run in local WSL2; measurements run on the Pi.** Full walkthrough: [docs/WSL_BUILD.md](docs/WSL_BUILD.md).

```bash
# One time (from the Windows checkout):
wsl -d Ubuntu -u root -- bash scripts/wsl-setup.sh deps
wsl -d Ubuntu          -- bash scripts/wsl-setup.sh build     # ~1 h: ATFE clang/lld/BOLT + runtimes
# After edits:
wsl -d Ubuntu          -- bash scripts/wsl-setup.sh sync
# One staged Pi measurement (PGO -> ThinLTO -> BOLT), from Git Bash with the Pi on COM5:
scripts/pi4/bolt_stage.sh 6:3
```

The QEMU path (`scripts/run-qemu-lk.sh`, `scripts/verify-bolt-workloads.sh`) still works inside WSL for debugging; it is never the source of a reported number.

`.env.example`'s RunPod block is legacy and unused.

## Two LLVM bases, one repo

The repository retains overlays for two LLVM bases: `BASE=upstream`
(`llvm/llvm-project`) and `BASE=atfe` (`arm/arm-toolchain`'s `arm-software`
branch). **Current correctness development and verification are ATFE only;
upstream work is stopped by owner request.** The latest fixes are not certified
on upstream. Set `BASE=atfe` before running source/build/patch scripts; the
generic scripts still default to `upstream` when unset:

```bash
BASE=atfe ./scripts/ensure-llvm-source.sh
BASE=atfe ./scripts/apply-overlays.sh
BASE=atfe ./scripts/build-llvm-bolt.sh
BASE=atfe ARCH=arm32 ./scripts/instrument-lk-bolt.sh
```

Each base gets its own source tree (`third_party/llvm-project-$BASE/`),
build directory (`build-$BASE/`), and patch set
(`overlay/llvm/patches/$BASE/`) — see `scripts/resolve-base.sh` for exactly
what each `BASE` value resolves to (remote, pinned commit, paths). LK
(`third_party/lk/`) is shared and base-agnostic; only `llvm-bolt` itself
needs building per base.

This repo used to be two separate repos — `bolt-aarch32` (this one) and
`atfe-bolt-aarch32` — kept in sync by hand across every fix. That second
repo has been deleted; its pre-merge history is kept offline as a git
bundle (`legacy-archives/atfe-bolt-aarch32-legacy.bundle`, gitignored, so back it up outside this checkout) rather than on GitHub, since
nothing current depends on it. Everything live is here.

The two patch sets aren't byte-identical (real API drift between the two
LLVM bases — e.g. `--instrument-funcs-file` exists on `upstream`'s pinned
commit but was removed upstream by the time `arm-software` synced past it;
`scripts/instrument-lk-bolt.sh` now uses the base-agnostic `--funcs-file`
instead). Expect some drift to keep tracking as `arm-software` keeps moving
and `upstream`'s pin gets bumped independently.

## Layout

```
overlay/llvm/patches/upstream/  # patch set for BASE=upstream (llvm/llvm-project)
overlay/llvm/patches/atfe/      # patch set for BASE=atfe (arm/arm-toolchain)
overlay/lk/patches/             # linker script, bolt_bench, dump hook — shared, base-agnostic
scripts/                        # source fetch, build, RunPod, BOLT instrument/optimize
scripts/resolve-base.sh         # BASE=upstream|atfe -> LLVM_DIR/LLVM_COMMIT/LLVM_REMOTE/PATCH_DIR/BUILD_DIR
docs/                           # plan + design
third_party/                    # llvm-project-upstream/, llvm-project-atfe/, lk/ — gitignored, cloned on demand
build-upstream/, build-atfe/    # per-base build output — gitignored
```

## License

Overlay scripts and docs: MIT. Upstream LLVM and LK keep their own licenses.
