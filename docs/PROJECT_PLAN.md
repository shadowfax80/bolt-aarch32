# Project plan

**Repo:** [somraj80/bolt-lk-overlay](https://github.com/somraj80/bolt-lk-overlay)  
**Updated:** 2026-09-11

**Goal:** bare-metal BOLT on LK (AArch64 first), then AArch32 BOLT backend merged to LLVM upstream.

| Doc | Contents |
|-----|----------|
| [architecture.md](architecture.md) | Overlay model, data flow, scope |
| [aarch64-bare-metal.md](aarch64-bare-metal.md) | Delta from stock BOLT, workloads |
| [aarch32-bolt.md](aarch32-bolt.md) | ARM/Thumb design, edge cases, upstream PRs |

---

## Status

| Phase | Focus | Status |
|-------|-------|--------|
| 0 | Repo, scripts, RunPod | **Done** |
| 1 | LLVM/BOLT toolchain build | **In progress** |
| 2 | AArch64 bare-metal profile + LK workloads | Not started |
| 3 | AArch32 BOLT backend → LLVM upstream | Not started |

**Pod:** `kn1kscmdlxcvge` (EU-RO-1, 8 vCPU, volume `j1d9e6wq5l` @ `/workspace`)

---

## Phase 0 — Infrastructure ✓

- [x] Overlay repo scaffold, scripts, cmake
- [x] Idempotent `ensure-*-source.sh` (flock + marker)
- [x] GitHub push; RunPod pod + 150 GB volume (single volume, EU-RO-1)
- [x] Deps installed on pod; repo at `/workspace/bolt-lk-overlay`

---

## Phase 1 — Toolchain

| # | Task | Status |
|---|------|--------|
| 1.1 | Full clone `llvm-project` release/19.x | In progress |
| 1.2 | `.overlay-source-ok` + `llvm/utils/TableGen` | Pending |
| 1.3 | `build-llvm-bolt.sh` (cmake + ninja) | Pending |
| 1.4 | Verify `llvm-bolt`, `clang`, `ld.lld` | Pending |
| 1.5 | `package-toolchain.sh` + download tarball | Pending |
| 1.6 | Stop pod when done | Pending |

```bash
tail -f /workspace/build-llvm.log
pgrep -a 'git clone|ninja|cmake'
```

---

## Phase 2 — AArch64 bare-metal BOLT on LK

LK = test harness. **Boot is smoke test only**; real validation uses `bolt_bench` workloads (see [aarch64-bare-metal.md](aarch64-bare-metal.md)).

### Overlay patches to land

| Patch | Target | Purpose |
|-------|--------|---------|
| `bolt-rt-baremetal.patch` | `bolt/runtime/` | RAM counters, no syscalls |
| `linker-bolt-profile.patch` | LK linker script | `.bolt_profile` section |
| `platform-dump-profile.patch` | LK platform | Dump profile RAM |
| `app-bolt-bench.patch` | LK `app/` | hot_loop, memcpy, threads |

### Steps

| # | Task | Status |
|---|------|--------|
| 2.1 | `ensure-lk-source.sh` + build `qemu-virt-arm64-test` (`-Wl,-q`) | |
| 2.2 | `bolt-rt-baremetal.patch` — RAM profile layout | |
| 2.3 | LK linker + dump hook patches | |
| 2.4 | `llvm-bolt -instrument` → `lk.instr.elf` (`--no-lse-atomics`) | |
| 2.5 | **T0:** boot smoke — counters non-zero | |
| 2.6 | **`app-bolt-bench`** — T1 hot_loop, T2 memcpy | |
| 2.7 | `scripts/ram-dump-to-fdata.sh` — host `.fdata` | |
| 2.8 | `llvm-bolt -data=prof.fdata` → `lk.bolt.elf` | |
| 2.9 | **T1/T2** on optimized ELF — measure speedup | |
| 2.10 | (Stretch) T3 threads, T4 timer IRQ | |

---

## Phase 3 — AArch32 BOLT → LLVM upstream

Full design: [aarch32-bolt.md](aarch32-bolt.md).

| # | Task | Status |
|---|------|--------|
| 3.1 | ELF32 reader + ARM-mode CFG | |
| 3.2 | MCPlusBuilder + branch veneers | |
| 3.3 | Thumb-2, IT blocks, interworking | |
| 3.4 | Instrumentation + RAM profile (reuse Phase 2) | |
| 3.5 | LK `qemu-virt-arm32-test` + `bolt_bench` | |
| 3.6 | Lit tests per upstream PR | |
| 3.7 | Merge backend to llvm-project; shrink overlay | |

---

## Scripts

| Script | Purpose |
|--------|---------|
| `ensure-llvm-source.sh` / `ensure-lk-source.sh` | Idempotent clones |
| `build-llvm-bolt.sh` | Toolchain build |
| `build-lk-aarch64.sh` | LK AArch64 ELF |
| `apply-overlays.sh` | Apply `overlay/*/patches/*.patch` |
| `package-toolchain.sh` | Tarball |
| `create-pod.sh` / `destroy-pod.sh` | RunPod |

---

## Cost

Pod ~$0.52/hr while running. Stop pod after Phase 1 tarball is downloaded.
