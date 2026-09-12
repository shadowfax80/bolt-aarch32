#!/usr/bin/env python3
"""Create a RunPod CPU pod with the project network volume attached.

Single entry point for pod creation — use this on Windows and Linux.
Do NOT use the RunPod MCP create-pod tool: it cannot pass networkVolumeId and
will create a billable pod without /workspace (must be deleted and recreated).

Reads RUNPOD_API_KEY from the environment, or from ~/.cursor/mcp.json when unset.
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
V1 = "https://rest.runpod.io/v1"
V2 = "https://api.runpod.io/v2"
UA = "curl/8.0"  # Cloudflare blocks default Python urllib (error 1010)


def api_key() -> str:
    key = os.environ.get("RUNPOD_API_KEY", "").strip()
    if key:
        return key
    mcp = Path.home() / ".cursor" / "mcp.json"
    if mcp.is_file():
        cfg = json.loads(mcp.read_text())
        key = cfg.get("mcpServers", {}).get("runpod", {}).get("env", {}).get(
            "RUNPOD_API_KEY", ""
        )
        if key:
            return key
    sys.exit("error: set RUNPOD_API_KEY or configure ~/.cursor/mcp.json runpod env")


def req(key: str, method: str, url: str, body: dict | None = None) -> dict | list:
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "User-Agent": UA,
        },
    )
    try:
        with urllib.request.urlopen(r) as resp:
            raw = resp.read()
    except urllib.error.HTTPError as e:
        sys.exit(f"error: {method} {url} -> {e.code} {e.read()[:300]!r}")
    if not raw:
        return {}
    return json.loads(raw)


def ssh_public_key() -> str:
    env = os.environ.get("SSH_PUBLIC_KEY", "").strip()
    if env:
        return env
    pub = Path.home() / ".ssh" / "id_ed25519.pub"
    if pub.is_file():
        return pub.read_text().strip()
    return ""


def list_pods(key: str) -> list[dict]:
    out = req(key, "GET", f"{V2}/pods")
    if isinstance(out, list):
        return out
    if isinstance(out, dict):
        return out.get("pods") or out.get("items") or []
    return []


def volume_id_of(pod: dict) -> str:
    mounts = (pod.get("mounts") or {}).get("network") or []
    return mounts[0].get("volumeId", "") if mounts else ""


def find_reusable(pods: list[dict], name: str, volume_id: str) -> dict | None:
    matches = [
        p
        for p in pods
        if p.get("name") == name
        and volume_id_of(p) == volume_id
        and p.get("status") in ("RUNNING", "STARTING")
    ]
    if not matches:
        return None
    if len(matches) > 1:
        saved = (ROOT / ".runpod-pod-id").read_text().strip() if (ROOT / ".runpod-pod-id").is_file() else ""
        for pod in matches:
            if pod.get("id") == saved:
                print(f"warning: {len(matches)} pods named {name!r}; reusing saved {saved}")
                return pod
        oldest = min(matches, key=lambda p: p.get("createdAt", ""))
        print(
            f"warning: {len(matches)} pods named {name!r}; reusing oldest {oldest['id']}. "
            "Delete extras with ./scripts/destroy-pod.sh <id>"
        )
        return oldest
    return matches[0]


def wait_ready(key: str, pod_id: str, volume_id: str, timeout_s: int = 300) -> dict:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        pod = req(key, "GET", f"{V2}/pods/{pod_id}")
        ssh = pod.get("ssh") or {}
        direct = ssh.get("direct") or {}
        if pod.get("status") == "RUNNING" and direct.get("port"):
            mounts = (pod.get("mounts") or {}).get("network") or []
            got = mounts[0].get("volumeId") if mounts else ""
            if got != volume_id:
                sys.exit(
                    f"error: pod {pod_id} mounted volume {got!r}, expected {volume_id}\n"
                    "delete this pod and recreate — volume cannot be attached later"
                )
            return pod
        time.sleep(5)
    sys.exit(f"error: pod {pod_id} not ready after {timeout_s}s — check RunPod console")


def main() -> int:
    key = api_key()
    name = os.environ.get("POD_NAME", "llvm-bolt-builder")
    volume_id = os.environ.get("NETWORK_VOLUME_ID", "j1d9e6wq5l")
    mount_path = os.environ.get("VOLUME_MOUNT_PATH", "/workspace")
    image = os.environ.get("IMAGE", "runpod/base:1.0.2-ubuntu2404")
    flavor = os.environ.get("CPU_FLAVOR", "cpu3c")
    dc = os.environ.get("DATA_CENTER", "EU-RO-1")
    disk = int(os.environ.get("CONTAINER_DISK_GB", "20"))
    vcpu_candidates = os.environ.get("VCPU_CANDIDATES", "2 4").split()
    ssh_key = ssh_public_key()

    if not volume_id:
        sys.exit("error: NETWORK_VOLUME_ID is empty — pod would be unrecoverable")

    pods = list_pods(key)
    # Refuse to create if a mountless namesake is billing — it can never be fixed.
    for pod in pods:
        if pod.get("name") == name and not volume_id_of(pod):
            sys.exit(
                f"error: pod {pod['id']} named {name!r} has no network volume — "
                "delete it with ./scripts/destroy-pod.sh before creating a new one"
            )

    existing = find_reusable(pods, name, volume_id)
    if existing:
        pod_id = existing["id"]
        print(f"reusing pod {pod_id} ({existing.get('status')}) — volume already attached")
        pod = wait_ready(key, pod_id, volume_id)
        (ROOT / ".runpod-pod-id").write_text(pod_id + "\n")
        mounts = pod["mounts"]["network"][0]
        print(f"mount: {mounts['volumeId']} at {mounts['path']}")
        print("ssh:", pod["ssh"]["direct"]["command"])
        return 0

    # Align data center with volume region.
    vol = req(key, "GET", f"{V2}/network-volumes/{volume_id}")
    vol_dc = vol.get("dataCenter") or vol.get("dataCenterId")
    if vol_dc and vol_dc != dc:
        print(f"note: volume in {vol_dc}, using that instead of {dc}")
        dc = vol_dc

    pod_id = ""
    for vcpu in vcpu_candidates:
        body = {
            "name": name,
            "computeType": "CPU",
            "cpuFlavorIds": [flavor],
            "cpuFlavorPriority": "custom",
            "vcpuCount": int(vcpu),
            "containerDiskInGb": disk,
            "imageName": image,
            "dataCenterIds": [dc],
            "ports": ["22/tcp"],
            "networkVolumeId": volume_id,
            "volumeMountPath": mount_path,
            "env": {"PUBLIC_KEY": ssh_key} if ssh_key else {},
        }
        print(f"requesting {flavor} with {vcpu} vCPU in {dc}...")
        out = req(key, "POST", f"{V1}/pods", body)
        pod_id = out.get("id") or ""
        if pod_id:
            print(f"created pod {pod_id} ({vcpu} vCPU)")
            break
        print(f"  declined: {out}")

    if not pod_id:
        sys.exit(f"error: no capacity for vCPU in {vcpu_candidates}")

    (ROOT / ".runpod-pod-id").write_text(pod_id + "\n")
    pod = wait_ready(key, pod_id, volume_id)
    mounts = pod["mounts"]["network"][0]
    print(f"mount: {mounts['volumeId']} at {mounts['path']}")
    print("ssh:", pod["ssh"]["direct"]["command"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
