#!/usr/bin/env python3
"""Reset e_entry on a BOLT-instrumented kernel ELF to the original boot path.

llvm-bolt -instrument points e_entry at __bolt_instr_start in .text.bolt.extra,
which tail-calls the relocated _start. LK's boot chain (MMU off, V=P+offset
load segments) must begin at the copy in .bolt.org.text instead.
"""

from __future__ import annotations

import argparse
import re
import struct
import subprocess
import sys

ORG_TEXT = ".bolt.org.text"
SECTION_RE = re.compile(
    r"\[\s*\d+\]\s+(?P<name>\S+)\s+\S+\s+(?P<addr>[0-9a-fA-F]+)\s+"
    r"(?P<off>[0-9a-fA-F]+)\s+(?P<size>[0-9a-fA-F]+)"
)


def section_addr(readelf: str, elf: str, name: str) -> int:
    out = subprocess.run(
        [readelf, "--sections", elf], check=True, capture_output=True, text=True
    ).stdout
    for line in out.splitlines():
        m = SECTION_RE.search(line)
        if m and m.group("name") == name:
            return int(m.group("addr"), 16)
    raise SystemExit(f"{elf} has no {name} section")


def elf_class(elf: bytes) -> int:
    """EI_CLASS: 1=ELF32, 2=ELF64."""
    return elf[4]


def read_entry(elf: bytes) -> int:
    if elf_class(elf) == 1:
        return struct.unpack_from("<I", elf, 24)[0]
    return struct.unpack_from("<Q", elf, 24)[0]


def write_entry(data: bytearray, entry: int) -> None:
    if elf_class(data) == 1:
        struct.pack_into("<I", data, 24, entry & 0xFFFFFFFF)
    else:
        struct.pack_into("<Q", data, 24, entry)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("elf", help="instrumented (or optimized) kernel ELF")
    ap.add_argument(
        "--original",
        help="uninstrumented lk.elf; e_entry is copied when set",
    )
    ap.add_argument(
        "--readelf",
        default="llvm-readelf",
        help="path to llvm-readelf (default: llvm-readelf)",
    )
    ap.add_argument("-o", "--output", help="write patched ELF here (default: in place)")
    args = ap.parse_args()

    with open(args.elf, "rb") as fh:
        data = bytearray(fh.read())

    if data[:4] != b"\x7fELF":
        print("not an ELF file", file=sys.stderr)
        return 1
    if data[4] not in (1, 2) or data[5] != 1:
        print("expected ELF32/ELF64 little-endian", file=sys.stderr)
        return 1

    old_entry = read_entry(data)
    if args.original:
        with open(args.original, "rb") as fh:
            orig = fh.read()
        new_entry = read_entry(orig)
        source = args.original
    else:
        new_entry = section_addr(args.readelf, args.elf, ORG_TEXT)
        source = ORG_TEXT

    if old_entry == new_entry:
        print(f"e_entry already 0x{old_entry:x} ({source})")
        return 0

    write_entry(data, new_entry)
    out = args.output or args.elf
    with open(out, "wb") as fh:
        fh.write(data)
    print(
        f"e_entry 0x{old_entry:x} -> 0x{new_entry:x} "
        f"(from {source}) in {out}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
