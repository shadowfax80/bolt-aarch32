#!/usr/bin/env python3
"""Boot an instrumented LK image and read BOLT's counter array out of the guest.

Upstream bolt-rt writes .fdata itself from a DT_FINI hook. LK never runs
DT_FINI and has no filesystem, so the bare-metal runtime only keeps counters
ticking in .bolt.instr.counters and extraction happens from outside: this
script drives QEMU over QMP and asks the monitor to save that address range.

Verifies the two things a first bring-up needs: the instrumented image still
boots, and the counters are actually being incremented.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import socket
import subprocess
import sys
import tempfile
import time

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
    raise SystemExit(
        f"{elf} has no {COUNTER_SECTION} — was it built with llvm-bolt -instrument?"
    )


GETTER_RE = re.compile(
    r"adrp\s+x0,\s+0x([0-9a-fA-F]+).*\n\s*[0-9a-fA-F]+:\s+add\s+x0,\s+x0,\s+#0x([0-9a-fA-F]+)",
    re.MULTILINE,
)


def getter_address(objdump: str, elf: str, name: str) -> int:
    """Decode the ADRP+ADD pair BOLT injects as __bolt_*_getter.

    The data symbols themselves are not exported in the rewritten ELF, so
    the getter is the only host-visible record of where the array lives.
    """
    nm = subprocess.run(
        [objdump.replace("llvm-objdump", "llvm-nm"), elf],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    start = None
    for line in nm.splitlines():
        parts = line.split()
        if len(parts) == 3 and parts[2] == name:
            start = int(parts[0], 16)
            break
    if start is None:
        raise SystemExit(f"{elf} has no {name}")
    out = subprocess.run(
        [
            objdump,
            "-d",
            "--no-show-raw-insn",
            f"--start-address={hex(start)}",
            f"--stop-address={hex(start + 16)}",
            elf,
        ],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    m = GETTER_RE.search(out)
    if not m:
        raise SystemExit(f"could not decode {name} from:\n{out}")
    return int(m.group(1), 16) + int(m.group(2), 16)


class Qmp:
    def __init__(self, path: str, timeout: float) -> None:
        deadline = time.time() + timeout
        while True:
            try:
                self.sock = socket.socket(socket.AF_UNIX)
                self.sock.connect(path)
                break
            except OSError:
                if time.time() > deadline:
                    raise SystemExit(f"could not connect to QMP socket {path}")
                time.sleep(0.1)
        self.f = self.sock.makefile("rw", encoding="utf-8", newline="\n")
        self._read()  # greeting
        self.execute("qmp_capabilities")

    def _read(self) -> dict:
        while True:
            line = self.f.readline()
            if not line:
                raise SystemExit("QMP connection closed")
            msg = json.loads(line)
            if "event" not in msg:
                return msg

    def execute(self, command: str, **arguments) -> dict:
        payload = {"execute": command}
        if arguments:
            payload["arguments"] = arguments
        self.f.write(json.dumps(payload) + "\n")
        self.f.flush()
        reply = self._read()
        if "error" in reply:
            raise SystemExit(f"{command} failed: {reply['error']}")
        return reply

    def monitor(self, command_line: str) -> str:
        return self.execute(
            "human-monitor-command", **{"command-line": command_line}
        ).get("return", "")


def wait_for_marker(log: str, marker: str, timeout: float) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with open(log, "r", errors="replace") as fh:
                if marker in fh.read():
                    return True
        except FileNotFoundError:
            pass
        time.sleep(0.25)
    return False


def nonzero_counters(path: str, offset: int, count: int) -> tuple[int, int]:
    """Count set counters in the array only.

    The overlay patch emits the metadata tables into this same section, so
    measuring the whole dump would report table bytes as live counters.
    """
    with open(path, "rb") as fh:
        blob = fh.read()
    array = blob[offset : offset + count * 8]
    hot = sum(
        1
        for i in range(len(array) // 8)
        if int.from_bytes(array[i * 8 : i * 8 + 8], "little") != 0
    )
    return hot, count


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--elf", required=True, help="instrumented LK image")
    ap.add_argument("--out", default="bolt-counters.bin")
    ap.add_argument("--serial-log", default="lk-serial.log")
    ap.add_argument(
        "--toolchain", default=os.environ.get("TOOLCHAIN", "build/bin")
    )
    ap.add_argument("--qemu", default=os.environ.get("QEMU", "qemu-system-aarch64"))
    ap.add_argument("--cpu", default=os.environ.get("QEMU_CPU", "cortex-a53"))
    ap.add_argument("--machine", default=os.environ.get("QEMU_MACHINE", "virt"))
    ap.add_argument("--mem", default=os.environ.get("QEMU_MEM", "512"))
    ap.add_argument("--smp", default=os.environ.get("QEMU_SMP", "4"))
    ap.add_argument(
        "--boot-marker",
        default="entering main console loop",
        help="serial output that means LK reached its shell",
    )
    ap.add_argument("--boot-timeout", type=float, default=120.0)
    ap.add_argument(
        "--settle",
        type=float,
        default=5.0,
        help="seconds to let the workload run after boot before dumping",
    )
    ap.add_argument(
        "--append",
        default="",
        help="QEMU kernel cmdline (e.g. lk.bolt_bench=all for bolt_bench workloads)",
    )
    args = ap.parse_args()

    readelf = os.path.join(args.toolchain, "llvm-readelf")
    objdump = os.path.join(args.toolchain, "llvm-objdump")
    addr, size = counter_range(readelf, args.elf)
    locations = getter_address(objdump, args.elf, "__bolt_instr_locations_getter")
    num_counters = getter_address(objdump, args.elf, "__bolt_num_counters_getter")
    locations_off = locations - addr
    num_counters_off = num_counters - addr

    print(f"{COUNTER_SECTION}: {size} bytes at 0x{addr:x}")
    print(f"counters at 0x{locations:x} (+0x{locations_off:x})")
    print(f"__bolt_num_counters at 0x{num_counters:x} (+0x{num_counters_off:x})")

    tmp = tempfile.mkdtemp(prefix="bolt-qemu-")
    qmp_path = os.path.join(tmp, "qmp.sock")
    log = os.path.abspath(args.serial_log)
    open(log, "w").close()

    cmd = [
        args.qemu,
        "-machine", args.machine,
        "-cpu", args.cpu,
        "-m", args.mem,
        "-smp", args.smp,
        "-display", "none",
        "-serial", f"file:{log}",
        "-qmp", f"unix:{qmp_path},server=on,wait=off",
        "-kernel", args.elf,
    ]
    if args.append:
        cmd.extend(["-append", args.append])
    print("launching:", " ".join(cmd))
    qemu_err = log + ".qemu-err"
    qemu = subprocess.Popen(
        cmd, stdout=subprocess.DEVNULL, stderr=open(qemu_err, "w")
    )

    try:
        qmp = Qmp(qmp_path, timeout=30.0)
        booted = wait_for_marker(log, args.boot_marker, args.boot_timeout)
        if not booted:
            print(
                f"warning: never saw {args.boot_marker!r} in {log}; dumping anyway",
                file=sys.stderr,
            )
        else:
            print(f"booted: saw {args.boot_marker!r}")
        time.sleep(args.settle)

        out = os.path.abspath(args.out)
        # memsave reads through CPU 0's translation, which matches the link
        # addresses while LK's kernel mapping is active. pmemsave is the
        # fallback for images running with the MMU off.
        qmp.monitor(f'memsave 0x{addr:x} {size} "{out}"')
        if not os.path.exists(out):
            print("virtual read produced no file, retrying physical", file=sys.stderr)
            qmp.monitor(f'pmemsave 0x{addr:x} {size} "{out}"')
    finally:
        qemu.terminate()
        try:
            qemu.wait(timeout=10)
        except subprocess.TimeoutExpired:
            qemu.kill()

    with open(args.out, "rb") as fh:
        blob = fh.read()
    if num_counters_off + 4 > len(blob):
        raise SystemExit(f"{args.out} is only {len(blob)} bytes, expected {size}")
    count = int.from_bytes(blob[num_counters_off : num_counters_off + 4], "little")
    print(f"__bolt_num_counters = {count}")
    hot, total = nonzero_counters(args.out, locations_off, count)
    print(f"{args.out}: {hot}/{total} counters non-zero")
    if hot == 0:
        print(
            "error: every counter is zero — instrumentation did not run",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
