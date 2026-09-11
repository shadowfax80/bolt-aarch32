# bolt-lk-overlay

Overlay repo for **BOLT on bare-metal Little Kernel** — AArch64 RAM profiling first, then **AArch32 BOLT** for LLVM upstream.

Upstream [llvm-project](https://github.com/llvm/llvm-project) and [lk](https://github.com/littlekernel/lk) are **not forked**. Only deltas live in `overlay/`; sources are cloned into `third_party/` by scripts.

## Documentation

| Doc | What |
|-----|------|
| [docs/PROJECT_PLAN.md](docs/PROJECT_PLAN.md) | Checklist and status |
| [docs/architecture.md](docs/architecture.md) | End-to-end flow, overlay split |
| [docs/aarch64-bare-metal.md](docs/aarch64-bare-metal.md) | Bare-metal delta vs stock BOLT; LK workloads |
| [docs/aarch32-bolt.md](docs/aarch32-bolt.md) | ARM/Thumb design, edge cases, upstream merge path |

## Phases

| Phase | Focus | Status |
|-------|-------|--------|
| 0 | Repo, scripts, RunPod | Done |
| 1 | LLVM + BOLT toolchain | In progress |
| 2 | AArch64 RAM profile + `bolt_bench` on LK | Not started |
| 3 | AArch32 backend → LLVM upstream | Not started |

## Quick start

```bash
git clone https://github.com/somraj80/bolt-lk-overlay.git
cd bolt-lk-overlay
./scripts/init-submodules.sh      # clones llvm + lk into third_party/
./scripts/install-deps.sh         # Linux
./scripts/build-llvm-bolt.sh
./scripts/apply-overlays.sh       # when patches exist
./scripts/build-lk-aarch64.sh
```

## Layout

```
overlay/llvm/patches/   # bolt-rt, AArch32 backend slices (→ upstream when merged)
overlay/lk/patches/     # linker script, bolt_bench, dump hook
scripts/                # build, RunPod, ram-dump-to-fdata (TBD)
docs/                   # plan + architecture
third_party/            # llvm-project, lk (gitignored; cloned on demand)
```

## License

Overlay scripts and docs: MIT. Upstream LLVM and LK keep their licenses.
