# Recreating the RunPod network volume from nothing

The network volume `j1d9e6wq5l` (150 GB, EU-RO-1) was deleted 2026-09-22 to
stop paying its ~$0.015/hr storage cost while no active work was happening.
**Nothing on it was unique** — everything needed to rebuild an equivalent
working state is either in this git repo or re-fetched from pinned upstream
commits. This doc is the exact sequence to do that.

Two loose files that existed only on the old volume were preserved
separately (not needed to *rebuild* the volume, only useful if you want the
historical record): `legacy-archives/volume-loose-files/` in this repo —
`d4-attempt-jitlinklinker.diff` (an unsuccessful D4 fix attempt, see
`docs/KNOWN_LIMITATIONS.md` U1) and `u7-orphans.tgz` (two test-input files
deliberately excluded from the lit suite).

## 1. Create a new volume

Via the RunPod console, or the API: 150 GB, data center `EU-RO-1` (same
region as the pod flavor `cpu3c`/`cpu5m` this project uses — cross-region
volume↔pod mounting isn't possible). Note the new volume ID.

## 2. Create a pod attached to it

```bash
export MSYS_NO_PATHCONV=1   # Windows/Git-Bash only — prevents /workspace mangling
export RUNPOD_API_KEY=...   # or configure ~/.cursor/mcp.json runpod env
NETWORK_VOLUME_ID=<new-volume-id> POD_NAME=llvm-bolt-builder \
  CPU_FLAVOR=cpu3c VCPU_CANDIDATES="4 8" \
  python3 scripts/create-pod.py
```

Size per the standing policy (`feedback_runpod_dynamic_sizing.md`): 2 vCPU
for light/inspection work, 4–8 for a from-scratch LLVM build. Terminate the
pod the moment its task is done — the volume, not the pod, is what should
persist.

## 3. Bootstrap the pod

```bash
ssh root@<pod-ip> -p <port>
apt-get update && ./scripts/install-deps.sh   # wiped on every fresh container
mkdir -p /workspace/bolt-lk-overlay   # NOTE: directory name != repo name
git clone https://github.com/shadowfax80/bolt-aarch32.git /workspace/bolt-lk-overlay
cd /workspace/bolt-lk-overlay
```

`install-deps.sh` installs: `build-essential cmake ninja-build python3
python3-venv git ccache zlib1g-dev libxml2-dev libedit-dev
libcurl4-openssl-dev lld clang curl ca-certificates jq qemu-system-aarch64
qemu-system-arm gdb-multiarch`.

## 4. Fetch pinned sources (per base)

Pins, from `.env.example` (durable — bump deliberately, re-verify after,
per that file's own comment):

| What | Remote | Pinned commit |
|---|---|---|
| `BASE=upstream` | `https://github.com/llvm/llvm-project.git` | `069ef0e7cb36ee1fcf3bfdad31533fd79ab85b58` |
| `BASE=atfe` | `https://github.com/arm/arm-toolchain.git` (branch `arm-software`) | `bcc08884995ff3cbee70749524621803b9bd258a` |
| LK (shared, base-agnostic) | `https://github.com/littlekernel/lk.git` | `79d2f56096fa32365846ceaba8b4a9d1c6b75cf0` |

```bash
BASE=upstream ./scripts/ensure-llvm-source.sh    # -> third_party/llvm-project-upstream/
BASE=atfe     ./scripts/ensure-llvm-source.sh    # -> third_party/llvm-project-atfe/
./scripts/ensure-lk-source.sh                     # -> third_party/lk/
```

The `arm-toolchain` (atfe) clone is ~2.9 GB and took **~40 minutes** last
time, purely from many-small-files checkout cost on the network-backed
volume — not a bug, budget for it.

## 5. Apply the overlay patches

```bash
BASE=upstream ./scripts/apply-overlays.sh   # replays the 7-commit series via `git am`
BASE=atfe     ./scripts/apply-overlays.sh   # legacy file-slice `git apply` path (L12: not yet converted)
```

For `BASE=upstream` this checks out branch `bolt-arm-backend` at the pinned
commit and replays `overlay/llvm/patches/upstream/*.patch` (real
`git format-patch` files) with `git am --keep-non-patch`. This was verified
this session to reproduce the original tip's tree **and commit messages**
exactly, and to be idempotent (safe to re-run).

## 6. Build

```bash
BASE=upstream ./scripts/build-llvm-bolt.sh   # -> build-upstream/bin/llvm-bolt
BASE=atfe     ./scripts/build-llvm-bolt.sh   # -> build-atfe/bin/llvm-bolt
BASE=upstream ARCH=arm32 ./scripts/build-bolt-rt-baremetal.sh
BASE=atfe     ARCH=arm32 ./scripts/build-bolt-rt-baremetal.sh
./scripts/build-lk-aarch32.sh
```

A from-scratch LLVM+BOLT build has historically taken **multiple hours** on
a 2-vCPU pod under host contention; use 4–8 vCPU for this step (see the pod
sizing policy). An incremental rebuild after a small source change is much
faster (~10 minutes observed for the U8/U9 refactor's ~700-line diff).

## 7. Verify before trusting it

```bash
ARCH=arm32 ./scripts/verify-bolt-workloads.sh          # full instrument->profile->optimize->boot, both bases
./build-upstream/bin/llvm-lit third_party/llvm-project-upstream/{bolt/test/ARM,bolt/test/elf32-basic.test}
```

Expect 12/12 ARM lit tests passing on `BASE=upstream`, all 16
`bolt_bench_*` workloads completing, 32/32 instrumentation counters
non-zero. Known-still-open at time of volume deletion: D4 non-determinism
(every rewrite run differs; see `docs/KNOWN_LIMITATIONS.md` U1) and
full-image rewrite only covering ~7% of functions — neither is new, don't
re-debug them as if they're a rebuild regression.

## What does *not* need recreating

Everything under the old volume's `/workspace/` that was pure scratch —
`atfe-bolt-aarch32/` (a stale leftover clone of the now-deleted repo, its
history is in `legacy-archives/atfe-bolt-aarch32-legacy.bundle`),
`lk-modloader-test/` (pure build output for a different project, source is
on GitHub), and ~150 log files / one-off Python refactor scripts (`m1`–`m6`,
`u7_*`/`u8_*`/`u9_*`) from recent debugging sessions — their *results* are
already the git commits on `main`; the scripts themselves aren't needed to
reproduce anything.
