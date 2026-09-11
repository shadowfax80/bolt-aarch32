#!/usr/bin/env python3
"""Restore kernel ELF sections BOLT must not rewrite for bare-metal boot.

BOLT moves instrumented code into a hot .text segment but also patches
.bolt.org.text entry points and rewrites .data/.rodata pointers. LK boots
with the MMU off using the org.text copy and fixed RAM mappings; corrupted
.data breaks page-table setup long before the serial console comes up.

This copies selected sections from the uninstrumented lk.elf back into the
BOLT output. Instrumentation still lives in hot .text; only boot-critical
images are reset.
"""

from __future__ import annotations

import argparse
import re
import struct
import subprocess
import sys

RESTORE_RENAME = (
    (".bolt.org.text", ".text"),
)
# Function-pointer tables BOLT rewrites to hot .text addresses.
RESTORE_SAME_NAME = (
    ".data",
    ".rodata",
    "lk_init",
    "commands",
    "apps",
    "fs_impl",
    ".ctors",
    ".got",
)
SECTION_RE = re.compile(
    r"\[\s*\d+\]\s+(?P<name>\S+)\s+\S+\s+(?P<addr>[0-9a-fA-F]+)\s+"
    r"(?P<off>[0-9a-fA-F]+)\s+(?P<size>[0-9a-fA-F]+)"
)


def sections(readelf: str, elf: str) -> dict[str, tuple[int, int, int]]:
    out = subprocess.run(
        [readelf, "--sections", elf], check=True, capture_output=True, text=True
    ).stdout
    result: dict[str, tuple[int, int, int]] = {}
    for line in out.splitlines():
        m = SECTION_RE.search(line)
        if m:
            result[m.group("name")] = (
                int(m.group("addr"), 16),
                int(m.group("off"), 16),
                int(m.group("size"), 16),
            )
    return result


def symbol_addr(nm: str, elf: str, name: str) -> int | None:
    out = subprocess.run([nm, elf], check=True, capture_output=True, text=True).stdout
    for line in out.splitlines():
        parts = line.split()
        if len(parts) == 3 and parts[2] == name:
            return int(parts[0], 16)
    return None


def encode_bl(pc: int, target: int) -> int:
    offset = (target - pc) // 4
    if offset < -(1 << 25) or offset >= (1 << 25):
        raise SystemExit(
            f"bl from 0x{pc:x} to 0x{target:x} is out of range; "
            "need a trampoline stub instead"
        )
    return 0x94000000 | (offset & 0x03FFFFFF)


def encode_b(pc: int, target: int) -> int:
    offset = (target - pc) // 4
    if offset < -(1 << 26) or offset >= (1 << 26):
        raise SystemExit(f"b from 0x{pc:x} to 0x{target:x} is out of range")
    return 0x14000000 | (offset & 0x03FFFFFF)


def encode_adrp(rd: int, pc: int, target: int) -> int:
    imm = ((target & ~0xFFF) - (pc & ~0xFFF)) >> 12
    immlo = imm & 3
    immhi = (imm >> 2) & 0x7FFFF
    return 0x90000000 | (immlo << 29) | (immhi << 5) | rd


def encode_add_imm12(rd: int, rn: int, imm12: int) -> int:
    return 0x91000000 | ((imm12 & 0xFFF) << 10) | (rn << 5) | rd


def vaddr_to_offset(section_map: dict[str, tuple[int, int, int]], vaddr: int) -> int:
    for _name, (sec_addr, sec_off, sec_size) in section_map.items():
        if sec_addr <= vaddr < sec_addr + sec_size:
            return sec_off + (vaddr - sec_addr)
    raise SystemExit(f"no section contains vaddr 0x{vaddr:x}")


def patch_orgtext_counter_hook(
    data: bytearray,
    nm: str,
    section_map: dict[str, tuple[int, int, int]],
    original: str,
    funcs: list[str],
) -> None:
    """Hook instrumented functions in org.text without entering hot .text.

    Hot .text is not mapped for early boot. Each target gets a counter-bump
    stub (overwriting print_fault_msg) and its NOP slot branches to the stub.
    """
    counter_addr = section_map[".bolt.instr.counters"][0]
    scratch = symbol_addr(nm, original, "print_fault_msg")
    if scratch is None:
        org_addr, _, org_size = section_map[".bolt.org.text"]
        scratch = org_addr + org_size - 0x60

    for func in funcs:
        entry = symbol_addr(nm, original, func)
        if entry is None:
            print(f"warning: skipping hook for missing symbol {func}", file=sys.stderr)
            continue
        hook_site = entry + 0xC
        resume = hook_site + 4

        stub = scratch
        insns: list[int] = [0xA9BF0BE0, 0xA9BF13E1]  # stp x0,x1; stp x2,x3
        adrp_pc = stub + len(insns) * 4
        insns.append(encode_adrp(0, adrp_pc, counter_addr))
        insns.append(encode_add_imm12(0, 0, counter_addr & 0xFFF))
        loop = stub + len(insns) * 4
        insns.extend([0xC85FFC01, 0x91000421, 0xC802FC01, 0x35FFFFA2])
        insns.extend([0xA8C113E1, 0xA8C10BE0])
        tail_pc = stub + len(insns) * 4
        insns.append(encode_b(tail_pc, resume))

        stub_bytes = struct.pack("<" + "I" * len(insns), *insns)
        stub_off = vaddr_to_offset(section_map, stub)
        data[stub_off : stub_off + len(stub_bytes)] = stub_bytes
        hook_off = vaddr_to_offset(section_map, hook_site)
        data[hook_off : hook_off + 4] = struct.pack("<I", encode_b(hook_site, stub))
        scratch += ((len(stub_bytes) + 15) // 16) * 16
        print(
            f"org.text hook {func}: nop at 0x{hook_site:x} -> stub 0x{stub:x}, "
            f"counter 0x{counter_addr:x}"
        )


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("elf", help="instrumented or optimized kernel ELF")
    ap.add_argument("--original", required=True, help="unmodified lk.elf")
    ap.add_argument(
        "--readelf",
        default="llvm-readelf",
        help="path to llvm-readelf (default: llvm-readelf)",
    )
    ap.add_argument("-o", "--output", help="write patched ELF here (default: in place)")
    ap.add_argument(
        "--hook-funcs",
        default="",
        help="comma-separated functions to hook in org.text for counter bumps",
    )
    args = ap.parse_args()
    nm = args.readelf.replace("llvm-readelf", "llvm-nm")
    if "/" not in nm:
        nm = "llvm-nm"

    dst_map = sections(args.readelf, args.elf)
    src_map = sections(args.readelf, args.original)

    with open(args.elf, "rb") as fh:
        data = bytearray(fh.read())
    with open(args.original, "rb") as fh:
        orig = fh.read()

    def restore(dst_name: str, src_name: str) -> None:
        if dst_name not in dst_map:
            print(f"warning: {args.elf} has no {dst_name}, skipping", file=sys.stderr)
            return
        if src_name not in src_map:
            print(f"error: {args.original} has no {src_name}", file=sys.stderr)
            raise SystemExit(1)
        _, dst_off, dst_size = dst_map[dst_name]
        _, src_off, src_size = src_map[src_name]
        copy_size = min(dst_size, src_size)
        if dst_size != src_size:
            print(
                f"warning: {dst_name} size 0x{dst_size:x} != "
                f"{src_name} size 0x{src_size:x}; copying 0x{copy_size:x}",
                file=sys.stderr,
            )
        data[dst_off : dst_off + copy_size] = orig[src_off : src_off + copy_size]
        print(f"restored {copy_size} bytes: {src_name} -> {dst_name}")

    for dst_name, src_name in RESTORE_RENAME:
        restore(dst_name, src_name)
    for name in RESTORE_SAME_NAME:
        restore(name, name)

    funcs = [f.strip() for f in args.hook_funcs.split(",") if f.strip()]
    if funcs:
        patch_orgtext_counter_hook(data, nm, dst_map, args.original, funcs)

    out = args.output or args.elf
    with open(out, "wb") as fh:
        fh.write(data)
    print(f"patched {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
