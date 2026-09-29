#!/usr/bin/env python3
"""Cross-check harness for the UART-based counter dump (Step 4 of the
real-hardware BOLT verification plan): boots an instrumented LK image
under QEMU with a TCP-socket serial chardev instead of QMP, runs the
workloads, then sends `bolt_dump <addr> <size>` and reassembles the
result -- so it can be diffed byte-for-byte against dump-bolt-counters.py's
QMP-based dump of the same image before either method is trusted on the
real Pi.

Not meant to replace dump-bolt-counters.py under QEMU long-term (QMP is
fine there); this only exists to validate the UART protocol with zero
hardware risk before scripts/pi4/pi4_bolt_dump.py trusts it on real serial.
"""

from __future__ import annotations

import argparse
import os
import re
import socket
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bolt_dump_reassemble import DumpResult, parse_dump_stream  # noqa: E402

SECTION_RE = re.compile(
    r"\[\s*\d+\]\s+(?P<name>\S+)\s+\S+\s+(?P<addr>[0-9a-fA-F]+)\s+"
    r"(?P<off>[0-9a-fA-F]+)\s+(?P<size>[0-9a-fA-F]+)"
)
COUNTER_SECTION = ".bolt.instr.counters"


def counter_range(readelf: str, elf: str) -> tuple[int, int]:
    out = subprocess.run(
        [readelf, "--sections", elf], check=True, capture_output=True, text=True
    ).stdout
    for line in out.splitlines():
        m = SECTION_RE.search(line)
        if m and m.group("name") == COUNTER_SECTION:
            return int(m.group("addr"), 16), int(m.group("size"), 16)
    raise SystemExit(f"{elf} has no {COUNTER_SECTION}")


class QemuSerial:
    def __init__(self, cmd: list[str], port: int):
        self.proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.sock = None
        deadline = time.time() + 10
        while time.time() < deadline:
            try:
                self.sock = socket.create_connection(("127.0.0.1", port), timeout=2)
                break
            except OSError:
                time.sleep(0.2)
        if self.sock is None:
            self.proc.terminate()
            raise SystemExit("could not connect to QEMU serial socket")
        self.sock.settimeout(30)
        self.buf = b""

    def read_until(self, marker: bytes, timeout: float) -> bytes:
        end = time.time() + timeout
        while marker not in self.buf and time.time() < end:
            try:
                chunk = self.sock.recv(65536)
            except socket.timeout:
                continue
            if not chunk:
                break
            self.buf += chunk
        return self.buf

    def send(self, line: str) -> None:
        self.sock.sendall((line + "\r\n").encode())

    def close(self) -> None:
        try:
            self.proc.terminate()
            self.proc.wait(timeout=10)
        except Exception:
            self.proc.kill()


def dump_via_uart(qs: QemuSerial, addr: int, size: int, retries: int = 3) -> bytes:
    result: DumpResult | None = None
    for attempt in range(retries):
        if result is None:
            qs.send(f"bolt_dump {addr:x} {size:x}")
        else:
            missing = result.missing_ranges()
            if not missing:
                break
            off, length = missing[0]
            qs.send(f"bolt_dump {addr + off:x} {length:x}")
        qs.buf = b""
        text = qs.read_until(b"BOLT_DUMP_END", 15).decode(errors="replace")
        result = parse_dump_stream(text, result)
        if result.is_complete():
            break
    if result is None or not result.is_complete():
        raise SystemExit(
            f"dump incomplete after {retries} attempts: "
            f"{result.missing_ranges() if result else 'no data'}"
        )
    if result.bad_seqs:
        print(f"warning: {len(result.bad_seqs)} chunk(s) failed checksum and were retried", file=sys.stderr)
    return result.to_bytes()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--elf", required=True)
    ap.add_argument("--out", default="bolt-counters-uart.bin")
    ap.add_argument("--toolchain", default=os.environ.get("TOOLCHAIN", "build-atfe/bin"))
    ap.add_argument("--qemu", default="qemu-system-arm")
    ap.add_argument("--cpu", default="cortex-a15")
    ap.add_argument("--machine", default="virt")
    ap.add_argument("--mem", default="512")
    ap.add_argument("--smp", default="1")
    ap.add_argument("--append", default="")
    ap.add_argument("--boot-marker", default="entering main console loop")
    ap.add_argument("--boot-timeout", type=float, default=20.0)
    ap.add_argument("--settle", type=float, default=3.0)
    ap.add_argument("--port", type=int, default=45455)
    args = ap.parse_args()

    readelf = os.path.join(args.toolchain, "llvm-readelf")
    addr, size = counter_range(readelf, args.elf)
    print(f"{COUNTER_SECTION}: {size} bytes at 0x{addr:x}")

    cmd = [
        args.qemu, "-machine", args.machine, "-cpu", args.cpu, "-m", args.mem,
        "-smp", args.smp, "-display", "none",
        "-chardev", f"socket,id=lkserial,host=127.0.0.1,port={args.port},server=on,wait=off",
        "-serial", "chardev:lkserial",
        "-kernel", args.elf,
    ]
    if args.append:
        cmd.extend(["-append", args.append])
    print("launching:", " ".join(cmd))

    qs = QemuSerial(cmd, args.port)
    try:
        out = qs.read_until(args.boot_marker.encode(), args.boot_timeout)
        if args.boot_marker.encode() not in out:
            raise SystemExit(f"never saw {args.boot_marker!r}")
        print(f"booted: saw {args.boot_marker!r}")
        time.sleep(args.settle)
        qs.buf = b""

        blob = dump_via_uart(qs, addr, size)
        with open(args.out, "wb") as fh:
            fh.write(blob)
        print(f"wrote {len(blob)} bytes to {args.out}")
    finally:
        qs.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
