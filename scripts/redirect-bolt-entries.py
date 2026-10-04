#!/usr/bin/env python3
"""Make a BOLT-optimized LK image actually *run* the optimized functions.

optimize-lk-bolt.sh ends with fix-kernel-elf-sections.py, which restores the
original text (LK boots from it with the MMU off) and only knows how to
install *instrumentation* hooks. Nothing redirects execution into the
optimized copies BOLT emitted, so the image boots and passes -- while running
byte-for-byte the same code as its input (verified: 0 differing bytes in the
original text). A benchmark of BOLT's layout changes measures nothing unless
each original entry branches to its new copy.

This patches every rewritten function's original entry (in .bolt.org.text)
with a branch (Thumb-2 `b.w`, or ARM `b`) to its optimized copy. Each copy is a
complete function with its own prologue, so entering it at its start is correct;
the rest of the original body simply becomes dead. Calls *between* optimized
copies already go straight to the new copies (BOLT relocates them); only entries
reached from the original text -- callers that were not rewritten, vectors,
function pointers -- pay the one extra branch.

Two ways to find the new entries:

  --map FILE   (any number of functions) the file written by
               `llvm-bolt --emit-function-map=FILE` (overlay patch
               0013-bolt-emit-function-map): one `<name> <in> <out> <size>` line
               per emitted function. Every function in it is redirected;
               --func NAME[,NAME...] (optional) additionally demands that exactly
               those functions are present, so a typo or a function BOLT declined
               to rewrite fails loudly instead of running unoptimized.

  --func NAME  (legacy, exactly ONE function, no map) the new entry is taken from
               the start of the output `.text`, because BOLT drops the moved
               function's symbol. Kept for images built without the map.

usage: redirect-bolt-entries.py <bolt.elf> --original <input.elf>
         (--map FILE [--func A,B,...] | --func NAME) [--instrumented]
         [--toolchain build-atfe/bin]
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location(
    "fix_sections", os.path.join(HERE, "fix-kernel-elf-sections.py")
)
fix = importlib.util.module_from_spec(_spec)
sys.modules["fix_sections"] = fix  # @dataclass in that module looks itself up here
_spec.loader.exec_module(fix)  # reuse sections()/encode_thumb_bw()/encode_arm_b()


def nm_symbols(nm: str, elf: str) -> dict[str, tuple[int, int]]:
    """name -> (address, size) for every sized symbol. llvm-nm strips the Thumb bit."""
    out = subprocess.run([nm, "-a", "-S", elf], check=True, capture_output=True, text=True).stdout
    syms: dict[str, tuple[int, int]] = {}
    for line in out.splitlines():
        parts = line.split()
        if len(parts) == 4:  # addr size type name
            try:
                syms.setdefault(parts[3], (int(parts[0], 16), int(parts[1], 16)))
            except ValueError:
                pass
    return syms


def require_whole_redirect_prefix(data,off,size,thumb,allow_split=False):
    """A four-byte branch must replace complete original instructions, unless
    the caller proved nothing can reach the split instruction (R13).

    Returns True when the branch splits a 32-bit Thumb instruction that starts
    two bytes into the function (16-bit first instruction)."""
    if off<0 or size<4 or off+4>len(data):
        raise SystemExit('redirect prefix is outside the original function/file')
    if thumb:
        first=fix.thumb_insn_len(int.from_bytes(data[off:off+2],'little'))
        covered=first
        if first==2:
            covered+=fix.thumb_insn_len(int.from_bytes(data[off+2:off+4],'little'))
        if covered!=4:
            if not allow_split or size<6:
                raise SystemExit('four-byte redirect would split an original Thumb instruction')
            return True
    return False


# Every 0x-prefixed value (branch targets, ADR/literal comments, .word data) of
# any width, plus bare 8-digit words; objdump prints small addresses unpadded.
_HEX = re.compile(r'\b0x([0-9a-f]+)\b|\b([0-9a-f]{8})\b')


def original_text_references(objdump, elf):
    """[(source address, referenced address)] for every 8-hex-digit value in the
    disassembly of the original .text: branch/call targets, ADR/literal results
    in comments and data words (literal pools, tables). Over-approximates on
    purpose; MOVW/MOVT halves are not combined (see R13 notes)."""
    out = subprocess.run([objdump, '-d', '-j', '.text', elf], check=True,
                         capture_output=True, text=True).stdout
    refs = []
    for line in out.splitlines():
        m = re.match(r'\s*([0-9a-f]+):\s+(?:[0-9a-f]{2,8} ?)+\s+(.*)', line)
        if not m:
            continue
        src = int(m.group(1), 16)
        for a, b in _HEX.findall(m.group(2)):
            refs.append((src, int(a or b, 16)))
    return refs


def split_prefix_reachable(refs, entry, size):
    """References from outside [entry, entry+size) into the bytes a split
    redirect leaves behind (entry+2 .. entry+3). Code inside the function only
    runs after entering it, and every entry now goes to the rewritten copy."""
    return sorted({(s, a) for s, a in refs
                   if entry + 2 <= (a & ~1) < entry + 4 and not entry <= s < entry + size})


def function_symbol(nm: str, elf: str, name: str) -> int:
    out = subprocess.run([nm, "-a", elf], check=True, capture_output=True, text=True).stdout
    for line in out.splitlines():
        parts = line.split()
        if len(parts) == 3 and parts[2] == name:
            return int(parts[0], 16)
    raise SystemExit(f"{elf}: no symbol {name}")


def read_map(path: str) -> dict[str, tuple[int, int, int]]:
    """name -> (input address, output address, output size), Thumb bit stripped."""
    entries: dict[str, tuple[int, int, int]] = {}
    with open(path) as fh:
        for n, line in enumerate(fh, 1):
            parts = line.split()
            if not parts:
                continue
            if len(parts) != 4:
                raise SystemExit(f"{path}:{n}: expected '<name> <in> <out> <size>', got {line!r}")
            name = parts[0]
            in_addr, out_addr, size = (int(x, 16) for x in parts[1:])
            if not (0 <= in_addr <= 0xffffffff and 0 <= out_addr <= 0xffffffff and size > 0):
                raise SystemExit(f"{path}:{n}: invalid AArch32 function range")
            if name in entries:
                raise SystemExit(f"{path}:{n}: function {name} listed twice")
            entries[name] = (in_addr & ~1, out_addr & ~1, size)
    return entries


def symbol_name(bolt_name: str) -> str:
    """BOLT names a local (static) function "<symbol>/<n>", sometimes with "(*<n>)";
    the ELF symbol is just <symbol>."""
    return re.sub(r"(/\d+)?(\(\*\d+\))?$", "", bolt_name)


def branch_bytes(thumb: bool, pc: int, target: int) -> bytes:
    return fix.encode_thumb_bw(pc, target) if thumb else fix.encode_arm_b(pc, target)


def select_entries(entries, requested, allow_missing=False):
    if requested is None:
        if not entries:
            raise SystemExit('BOLT function map is empty')
        return entries.copy()
    wanted = requested.split(',')
    if not all(wanted) or len(set(wanted)) != len(wanted):
        raise SystemExit('--func must name distinct, nonempty functions')
    missing = set(wanted) - entries.keys()
    if missing and not allow_missing:
        raise SystemExit('BOLT did not emit: ' + ', '.join(sorted(missing)))
    # An empty explicit selection must never redirect the entire map.
    selected = {name: entries[name] for name in wanted if name in entries}
    if not selected:
        raise SystemExit('none of the explicitly selected functions were emitted')
    return selected


def function_symbols(readelf, elf):
    """Use ELF STT_FUNC's Thumb bit; nm intentionally strips that bit."""
    text = subprocess.run([readelf, '--symbols', '--wide', elf], check=True,
                          capture_output=True, text=True).stdout
    result = {}
    for line in text.splitlines():
        parts = line.split()
        if len(parts) < 8 or parts[3] != 'FUNC' or parts[6] == 'UND':
            continue
        value, size = int(parts[1], 16), int(parts[2], 0)
        result.setdefault(parts[7], []).append((value & ~1, size, bool(value & 1)))
    return result


def bounded_offset(section, address, length, file_size):
    base, offset, size = section
    if length <= 0 or not base <= address or address + length > base + size:
        raise SystemExit(f'range 0x{address:x}+{length} is outside its section')
    position = offset + address - base
    if position < 0 or position + length > file_size:
        raise SystemExit('redirect range is outside ELF file bytes')
    return position


def sha256(path):
    digest = hashlib.sha256()
    with open(path, 'rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("elf", help="BOLT-optimized ELF (patched in place)")
    ap.add_argument("--original", required=True, help="the un-optimized input ELF")
    ap.add_argument("--func", help="function name; comma-separated list with --map")
    ap.add_argument("--map", help="function map written by llvm-bolt --emit-function-map")
    ap.add_argument("--toolchain", default=os.environ.get("TOOLCHAIN", "build-atfe/bin"))
    ap.add_argument("--instrumented", action="store_true",
                    help="redirect into BOLT's *instrumented* copy: its entry runs counter "
                         "code before the original prologue, so skip the prologue check")
    ap.add_argument("--also-rewritten", default="",
                    help="comma-separated functions BOLT may rewrite without being redirected "
                         "(small helpers given to the optimizer only as inlining candidates; "
                         "code outside the rewritten set keeps calling the original copy)")
    ap.add_argument("--allow-missing", action="store_true",
                    help="tolerate --func names BOLT did not emit (e.g. folded by -icf)")
    ap.add_argument("--select-emitted", action="store_true",
                    help="with --func, explicitly leave other emitted functions unredirected")
    ap.add_argument("--report", help="write hashes and emitted/redirected coverage as JSON")
    args = ap.parse_args()
    if not args.map and not args.func:
        ap.error("need --map FILE and/or --func NAME")
    if args.select_emitted and (not args.map or not args.func):
        ap.error("--select-emitted requires --map and --func")

    readelf = os.path.join(args.toolchain, "llvm-readelf")
    nm = os.path.join(args.toolchain, "llvm-nm")

    secs = fix.sections(readelf, args.elf)
    for need in (".bolt.org.text", ".text"):
        if need not in secs:
            raise SystemExit(f"{args.elf}: no {need} section -- not an optimized image?")
    new_text_addr, _new_text_off, new_text_size = secs[".text"]
    org_addr, org_off, _org_size = secs[".bolt.org.text"]

    # name -> (original entry, new entry)
    plan: dict[str, tuple[int, int]] = {}
    entries = {}
    if args.map:
        entries = read_map(args.map)
        selected = select_entries(entries, args.func, args.allow_missing)
        if args.func and not args.select_emitted:
            allowed = {f for f in args.also_rewritten.split(",") if f}
            extra = sorted(set(entries) - set(selected) - allowed)
            if extra:
                raise SystemExit(f"{args.map}: BOLT also rewrote {', '.join(extra)}; not in --func")
        orig_syms = nm_symbols(nm, args.original)
        for name, (in_addr, out_addr, _size) in selected.items():
            # The map's input address is authoritative; the symbol only has to agree.
            sym = symbol_name(name)
            if sym in orig_syms and orig_syms[sym][0] != in_addr:
                raise SystemExit(
                    f"{name}: map says input 0x{in_addr:x} but {args.original} has 0x{orig_syms[sym][0]:x}"
                )
            plan[name] = (in_addr, out_addr)
    else:
        if "," in args.func:
            raise SystemExit("--func with several names needs --map (legacy mode is one function)")
        plan[args.func] = (function_symbol(nm, args.original, args.func), new_text_addr)

    with open(args.elf, "rb") as fh:
        data = bytearray(fh.read())
    with open(args.original, "rb") as fh:
        original_data = fh.read()
    original_secs = fix.sections(readelf, args.original)
    input_functions = function_symbols(readelf, args.original)
    output_functions = function_symbols(readelf, args.elf)
    records = []
    patched_ranges = []
    text_refs = None

    orig_syms = nm_symbols(nm, args.original)
    for name, (orig_entry, new_entry) in sorted(plan.items(), key=lambda kv: kv[1][0]):
        sym = symbol_name(name)
        if sym not in orig_syms:
            # Guessing the instruction set would write a Thumb B.W into ARM code (or
            # the reverse) -- an undefined instruction the first time it runs.
            raise SystemExit(f"{name}: no symbol {sym} in {args.original}; cannot tell ARM from Thumb")
        definitions = set(input_functions.get(sym, []))
        if len(definitions) != 1:
            raise SystemExit(f"{name}: missing or ambiguous input STT_FUNC symbol")
        input_address, size, thumb = definitions.pop()
        if input_address != orig_entry:
            raise SystemExit(f"{name}: map input does not match its function symbol")
        output_definitions = set(output_functions.get(sym, []))
        if (new_entry, thumb) not in {(a, t) for a, _s, t in output_definitions}:
            raise SystemExit(f"{name}: map destination/mode does not match an output STT_FUNC")
        # BOLT places a rewritten function in .text (hot) or, when it has no profile,
        # entirely in .text.cold; anything else means the map does not match this image.
        if not any(
            n.startswith(".text") and n != ".bolt.org.text" and a <= new_entry < a + sz
            for n, (a, _o, sz) in secs.items()
        ):
            raise SystemExit(
                f"{name}: new entry 0x{new_entry:x} is not in any output .text* section"
            )
        if size < 4:
            raise SystemExit(f"{name}: only {size} bytes; cannot hold a 4-byte redirect branch")
        alignment = 2 if thumb else 4
        if orig_entry % alignment or new_entry % alignment or orig_entry == new_entry:
            raise SystemExit(f"{name}: misaligned or unmoved redirect")
        orig_off = bounded_offset(secs['.bolt.org.text'], orig_entry, 4, len(data))
        input_off = bounded_offset(original_secs['.text'], orig_entry, 4, len(original_data))
        split = require_whole_redirect_prefix(original_data,input_off,size,thumb,allow_split=True)
        if split:
            # R13: a 16-bit first instruction followed by a 32-bit one. The B.W
            # leaves half of the second instruction behind; that is safe only
            # if nothing outside the function can branch or point there.
            if text_refs is None:
                text_refs = original_text_references(os.path.join(args.toolchain, "llvm-objdump"),
                                                     args.original)
            reach = split_prefix_reachable(text_refs, orig_entry, size)
            if reach:
                raise SystemExit(f"{name}: four-byte redirect would split an original Thumb "
                                 f"instruction that is referenced from 0x{reach[0][0]:x}")
        output_size = entries[name][2] if args.map else 4
        if output_size <= 0:
            raise SystemExit(f"{name}: empty output function")
        output_section = next((section for section_name, section in secs.items()
                               if section_name.startswith('.text') and
                               section[0] <= new_entry < section[0] + section[2]), None)
        new_off = bounded_offset(output_section, new_entry, max(4, output_size), len(data))
        if data[orig_off:orig_off + 4] != original_data[input_off:input_off + 4]:
            raise SystemExit(f"{name}: original entry bytes were not restored correctly")
        if any(orig_entry < end and start < orig_entry + 4 for start, end in patched_ranges):
            raise SystemExit(f"{name}: redirect overlaps another entry")
        if any(orig_entry < a < orig_entry + 4 for definitions in input_functions.values()
               for a, _s, _t in definitions):
            raise SystemExit(f"{name}: redirect overwrites a secondary function entry")
        # Sanity: a copy begins like its original (same prologue) unless it is BOLT's
        # instrumented copy, which runs counter code first.
        if not args.instrumented and data[orig_off : orig_off + 4] != data[new_off : new_off + 4]:
            raise SystemExit(
                f"{name}: new copy at 0x{new_entry:x} does not start with the original "
                f"prologue ({bytes(data[new_off:new_off + 4]).hex()} vs "
                f"{bytes(data[orig_off:orig_off + 4]).hex()}): refusing to redirect"
            )
        branch = branch_bytes(thumb, orig_entry, new_entry)
        data[orig_off : orig_off + 4] = branch
        patched_ranges.append((orig_entry, orig_entry + 4))
        records.append(dict(name=name, input=orig_entry, output=new_entry,
                            output_size=output_size, thumb=thumb, branch_hex=branch.hex(),
                            split_prefix=split))
        print(f"redirected {name}: 0x{orig_entry:x} -> {'b.w' if thumb else 'b'} 0x{new_entry:x}")

    with open(args.elf, "wb") as fh:
        fh.write(data)
    if args.report:
        report = dict(schema=1, input_sha256=sha256(args.original),
                      elf_sha256=sha256(args.elf), map_sha256=sha256(args.map) if args.map else None,
                      emitted=[dict(name=n, input=a, output=b, output_size=s)
                               for n, (a, b, s) in entries.items()],
                      redirected=records, execution_verified=False)
        with open(args.report, 'w', encoding='utf-8') as stream:
            json.dump(report, stream, indent=2)
            stream.write('\n')
    print(f"{len(plan)} function(s) redirected (new .text is {new_text_size} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
