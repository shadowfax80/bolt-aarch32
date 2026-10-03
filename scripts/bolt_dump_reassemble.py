#!/usr/bin/env python3
"""Parse `bolt_dump` output (see app/bolt_bench's bolt_dump command) back
into the raw bytes it dumped.

Kept transport-agnostic on purpose: the same parser backs both the QEMU
cross-check (scripts/qemu_bolt_dump.py) and the real-Pi dump script, since
the wire format -- BOLT_DUMP_BEGIN/BOLT_DUMP/BOLT_DUMP_END text lines -- is
identical either way. Real hardware is the one that can actually corrupt a
chunk in transit (lk-perf found a real, silent USB packet-boundary artifact
at both 3M and 6M baud); this always verifies the per-chunk checksum and
reports gaps instead of assuming the transport was clean.
"""

from __future__ import annotations

import re

BEGIN_RE = re.compile(r"BOLT_DUMP_BEGIN addr=([0-9a-fA-F]+) size=([0-9a-fA-F]+)")
LINE_RE = re.compile(
    r"BOLT_DUMP seq=([0-9a-fA-F]+) off=([0-9a-fA-F]+) len=([0-9a-fA-F]+) "
    r"crc=([0-9a-fA-F]+) data=([0-9a-fA-F]*)"
)
END_RE = re.compile(r"BOLT_DUMP_END seq=([0-9a-fA-F]+) total=([0-9a-fA-F]+)")


def checksum(buf: bytes) -> int:
    """Must match bolt_dump_checksum() in app/bolt_bench/bolt_bench.c exactly."""
    c = 0x811C9DC5
    for b in buf:
        c ^= b
        c = (c * 16777619) & 0xFFFFFFFF
    return c


class DumpResult:
    def __init__(self, addr: int, size: int):
        self.addr = addr
        self.size = size
        self.chunks: dict[int, bytes] = {}  # off -> verified bytes
        self.bad_seqs: list[int] = []
        self.total_seq: int | None = None

    def missing_ranges(self) -> list[tuple[int, int]]:
        """(offset, length) ranges not yet covered by a verified chunk."""
        covered = sorted(self.chunks.items())
        ranges = []
        pos = 0
        for off, data in covered:
            if off > pos:
                ranges.append((pos, off - pos))
            pos = max(pos, off + len(data))
        if pos < self.size:
            ranges.append((pos, self.size - pos))
        return ranges

    def is_complete(self) -> bool:
        return not self.missing_ranges()

    def to_bytes(self) -> bytes:
        if not self.is_complete():
            raise ValueError(f"dump incomplete: missing {self.missing_ranges()}")
        buf = bytearray(self.size)
        for off, data in self.chunks.items():
            buf[off : off + len(data)] = data
        return bytes(buf)


def parse_dump_stream(text: str, result: DumpResult | None = None) -> DumpResult:
    """Parse one bolt_dump invocation's output (BEGIN..END) into a DumpResult.

    Pass an existing DumpResult back in on a retry (re-requesting just the
    missing/bad ranges) to accumulate chunks across multiple invocations.
    """
    m = BEGIN_RE.search(text)
    if result is None:
        if not m:
            raise ValueError("no BOLT_DUMP_BEGIN in stream")
        result = DumpResult(int(m.group(1), 16), int(m.group(2), 16))
    elif m:
        addr, size = int(m.group(1), 16), int(m.group(2), 16)
        if addr != result.addr:
            raise ValueError(
                f"BEGIN addr mismatch on retry: {addr:#x} != {result.addr:#x}"
            )

    for lm in LINE_RE.finditer(text):
        seq = int(lm.group(1), 16)
        off = int(lm.group(2), 16)
        length = int(lm.group(3), 16)
        crc = int(lm.group(4), 16)
        hexdata = lm.group(5)
        if len(hexdata) != length * 2:
            result.bad_seqs.append(seq)
            continue
        try:
            data = bytes.fromhex(hexdata)
        except ValueError:
            result.bad_seqs.append(seq)
            continue
        if checksum(data) != crc:
            result.bad_seqs.append(seq)
            continue
        result.chunks[off] = data

    em = END_RE.search(text)
    if em:
        result.total_seq = int(em.group(1), 16)

    return result


def validate_single_dump(text: str, address: int, size: int) -> bytes:
    """Validate one exact dump; retry/merge parsing alone is not a proof gate."""
    if address < 0 or size <= 0 or address + size > 1 << 32:
        raise ValueError('invalid expected dump extent')
    begins, ends, lines = list(BEGIN_RE.finditer(text)), list(END_RE.finditer(text)), list(LINE_RE.finditer(text))
    chunks = (size + 63) // 64
    if len(begins) != 1 or len(ends) != 1 or len(lines) != chunks:
        raise ValueError('expected one dump with exactly the required chunks')
    begin, end = begins[0], ends[0]
    if ((int(begin[1], 16), int(begin[2], 16)) != (address, size)
            or (int(end[1], 16), int(end[2], 16)) != (chunks, size)
            or begin.end() > end.start()):
        raise ValueError('dump marker extent/order/total mismatch')
    for line in text.splitlines():
        if 'BOLT_DUMP' in line and not any(pattern.fullmatch(line.strip()) for pattern in (BEGIN_RE, LINE_RE, END_RE)):
            raise ValueError('malformed dump record')
    for sequence, line in enumerate(lines):
        seq, off, length = [int(line[i], 16) for i in (1, 2, 3)]
        if (line.start() < begin.end() or line.end() > end.start()
                or (seq, off, length) != (sequence, sequence * 64, min(64, size - sequence * 64))):
            raise ValueError('dump chunk sequence/order/extent mismatch')
    result = parse_dump_stream(text)
    if result.bad_seqs or not result.is_complete():
        raise ValueError('dump checksum or completeness failure')
    return result.to_bytes()
