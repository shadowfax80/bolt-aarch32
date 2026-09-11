# Resume guide

**Saved:** 2026-09-11  
**GitHub (overlay only):** [somraj80/bolt-aarch32](https://github.com/somraj80/bolt-aarch32)

All upstream sources, builds, and QEMU runs live on the **RunPod network volume** — not on your laptop. The GitHub repo holds overlay patches, scripts, and docs only.

---

## RunPod resources

| Resource | ID / value | Notes |
|----------|------------|-------|
| Pod | `kn1kscmdlxcvge` | Name: `llvm-bolt-builder` — **STOPPED** (compute billing off) |
| Network volume | `j1d9e6wq5l` | 150 GB, EU-RO-1 — **keeps all work** (~$0.07/GB/mo storage) |
| Region | EU-RO-1 | Pod must mount this volume in the same region |
| Image | `runpod/base:1.0.2-ubuntu2404` | Do not use plain `ubuntu:24.04` (no sshd) |
| Compute | cpu5m, 8 vCPU, 64 GB RAM | ~$0.52/hr when running |

---

## What is on the volume (`/workspace`)

```
/workspace/bolt-lk-overlay/          ← overlay repo clone
├── build/                           ← LLVM 23.1.2 toolchain (3.3 GB)
├── llvm-bolt-toolchain.tar.gz       ← packaged tools (167 MB)
├── third_party/llvm-project/        ← release/23.x @ 069ef0e7cb36
└── third_party/lk/                  ← master @ 79d2f560
    └── build-qemu-virt-arm64-test/
        └── lk.elf                   ← LK AArch64, boots in QEMU ✓
```

**Verified on pod before stop:**

- `llvm-bolt`, `clang`, `ld.lld`, llvm binutils — built
- LK `qemu-virt-arm64-test` — built and booted to shell in QEMU (`cortex-a53`, 4 CPUs)

**Not done yet (Phase 2):**

- Bare-metal BOLT runtime (`libbolt_rt_baremetal.a`)
- LK overlay patches (linker script, `bolt_bench`, profile dump)
- BOLT instrument → profile → optimize loop

---

## How to resume

### 1. Start the pod (RunPod console or API)

Attach network volume `j1d9e6wq5l` at `/workspace`, same settings as before:

- Image: `runpod/base:1.0.2-ubuntu2404`
- Region: **EU-RO-1**
- 8 vCPU, cpu5m, 20 GB container disk
- SSH key in `PUBLIC_KEY` env

Or use RunPod MCP / `scripts/create-pod.sh` with `NETWORK_VOLUME_ID=j1d9e6wq5l`.

### 2. SSH in

```bash
ssh -i ~/.ssh/id_ed25519 root@<pod-ip> -p <port>
# or: ssh kn1kscmdlxcvge-<suffix>@ssh.runpod.io
```

### 3. Sync overlay repo (if GitHub moved ahead)

```bash
cd /workspace/bolt-lk-overlay
git pull origin main
```

Upstream trees (`third_party/`) are already on the volume — no re-clone unless corrupted.

### 4. Quick sanity checks

```bash
/workspace/bolt-lk-overlay/build/bin/llvm-bolt --version    # LLVM 23.1.2
ls /workspace/bolt-lk-overlay/third_party/lk/build-qemu-virt-arm64-test/lk.elf

# Boot LK in QEMU (on pod)
/workspace/bolt-lk-overlay/scripts/run-qemu-lk.sh
# Expect: "entering main console loop" and "]" prompt
```

### 5. Next work — Phase 2

See [PROJECT_PLAN.md](PROJECT_PLAN.md) and [aarch64-bare-metal.md](aarch64-bare-metal.md).

1. Cross-build bare-metal bolt-rt for `aarch64-elf` → `libbolt_rt_baremetal.a`
2. LK patches: `.bolt_profile` section, dump hook, `bolt_bench` app
3. Rebuild LK with `--emit-relocs`
4. `llvm-bolt -instrument --no-lse-atomics --runtime-instrumentation-lib=…`
5. Run workload in QEMU, dump profile RAM → `.fdata`, re-optimize

Build LK (already works):

```bash
cd /workspace/bolt-lk-overlay/third_party/lk
make qemu-virt-arm64-test TOOLCHAIN=clang \
  CLANG_BINDIR=/workspace/bolt-lk-overlay/build/bin -j8
```

Monitor LLVM build (if ever needed again):

```bash
/workspace/bolt-lk-overlay/scripts/build-status.sh
/workspace/bolt-lk-overlay/scripts/build-status.sh -f   # live log
```

### 6. Stop again when idle

Stop the pod to end compute billing. **Do not delete** volume `j1d9e6wq5l`.

---

## GitHub vs pod

| Location | Contains |
|----------|----------|
| **GitHub** `bolt-aarch32` | Overlay patches, scripts, docs — small repo |
| **Pod volume** `/workspace` | llvm-project, lk, build/, tarballs, QEMU runs |

Never clone llvm/lk on the laptop. Edit overlay on GitHub (or on pod + push), apply on pod with `scripts/apply-overlays.sh`.

---

## Cost reminder

| Billing | When |
|---------|------|
| ~$0.52/hr | Pod **running** |
| Volume storage | Always while volume exists |
| Laptop off | Pod/volume unaffected |
