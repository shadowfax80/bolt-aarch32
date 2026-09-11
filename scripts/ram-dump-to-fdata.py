#!/usr/bin/env python3
"""Convert a QMP counter dump from instrumented LK into BOLT .fdata text.

Mirrors bolt/runtime/instr.cpp: readDescriptions(), Graph, and
writeFunctionProfile(). Tables come from the .bolt.instr.tables ELF note;
counter values from the guest RAM dump produced by dump-bolt-counters.py.
"""

from __future__ import annotations

import argparse
import re
import struct
import subprocess
import sys
from dataclasses import dataclass

SECTION_RE = re.compile(
    r"\[\s*\d+\]\s+(?P<name>\S+)\s+\S+\s+(?P<addr>[0-9a-fA-F]+)\s+"
    r"(?P<off>[0-9a-fA-F]+)\s+(?P<size>[0-9a-fA-F]+)"
)
GETTER_RE = re.compile(
    r"adrp\s+x0,\s+0x([0-9a-fA-F]+).*\n\s*[0-9a-fA-F]+:\s+add\s+x0,\s+x0,\s+#0x([0-9a-fA-F]+)",
    re.MULTILINE,
)
INFERRED = 0xFFFFFFFF


@dataclass
class Location:
    function_name: int
    offset: int


@dataclass
class EdgeDescription:
    from_loc: Location
    from_node: int
    to_loc: Location
    to_node: int
    counter: int


@dataclass
class CallDescription:
    from_loc: Location
    from_node: int
    to_loc: Location
    counter: int
    target_address: int


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
    num_edges: int
    edges: list[EdgeDescription]
    num_calls: int
    calls: list[CallDescription]
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
        edges = []
        for i in range(num_edges):
            o = edge_base + i * 28
            fn, fo, from_node, tn, to, to_node, counter = struct.unpack_from(
                "<IIIIIII", blob, o
            )
            edges.append(
                EdgeDescription(
                    Location(fn, fo), from_node, Location(tn, to), to_node, counter
                )
            )
        call_base = edge_base + num_edges * 28
        num_calls = struct.unpack_from("<I", blob, call_base)[0]
        calls = []
        for i in range(num_calls):
            o = call_base + 4 + i * 32
            fn, fo, from_node, tn, to, counter, target = struct.unpack_from(
                "<IIIIIIQ", blob, o
            )
            calls.append(
                CallDescription(
                    Location(fn, fo), from_node, Location(tn, to), counter, target
                )
            )
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
                num_edges,
                edges,
                num_calls,
                calls,
                num_entry,
                entry_nodes,
            ),
            end,
        )

    @property
    def size(self) -> int:
        return (
            16
            + self.num_leaf_nodes * 8
            + self.num_edges * 28
            + self.num_calls * 32
            + self.num_entry_nodes * 16
        )


@dataclass
class ProfileWriterContext:
    func_descriptions: bytes
    strings: bytes


def section_info(readelf: str, elf: str, name: str) -> tuple[int, int, int]:
    out = subprocess.run(
        [readelf, "--sections", elf], check=True, capture_output=True, text=True
    ).stdout
    for line in out.splitlines():
        m = SECTION_RE.search(line)
        if m and m.group("name") == name:
            return (
                int(m.group("addr"), 16),
                int(m.group("off"), 16),
                int(m.group("size"), 16),
            )
    raise SystemExit(f"{elf} has no {name} section")


def getter_address(toolchain: str, elf: str, name: str) -> int:
    nm = subprocess.run(
        [f"{toolchain}/llvm-nm", elf],
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
            f"{toolchain}/llvm-objdump",
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


def parse_tables_note(elf_data: bytes, file_off: int, size: int) -> ProfileWriterContext:
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
    return ProfileWriterContext(func_descriptions, strings)


def serialize_loc(strings: bytes, loc: Location) -> str:
    end = strings.index(b"\0", loc.function_name)
    name = strings[loc.function_name : end].decode()
    return f"1 {name} {loc.offset:x} "


class Graph:
    def __init__(
        self,
        func: FunctionDescription,
        counters: list[int],
        call_flow: dict[int, int],
    ) -> None:
        self.func = func
        self.counters = counters
        self.call_flow = call_flow
        self.edge_freqs = [0] * func.num_edges
        self.call_freqs = [0] * func.num_calls
        self._build()

    def _build(self) -> None:
        d = self.func
        max_nodes = -1
        for e in d.edges:
            max_nodes = max(max_nodes, e.from_node, e.to_node)
        for n in d.leaf_nodes:
            max_nodes = max(max_nodes, n.node)
        for c in d.calls:
            max_nodes = max(max_nodes, c.from_node)
        if max_nodes < 0:
            return
        num_nodes = max_nodes + 1

        cfg_in = [0] * num_nodes
        cfg_out = [0] * num_nodes
        st_in = [0] * num_nodes
        st_out = [0] * num_nodes
        for e in d.edges:
            cfg_out[e.from_node] += 1
            cfg_in[e.to_node] += 1
            if e.counter == INFERRED:
                st_out[e.from_node] += 1
                st_in[e.to_node] += 1

        cfg_out_edges: list[list[tuple[int, int]]] = [[] for _ in range(num_nodes)]
        cfg_in_edges: list[list[tuple[int, int]]] = [[] for _ in range(num_nodes)]
        st_out_edges: list[list[tuple[int, int]]] = [[] for _ in range(num_nodes)]
        st_in_edges: list[list[tuple[int, int]]] = [[] for _ in range(num_nodes)]
        for i, e in enumerate(d.edges):
            cfg_out_edges[e.from_node].append((e.to_node, i))
            cfg_in_edges[e.to_node].append((e.from_node, i))
            if e.counter == INFERRED:
                st_out_edges[e.from_node].append((e.to_node, i))
                st_in_edges[e.to_node].append((e.from_node, i))

        calls_by_node: list[list[int]] = [[] for _ in range(num_nodes)]
        for i, c in enumerate(d.calls):
            calls_by_node[c.from_node].append(i)

        leaf_freq = [0] * num_nodes
        for n in d.leaf_nodes:
            leaf_freq[n.node] = self.counters[n.counter]
        entry_addr = [0] * num_nodes
        for n in d.entry_nodes:
            entry_addr[n.node] = n.address

        for i, e in enumerate(d.edges):
            if e.counter != INFERRED:
                self.edge_freqs[i] = self.counters[e.counter]

        visited = [0] * num_nodes  # 0=new, 1=visiting, 2=visited
        stack: list[int] = []
        for i in range(num_nodes):
            if st_in[i] == 0:
                stack.append(i)

        while stack:
            cur = stack.pop()
            if visited[cur] == 0:
                visited[cur] = 1
                stack.append(cur)
                for succ, _ in st_out_edges[cur]:
                    stack.append(succ)
                continue
            if visited[cur] == 2:
                continue
            visited[cur] = 2

            cur_node_freq = leaf_freq[cur]
            if not cur_node_freq:
                for _, edge_id in cfg_out_edges[cur]:
                    cur_node_freq += self.edge_freqs[edge_id]
            if cur_node_freq < 0:
                cur_node_freq = 0

            call_freq = 0
            for call_id in calls_by_node[cur]:
                c = d.calls[call_id]
                if c.counter == INFERRED:
                    self.call_freqs[call_id] = cur_node_freq
                else:
                    val = self.counters[c.counter]
                    self.call_freqs[call_id] = val
                    call_freq = max(call_freq, val)
                if self.call_freqs[call_id] > 0:
                    self.call_flow[c.target_address] = (
                        self.call_flow.get(c.target_address, 0)
                        + self.call_freqs[call_id]
                    )
            if call_freq > cur_node_freq:
                cur_node_freq = call_freq
            if cur_node_freq > 0 and entry_addr[cur]:
                self.call_flow[entry_addr[cur]] = cur_node_freq

            if st_in[cur] == 0:
                continue
            assert st_in[cur] == 1
            parent_edge = st_in_edges[cur][0][1]
            parent_edge_freq = cur_node_freq
            for _, edge_id in cfg_in_edges[cur]:
                parent_edge_freq -= self.edge_freqs[edge_id]
            if parent_edge_freq < 0:
                parent_edge_freq = 0
            self.edge_freqs[parent_edge] = parent_edge_freq

    def has_profile(self) -> bool:
        return any(self.edge_freqs) or any(self.call_freqs)


def write_function_profile(
    out,
    ctx: ProfileWriterContext,
    func: FunctionDescription,
    counters: list[int],
    call_flow: dict[int, int],
) -> None:
    counters_freq = 0
    for n in func.leaf_nodes:
        counters_freq += counters[n.counter]
    if counters_freq == 0:
        for e in func.edges:
            if e.counter != INFERRED:
                counters_freq += counters[e.counter]
        if counters_freq == 0:
            for c in func.calls:
                if c.counter != INFERRED:
                    counters_freq += counters[c.counter]
            if counters_freq == 0:
                return

    if func.num_edges == 0 and func.num_calls == 0 and func.num_leaf_nodes:
        freq = sum(counters[n.counter] for n in func.leaf_nodes)
        if freq == 0:
            return
        for n in func.leaf_nodes:
            freq = counters[n.counter]
            if freq == 0:
                continue
            if ctx.strings:
                name_end = ctx.strings.index(b"\0", 0)
                name = ctx.strings[:name_end].decode()
            else:
                name = "lk_main"
            line = f"1 {name} 0 1 {name} 0 0 {freq}\n"
            out.write(line)
        return

    graph = Graph(func, counters, call_flow)
    if not graph.has_profile():
        return

    for i, e in enumerate(func.edges):
        freq = graph.edge_freqs[i]
        if freq == 0:
            continue
        line = (
            serialize_loc(ctx.strings, e.from_loc)
            + serialize_loc(ctx.strings, e.to_loc)
            + f"0 {freq}\n"
        )
        out.write(line)

    for i, c in enumerate(func.calls):
        freq = graph.call_freqs[i]
        if freq == 0:
            continue
        line = (
            serialize_loc(ctx.strings, c.from_loc)
            + serialize_loc(ctx.strings, c.to_loc)
            + f"0 {freq}\n"
        )
        out.write(line)


def load_counters(
    dump_path: str,
    dump_base: int,
    locations: int,
    num_counters_addr: int,
) -> list[int]:
    with open(dump_path, "rb") as fh:
        blob = fh.read()
    loc_off = locations - dump_base
    count_off = num_counters_addr - dump_base
    count = int.from_bytes(blob[count_off : count_off + 4], "little")
    return [
        int.from_bytes(blob[loc_off + i * 8 : loc_off + i * 8 + 8], "little")
        for i in range(count)
    ]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--elf", required=True, help="instrumented LK ELF")
    ap.add_argument("--dump", required=True, help="counter RAM dump from QMP")
    ap.add_argument(
        "--toolchain",
        default="build/bin",
        help="directory containing llvm-readelf/llvm-nm/llvm-objdump",
    )
    ap.add_argument("-o", "--output", default="-", help="fdata output (default stdout)")
    args = ap.parse_args()

    readelf = f"{args.toolchain}/llvm-readelf"
    _, tables_off, tables_size = section_info(readelf, args.elf, ".bolt.instr.tables")
    dump_base, _, _ = section_info(readelf, args.elf, ".bolt.instr.counters")

    with open(args.elf, "rb") as fh:
        elf_data = fh.read()
    ctx = parse_tables_note(elf_data, tables_off, tables_size)

    locations = getter_address(args.toolchain, args.elf, "__bolt_instr_locations_getter")
    num_counters_addr = getter_address(
        args.toolchain, args.elf, "__bolt_num_counters_getter"
    )
    counters = load_counters(args.dump, dump_base, locations, num_counters_addr)

    call_flow: dict[int, int] = {}
    off = 0
    func_blob = ctx.func_descriptions
    out = sys.stdout if args.output == "-" else open(args.output, "w")
    try:
        for _ in range(10000):
            if off >= len(func_blob):
                break
            func, next_off = FunctionDescription.parse(func_blob, off)
            write_function_profile(out, ctx, func, counters, call_flow)
            if next_off <= off:
                break
            off = next_off
    finally:
        if args.output != "-":
            out.close()
            print(f"wrote {args.output}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
