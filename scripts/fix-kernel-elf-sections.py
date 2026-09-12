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
from dataclasses import dataclass

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


AARCH64_NOP = 0xD503201F
INFERRED = 0xFFFFFFFF


@dataclass
class InstrumentedNode:
    node: int
    counter: int


@dataclass
class EntryNode:
    node: int
    address: int


@dataclass
class FunctionDescription:
    num_leaf_nodes: int
    leaf_nodes: list[InstrumentedNode]
    edge_counters: list[int]
    call_counters: list[int]
    num_entry_nodes: int
    entry_nodes: list[EntryNode]

    @classmethod
    def parse(cls, blob: bytes, off: int = 0) -> tuple[FunctionDescription, int]:
        num_leaf = struct.unpack_from("<I", blob, off)[0]
        leaf_nodes = [
            InstrumentedNode(*struct.unpack_from("<II", blob, off + 4 + i * 8))
            for i in range(num_leaf)
        ]
        base = off + 4 + num_leaf * 8
        num_edges = struct.unpack_from("<I", blob, base)[0]
        edge_base = base + 4
        edge_counters: list[int] = []
        for i in range(num_edges):
            counter = struct.unpack_from("<I", blob, edge_base + i * 28 + 24)[0]
            if counter != INFERRED:
                edge_counters.append(counter)
        call_base = edge_base + num_edges * 28
        num_calls = struct.unpack_from("<I", blob, call_base)[0]
        call_counters: list[int] = []
        for i in range(num_calls):
            counter = struct.unpack_from("<I", blob, call_base + 4 + i * 32 + 20)[0]
            if counter != INFERRED:
                call_counters.append(counter)
        entry_base = call_base + 4 + num_calls * 32
        num_entry = struct.unpack_from("<I", blob, entry_base)[0]
        entry_nodes = [
            EntryNode(*struct.unpack_from("<QQ", blob, entry_base + 4 + i * 16))
            for i in range(num_entry)
        ]
        end = entry_base + 4 + num_entry * 16
        return (
            cls(
                num_leaf,
                leaf_nodes,
                edge_counters,
                call_counters,
                num_entry,
                entry_nodes,
            ),
            end,
        )


def parse_tables_note(elf_data: bytes, file_off: int, size: int) -> tuple[bytes, bytes]:
    blob = elf_data[file_off : file_off + size]
    namesz = struct.unpack_from("<I", blob, 0)[0]
    descsz = struct.unpack_from("<I", blob, 4)[0]
    name_end = 12 + ((namesz + 3) // 4) * 4
    desc = blob[name_end : name_end + descsz]

    ind_call_desc_size = struct.unpack_from("<I", desc, 0)[0]
    ind_call_target_size = struct.unpack_from("<I", desc, 4 + ind_call_desc_size)[0]
    func_desc_size = struct.unpack_from(
        "<I", desc, 8 + ind_call_desc_size + ind_call_target_size
    )[0]
    func_start = 12 + ind_call_desc_size + ind_call_target_size
    func_descriptions = desc[func_start : func_start + func_desc_size]
    strings = desc[func_start + func_desc_size :]
    return func_descriptions, strings


def function_counter_indices(func: FunctionDescription) -> list[int]:
    """All distinct counter slots BOLT assigned to one instrumented function."""
    counters = {leaf.counter for leaf in func.leaf_nodes}
    counters.update(func.edge_counters)
    counters.update(func.call_counters)
    if not counters:
        raise SystemExit("instrumented function has no counters")
    return sorted(counters)


def decode_table_name(strings: bytes, offset: int) -> str | None:
    if offset >= len(strings):
        return None
    try:
        end = strings.index(b"\0", offset)
    except ValueError:
        return None
    return strings[offset:end].decode()


def function_name_from_blob(func_blob: bytes, strings: bytes, off: int) -> str | None:
    num_leaf = struct.unpack_from("<I", func_blob, off)[0]
    base = off + 4 + num_leaf * 8
    num_edges = struct.unpack_from("<I", func_blob, base)[0]
    if num_edges:
        fn = struct.unpack_from("<I", func_blob, base + 4)[0]
        return decode_table_name(strings, fn)
    call_base = base + 4 + num_edges * 28
    num_calls = struct.unpack_from("<I", func_blob, call_base)[0]
    if num_calls:
        fn = struct.unpack_from("<I", func_blob, call_base + 4)[0]
        return decode_table_name(strings, fn)
    if num_leaf == 0:
        return None
    return decode_table_name(strings, 0)


def function_counter_map(
    elf_data: bytes,
    section_map: dict[str, tuple[int, int, int]],
    funcs: list[str] | None = None,
) -> dict[str, list[int]]:
    if ".bolt.instr.tables" not in section_map:
        raise SystemExit("ELF has no .bolt.instr.tables section")
    _, tables_off, tables_size = section_map[".bolt.instr.tables"]
    func_blob, strings = parse_tables_note(elf_data, tables_off, tables_size)
    result: dict[str, list[int]] = {}
    unnamed: list[list[int]] = []
    off = 0
    while off < len(func_blob):
        func, next_off = FunctionDescription.parse(func_blob, off)
        if next_off <= off:
            break
        name = function_name_from_blob(func_blob, strings, off)
        indices = function_counter_indices(func)
        if name is not None:
            result[name] = indices
        else:
            unnamed.append(indices)
        off = next_off
    if unnamed and funcs:
        if len(unnamed) == len(funcs):
            for func, indices in zip(funcs, unnamed):
                result[func] = indices
        elif len(unnamed) == 1 and len(funcs) == 1:
            result[funcs[0]] = unnamed[0]
    return result


def find_hook_site(
    data: bytearray, section_map: dict[str, tuple[int, int, int]], entry: int
) -> int:
    """Pick a NOP slot in org.text for the counter branch hook."""
    for delta in range(0x4, 0x24, 4):
        site = entry + delta
        off = vaddr_to_offset(section_map, site)
        insn = struct.unpack_from("<I", data, off)[0]
        if insn == AARCH64_NOP:
            return site
    return entry + 0xC


def patch_orgtext_counter_hook(
    data: bytearray,
    nm: str,
    section_map: dict[str, tuple[int, int, int]],
    original: str,
    funcs: list[str],
    counter_indices: dict[str, list[int]],
) -> None:
    """Bump bolt_bench BOLT counter slots from org.text.

    LK runs the org.text copy; hot .text is not used on this bare-metal path.
    Each hooked function bumps every counter index BOLT assigned to it.
    """
    counter_base = section_map[".bolt.instr.counters"][0]
    scratch = symbol_addr(nm, original, "print_fault_msg")
    if scratch is None:
        org_addr, _, org_size = section_map[".bolt.org.text"]
        scratch = org_addr + org_size - 0x60

    for func in funcs:
        entry = symbol_addr(nm, original, func)
        if entry is None:
            print(f"warning: skipping hook for missing symbol {func}", file=sys.stderr)
            continue
        if func not in counter_indices:
            print(
                f"warning: no BOLT counter indices for {func}, skipping hook",
                file=sys.stderr,
            )
            continue
        indices = counter_indices[func]
        hook_site = find_hook_site(data, section_map, entry)
        resume = hook_site + 4

        stub = scratch
        insns: list[int] = [0xA9BF0BE0, 0xA9BF13E1]  # stp x0,x1; stp x2,x3
        for counter_index in indices:
            counter_addr = counter_base + counter_index * 8
            adrp_pc = stub + len(insns) * 4
            insns.append(encode_adrp(0, adrp_pc, counter_addr))
            insns.append(encode_add_imm12(0, 0, counter_addr & 0xFFF))
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
        addrs = ", ".join(f"{idx}->0x{counter_base + idx * 8:x}" for idx in indices)
        print(
            f"org.text hook {func}: nop at 0x{hook_site:x} -> stub 0x{stub:x}, "
            f"counters [{addrs}]"
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
        elf_data = fh.read()
    data = bytearray(elf_data)
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
        counter_indices = function_counter_map(elf_data, dst_map, funcs)
        patch_orgtext_counter_hook(
            data, nm, dst_map, args.original, funcs, counter_indices
        )

    out = args.output or args.elf
    with open(out, "wb") as fh:
        fh.write(data)
    print(f"patched {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
