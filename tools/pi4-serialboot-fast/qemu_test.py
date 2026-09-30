#!/usr/bin/env python3
"""Protocol test of the fast-upload chainloader in QEMU (raspi2b, 32-bit), driven by the real
host code (scripts/pi4/pi4_serial_boot.send_image) over a TCP serial port.

What this tests: the LKB3/LKBT handshake, the baud-change ordering, the receive loop, the
CRC checks and recovery after each kind of failure. What it cannot test: real UART timing
(QEMU's PL011 ignores the baud rate, so a FIFO overrun cannot happen here) or the USB
adapter. Those are tested on the real Pi.

Run inside WSL:  python3 tools/pi4-serialboot-fast/qemu_test.py
"""
import os
import random
import struct
import subprocess
import sys
import time
import zlib

import serial

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "scripts", "pi4"))
import pi4_serial_boot as sb  # noqa: E402

IMG = os.path.join(HERE, "out", "kernel7l_fast_qemu.img")
PORT = 45871


class Quiet(sb.Console):
    def __init__(self):
        super().__init__(None)
        self.lines = []

    def write(self, data: bytes) -> None:
        self.lines.append(data.decode("utf-8", "replace"))


def start_qemu():
    p = subprocess.Popen(
        ["qemu-system-arm", "-M", "raspi2b", "-kernel", IMG, "-display", "none", "-monitor", "none",
         "-serial", f"tcp:127.0.0.1:{PORT},server,nowait"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    port = None
    for _ in range(50):
        try:
            port = serial.serial_for_url(f"socket://127.0.0.1:{PORT}", timeout=0.1)
            break
        except Exception:
            time.sleep(0.1)
    assert port is not None, "could not connect to QEMU's serial port"
    port.baudrate = 115200
    return p, port


def scenario(name, payload, fast, corrupt=None, truncate=None, expect="CRC OK"):
    """Boot a fresh chainloader, run one upload, check the outcome, then (for failures) check
    that a following good upload still works."""
    qemu, port = start_qemu()
    con = Quiet()
    ok = False
    detail = ""
    try:
        crc = zlib.crc32(payload) & 0xFFFFFFFF
        wire = bytearray(payload)
        if corrupt is not None:
            wire[corrupt] ^= 0x40           # bit flip on the wire, header CRC is of the good bytes
        if truncate is not None:
            wire = wire[:truncate]
        sb.wait_for(port, con, ("SBOOT?",), 20.0)
        port.write((b"LKB3" if fast else b"LKBT") + struct.pack("<II", len(payload), crc))
        reply = sb.wait_for(port, con, ("OK", "ER"), 5.0, quiet=("SBOOT?",))
        assert reply.startswith("OK"), reply
        loader_baud = port.baudrate
        if fast:
            sb.switch_baud(port, sb.FAST_BAUD, settle_s=0.35)
        port.write(bytes(wire))
        if fast:
            time.sleep(0.10)
            sb.switch_baud(port, loader_baud, settle_s=0.05)
        result = sb.wait_for(port, con, ("CRC OK", "ER"), 30.0)
        ok = result.startswith(expect)
        detail = result
        if not ok and expect.startswith("ER") is False:
            detail = "unexpected: " + result
        if expect.startswith("ER") and ok:
            # the chainloader must be back at its prompt and accept a good fast upload
            time.sleep(0.5)
            good = bytes(random.Random(7).randrange(256) for _ in range(20000))
            gcrc = zlib.crc32(good) & 0xFFFFFFFF
            sb.wait_for(port, con, ("SBOOT?",), 5.0)
            port.write(b"LKB3" + struct.pack("<II", len(good), gcrc))
            r2 = sb.wait_for(port, con, ("OK", "ER"), 5.0, quiet=("SBOOT?",))
            assert r2.startswith("OK"), r2
            sb.switch_baud(port, sb.FAST_BAUD, settle_s=0.35)
            port.write(good)
            time.sleep(0.10)
            sb.switch_baud(port, loader_baud, settle_s=0.05)
            r3 = sb.wait_for(port, con, ("CRC OK", "ER"), 30.0)
            ok = r3.startswith("CRC OK")
            detail = f"{result}  ->  recovery: {r3}"
    except SystemExit as e:
        detail = f"SystemExit: {e}"
    except Exception as e:  # noqa: BLE001
        detail = f"{type(e).__name__}: {e}"
    finally:
        port.close()
        qemu.kill()
        qemu.wait()
    print(f"{'PASS' if ok else 'FAIL'}  {name:<46} {detail}")
    return ok


def main() -> int:
    if not os.path.exists(IMG):
        sys.exit(f"missing {IMG}; run tools/pi4-serialboot-fast/build.sh")
    rnd = random.Random(1)
    big = bytes(rnd.randrange(256) for _ in range(200_000))
    small = bytes(rnd.randrange(256) for _ in range(20_000))
    results = [
        scenario("fast (LKB3) upload, 200 KB", big, fast=True),
        scenario("slow (LKBT) upload, 20 KB (regression)", small, fast=False),
        scenario("fast upload, one flipped bit -> ER crc, recovers", big, fast=True, corrupt=123_457,
                 expect="ER crc"),
        scenario("fast upload, truncated -> ER timeout, recovers", big, fast=True, truncate=100_000,
                 expect="ER timeout"),
        scenario("slow upload, one flipped bit -> ER crc", small, fast=False, corrupt=999, expect="ER crc"),
    ]
    print(f"{sum(results)}/{len(results)} scenarios passed")
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(main())
