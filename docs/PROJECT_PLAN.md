# Project plan

**Repo:** [somraj80/bolt-aarch32](https://github.com/somraj80/bolt-aarch32)  
**Updated:** 2026-09-11 (paused — pod stopped)

**Resume:** [RESUME.md](RESUME.md)

**Goal:** an AArch32 BOLT backend merged into LLVM upstream, proven on a bare-metal LK harness with in-RAM profiling.

| Doc | Contents |
|-----|----------|
| [RESUME.md](RESUME.md) | **Start here** — volume paths, how to restart pod |
| [why-bolt.md](why-bolt.md) | What BOLT adds over PGO and LTO |
| [architecture.md](architecture.md) | Overlay model, data flow |
| [aarch64-bare-metal.md](aarch64-bare-metal.md) | Bare-metal delta, runtime, workloads |
| [aarch32-bolt.md](aarch32-bolt.md) | ARM/Thumb design, upstream path |

---

## Status

| Phase | Focus | Status |
|-------|-------|--------|
| 0 | Repo, scripts, RunPod | **Done** |
| 1 | LLVM/BOLT toolchain | **Done** |
| 2 | AArch64 bare-metal + LK | **Started** — LK built, QEMU boot OK; runtime TBD |
| 3 | AArch32 BOLT → upstream | Not started |

**Pod:** `kn1kscmdlxcvge` — **STOPPED**  
**Volume:** `j1d9e6wq5l` @ `/workspace` (EU-RO-1)

---

## Phase 0 ✓

- [x] Overlay repo, scripts, RunPod + single 150 GB volume
- [x] All upstream work on pod volume only (not laptop)

---

## Phase 1 ✓

| # | Task | Status |
|---|------|--------|
| 1.1 | `llvm-project` `release/23.x` | Done — `069ef0e7cb36` |
| 1.2 | Toolchain build (clang, lld, llvm-bolt, binutils) | Done — LLVM 23.1.2 |
| 1.3 | Tarball on volume | Done — `llvm-bolt-toolchain.tar.gz` (167 MB) |
| 1.4 | Pod stopped | Done — 2026-09-11 |

---

## Phase 2 — in progress

| # | Task | Status |
|---|------|--------|
| 2.1 | LK clone + build `qemu-virt-arm64-test` | **Done** — `lk.elf` on volume |
| 2.1b | QEMU boot smoke test on pod | **Done** — shell prompt |
| 2.2 | Bare-metal bolt-rt (`libbolt_rt_baremetal.a`) | **Next** |
| 2.3 | LK linker + dump + `bolt_bench` patches | Pending |
| 2.4 | `llvm-bolt -instrument --no-lse-atomics` | Pending |
| 2.5–2.10 | Profile, optimize, measure | Pending |

---

## Phase 3 — not started

See [aarch32-bolt.md](aarch32-bolt.md).

---

## Scripts (on pod at `/workspace/bolt-lk-overlay/scripts/`)

| Script | Purpose |
|--------|---------|
| `build-status.sh` | Ninja progress; `-f` for live log |
| `build-llvm-bolt.sh` | Toolchain build |
| `ensure-lk-source.sh` / `ensure-llvm-source.sh` | Idempotent clones |
| `build-lk-aarch64.sh` | LK with `--emit-relocs` |
| `run-qemu-lk.sh` | Boot LK in QEMU on pod |
| `apply-overlays.sh` | Apply `overlay/*/patches/` |
| `create-pod.sh` / `destroy-pod.sh` | RunPod lifecycle |
