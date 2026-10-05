"""R3 scope: sampled functions with an unambiguous name, minus BOLT's skip list."""
import bisect
import struct
import subprocess
import sys
from collections import Counter

elf, samples, skips, out = sys.argv[1:5]
nm = subprocess.run(['/home/user/bolt-aarch32/build-atfe/bin/llvm-nm', '-S', '--defined-only', elf],
                    capture_output=True, text=True, check=True).stdout
funcs = []
for line in nm.splitlines():
    p = line.split()
    if len(p) == 4 and p[2] in 'tTwW' and int(p[1], 16) > 0:
        funcs.append((int(p[0], 16) & ~1, int(p[1], 16), p[3]))
funcs.sort()
names = Counter(f[2] for f in funcs)
starts = [f[0] for f in funcs]
skip = {n.split('/')[0] for n in open(skips).read().strip().split(',')}
hits = Counter()
for (w,) in struct.iter_unpack('<I', open(samples, 'rb').read()):
    pc = w & ~1
    i = bisect.bisect_right(starts, pc) - 1
    if i >= 0 and pc < funcs[i][0] + funcs[i][1]:
        hits[funcs[i][2]] += 1
keep = sorted(n for n in hits if names[n] == 1 and n not in skip)
ambiguous = sorted(n for n in hits if names[n] > 1)
open(out, 'w').write(','.join(keep))
print(f'{len(keep)} functions in scope ({sum(hits[n] for n in keep)} samples); '
      f'ambiguous names left out: {ambiguous} ({sum(hits[n] for n in ambiguous)} samples)')
