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
    out = subprocess.run([nm, "-a", elf], check=True, capture_output=True, text=True).stdout
    for line in out.splitlines():
        parts = line.split()
        if len(parts) == 3 and parts[2] == name:
            return int(parts[0], 16)
    return None


def is_thumb_symbol(nm: str, elf: str, name: str) -> bool:
    """Per-function ARM/Thumb detection for AArch32, mirroring what BOLT
    itself does (RewriteInstance.cpp): a function is Thumb if a $t mapping
    symbol sits at its exact entry address. ELFObjectFile::getSymbolAddress()
    clears the Thumb LSB for STT_FUNC symbols before nm ever sees them, so
    the symbol's own address can't be used -- only a co-located $t marker
    tells you. Defaults to ARM (False) when no marker is found there, same
    as BOLT's own default.

    This exists because a prior version of this script decided ARM vs Thumb
    encoding from the ELF's EI_CLASS byte (data[4] == 1 for any 32-bit ELF,
    including AArch32-ARM-mode binaries) instead of from the actual target
    function's ISA mode -- always Thumb-encoding the hook for AArch32,
    corrupting ARM-mode functions' entry points with Thumb bytes that get
    misdecoded as garbage the instant the CPU arrives there in ARM state.
    """
    out = subprocess.run([nm, "-a", elf], check=True, capture_output=True, text=True).stdout
    rows: list[tuple[int, str]] = []
    addr = None
    for line in out.splitlines():
        parts = line.split()
        if len(parts) != 3:
            continue
        try:
            value = int(parts[0], 16)
        except ValueError:
            continue
        rows.append((value, parts[2]))
        if parts[2] == name:
            addr = value
    if addr is None:
        raise SystemExit(f"symbol {name} not found in {elf}")
    for value, sym_name in rows:
        if value == addr and (sym_name == "$t" or sym_name.startswith("$t.")):
            return True
    return False


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
    # Leaf-only descriptors omit a name offset; do not assume strings[0]
    # (that falsely labels every unnamed leaf as the first string).
    return None


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
        missing = [f for f in funcs if f not in result]
        if len(unnamed) == len(missing):
            for func, indices in zip(missing, unnamed):
                result[func] = indices
        elif len(unnamed) == len(funcs):
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


def encode_thumb_movw(rd: int, imm16: int) -> bytes:
    i = (imm16 >> 11) & 1
    imm4 = (imm16 >> 12) & 0xF
    imm3 = (imm16 >> 8) & 0x7
    imm8 = imm16 & 0xFF
    hw1 = 0xF240 | (i << 10) | imm4
    hw2 = (imm3 << 12) | (rd << 8) | imm8
    return struct.pack("<HH", hw1, hw2)


def encode_thumb_movt(rd: int, imm16: int) -> bytes:
    i = (imm16 >> 11) & 1
    imm4 = (imm16 >> 12) & 0xF
    imm3 = (imm16 >> 8) & 0x7
    imm8 = imm16 & 0xFF
    hw1 = 0xF2C0 | (i << 10) | imm4
    hw2 = (imm3 << 12) | (rd << 8) | imm8
    return struct.pack("<HH", hw1, hw2)


def encode_thumb_bw(pc: int, target: int) -> bytes:
    """Unconditional Thumb-2 B.W (encoding T4)."""
    offset = target - pc - 4
    if offset % 2:
        raise SystemExit(f"thumb b.w to odd offset from 0x{pc:x} -> 0x{target:x}")
    imm = offset >> 1
    if imm < -(1 << 23) or imm >= (1 << 23):
        raise SystemExit(f"thumb b.w from 0x{pc:x} to 0x{target:x} out of range")
    s = (imm >> 23) & 1
    i1 = (imm >> 22) & 1
    i2 = (imm >> 21) & 1
    imm10 = (imm >> 11) & 0x3FF
    imm11 = imm & 0x7FF
    j1 = (s ^ i1 ^ 1) & 1
    j2 = (s ^ i2 ^ 1) & 1
    hw1 = 0xF000 | (s << 10) | imm10
    hw2 = 0x9000 | (j1 << 13) | (1 << 12) | (j2 << 11) | imm11
    return struct.pack("<HH", hw1, hw2)


def patch_orgtext_counter_hook_thumb(
    data: bytearray,
    nm: str,
    section_map: dict[str, tuple[int, int, int]],
    original: str,
    funcs: list[str],
    counter_indices: dict[str, list[int]],
    scratch: int,
) -> int:
    """Thumb org.text entry hooks that bump BOLT counter slots once per call.

    Returns the next free scratch address, so a mixed ARM+Thumb batch can
    hand off to patch_orgtext_counter_hook_arm32 without colliding stubs.
    """
    counter_base = section_map[".bolt.instr.counters"][0]
    scratch &= ~1

    for func in funcs:
        entry = symbol_addr(nm, original, func)
        if entry is None:
            print(f"warning: skipping hook for missing symbol {func}", file=sys.stderr)
            continue
        entry &= ~1
        if func not in counter_indices:
            print(
                f"warning: no BOLT counter indices for {func}, skipping hook",
                file=sys.stderr,
            )
            continue
        indices = counter_indices[func]
        hook_off = vaddr_to_offset(section_map, entry)
        orig_bytes = bytes(data[hook_off : hook_off + 4])
        resume = entry + 4
        stub = scratch & ~1

        body = bytearray()
        body += struct.pack("<H", 0xB403)  # push {r0, r1}
        for counter_index in indices:
            counter_addr = counter_base + counter_index * 8
            body += encode_thumb_movw(0, counter_addr & 0xFFFF)
            body += encode_thumb_movt(0, (counter_addr >> 16) & 0xFFFF)
            body += struct.pack("<H", 0x6801)  # ldr r1, [r0]
            body += struct.pack("<H", 0x3101)  # adds r1, #1
            body += struct.pack("<H", 0x6001)  # str r1, [r0]
        body += struct.pack("<H", 0xBC03)  # pop {r0, r1}
        body += orig_bytes
        body += encode_thumb_bw(stub + len(body), resume)

        stub_off = vaddr_to_offset(section_map, stub)
        data[stub_off : stub_off + len(body)] = body
        data[hook_off : hook_off + 4] = encode_thumb_bw(entry, stub)
        scratch = (stub + len(body) + 15) & ~15
        addrs = ", ".join(f"{idx}->0x{counter_base + idx * 8:x}" for idx in indices)
        print(
            f"org.text thumb hook {func}: entry 0x{entry:x} -> stub 0x{stub:x}, "
            f"counters [{addrs}]"
        )
    return scratch


def encode_arm_movw(rd: int, imm16: int) -> int:
    imm4 = (imm16 >> 12) & 0xF
    imm12 = imm16 & 0xFFF
    return 0xE3000000 | (imm4 << 16) | (rd << 12) | imm12


def encode_arm_movt(rd: int, imm16: int) -> int:
    imm4 = (imm16 >> 12) & 0xF
    imm12 = imm16 & 0xFFF
    return 0xE3400000 | (imm4 << 16) | (rd << 12) | imm12


def encode_arm_b(pc: int, target: int) -> bytes:
    """Unconditional ARM B. ARM state reads PC as the branch's own address
    + 8 (classic 3-stage-pipeline convention); ARM instructions are always
    4-byte aligned so the low 2 bits of the offset are always zero.
    Verified against llvm-mc ground truth: `b target` at pc=0 -> 0x1000
    encodes as 0xea0003fe, matching offset=(0x1000-8)>>2=0x3fe exactly.
    """
    offset = target - (pc + 8)
    if offset % 4:
        raise SystemExit(f"arm b to unaligned offset from 0x{pc:x} -> 0x{target:x}")
    imm = offset >> 2
    if imm < -(1 << 23) or imm >= (1 << 23):
        raise SystemExit(f"arm b from 0x{pc:x} to 0x{target:x} out of range")
    return struct.pack("<I", 0xEA000000 | (imm & 0xFFFFFF))


def patch_orgtext_counter_hook_arm32(
    data: bytearray,
    nm: str,
    section_map: dict[str, tuple[int, int, int]],
    original: str,
    funcs: list[str],
    counter_indices: dict[str, list[int]],
    scratch: int,
) -> int:
    """ARM-mode (non-Thumb) org.text entry hooks, for AArch32 functions
    compiled without -mthumb (e.g. BOLT_BENCH_ISA=arm test builds). Same
    push/counter-bump/pop/orig/branch-back structure as the Thumb version,
    but every instruction is 4 bytes and ARM-encoded throughout -- entering
    a Thumb-encoded stub in ARM state (or vice versa) misdecodes every byte
    that follows, which is exactly the bug this function exists to avoid.

    ldr/add/str encodings below (0xe5901000 / 0xe2811001 / 0xe5801000) were
    independently confirmed correct via a real instrumented-ARM boot
    earlier in this investigation (see docs/KNOWN_LIMITATIONS.md, the
    register-spill operand-order fix); push/pop/movw/movt/b were verified
    here against llvm-mc -show-encoding ground truth.
    """
    counter_base = section_map[".bolt.instr.counters"][0]
    scratch &= ~3

    for func in funcs:
        entry = symbol_addr(nm, original, func)
        if entry is None:
            print(f"warning: skipping hook for missing symbol {func}", file=sys.stderr)
            continue
        entry &= ~3
        if func not in counter_indices:
            print(
                f"warning: no BOLT counter indices for {func}, skipping hook",
                file=sys.stderr,
            )
            continue
        indices = counter_indices[func]
        hook_off = vaddr_to_offset(section_map, entry)
        orig_bytes = bytes(data[hook_off : hook_off + 4])
        resume = entry + 4
        stub = scratch & ~3

        insns: list[int] = [0xE92D0003]  # push {r0, r1}
        for counter_index in indices:
            counter_addr = counter_base + counter_index * 8
            insns.append(encode_arm_movw(0, counter_addr & 0xFFFF))
            insns.append(encode_arm_movt(0, (counter_addr >> 16) & 0xFFFF))
            insns.append(0xE5901000)  # ldr r1, [r0]
            insns.append(0xE2811001)  # add r1, r1, #1
            insns.append(0xE5801000)  # str r1, [r0]
        insns.append(0xE8BD0003)  # pop {r0, r1}

        body = struct.pack("<" + "I" * len(insns), *insns)
        body += orig_bytes
        body += encode_arm_b(stub + len(body), resume)

        stub_off = vaddr_to_offset(section_map, stub)
        data[stub_off : stub_off + len(body)] = body
        data[hook_off : hook_off + 4] = encode_arm_b(entry, stub)
        scratch = (stub + len(body) + 15) & ~15
        addrs = ", ".join(f"{idx}->0x{counter_base + idx * 8:x}" for idx in indices)
        print(
            f"org.text arm hook {func}: entry 0x{entry:x} -> stub 0x{stub:x}, "
            f"counters [{addrs}]"
        )
    return scratch


def patch_orgtext_counter_hook_aarch64(
    data: bytearray,
    nm: str,
    section_map: dict[str, tuple[int, int, int]],
    original: str,
    funcs: list[str],
    counter_indices: dict[str, list[int]],
) -> None:
    """Bump bolt_bench BOLT counter slots from org.text (AArch64).

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


def patch_orgtext_counter_hook(
    data: bytearray,
    nm: str,
    section_map: dict[str, tuple[int, int, int]],
    original: str,
    funcs: list[str],
    counter_indices: dict[str, list[int]],
) -> None:
    if data[4] != 1:
        # EI_CLASS == 2 (ELFCLASS64): genuinely AArch64, no ARM/Thumb split.
        patch_orgtext_counter_hook_aarch64(
            data, nm, section_map, original, funcs, counter_indices
        )
        return

    # EI_CLASS == 1 covers every 32-bit ARM ELF, but that says nothing about
    # whether any given function within it is ARM-mode or Thumb-mode code --
    # AArch32 mixes both freely, and this project's own bolt_bench harness
    # builds ARM-mode test binaries (BOLT_BENCH_ISA=arm) as well as the
    # default Thumb ones. Route each function to the encoder matching its
    # own ISA mode (detected via its $t mapping symbol, the same mechanism
    # BOLT itself uses), instead of assuming one mode for the whole ELF.
    thumb_funcs = [f for f in funcs if is_thumb_symbol(nm, original, f)]
    arm_funcs = [f for f in funcs if f not in thumb_funcs]

    if ".text" in section_map:
        scratch = section_map[".text"][0] & ~1
    else:
        org_addr, _, org_size = section_map[".bolt.org.text"]
        scratch = (org_addr + org_size - 0x200) & ~1

    # Prefer unused hot .text (org.text is what actually runs). Falling back
    # to the org.text tail risks overwriting live helpers like
    # print_fault_msg -- shared across both encoders via the threaded
    # scratch cursor so a mixed ARM+Thumb batch never collides stubs.
    if thumb_funcs:
        scratch = patch_orgtext_counter_hook_thumb(
            data, nm, section_map, original, thumb_funcs, counter_indices, scratch
        )
    if arm_funcs:
        patch_orgtext_counter_hook_arm32(
            data, nm, section_map, original, arm_funcs, counter_indices, scratch
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
