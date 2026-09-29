#!/usr/bin/env python3
"""Debugging aid: boot an LK image under QEMU, type shell commands, print the
transcript. QEMU is for *debugging* (one readable console instead of the Pi's
interleaved per-core output, optional gdb stub, no power-cycling after a hang);
it is never the source of a reported result -- its cycle/PMU numbers are not
real. Final verification and every measurement are on the real Pi.

usage: qemu_console.py <lk.elf> [--smp 4] [--gdb] [--wait 20] <cmd> [<cmd> ...]
"""

from __future__ import annotations

import argparse
import socket
import subprocess
import sys
import time


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("elf")
    ap.add_argument("--qemu", default="qemu-system-arm")
    ap.add_argument("--cpu", default="cortex-a15")
    ap.add_argument("--smp", default="4")
    ap.add_argument("--mem", default="512")
    ap.add_argument("--port", type=int, default=45460)
    ap.add_argument("--boot-marker", default="entering main console loop")
    ap.add_argument("--wait", type=float, default=20.0, help="seconds to wait for output after each command")
    ap.add_argument("--gdb", action="store_true", help="start with a gdb stub on :1234, paused (-S)")
    ap.add_argument("cmds", nargs="*")
    args = ap.parse_intermixed_args()

    cmd = [
        args.qemu, "-machine", "virt", "-cpu", args.cpu, "-m", args.mem, "-smp", args.smp,
        "-display", "none", "-monitor", "none",
        "-chardev", f"socket,id=s0,host=127.0.0.1,port={args.port},server=on,wait=off",
        "-serial", "chardev:s0", "-kernel", args.elf,
    ]
    if args.gdb:
        cmd += ["-s", "-S"]
    proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    sock = None
    end = time.time() + 10
    while time.time() < end and sock is None:
        try:
            sock = socket.create_connection(("127.0.0.1", args.port), timeout=2)
        except OSError:
            time.sleep(0.2)
    if sock is None:
        proc.kill()
        sys.exit("could not connect to the QEMU serial socket")
    sock.settimeout(1.0)

    transcript = b""

    def drain(seconds: float, until: bytes | None = None, since: int = 0,
              after: bytes = b"") -> None:
        """Read until `until` appears in what arrived after offset `since`, or the
        deadline. The shell prints a fresh NL + "] " prompt when a command finishes,
        so waiting for that is exact -- an idle-timeout heuristic killed QEMU under
        a still-running (slow, BOLT-instrumented) workload."""
        nonlocal transcript
        stop = time.time() + seconds
        while time.time() < stop:
            try:
                chunk = sock.recv(65536)
            except socket.timeout:
                continue
            if not chunk:
                return
            transcript += chunk
            if until:
                # The shell prints its prompt again while echoing the command, so only
                # a prompt that arrives AFTER the echoed command text means "finished".
                i = transcript.find(after, since) if after else since
                if i >= 0 and until in transcript[i + len(after):]:
                    return

    try:
        drain(args.wait, until=args.boot_marker.encode())
        for c in args.cmds:
            transcript += f"\n>>> {c}\n".encode()
            start = len(transcript)
            sock.sendall((c + "\r\n").encode())
            drain(args.wait, until=b"\n] ", since=start, after=c.encode())
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
    sys.stdout.write(transcript.decode("utf-8", errors="replace"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
