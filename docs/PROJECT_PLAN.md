# Project plan — BOLT on bare-metal Little Kernel

**Repository:** [somraj80/bolt-lk-overlay](https://github.com/somraj80/bolt-lk-overlay)  
**Last updated:** 2026-09-11

## Goal

Build and validate **LLVM BOLT** on **bare-metal Little Kernel (LK)** — first on **AArch64** in QEMU, then design an **AArch32 (ARM/Thumb)** BOLT backend. Profile data is collected **in RAM** (no Linux `perf`, no filesystem).

Upstream LLVM and LK are **not forked**. This repo holds overlay patches, build scripts, and docs on top of git submodules.

---

## Status at a glance

| Phase | Description | Status |
|-------|-------------|--------|
| 0 | Repo, scripts, RunPod infra | **Done** |
| 1 | LLVM + Clang + LLD + BOLT toolchain | **In progress** (source clone on pod) |
| 2 | AArch64 LK QEMU PoC + in-RAM profiling | Not started |
| 3 | AArch32 BOLT design | Not started |

**Active RunPod pod:** `llvm-bolt-builder` (`kn1kscmdlxcvge`) — EU-RO-1, 8 vCPU, 64 GB RAM, ~$0.52/hr, **RUNNING**

---

## Phase 0 — Repository and infrastructure

| Step | Task | Status | Notes |
|------|------|--------|-------|
| 0.1 | Create overlay repo scaffold (scripts, cmake, docs, patches dirs) | Done | Initial commit |
| 0.2 | Add git submodules for `llvm-project` (release/19.x) and `lk` | Done | `third_party/` gitignored; scripts clone on demand |
| 0.3 | Idempotent source fetch (`ensure-llvm-source.sh`, `ensure-lk-source.sh`) | Done | flock lock + `.overlay-source-ok` marker |
| 0.4 | Push to GitHub (`somraj80/bolt-lk-overlay`) | Done | Public repo |
| 0.5 | Provision RunPod CPU pod + 150 GB network volume | Done | EU-RO-1, `runpod/base:1.0.2-ubuntu2404` |
| 0.6 | Install build deps on pod (`install-deps.sh`) | Done | cmake, ninja, clang, qemu-system-aarch64, etc. |
| 0.7 | Clone overlay repo on pod at `/workspace/bolt-lk-overlay` | Done | From GitHub |

### RunPod resources

| Resource | ID / value |
|----------|------------|
| Pod | `kn1kscmdlxcvge` (`llvm-bolt-builder`) |
| Network volume | `j1d9e6wq5l` (150 GB, mounted at `/workspace`) |
| SSH (direct) | `ssh -i ~/.ssh/id_ed25519 root@213.173.111.83 -p 45358` |
| SSH (proxy) | `ssh kn1kscmdlxcvge-6441163e@ssh.runpod.io` |

**Cleanup (when done):** stop/delete pod `kn1kscmdlxcvge`; delete orphan volume `7r1yjbov27` in EU-NL-1 if still present.

---

## Phase 1 — Toolchain build (LLVM + Clang + LLD + BOLT)

| Step | Task | Status | Command / check |
|------|------|--------|-----------------|
| 1.1 | Full clone `llvm-project` release/19.x (no shallow clone) | **In progress** | `bash scripts/ensure-llvm-source.sh` |
| 1.2 | Verify source marker and TableGen tree | Pending | `cat third_party/llvm-project/.overlay-source-ok` and `llvm/utils/TableGen` exists |
| 1.3 | CMake configure (X86, AArch64, ARM targets) | Pending | `bash scripts/build-llvm-bolt.sh` |
| 1.4 | Ninja build (~2–4 h on 8 vCPU) | Pending | `pgrep -a ninja` on pod |
| 1.5 | Verify binaries | Pending | `build/bin/llvm-bolt`, `clang`, `ld.lld` |
| 1.6 | Package toolchain tarball | Pending | `bash scripts/package-toolchain.sh` |
| 1.7 | Download tarball to local machine | Pending | `scp` from `/workspace/` |
| 1.8 | Stop RunPod pod to end billing | Pending | `bash scripts/destroy-pod.sh` or RunPod console |

### Monitor on pod

```bash
tail -f /workspace/build-llvm.log
du -sh /workspace/bolt-lk-overlay/third_party/llvm-project
pgrep -a 'git clone|ninja|cmake'
```

### Lessons learned (Phase 1)

- **Do not** use `git clone --depth 1` for llvm-project — shallow trees miss `llvm/utils/TableGen` and cmake fails.
- **Do not** start multiple parallel `git clone` processes; `ensure-llvm-source.sh` uses flock.
- CPU pods: max ~20 GB container disk; keep source + build on `/workspace` network volume.
- Use `runpod/base:1.0.2-ubuntu2404` (plain `ubuntu:24.04` broke SSH).

---

## Phase 2 — AArch64 LK proof of concept

See [phase1-aarch64-lk.md](phase1-aarch64-lk.md) for detail.

| Step | Task | Status |
|------|------|--------|
| 2.1 | Clone LK source (`ensure-lk-source.sh`) | Not started |
| 2.2 | Build LK `qemu-virt-arm64-test` with `--emit-relocs` (`-Wl,-q`) | Not started |
| 2.3 | Instrument with BOLT: `llvm-bolt lk.elf -instrument -o lk.instr.elf` | Not started |
| 2.4 | Add overlay patch: profile counters in linker-script RAM section | Not started |
| 2.5 | Boot instrumented LK in QEMU (`--no-lse-atomics` for cortex-a53) | Not started |
| 2.6 | Run workload, dump counter region from RAM → host `.fdata` | Not started |
| 2.7 | Re-optimize: `llvm-bolt lk.elf -o lk.bolt.elf -data=prof.fdata` | Not started |
| 2.8 | Boot optimized LK and verify behavior | Not started |

**Why overlay patches are needed:** stock `bolt/runtime/instr.cpp` writes `/tmp/prof.fdata` via Linux syscalls. LK has no filesystem — counters must live in a fixed RAM buffer defined in the linker script.

---

## Phase 3 — AArch32 BOLT design

See [phase2-aarch32-bolt-design.md](phase2-aarch32-bolt-design.md). Upstream BOLT has **no ARM32/Thumb backend** today.

| Step | Task | Status |
|------|------|--------|
| 3.1 | ELF32 reader + ARM-mode disassemble-only | Not started |
| 3.2 | `ARM MCPlusBuilder` + CFG (ARM-only functions) | Not started |
| 3.3 | Rewrite with branch veneers (range limits) | Not started |
| 3.4 | Thumb-2 without IT blocks | Not started |
| 3.5 | IT blocks as atomic instrumentation units | Not started |
| 3.6 | ARM/Thumb interworking edges (BL, BLX, BX, LDR PC) | Not started |
| 3.7 | LK ARM32 QEMU target + in-RAM profile dump (reuse Phase 2) | Not started |

---

## Script reference

| Script | Purpose |
|--------|---------|
| `scripts/ensure-llvm-source.sh` | Idempotent full llvm-project clone |
| `scripts/ensure-lk-source.sh` | Idempotent LK clone |
| `scripts/build-llvm-bolt.sh` | CMake + Ninja build |
| `scripts/build-lk-aarch64.sh` | Build LK for QEMU virt |
| `scripts/package-toolchain.sh` | Tarball of built tools |
| `scripts/install-deps.sh` | Apt packages on Ubuntu 24.04 |
| `scripts/create-pod.sh` / `destroy-pod.sh` | RunPod lifecycle |

---

## Cost notes

- Pod bills while **RUNNING** (~$0.52/hr for current config). Laptop shutdown does **not** stop the pod.
- Monitor via [RunPod console](https://www.runpod.io/console/pods) or GitHub mobile app for repo updates.
- Delete unused network volumes to avoid storage charges.
