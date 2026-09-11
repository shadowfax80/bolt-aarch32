# Overlay patches

Incremental changes on top of upstream — **not forks**. Applied by `scripts/apply-overlays.sh`.

```
overlay/
├── llvm/patches/     # bolt/runtime, bolt/lib (AArch32 backend slices)
└── lk/patches/       # linker script, bolt_bench app, profile dump
```

## Expected patches

| Patch (planned) | Upstream path | Purpose |
|-----------------|---------------|---------|
| `bolt-rt-baremetal.patch` | `bolt/runtime/` | RAM counters, no syscalls, freestanding |
| `linker-bolt-profile.patch` | LK linker script | `.bolt_profile` section |
| `platform-dump-profile.patch` | LK platform | Export the profile region |
| `app-bolt-bench.patch` | LK `app/` | Workload benchmarks |
| `aarch32-*.patch` | `bolt/lib/Target/` | AArch32 backend, until merged upstream |

Selecting the bare-metal runtime needs no patch — `llvm-bolt --runtime-instrumentation-lib=` already exists upstream.

When a patch lands in llvm-project, **delete it here**.

See [docs/architecture.md](../docs/architecture.md).
