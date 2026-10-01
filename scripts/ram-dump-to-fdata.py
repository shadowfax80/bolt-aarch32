#!/usr/bin/env python3
"""Convert a QMP counter dump from instrumented LK into BOLT .fdata text.

Mirrors bolt/runtime/instr.cpp: readDescriptions(), Graph, and
writeFunctionProfile(). Tables come from the .bolt.instr.tables ELF note;
counter values from the guest RAM dump produced by dump-bolt-counters.py.
"""

from __future__ import annotations

import argparse
from collections import deque
import io
import os
import re
import struct
import subprocess
import sys
import tempfile
from dataclasses import dataclass

SECTION_RE = re.compile(
    r"\[\s*\d+\]\s+(?P<name>\S+)\s+\S+\s+(?P<addr>[0-9a-fA-F]+)\s+"
    r"(?P<off>[0-9a-fA-F]+)\s+(?P<size>[0-9a-fA-F]+)"
)
GETTER_RE_AARCH64 = re.compile(
    r"adrp\s+x0,\s+0x([0-9a-fA-F]+).*\n\s*[0-9a-fA-F]+:\s+add\s+x0,\s+x0,\s+#0x([0-9a-fA-F]+)",
    re.MULTILINE,
)
GETTER_RE_ARM = re.compile(
    r"movw\s+r0,\s+#(?:0x)?([0-9a-fA-F]+).*\n"
    r"\s*[0-9a-fA-F]+:\s+movt\s+r0,\s+#(?:0x)?([0-9a-fA-F]+)",
    re.MULTILINE | re.IGNORECASE,
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
            f"--stop-address={hex(start + 24)}",
            elf,
        ],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    m = GETTER_RE_AARCH64.search(out)
    if m:
        return int(m.group(1), 16) + int(m.group(2), 16)
    m = GETTER_RE_ARM.search(out)
    if m:
        return (int(m.group(2), 16) << 16) | int(m.group(1), 16)
    raise SystemExit(f"could not decode {name} from:\n{out}")


def parse_tables_note(elf_data: bytes, file_off: int, size: int) -> ProfileWriterContext:
    if file_off < 0 or size < 12 or file_off + size > len(elf_data):
        raise ValueError("instrumentation note is outside the ELF or truncated")
    blob = elf_data[file_off : file_off + size]
    namesz = struct.unpack_from("<I", blob, 0)[0]
    descsz = struct.unpack_from("<I", blob, 4)[0]
    name_end = 12 + ((namesz + 3) // 4) * 4
    if name_end + descsz > len(blob):
        raise ValueError("instrumentation note descriptor is truncated")
    desc = blob[name_end : name_end + descsz]

    ind_call_desc_size = struct.unpack_from("<I", desc, 0)[0]
    ind_call_target_size = struct.unpack_from("<I", desc, 4 + ind_call_desc_size)[0]
    func_desc_size = struct.unpack_from(
        "<I", desc, 8 + ind_call_desc_size + ind_call_target_size
    )[0]
    func_start = 12 + ind_call_desc_size + ind_call_target_size
    if func_start + func_desc_size > len(desc):
        raise ValueError("instrumentation function descriptions are truncated")
    func_descriptions = desc[func_start : func_start + func_desc_size]
    strings = desc[func_start + func_desc_size :]
    return ProfileWriterContext(func_descriptions, strings)


def serialize_loc(strings: bytes, loc: Location) -> str:
    if not 0 <= loc.function_name < len(strings) or (loc.function_name and strings[loc.function_name - 1] != 0):
        raise ValueError('function name offset is not a string-table boundary')
    end = strings.index(b"\0", loc.function_name)
    name = strings[loc.function_name : end].decode()
    if not name or any(c.isspace() for c in name):
        raise ValueError('invalid function name in profile metadata')
    return f"1 {name} {loc.offset:x} "


def validate_function(ctx, func, counters):
    if (func.num_leaf_nodes, func.num_edges, func.num_calls, func.num_entry_nodes) != (
            len(func.leaf_nodes), len(func.edges), len(func.calls), len(func.entry_nodes)):
        raise ValueError('descriptor counts do not match records')
    if len({n.node for n in func.leaf_nodes}) != len(func.leaf_nodes):
        raise ValueError('duplicate leaf node')
    if len({n.node for n in func.entry_nodes}) != len(func.entry_nodes):
        raise ValueError('duplicate entry node')
    if len({(e.from_node, e.to_node) for e in func.edges}) != len(func.edges):
        raise ValueError('duplicate CFG edge')
    for counter in ([n.counter for n in func.leaf_nodes] + [e.counter for e in func.edges] + [c.counter for c in func.calls]):
        if counter != INFERRED and not 0 <= counter < len(counters):
            raise ValueError(f'descriptor refers to missing counter {counter}')
    if any(n.counter == INFERRED for n in func.leaf_nodes):
        raise ValueError('leaf frequency must have a measured counter')
    for loc in ([e.from_loc for e in func.edges] + [e.to_loc for e in func.edges] +
                [c.from_loc for c in func.calls] + [c.to_loc for c in func.calls]):
        serialize_loc(ctx.strings, loc)
    if any(e.from_loc.function_name != e.to_loc.function_name for e in func.edges):
        raise ValueError('cross-function CFG edge is not supported by this profile format')
    owners = {serialize_loc(ctx.strings, e.from_loc).split()[1] for e in func.edges}
    owners |= {serialize_loc(ctx.strings, c.from_loc).split()[1] for c in func.calls}
    if len(owners) > 1:
        raise ValueError('one descriptor has multiple source functions')
    if func.leaf_nodes and not owners:
        raise ValueError('leaf-only metadata has no verifiable function identity')
    # Validate the graph even if every measured counter is zero.
    Graph(func, counters, {})


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
        node_ids = sorted({n.node for n in d.leaf_nodes} | {n.node for n in d.entry_nodes} |
                          {e.from_node for e in d.edges} | {e.to_node for e in d.edges} |
                          {c.from_node for c in d.calls})
        if not node_ids:
            return
        # IDs are metadata, not allocation sizes. A sparse/malformed ID cannot
        # force allocation of billions of list elements.
        indices = {node: index for index, node in enumerate(node_ids)}
        num_nodes = len(node_ids)

        cfg_in = [0] * num_nodes
        cfg_out = [0] * num_nodes
        st_in = [0] * num_nodes
        st_out = [0] * num_nodes
        for e in d.edges:
            source, target = indices[e.from_node], indices[e.to_node]
            cfg_out[source] += 1
            cfg_in[target] += 1
            if e.counter == INFERRED:
                st_out[source] += 1
                st_in[target] += 1
        if any(parents > 1 for parents in st_in):
            raise ValueError('inferred edges do not form a forest: multiple parents')

        cfg_out_edges: list[list[tuple[int, int]]] = [[] for _ in range(num_nodes)]
        cfg_in_edges: list[list[tuple[int, int]]] = [[] for _ in range(num_nodes)]
        st_out_edges: list[list[tuple[int, int]]] = [[] for _ in range(num_nodes)]
        st_in_edges: list[list[tuple[int, int]]] = [[] for _ in range(num_nodes)]
        for i, e in enumerate(d.edges):
            source, target = indices[e.from_node], indices[e.to_node]
            cfg_out_edges[source].append((target, i))
            cfg_in_edges[target].append((source, i))
            if e.counter == INFERRED:
                st_out_edges[source].append((target, i))
                st_in_edges[target].append((source, i))

        calls_by_node: list[list[int]] = [[] for _ in range(num_nodes)]
        for i, c in enumerate(d.calls):
            calls_by_node[indices[c.from_node]].append(i)

        leaf_freq = [0] * num_nodes
        measured_leaves = set()
        for n in d.leaf_nodes:
            leaf_freq[indices[n.node]] = self.counters[n.counter]
            measured_leaves.add(indices[n.node])
        entry_addr = [0] * num_nodes
        for n in d.entry_nodes:
            entry_addr[indices[n.node]] = n.address

        for i, e in enumerate(d.edges):
            if e.counter != INFERRED:
                self.edge_freqs[i] = self.counters[e.counter]

        pending = list(st_in)
        ready = deque(i for i in range(num_nodes) if pending[i] == 0)
        order = []
        while ready:
            node = ready.popleft()
            order.append(node)
            for successor, _ in st_out_edges[node]:
                pending[successor] -= 1
                if pending[successor] == 0:
                    ready.append(successor)
        if len(order) != num_nodes:
            raise ValueError('inferred edges contain a cycle')
        for cur in reversed(order):
            if st_in[cur] and not cfg_out_edges[cur] and cur not in measured_leaves:
                raise ValueError('inferred flow has an unmeasured exit; use conservative instrumentation')
            outgoing = sum(self.edge_freqs[edge_id] for _, edge_id in cfg_out_edges[cur])
            cur_node_freq = leaf_freq[cur] if cur in measured_leaves else outgoing
            if cur in measured_leaves and cfg_out_edges[cur] and outgoing != cur_node_freq:
                raise ValueError('measured leaf and outgoing edge counts disagree')

            call_freq = 0
            for call_id in calls_by_node[cur]:
                c = d.calls[call_id]
                if c.counter == INFERRED:
                    if cur not in measured_leaves and not cfg_out_edges[cur]:
                        raise ValueError('inferred call frequency has no measured node flow')
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
                if cur in measured_leaves:
                    raise ValueError('call frequency exceeds measured node frequency')
                cur_node_freq = call_freq
            if cur_node_freq > 0 and entry_addr[cur]:
                self.call_flow[entry_addr[cur]] = cur_node_freq

            if st_in[cur] == 0:
                continue
            parent_edge = st_in_edges[cur][0][1]
            parent_edge_freq = cur_node_freq
            for _, edge_id in cfg_in_edges[cur]:
                parent_edge_freq -= self.edge_freqs[edge_id]
            if parent_edge_freq < 0:
                raise ValueError('inconsistent counters would produce a negative inferred edge')
            self.edge_freqs[parent_edge] = parent_edge_freq

    def has_profile(self) -> bool:
        return any(self.edge_freqs) or any(self.call_freqs)


def write_function_profile(
    out,
    ctx: ProfileWriterContext,
    func: FunctionDescription,
    counters: list[int],
    call_flow: dict[int, int],
    leaf_name: str | None = None,
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
        if leaf_name:
            name = leaf_name
        elif ctx.strings:
            name_end = ctx.strings.index(b"\0", 0)
            name = ctx.strings[:name_end].decode()
        else:
            name = "unknown"
        for n in func.leaf_nodes:
            freq = counters[n.counter]
            if freq == 0:
                continue
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
    if count_off < 0 or count_off + 4 > len(blob):
        raise ValueError("counter-count address is outside the dump or truncated")
    count = int.from_bytes(blob[count_off : count_off + 4], "little")
    if loc_off < 0 or loc_off > len(blob) or count > (len(blob) - loc_off) // 8:
        raise ValueError(f"counter dump is truncated or misplaced: {count} counters at offset {loc_off}, {len(blob)} bytes available")
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
    ap.add_argument(
        "--funcs",
        default="",
        help="comma-separated instrumented function names in BOLT order "
        "(labels leaf-only descriptors that omit a name string)",
    )
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

    funcs = [f.strip() for f in args.funcs.split(",") if f.strip()]
    leaf_names = list(funcs)

    call_flow: dict[int, int] = {}
    off = 0
    func_blob = ctx.func_descriptions
    out = io.StringIO()
    seen_counters = set()
    while off < len(func_blob):
        func, next_off = FunctionDescription.parse(func_blob, off)
        if next_off <= off or next_off > len(func_blob):
            raise ValueError("invalid function descriptor length")
        validate_function(ctx, func, counters)
        references = [n.counter for n in func.leaf_nodes] + [e.counter for e in func.edges] + [c.counter for c in func.calls]
        references = [counter for counter in references if counter != INFERRED]
        if len(references) != len(set(references)) or seen_counters.intersection(references):
            raise ValueError('metadata assigns one counter to multiple records')
        seen_counters.update(references)
        leaf_name = None
        if func.num_edges == 0 and func.num_calls == 0 and leaf_names:
            leaf_name = leaf_names.pop(0)
        write_function_profile(out, ctx, func, counters, call_flow, leaf_name=leaf_name)
        off = next_off
    if seen_counters != set(range(len(counters))):
        raise ValueError('declared counters do not match descriptor counter coverage')
    if args.output == "-":
        sys.stdout.write(out.getvalue())
    else:
        destination = os.path.abspath(args.output)
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=os.path.dirname(destination), delete=False) as stream:
                temporary = stream.name
                stream.write(out.getvalue())
            os.replace(temporary, destination)
        finally:
            if temporary and os.path.exists(temporary):
                os.unlink(temporary)
        print(f"wrote {args.output}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, ValueError, IndexError, struct.error) as error:
        sys.exit(f"error: invalid profile input: {error}")
