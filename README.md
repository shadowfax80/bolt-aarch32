# bolt-aarch32

Working toward an **AArch32 (ARM/Thumb) backend for LLVM BOLT**, with a bare-metal **Little Kernel** harness that collects instrumentation profiles **in RAM** — no OS, no filesystem, no `perf`.

Upstream [llvm-project](https://github.com/llvm/llvm-project) and [lk](https://github.com/littlekernel/lk) are **not forked**. Only deltas live in `overlay/`; the upstream trees are cloned into `third_party/` (gitignored) by `scripts/fetch-sources.sh`. Patches are deleted from `overlay/` as they merge upstream.

## Documentation

| Doc | What |
|-----|------|
| [docs/why-bolt.md](docs/why-bolt.md) | What BOLT does that PGO and LTO cannot, with examples |
| [docs/PROJECT_PLAN.md](docs/PROJECT_PLAN.md) | Checklist, status, decisions |
| [docs/architecture.md](docs/architecture.md) | End-to-end flow, overlay split, toolchain baseline |
| [docs/aarch64-bare-metal.md](docs/aarch64-bare-metal.md) | Delta vs stock BOLT; runtime library; LK workloads |
| [docs/aarch32-bolt.md](docs/aarch32-bolt.md) | ARM/Thumb design, edge cases, upstream merge path |

## Phases

| Phase | Focus | Status |
|-------|-------|--------|
| 0 | Repo, scripts, RunPod | Done |
| 1 | LLVM + BOLT toolchain (`release/23.x`) | In progress |
| 2 | AArch64 in-RAM profiling + `bolt_bench` on LK | Not started |
| 3 | AArch32 backend → LLVM upstream | Not started |

Phase 2 exists to prove bare-metal profiling on an architecture BOLT already supports, so that Phase 3 only has to solve the AArch32 problem.

## Quick start

```bash
git clone https://github.com/somraj80/bolt-aarch32.git
cd bolt-aarch32
./scripts/install-deps.sh         # Ubuntu 24.04
./scripts/fetch-sources.sh        # clones llvm + lk into third_party/
./scripts/build-llvm-bolt.sh
./scripts/apply-overlays.sh       # once patches exist
./scripts/build-lk-aarch64.sh
```

Copy `.env.example` to `.env` for RunPod and branch settings; see the header for how to load it.

## Layout

```
overlay/llvm/patches/   # bare-metal runtime, AArch32 backend slices
overlay/lk/patches/     # linker script, bolt_bench, dump hook
scripts/                # source fetch, build, RunPod, ram-dump-to-fdata (TBD)
docs/                   # plan + design
third_party/            # llvm-project, lk — gitignored, cloned on demand
```

## License

Overlay scripts and docs: MIT. Upstream LLVM and LK keep their own licenses.
