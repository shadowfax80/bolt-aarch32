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
| 2 | AArch64 in-RAM profiling + `bolt_bench` on LK | Started — LK+QEMU OK; runtime next |
| 3 | AArch32 backend → LLVM upstream | Not started |

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
```

Copy `.env.example` to `.env` on the pod; set `NETWORK_VOLUME_ID=j1d9e6wq5l` to reattach the saved volume.

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
