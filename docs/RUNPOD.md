# RunPod pod playbook

**Volume:** `j1d9e6wq5l` → `/workspace` (EU-RO-1) — all builds live here.  
**Billing:** ~$0.06/hr while a 2 vCPU cpu3c pod runs; ~$10/mo volume storage when stopped.

## Create (one command)

```bash
python3 scripts/create-pod.py
# or on the pod / Linux: ./scripts/create-pod.sh
```

Then bootstrap container packages (QEMU etc., lost on every redeploy):

```bash
./scripts/pod-ssh.sh 'cd /workspace/bolt-lk-overlay && git pull && ./scripts/bootstrap-pod.sh'
```

## Stop / delete

```bash
./scripts/destroy-pod.sh          # stops first, deletes pod; volume untouched
```

---

## Lessons (2026-09-12 duplicate-pod incident)

| Mistake | What happened | Rule |
|---------|---------------|------|
| **RunPod MCP `create-pod`** | Creates CPU pod via v1 but **cannot pass `networkVolumeId`** — pod bills at ~$0.06/hr with empty `/workspace` | **Never use MCP create-pod for this project** |
| **Parallel create paths** | MCP + Python REST fired together → **two pods**, double billing | **One script only:** `create-pod.py` |
| **Windows bash + `create-pod.sh`** | `jq` missing; `RUNPOD_API_KEY` not exported into bash from PowerShell | Use **`python scripts/create-pod.py`** on Windows |
| **Python without User-Agent** | Cloudflare **403 / error 1010** on REST API | `create-pod.py` sends `User-Agent: curl/8.0` |
| **No pre-flight check** | Recreated pod while one could be reused | Script **reuses** running pod if name + volume match |
| **Wrong list API shape** | `GET /v2/pods` returns `{pods:[…]}` not `{items:[…]}` — reuse check silently missed existing pod | Fixed in `create-pod.py` |
| **No mount verify** | Mountless pod looks “fine” until `/workspace` is empty | Script **aborts** if `mounts.network[0].volumeId != j1d9e6wq5l` |

## Correct API shape (v1 REST)

CPU pods must be created with **`networkVolumeId`** at create time — it is **immutable**:

```json
{
  "name": "llvm-bolt-builder",
  "computeType": "CPU",
  "cpuFlavorIds": ["cpu3c"],
  "vcpuCount": 2,
  "containerDiskInGb": 20,
  "imageName": "runpod/base:1.0.2-ubuntu2404",
  "dataCenterIds": ["EU-RO-1"],
  "ports": ["22/tcp"],
  "networkVolumeId": "j1d9e6wq5l",
  "volumeMountPath": "/workspace"
}
```

Poll **`GET /v2/pods/{id}`** until `RUNNING` and SSH port is assigned.

## Cost defaults

| Setting | Value | Why |
|---------|-------|-----|
| `CPU_FLAVOR` | `cpu3c` | Cheapest compute-optimized (~$0.03/vCPU-hr) |
| `VCPU_CANDIDATES` | `2 4` | Smallest shape first; 8 vCPU often “no capacity” |
| `CONTAINER_DISK_GB` | `20` | CPU pod max; build tree is on the volume |

## API key

`RUNPOD_API_KEY` from RunPod → Settings → API Keys, or auto-read from `~/.cursor/mcp.json` when using Cursor locally.
