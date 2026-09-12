# Project plan

**Repo:** [somraj80/bolt-aarch32](https://github.com/somraj80/bolt-aarch32)  
**Updated:** 2026-09-12

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
| 2 | AArch64 bare-metal + LK | **Done** — instrument, profile, optimize, boot verified |
| 3 | AArch32 BOLT → upstream | **P0 done** — ARM32 LK + QEMU + bolt_bench |

**Pod:** `ddib0g7kwvdk33` — **RUNNING**  
**Volume:** `j1d9e6wq5l` @ `/workspace/bolt-lk-overlay` (EU-RO-1)

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
| 2.2 | Bare-metal bolt-rt (`libbolt_rt_baremetal.a`) | **Done** |
| 2.3 | LK `--emit-relocs` overlay patch | **Done** |
| 2.4 | `llvm-bolt -instrument --no-lse-atomics` | **Done** |
| 2.5 | RAM dump → `.fdata` (host-side) | **Done** |
| 2.6 | `llvm-bolt -data=prof.fdata` + boot fixes | **Done** |
| 2.7 | End-to-end `verify-bolt-workloads.sh` | **Done** |
| 2.8 | On-target UART `.fdata` export | Pending |

---

## Phase 3 — AArch32 BOLT (P0 done)

LK stays the host; only `bolt_bench_*` is profiled. Details: [aarch32-bolt.md](aarch32-bolt.md).

| # | Rung | What |
|---|------|------|
| 3.0 | P0 | ARM32 LK + QEMU + `bolt_bench` (no backend yet) | **Done** — `verify-bolt-arm32-harness.sh` |
| 3.1 | P1–P4 | ELF32, ARM disasm, CFG, identity rewrite |
| 3.2 | P5–P6 | Veneers, Thumb-2 without IT |
| 3.3 | P7–P8 | IT blocks, ARM↔Thumb interworking |
| 3.4 | P9–P10 | Instrument + QMP `.fdata` + optimize |
| 3.5 | P11 | Upstream PRs to llvm-project `main` |

---

## Scripts (on pod at `/workspace/bolt-lk-overlay/scripts/`)

| Script | Purpose |
|--------|---------|
| `build-status.sh` | Ninja progress; `-f` for live log |
| `build-llvm-bolt.sh` | Toolchain build |
| `ensure-lk-source.sh` / `ensure-llvm-source.sh` | Idempotent clones |
| `build-lk-aarch64.sh` | LK with `--emit-relocs` |
| `run-qemu-lk.sh` | Boot LK in QEMU on pod |
| `build-bolt-rt-baremetal.sh` | Bare-metal BOLT runtime library |
| `instrument-lk-bolt.sh` | Instrument bolt_bench workloads in lk.elf |
| `dump-bolt-counters.py` | QEMU QMP counter dump |
| `ram-dump-to-fdata.sh` | Counter RAM → `.fdata` |
| `optimize-lk-bolt.sh` | BOLT optimize pass |
| `verify-bolt-workloads.sh` | End-to-end pipeline (bolt_bench only) |
| `apply-overlays.sh` | Apply `overlay/*/patches/` |
| `create-pod.sh` / `destroy-pod.sh` | RunPod lifecycle |
