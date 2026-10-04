#!/usr/bin/env python3
"""Check BOLT's raw re-patching of non-emitted code (found R1, see HANDOFF.md).

llvm-bolt keeps the input code in `.bolt.org.text` and re-patches direct
branches from functions it does not emit to the moved functions. The
full-image pipeline later restores that section, so these patches are only
visible in llvm-bolt's raw output. Decode every patched instruction with the
input's ARM/Thumb mapping and flag any change of ISA, condition or opcode
class (B vs BL vs BLX, B<c>.W).

Run in WSL:
  python3 scripts/check_raw_original_text.py --input lk.elf --raw raw.elf \
      --toolchain /home/user/bolt-aarch32/build-atfe/bin
where raw.elf is plain `llvm-bolt lk.elf -o raw.elf ...` output.
Exit status 1 if any patched instruction changed shape.
"""
import argparse
import collections
import re
import struct
import subprocess
import sys
from pathlib import Path


def section_bytes(tc, elf, name, tmp):
    subprocess.run([str(tc / 'llvm-objcopy'), '-O', 'binary',
                    '--only-section=' + name, str(elf), str(tmp)], check=True)
    return tmp.read_bytes()


def section_addr(tc, elf, name):
    out = subprocess.run([str(tc / 'llvm-readelf'), '-SW', str(elf)],
                         capture_output=True, text=True, check=True).stdout
    m = re.search(re.escape(name) + r'\s+PROGBITS\s+([0-9a-f]+)', out)
    if not m:
        sys.exit(f'error: no {name} in {elf}')
    return int(m.group(1), 16)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument('--input', type=Path, required=True)
    ap.add_argument('--raw', type=Path, required=True)
    ap.add_argument('--toolchain', type=Path, required=True)
    a = ap.parse_args()
    tc, work = a.toolchain, a.raw.parent
    base = section_addr(tc, a.input, '.text')
    if section_addr(tc, a.raw, '.bolt.org.text') != base:
        sys.exit('error: .bolt.org.text is not at the input .text address')
    inp = section_bytes(tc, a.input, '.text', work / '.in-text.bin')
    out = section_bytes(tc, a.raw, '.bolt.org.text', work / '.org-text.bin')
    if len(inp) != len(out):
        sys.exit('error: section sizes differ')

    dis = subprocess.run([str(tc / 'llvm-objdump'), '-d', '-j', '.text', str(a.input)],
                         capture_output=True, text=True, check=True).stdout
    ins, fn = {}, None
    for line in dis.splitlines():
        m = re.match(r'^([0-9a-f]+) <(.*)>:', line)
        if m:
            fn = m.group(2)
            continue
        m = re.match(r'^\s*([0-9a-f]+):\s+((?:[0-9a-f]{2,8} ?)+)\s+(\S+)\s*(.*)', line)
        if m:
            raw = m.group(2).split()
            ins[int(m.group(1), 16)] = (sum(len(x) // 2 for x in raw), m.group(3),
                                        m.group(4), fn, len(raw[0]) == 4)
    starts = {}
    for off in (i for i in range(len(out)) if out[i] != inp[i]):
        for k in range(4):
            addr = base + off - k
            if addr in ins and addr + ins[addr][0] > base + off:
                starts[addr] = ins[addr]
                break
    kinds, bad = collections.Counter(), []
    for addr, (size, mn, ops, func, thumb) in sorted(starts.items()):
        o, n = inp[addr - base:addr - base + size], out[addr - base:addr - base + size]
        if not thumb:
            ow, nw = struct.unpack('<I', o)[0], struct.unpack('<I', n)[0]
            # BLX (immediate) keeps its H bit in bit 24: compare 0xfa/0xfb as one class.
            blx = lambda w: (w & 0xfe000000) == 0xfa000000
            ok = (blx(ow) and blx(nw)) or (not blx(ow) and (ow >> 24) == (nw >> 24))
        elif size == 2:
            ok = False  # narrow branches are never re-patched safely
        else:
            oh, ol = struct.unpack('<HH', o)
            nh, nl = struct.unpack('<HH', n)
            okind, nkind = (ol >> 12) & 5, (nl >> 12) & 5  # BL=5 B.W=1 Bcc.W=0 BLX=4
            ok = okind == nkind and (okind != 0 or ((oh >> 6) & 15) == ((nh >> 6) & 15))
        kinds[(mn, ok)] += 1
        if not ok:
            bad.append((hex(addr), func, mn, ops))
    for (mn, ok), count in kinds.most_common():
        print(f'{count:5} {mn:10} {"kept" if ok else "CHANGED"}')
    print(f'{len(starts)} patched instructions; {len(bad)} changed shape')
    for row in bad[:25]:
        print('  ', row)
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
