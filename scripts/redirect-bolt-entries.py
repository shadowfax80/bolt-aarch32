#!/usr/bin/env python3
"""Make a BOLT-optimized LK image actually *run* the optimized function.

optimize-lk-bolt.sh ends with fix-kernel-elf-sections.py, which restores the
original text (LK boots from it with the MMU off) and only knows how to
install *instrumentation* hooks. Nothing redirects execution into the
optimized copy BOLT emitted, so the image boots and passes -- while running
byte-for-byte the same code as its input (verified: 0 differing bytes in the
original text). A benchmark of BOLT's layout changes measures nothing unless
the original entry branches to the new copy.

This patches the original function's entry (in .bolt.org.text) with a Thumb-2
`b.w` to the optimized copy. The optimized copy is a complete function with
its own prologue, so entering it at its start is correct; the rest of the
original body simply becomes dead.

Limitation, deliberately explicit: BOLT drops the moved function's symbol in
its output, so the new entry is taken from the start of the output `.text`,
which is valid only when exactly ONE function was rewritten (optimize with
OPTIMIZE_FUNCS=<one function>). Refuses otherwise.

usage: redirect-bolt-entries.py <bolt.elf> --original <input.elf> --func NAME
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
_spec.loader.exec_module(fix)  # reuse sections()/encode_thumb_bw()


def function_symbol(nm: str, elf: str, name: str) -> int:
    out = subprocess.run([nm, "-a", elf], check=True, capture_output=True, text=True).stdout
    for line in out.splitlines():
        parts = line.split()
        if len(parts) == 3 and parts[2] == name:
            return int(parts[0], 16)
    raise SystemExit(f"{elf}: no symbol {name}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("elf", help="BOLT-optimized ELF (patched in place)")
    ap.add_argument("--original", required=True, help="the un-optimized input ELF")
    ap.add_argument("--func", required=True, help="the single function BOLT rewrote")
    ap.add_argument("--toolchain", default=os.environ.get("TOOLCHAIN", "build-atfe/bin"))
    args = ap.parse_args()

    readelf = os.path.join(args.toolchain, "llvm-readelf")
    nm = os.path.join(args.toolchain, "llvm-nm")

    secs = fix.sections(readelf, args.elf)
    for need in (".bolt.org.text", ".text"):
        if need not in secs:
            raise SystemExit(f"{args.elf}: no {need} section -- not an optimized image?")
    new_text_addr, new_text_off, new_text_size = secs[".text"]
    org_addr, org_off, org_size = secs[".bolt.org.text"]

    # llvm-nm already strips the Thumb bit from the value; ask the same
    # $t-mapping-symbol logic BOLT itself uses whether this is Thumb.
    orig_entry = function_symbol(nm, args.original, args.func)
    if not fix.is_thumb_symbol(nm, args.original, args.func):
        raise SystemExit(f"{args.func} is not Thumb; only Thumb B.W is implemented")
    new_entry = new_text_addr  # single rewritten function; see docstring

    with open(args.elf, "rb") as fh:
        data = bytearray(fh.read())

    # Sanity: the new copy must begin like the original function (same
    # prologue), else the "single function at start of .text" assumption is wrong.
    orig_off = org_off + (orig_entry - org_addr)
    if data[orig_off : orig_off + 4] != data[new_text_off : new_text_off + 4]:
        raise SystemExit(
            f"new .text does not start with {args.func}'s prologue "
            f"({bytes(data[new_text_off:new_text_off + 4]).hex()} vs "
            f"{bytes(data[orig_off:orig_off + 4]).hex()}): refusing to redirect"
        )

    branch = fix.encode_thumb_bw(orig_entry, new_entry)
    data[orig_off : orig_off + 4] = branch
    with open(args.elf, "wb") as fh:
        fh.write(data)
    print(f"redirected {args.func}: 0x{orig_entry:x} -> b.w 0x{new_entry:x} "
          f"(new .text is {new_text_size} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
