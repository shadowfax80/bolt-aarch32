# Resume guide

**Saved:** 2026-09-13  
**GitHub (overlay only):** [somraj80/bolt-aarch32](https://github.com/somraj80/bolt-aarch32)

All upstream sources, builds, and QEMU runs live on the **RunPod network volume** — not on your laptop. The GitHub repo holds overlay patches, scripts, and docs only.

---

## RunPod resources

| Resource | ID / value | Notes |
|----------|------------|-------|
| Pod | `i5dkz4se4q2qv0` | 2 vCPU cpu3c, Ubuntu 24.04 — recreate via `create-pod.py` if EXITED on a full host |
| Network volume | `j1d9e6wq5l` | 150 GB, EU-RO-1 — **keeps all work** (~$0.07/GB/mo storage) |
| Region | EU-RO-1 | The volume only attaches to pods in its own region |
| Image | `runpod/base:1.0.2-ubuntu2404` | Must be the 24.04 tag — see the traps below |
| Compute | cpu3c, 2 vCPU (default) | ~$0.06/hr while running |

### Recreating the pod

See [RUNPOD.md](RUNPOD.md) for the full playbook (duplicate-pod traps, API shape).

```bash
python3 scripts/create-pod.py    # attaches j1d9e6wq5l; reuses pod if already running
./scripts/pod-ssh.sh             # resolves the current host and port, then connects
./scripts/pod-ssh.sh 'cd /workspace/bolt-lk-overlay && git pull && ./scripts/bootstrap-pod.sh'
```

`bootstrap-pod.sh` reinstalls the container-disk packages that vanish on every
redeploy (QEMU, ninja, lld, ccache). The toolchain itself lives on the volume.

Four traps, each of which has already cost a redeploy, all now handled by those
two scripts:

| Trap | Consequence |
|------|-------------|
| RunPod MCP `create-pod` | No `networkVolumeId` — creates a billable pod without `/workspace` (scrap) |
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
│                                      branch bolt-arm-backend (local)
└── third_party/lk/                  ← master @ 79d2f560
    ├── build-qemu-virt-arm64-test/lk.elf   ← AArch64 Phase 2 ✓
    └── build-qemu-virt-arm32-test/lk.elf   ← ARM32 P0 harness ✓
```

**Verified on volume:**

- `llvm-bolt`, `clang`, `ld.lld`, llvm binutils — LLVM 23.1.2
- LK `qemu-virt-arm64-test` — Phase 2 instrument → QMP → optimize → boot
- LK `qemu-virt-arm32-test` — P0 boot + `lk.bolt_bench=all`
- P1: `llvm-bolt --print-sections --funcs-file=bolt_bench_*` on ARM32 `lk.elf` lists `.text` (exit 0)
- P2/P3: `--print-cfg` prints ARM `bolt_bench_hot_loop` CFG with successors
- **P0–P4 one-shot:** `./scripts/verify-bolt-arm32-milestones.sh` → `ALL MILESTONES P0-P4 PASSED`
- **P4 identity rewrite:** `BOLT_BENCH_ISA=arm` → **4/1389 overwritten**; QEMU boots rewritten ELF; all four `bolt_bench: … done` lines print
- **P5 veneers:** `./scripts/verify-bolt-arm32-veneer.sh` → linker veneer removed + LongJmp stub inserted

**Still pending:**

- Lit FileCheck hardening for P2–P4 (`check-bolt`)
- Full-binary rewrite without `--funcs-file` (kernel host functions)
- P6 Thumb disasm of default `-mthumb` benches (fails at +0x8 without `-marm`)
- On-target `.fdata` serialization over UART (optional; QMP works)
- Rebase llvm-project to `main` before opening upstream PRs

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

### 5. BOLT pipeline (Phase 2 complete)

Full end-to-end check:

```bash
cd /workspace/bolt-lk-overlay
git pull
./scripts/verify-bolt-workloads.sh
```

Or step-by-step:

```bash
./scripts/build-bolt-rt-baremetal.sh
./scripts/instrument-lk-bolt.sh
python3 scripts/dump-bolt-counters.py --elf build/lk.instr.elf --toolchain build/bin
./scripts/ram-dump-to-fdata.sh
./scripts/optimize-lk-bolt.sh
./scripts/run-qemu-lk.sh build/lk.bolt.elf
```

Phase 3 next (on the volume, after `git pull`):

```bash
./scripts/apply-overlays.sh
# if llvm-project already has the backend, ninja will just rebuild dirty files
ninja -C build bolt

# P0–P4 one-shot (ARM-mode benches already on volume)
./scripts/verify-bolt-arm32-milestones.sh

# Or stepwise:
./scripts/verify-bolt-arm32-harness.sh
BOLT_BENCH_ISA=arm REQUIRE_OVERWRITE=1 BOOT_REWRITTEN=1 \
  ./scripts/verify-bolt-arm32-identity.sh
```

Refresh overlay patches from the volume tree:

```bash
./scripts/export-llvm-arm-patches.sh
```

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
