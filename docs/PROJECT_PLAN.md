# Project plan

**Repo:** [somraj80/bolt-aarch32](https://github.com/somraj80/bolt-aarch32)  
**Updated:** 2026-09-11

**Goal:** an AArch32 BOLT backend merged into LLVM upstream, proven on a bare-metal LK harness with in-RAM profiling. AArch64 comes first because BOLT already supports it, so Phase 2 isolates the bare-metal problem from the new-backend problem.

| Doc | Contents |
|-----|----------|
| [why-bolt.md](why-bolt.md) | What BOLT adds over PGO and LTO, with examples |
| [architecture.md](architecture.md) | Overlay model, data flow, toolchain baseline |
| [aarch64-bare-metal.md](aarch64-bare-metal.md) | Delta from stock BOLT, runtime library, workloads |
| [aarch32-bolt.md](aarch32-bolt.md) | ARM/Thumb design, edge cases, upstream PR ladder |

---

## Status

| Phase | Focus | Status |
|-------|-------|--------|
| 0 | Repo, scripts, RunPod | **Done** |
| 1 | LLVM/BOLT toolchain build | **In progress** — on `release/23.x` |
| 2 | AArch64 bare-metal profile + LK workloads | Not started |
| 3 | AArch32 BOLT backend → LLVM upstream | Not started |

**Pod:** `kn1kscmdlxcvge` (EU-RO-1, 8 vCPU, volume `j1d9e6wq5l` at `/workspace`)

---

## Phase 0 — Infrastructure ✓

- [x] Overlay repo scaffold, scripts, cmake cache
- [x] Idempotent `ensure-*-source.sh` (flock, branch-aware marker)
- [x] GitHub push; RunPod pod + a single 150 GB volume in EU-RO-1
- [x] Deps installed on pod; repo checked out under `/workspace`

---

## Phase 1 — Toolchain

| # | Task | Status |
|---|------|--------|
| 1.1 | Clone `llvm-project`, checkout `release/23.x` | In progress |
| 1.2 | Verify `.overlay-source-ok` records the right branch | Pending |
| 1.3 | `build-llvm-bolt.sh` — cmake + ninja | Pending |
| 1.4 | Verify `llvm-bolt`, `clang`, `ld.lld`, llvm-binutils | Pending |
| 1.5 | `package-toolchain.sh`, download tarball | Pending |
| 1.6 | Stop the pod | Pending |

```bash
tail -f /workspace/build-llvm.log
pgrep -a 'git|ninja|cmake'
```

### Why `release/23.x`

`release/19.x` was an unexamined default in the original scaffold. It breaks the plan:

- **`--no-lse-atomics` does not exist in 19.x** (verified by grep). QEMU's cortex-a53 has no LSE, so without it BOLT emits `stadd` and the instrumented kernel faults. The flag landed in LLVM 22.
- Phase 3 upstreaming is reviewed against `main`; a 2024 base means a punishing rebase.
- 19.x is end-of-life. Current stable is 23.1.0 (Aug 2026).

Phase 3 moves to `main` pinned at a commit, since that is what upstream PRs target.

### Pod lessons

- No shallow clones of llvm-project — `llvm/utils/TableGen` goes missing and cmake fails.
- Never run parallel clones; `ensure-llvm-source.sh` holds a flock.
- Background work over SSH needs `setsid nohup … </dev/null &`, or it dies with the session.
- CPU pods cap the container disk at 20 GB — source and build live on `/workspace`.
- Use `runpod/base:1.0.2-ubuntu2404`; plain `ubuntu:24.04` ships no sshd.

---

## Phase 2 — AArch64 bare-metal BOLT on LK

LK is the harness. Boot is a smoke test; real validation uses `bolt_bench` workloads. See [aarch64-bare-metal.md](aarch64-bare-metal.md).

**Main risk:** BOLT builds `libbolt_rt_instr.a` for the host arch only, and upstream's per-triple fix ([#187308](https://github.com/llvm/llvm-project/pull/187308)) is unmerged. We supply our own runtime for `aarch64-none-elf` and select it with `--runtime-instrumentation-lib=`, which needs no BOLT source patch.

### Overlay patches to land

| Patch | Target | Purpose |
|-------|--------|---------|
| `bolt-rt-baremetal.patch` | `bolt/runtime/` | RAM counters, no syscalls, freestanding |
| `linker-bolt-profile.patch` | LK linker script | `.bolt_profile` section |
| `platform-dump-profile.patch` | LK platform | Export the profile region |
| `app-bolt-bench.patch` | LK `app/` | hot_loop, memcpy, threads |

### Steps

| # | Task |
|---|------|
| 2.1 | `ensure-lk-source.sh`; build `qemu-virt-arm64-test` with `--emit-relocs` |
| 2.2 | Write the bare-metal runtime; cross-build for `aarch64-none-elf` |
| 2.3 | LK linker script + dump hook patches |
| 2.4 | `llvm-bolt -instrument --no-lse-atomics --runtime-instrumentation-lib=…` |
| 2.5 | **T0:** boot smoke test, counters non-zero |
| 2.6 | `app-bolt-bench` — **T1** hot_loop, **T2** memcpy |
| 2.7 | `scripts/ram-dump-to-fdata.sh` |
| 2.8 | `llvm-bolt -data=prof.fdata` → `lk.bolt.elf` |
| 2.9 | Re-run T1/T2, measure with `CNTVCT_EL0` |
| 2.10 | Stretch: T3 threads, T4 timer IRQ |

---

## Phase 3 — AArch32 BOLT → LLVM upstream

Full design in [aarch32-bolt.md](aarch32-bolt.md).

| # | Task |
|---|------|
| 3.1 | Rebase overlay onto `main` |
| 3.2 | ELF32 reader + ARM-mode CFG |
| 3.3 | MCPlusBuilder + branch veneers |
| 3.4 | Thumb-2, IT blocks, interworking |
| 3.5 | Instrumentation reusing the Phase 2 RAM profile |
| 3.6 | LK `qemu-virt-arm32-test` + `bolt_bench` |
| 3.7 | Lit tests per PR; merge; shrink the overlay |

---

## Scripts

| Script | Purpose |
|--------|---------|
| `fetch-sources.sh` | Clone both upstreams |
| `ensure-llvm-source.sh` / `ensure-lk-source.sh` | Idempotent, branch-aware checkouts |
| `build-llvm-bolt.sh` | Toolchain build |
| `build-lk-aarch64.sh` | LK AArch64 ELF |
| `apply-overlays.sh` | Apply `overlay/*/patches/*.patch` |
| `package-toolchain.sh` | Tarball, with presence checks |
| `create-pod.sh` / `destroy-pod.sh` | RunPod lifecycle |

---

## Cost

The pod bills at roughly $0.52/hr while running, and keeps running when the laptop is off. Stop it once the Phase 1 tarball is downloaded. Keep exactly one network volume.
