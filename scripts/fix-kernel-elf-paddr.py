#!/usr/bin/env python3
"""Rewrite p_paddr on BOLT-added PT_LOAD segments of a kernel ELF.

LK is a V=P+offset image: VirtAddr lives in the TTBR1 window, PhysAddr in
DRAM. llvm-bolt emits its extra segments with p_paddr = p_vaddr, so QEMU's
-kernel loader tries to place them at 0xffff…, which is not RAM, and the
guest never fetches an instruction. Serial stays empty.

This copies the vaddr→paddr delta of the first original LOAD onto every
LOAD whose physical address still equals its virtual address.
"""

from __future__ import annotations

import argparse
import struct
import sys

PT_LOAD = 1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("elf")
    ap.add_argument("-o", "--output")
    args = ap.parse_args()

    with open(args.elf, "rb") as fh:
        data = bytearray(fh.read())

    if data[:4] != b"\x7fELF":
        print("not an ELF file", file=sys.stderr)
        return 1
    if data[4] != 2 or data[5] != 1:
        print("expected ELF64 little-endian", file=sys.stderr)
        return 1

    e_phoff = struct.unpack_from("<Q", data, 32)[0]
    e_phentsize, e_phnum = struct.unpack_from("<HH", data, 54)

    loads = []
    for i in range(e_phnum):
        off = e_phoff + i * e_phentsize
        p_type, p_flags = struct.unpack_from("<II", data, off)
        p_offset, p_vaddr, p_paddr, p_filesz, p_memsz, p_align = struct.unpack_from(
            "<QQQQQQ", data, off + 8
        )
        if p_type == PT_LOAD:
            loads.append((off, p_vaddr, p_paddr))

    if not loads:
        print("no PT_LOAD segments", file=sys.stderr)
        return 1

    orig_vaddr, orig_paddr = loads[0][1], loads[0][2]
    if orig_vaddr == orig_paddr:
        print("first LOAD is already V=P; nothing to rewrite", file=sys.stderr)
        return 0
    delta = orig_paddr - orig_vaddr

    rewritten = 0
    for off, vaddr, paddr in loads:
        if vaddr == paddr:
            new_paddr = (vaddr + delta) & 0xFFFFFFFFFFFFFFFF
            struct.pack_into("<Q", data, off + 24, new_paddr)
            print(f"LOAD vaddr 0x{vaddr:x}: paddr 0x{paddr:x} -> 0x{new_paddr:x}")
            rewritten += 1

    if rewritten == 0:
        print("no BOLT-style V=P LOAD segments found")
        return 0

    out = args.output or args.elf
    with open(out, "wb") as fh:
        fh.write(data)
    print(f"rewrote {rewritten} LOAD p_paddr field(s) in {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
