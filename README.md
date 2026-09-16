# bolt-aarch32

Working toward an **AArch32 (ARM/Thumb) backend for LLVM BOLT**, with a bare-metal **Little Kernel** harness that collects instrumentation profiles **in RAM** — no OS, no filesystem, no `perf`.

Upstream [llvm-project](https://github.com/llvm/llvm-project) and [lk](https://github.com/littlekernel/lk) are **not forked**. Only deltas live in `overlay/` on GitHub. **llvm, lk, builds, and QEMU all run on the RunPod network volume** — see [docs/RESUME.md](docs/RESUME.md). Do not clone upstream on your laptop.

## Documentation

| Doc | What |
|-----|------|
| [docs/RESUME.md](docs/RESUME.md) | **Paused? Start here** — volume, pod, resume steps |
| [docs/why-bolt.md](docs/why-bolt.md) | What BOLT does that PGO and LTO cannot, with examples |
| [docs/PROJECT_PLAN.md](docs/PROJECT_PLAN.md) | Checklist, status, decisions |
| [docs/architecture.md](docs/architecture.md) | End-to-end flow, overlay split, toolchain baseline |
| [docs/aarch64-bare-metal.md](docs/aarch64-bare-metal.md) | Delta vs stock BOLT; runtime library; LK workloads |
| [docs/aarch32-bolt.md](docs/aarch32-bolt.md) | ARM/Thumb design, edge cases, upstream merge path |

## Phases

| Phase | Focus | Status |
|-------|-------|--------|
| 0 | Repo, scripts, RunPod | Done |
| 1 | LLVM + BOLT toolchain (`release/23.x`) | Done (on pod volume) |
| 2 | AArch64 in-RAM profiling + BOLT optimize on LK | **Done** — instrument → fdata → optimize boots |
| 3 | AArch32 backend → LLVM upstream | **P1 done** — patches `0003`–`0007` staged |

Phase 2 exists to prove bare-metal profiling on an architecture BOLT already supports, so that Phase 3 only has to solve the AArch32 problem.

## Quick start

**All builds run on the RunPod pod** (network volume `/workspace`). See [docs/RESUME.md](docs/RESUME.md) to restart after a pause.

```bash
# On the pod, after git pull:
cd /workspace/bolt-lk-overlay
./scripts/install-deps.sh          # once per fresh pod
./scripts/fetch-sources.sh         # only if third_party/ missing on volume
./scripts/build-llvm-bolt.sh       # Phase 1 — already done on volume
./scripts/apply-overlays.sh        # when overlay patches exist
./scripts/run-qemu-lk.sh             # boot LK in QEMU
./scripts/verify-bolt-workloads.sh   # bolt_bench → profile → optimize → boot
```

Copy `.env.example` to `.env` on the pod; set `NETWORK_VOLUME_ID=j1d9e6wq5l` to reattach the saved volume.

## Two LLVM bases, one repo

The AArch32 backend is built and verified against **two** LLVM forks side by
side — `BASE=upstream` (`llvm/llvm-project`, pinned, the actual upstreaming
target) and `BASE=atfe` (`arm/arm-toolchain`'s `arm-software` branch, Arm's
own actively-synced integration branch). Set `BASE` before running any
source/build/patch script; it defaults to `upstream` when unset:

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
`atfe-bolt-aarch32` — kept in sync by hand across every fix. That repo is
now archived at
[`shadowfax80/atfe-bolt-aarch32-legacy`](https://github.com/shadowfax80/atfe-bolt-aarch32-legacy)
(read-only; its history predates the 2026-09-15 merge into this repo) —
useful only if you need pre-merge commit history for the `arm-toolchain`
side of the work. Everything current lives here.

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
