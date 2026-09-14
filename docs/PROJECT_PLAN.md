# Project plan

**Repo:** [somraj80/bolt-aarch32](https://github.com/somraj80/bolt-aarch32)  
**Updated:** 2026-09-13 (P0–P1 gated; P4 emit saved; overwrite still open)

**Resume:** [RESUME.md](RESUME.md)

**Goal:** an AArch32 BOLT backend merged into LLVM upstream, proven on a bare-metal LK harness with in-RAM profiling.

| Doc | Contents |
|-----|----------|
| [RESUME.md](RESUME.md) | **Start here** — volume paths, how to restart pod |
| [why-bolt.md](why-bolt.md) | What BOLT adds over PGO and LTO |
| [architecture.md](architecture.md) | Overlay model, data flow, upstream workflow |
| [aarch64-bare-metal.md](aarch64-bare-metal.md) | Bare-metal delta, runtime, workloads |
| [aarch32-bolt.md](aarch32-bolt.md) | **P0–P11 plan** — ARM/Thumb backend, upstream PRs, verification |

---

## Status

| Phase | Focus | Status |
|-------|-------|--------|
| 0 | Repo, scripts, RunPod | **Done** |
| 1 | LLVM/BOLT toolchain | **Done** |
| 2 | AArch64 bare-metal + LK | **Done** (2.8 optional UART export pending) |
| 3 | AArch32 BOLT → upstream | **P0–P5 done** — P6 Thumb next |

**Pod:** `ddib0g7kwvdk33` — check RunPod console for current state  
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

**Before P1:** rebase volume checkout to llvm-project `main` and rebuild (see [aarch32-bolt.md](aarch32-bolt.md)).

---

## Phase 2 ✓

| # | Task | Status |
|---|------|--------|
| 2.1 | LK clone + build `qemu-virt-arm64-test` | Done |
| 2.2 | Bare-metal bolt-rt (`libbolt_rt_baremetal.a`) | Done |
| 2.3 | LK `--emit-relocs` overlay patch | Done |
| 2.4 | `llvm-bolt -instrument --no-lse-atomics` | Done |
| 2.5 | RAM dump → `.fdata` (QMP + host script) | Done |
| 2.6 | `llvm-bolt -data=prof.fdata` + boot fixes | Done |
| 2.7 | End-to-end `verify-bolt-workloads.sh` | Done |
| 2.8 | On-target UART `.fdata` export | Optional — QMP path works |

---

## Phase 3 — AArch32 BOLT (P0–P11)

LK stays the host; only `bolt_bench_*` is profiled. Full detail: [aarch32-bolt.md](aarch32-bolt.md).

Each rung P1–P10 maps to **one upstream llvm-project PR** with lit tests. P11 tracks merge and overlay cleanup.

| Rung | Focus | Upstream PR | Lit | QEMU gate | Status |
|------|-------|-------------|-----|-----------|--------|
| P0 | ARM32 harness | — | — | `verify-bolt-arm32-harness.sh` | **Done** |
| P1 | ELF32 reader | `[BOLT][ARM] ELF32 support` | Parse ARM ET_EXEC | `--print-sections` on `lk.elf` | **Done** — `0003` |
| P2 | ARM disassembly | `[BOLT][ARM] ARM-mode disasm` | ARM `.s` FileCheck | `hot_loop` vs objdump | **Done** — ARM benches via `--print-cfg`; lit TBD |
| P3 | CFG (ARM) | `[BOLT][ARM] ARM CFG` | `--print-cfg` FileCheck | ARM bench CFG | **Done** — ARM bench CFG + successors; lit TBD |
| P4 | Identity rewrite | `[BOLT][ARM] ARM identity rewrite` | Rewritten lit ELF | Rewritten `lk.elf` + `bolt_bench all` | **Done** — 4/1389 overwritten (`BOLT_BENCH_ISA=arm`); QEMU benches green |
| P5 | Veneers | `[BOLT][ARM] Branch veneers` | Far `bl` lit | `verify-bolt-arm32-veneer.sh` | **Done** — LongJmp + veneer elim (`0009`) |
| P6 | Thumb-2 (no IT) | `[BOLT][ARM] Thumb-2 rewrite` | Thumb `.s` lit | `-mthumb` benches boot | **Partial** — STI/LSB/`$t`; benches fail disasm at +0x8 |
| P7 | IT blocks | `[BOLT][ARM] IT bundles` | IT not split | `it_cond` bench | Pending — skip as unsupported |
| P8 | Interworking | `[BOLT][ARM] Interworking` | ARM↔Thumb lit | `interwork` bench | Pending — LSB + BX/BLX classify only |
| P9 | Instrumentation | `[BOLT][ARM] Instrumentation` | Counter FileCheck | `verify-bolt-workloads.sh` ARM32 | Pending |
| P10 | Layout optimize | `[BOLT][ARM] PGO layout` | Optimize lit | `lk.bolt.elf` boots + cycles | Pending |
| P11 | Upstream landing | Merge tracking | All lit in tree | Full pipeline on `main` | Pending — still `release/23.x`, no PRs |

**Overlay patches (upstream staging):**

| Patch | Upstream PR scope |
|-------|-------------------|
| `0003-bolt-arm-elf32-and-target.patch` | P1 — CMake, BinaryContext, BinaryFunction, `$a/$t/$d` |
| `0004-bolt-arm-mcplusbuilder.patch` | P2–P6 — `bolt/lib/Target/ARM/` |
| `0005-bolt-arm-relocations.patch` | P4 — `R_ARM_*` including GOT/TLS/relative dispatch |
| `0006-bolt-arm-rewrite-dispatch.patch` | P1/P6 — RewriteInstance, Thumb LSB, ARM mapping-symbol partition |
| `0007-bolt-arm-lit-tests.patch` | Lit tests under `bolt/test/ARM/` (incl. far-BL veneer) |
| `0008-jitlink-arm-generic-archkind.patch` | P4 emit — JITLink treats generic `arm` as ARMv7-A |
| `0009-bolt-arm-longjmp-veneers.patch` | P5 — LongJmp + VeneerElimination for `Triple::arm` |

**Next action:** P6 Thumb-2 rewrite of default `-mthumb` benches. Upstream PRs can start at P1 in parallel.

---

## Scripts (on pod at `/workspace/bolt-lk-overlay/scripts/`)

| Script | Purpose |
|--------|---------|
| `verify-workspace.sh` | Check volume has llvm-project, lk, build/ |
| `bootstrap-pod.sh` | Fresh pod: apt packages + fetch sources + verify |
| `build-status.sh` | Ninja progress; `-f` for live log |
| `build-llvm-bolt.sh` | Toolchain build |
| `ensure-lk-source.sh` / `ensure-llvm-source.sh` | Idempotent clones |
| `build-lk-aarch64.sh` / `build-lk-aarch32.sh` | LK with `--emit-relocs` |
| `run-qemu-lk.sh` | Boot LK in QEMU (AArch64 or ARM32 via `LK_PROJECT`) |
| `verify-bolt-arm32-harness.sh` | P0 gate: ARM32 boot + `bolt_bench all` |
| `verify-bolt-arm32-milestones.sh` | P0–P4 one-shot gate |
| `verify-bolt-arm32-veneer.sh` | P5 LongJmp veneer gate |
| `export-llvm-arm-patches.sh` | Refresh `overlay/llvm/patches/0003–0009` from the volume tree |
| `build-bolt-rt-baremetal.sh` | Bare-metal BOLT runtime (AArch64; ARM32 at P9) |
| `instrument-lk-bolt.sh` | Instrument bolt_bench workloads |
| `dump-bolt-counters.py` | QEMU QMP counter dump |
| `ram-dump-to-fdata.sh` | Counter RAM → `.fdata` |
| `optimize-lk-bolt.sh` | BOLT optimize pass |
| `verify-bolt-workloads.sh` | End-to-end pipeline (AArch64; ARM32 at P9) |
| `apply-overlays.sh` | Apply `overlay/*/patches/` |
| `create-pod.sh` / `create-pod.py` / `destroy-pod.sh` | RunPod lifecycle |
