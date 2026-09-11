# Resume guide

**Saved:** 2026-09-11  
**GitHub (overlay only):** [somraj80/bolt-aarch32](https://github.com/somraj80/bolt-aarch32)

All upstream sources, builds, and QEMU runs live on the **RunPod network volume** — not on your laptop. The GitHub repo holds overlay patches, scripts, and docs only.

---

## RunPod resources

| Resource | ID / value | Notes |
|----------|------------|-------|
| Pod | `h9cs2sqm4h7w66` (`outer_gray_macaw`) | 4 vCPU, Ubuntu 24.04 — **RUNNING** |
| Network volume | `j1d9e6wq5l` | 150 GB, EU-RO-1 — **keeps all work** (~$0.07/GB/mo storage) |
| Region | EU-RO-1 | The volume only attaches to pods in its own region |
| Image | `runpod/base:1.0.2-ubuntu2404` | Must be the 24.04 tag — see the traps below |
| Compute | cpu5m / cpu3c, 4–8 vCPU | ~$0.12–0.52/hr while running |

### Recreating the pod

```bash
export RUNPOD_API_KEY=...        # RunPod -> Settings -> API Keys
./scripts/create-pod.sh          # attaches j1d9e6wq5l, falls back 8 -> 4 -> 2 vCPU
./scripts/pod-ssh.sh             # resolves the current host and port, then connects
./scripts/pod-ssh.sh 'cd /workspace/bolt-lk-overlay && git pull && ./scripts/bootstrap-pod.sh'
```

`bootstrap-pod.sh` reinstalls the container-disk packages that vanish on every
redeploy (QEMU, ninja, lld, ccache). The toolchain itself lives on the volume.

Four traps, each of which has already cost a redeploy, all now handled by those
two scripts:

| Trap | Consequence |
|------|-------------|
| Volume not attached at create | Unrecoverable — RunPod rejects adding a mount to a mountless pod and treats `volumeId` as immutable, so the pod is scrap |
| Image other than `ubuntu2404` | `llvm-bolt` dies with `GLIBC_2.32 not found`; the toolchain was linked against glibc 2.39, and the console's `runpod-ubuntu` template defaults to 20.04 |
| SSH key added inside the pod | Lost on the next deploy, because the container disk is ephemeral — add it under **Settings -> SSH Public Keys** so every new pod authorizes it |
| Hardcoded IP and port | Reassigned on every deploy; a stale pair fails as "Connection refused" or "banner exchange", which looks nothing like the real cause |

Deploying by hand instead? Start from the **Storage** page and click Deploy on the
volume — that pre-attaches it and pins the region — then override the image to
`runpod/base:1.0.2-ubuntu2404`.

QEMU lives on the container disk rather than the volume, so every fresh pod needs:

```bash
apt-get update -qq && apt-get install -y -qq qemu-system-arm
```

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

- First run of the bare-metal runtime on the pod (source is committed, never compiled)
- On-target `.fdata` serialization over UART
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

Verify instrumentation end to end before touching LK source — the first bring-up
needs no LK patches at all, because the counters live in a section BOLT emits
itself and the host reads them out of the guest:

```bash
cd /workspace/bolt-lk-overlay
./scripts/build-bolt-rt-baremetal.sh          # libbolt_rt_baremetal.a
./scripts/build-lk-aarch64.sh                 # lk.elf, LDFLAGS=--emit-relocs
./scripts/instrument-lk-bolt.sh               # build/lk.instr.elf
python3 scripts/dump-bolt-counters.py --elf build/lk.instr.elf
```

Expected: LK reaches `entering main console loop` and the dump reports a
non-zero share of counters set. Then continue with:

1. On-target `.fdata` serialization (port upstream `writeFunctionProfile` to UART)
2. LK patches: `.bolt_profile` section, dump hook, `bolt_bench` app
3. `llvm-bolt lk.elf -data=prof.fdata -o lk.bolt.elf`, re-run and measure

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
