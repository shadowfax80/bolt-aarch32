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
import importlib.util
import os
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
            if name in entries:
                raise SystemExit(f"{path}:{n}: function {name} listed twice")
            entries[name] = (in_addr & ~1, out_addr & ~1, size)
    return entries


def branch_bytes(thumb: bool, pc: int, target: int) -> bytes:
    return fix.encode_thumb_bw(pc, target) if thumb else fix.encode_arm_b(pc, target)


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
    args = ap.parse_args()
    if not args.map and not args.func:
        ap.error("need --map FILE and/or --func NAME")

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
    if args.map:
        entries = read_map(args.map)
        wanted = [f for f in (args.func or "").split(",") if f]
        for f in wanted:
            if f not in entries:
                raise SystemExit(
                    f"{args.map}: BOLT did not emit {f} (emitted: {', '.join(sorted(entries)) or 'none'})"
                )
        if wanted:
            extra = sorted(set(entries) - set(wanted))
            if extra:
                raise SystemExit(f"{args.map}: BOLT also rewrote {', '.join(extra)}; not in --func")
        orig_syms = nm_symbols(nm, args.original)
        for name, (in_addr, out_addr, _size) in entries.items():
            # The map's input address is authoritative; the symbol only has to agree.
            if name in orig_syms and orig_syms[name][0] != in_addr:
                raise SystemExit(
                    f"{name}: map says input 0x{in_addr:x} but {args.original} has 0x{orig_syms[name][0]:x}"
                )
            plan[name] = (in_addr, out_addr)
    else:
        if "," in args.func:
            raise SystemExit("--func with several names needs --map (legacy mode is one function)")
        plan[args.func] = (function_symbol(nm, args.original, args.func), new_text_addr)

    with open(args.elf, "rb") as fh:
        data = bytearray(fh.read())

    orig_syms = nm_symbols(nm, args.original)
    for name, (orig_entry, new_entry) in sorted(plan.items(), key=lambda kv: kv[1][0]):
        thumb = fix.is_thumb_symbol(nm, args.original, name) if name in orig_syms else True
        # BOLT places a rewritten function in .text (hot) or, when it has no profile,
        # entirely in .text.cold; anything else means the map does not match this image.
        if not any(
            n.startswith(".text") and n != ".bolt.org.text" and a <= new_entry < a + sz
            for n, (a, _o, sz) in secs.items()
        ):
            raise SystemExit(
                f"{name}: new entry 0x{new_entry:x} is not in any output .text* section"
            )
        size = orig_syms.get(name, (0, 0))[1]
        if size and size < 4:
            raise SystemExit(f"{name}: only {size} bytes; cannot hold a 4-byte redirect branch")
        orig_off = org_off + (orig_entry - org_addr)
        new_off = fix.vaddr_to_offset(secs, new_entry)
        # Sanity: a copy begins like its original (same prologue) unless it is BOLT's
        # instrumented copy, which runs counter code first.
        if not args.instrumented and data[orig_off : orig_off + 4] != data[new_off : new_off + 4]:
            raise SystemExit(
                f"{name}: new copy at 0x{new_entry:x} does not start with the original "
                f"prologue ({bytes(data[new_off:new_off + 4]).hex()} vs "
                f"{bytes(data[orig_off:orig_off + 4]).hex()}): refusing to redirect"
            )
        data[orig_off : orig_off + 4] = branch_bytes(thumb, orig_entry, new_entry)
        print(f"redirected {name}: 0x{orig_entry:x} -> {'b.w' if thumb else 'b'} 0x{new_entry:x}")

    with open(args.elf, "wb") as fh:
        fh.write(data)
    print(f"{len(plan)} function(s) redirected (new .text is {new_text_size} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
