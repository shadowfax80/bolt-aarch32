#!/usr/bin/env bash
# Full-image BOLT of the plain `baseline` LK image (no function allowlist): every function
# BOLT can process is rewritten into the new .text; the rest stay in place. Uses the profile
# from passes_stage.sh if present. Output: <outdir>/baseline_full.{elf,bin}, full_stats.txt.
#
#   full_image_wsl.sh <outdir> [extra llvm-bolt flags...]
set -euo pipefail
cd "$HOME/bolt-aarch32"
out="$1"; shift
V=build-atfe/variants; T=build-atfe/bin
ELF="$V/baseline.elf"; OUT="$V/baseline_full.elf"
DATA=(); [[ -f "$V/baseline.fdata" ]] && DATA=(-data="$V/baseline.fdata")
"$T/llvm-bolt" "$ELF" -o "$OUT" "${DATA[@]}" --no-huge-pages -lite=0 \
  -reorder-blocks=ext-tsp -reorder-functions=hfsort+ -icf=all "$@" > "$out/full.log" 2>&1 \
  || { tail -20 "$out/full.log" >&2; exit 1; }
python3 scripts/fix-kernel-elf-paddr.py "$OUT"
python3 scripts/fix-kernel-elf-entry.py "$OUT" --original "$ELF" --readelf "$T/llvm-readelf"
python3 scripts/fix-kernel-elf-sections.py "$OUT" --original "$ELF" --readelf "$T/llvm-readelf"
"$T/llvm-objcopy" -O binary "$OUT" "$V/baseline_full.bin"
cp "$OUT" "$V/baseline_full.bin" "$out/"
python3 - "$ELF" "$OUT" "$T" > "$out/full_stats.txt" <<'EOF'
import re, subprocess, sys
elf, out, t = sys.argv[1:]
def syms(f):
    r = {}
    for l in subprocess.run([t + "/llvm-nm", "--defined-only", f], capture_output=True, text=True).stdout.splitlines():
        p = l.split()
        if len(p) == 3 and p[1] in "tT":
            r[p[2]] = int(p[0], 16)
    return r
secs = subprocess.run([t + "/llvm-readelf", "-S", "-W", out], capture_output=True, text=True).stdout
lo = hi = 0
for l in secs.splitlines():
    m = re.match(r"\s*\[\s*\d+\]\s+(\S+)\s+\S+\s+([0-9a-f]+)\s+[0-9a-f]+\s+([0-9a-f]+)", l)
    if m and m[1] in (".text", ".text.cold"):
        a, s = int(m[2], 16), int(m[3], 16)
        lo = a if not lo else min(lo, a); hi = max(hi, a + s)
fi, fo = syms(elf), syms(out)
moved = [n for n in fi if n in fo and lo <= fo[n] < hi]
print(f"functions in input: {len(fi)}; rewritten into the new .text: {len(moved)}")
print("left in place:", ", ".join(sorted(set(fi) - set(moved))))
EOF
cat "$out/full_stats.txt"
