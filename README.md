# bolt-lk-overlay

Overlay repo for **BOLT on bare-metal Little Kernel** — AArch64 in-RAM profiling first, then an **AArch32 BOLT backend** for LLVM upstream.

Upstream [llvm-project](https://github.com/llvm/llvm-project) and [lk](https://github.com/littlekernel/lk) are **not forked**. Only deltas live in `overlay/`; the upstream trees are cloned into `third_party/` (gitignored) by `scripts/fetch-sources.sh`.

## Documentation

| Doc | What |
|-----|------|
| [docs/PROJECT_PLAN.md](docs/PROJECT_PLAN.md) | Checklist, status, decisions |
| [docs/architecture.md](docs/architecture.md) | End-to-end flow, overlay split, toolchain baseline |
| [docs/aarch64-bare-metal.md](docs/aarch64-bare-metal.md) | Delta vs stock BOLT; runtime library; LK workloads |
| [docs/aarch32-bolt.md](docs/aarch32-bolt.md) | ARM/Thumb design, edge cases, upstream merge path |

## Phases

| Phase | Focus | Status |
|-------|-------|--------|
| 0 | Repo, scripts, RunPod | Done |
| 1 | LLVM + BOLT toolchain (`release/23.x`) | In progress |
| 2 | AArch64 RAM profile + `bolt_bench` on LK | Not started |
| 3 | AArch32 backend → LLVM upstream | Not started |

## Quick start

```bash
git clone https://github.com/somraj80/bolt-lk-overlay.git
cd bolt-lk-overlay
./scripts/install-deps.sh         # Ubuntu 24.04
./scripts/fetch-sources.sh        # clones llvm + lk into third_party/
./scripts/build-llvm-bolt.sh
./scripts/apply-overlays.sh       # once patches exist
./scripts/build-lk-aarch64.sh
```

Copy `.env.example` to `.env` for RunPod and branch settings.

## Layout

```
overlay/llvm/patches/   # bare-metal runtime, AArch32 slices (deleted as they merge upstream)
overlay/lk/patches/     # linker script, bolt_bench, dump hook
scripts/                # source fetch, build, RunPod, ram-dump-to-fdata (TBD)
docs/                   # plan + design
third_party/            # llvm-project, lk — gitignored, cloned on demand
```

## License

Overlay scripts and docs: MIT. Upstream LLVM and LK keep their own licenses.
