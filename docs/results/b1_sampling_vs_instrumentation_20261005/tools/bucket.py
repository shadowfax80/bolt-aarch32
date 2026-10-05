import bisect, struct, subprocess, sys
from collections import Counter
elf, samples = sys.argv[1], sys.argv[2]
nm = subprocess.run(['/home/user/bolt-aarch32/build-atfe/bin/llvm-nm', '-S', '--defined-only', elf], capture_output=True, text=True).stdout
syms = []
for l in nm.splitlines():
    p = l.split()
    if len(p) == 4 and p[2] in 'tTwW':
        syms.append((int(p[0], 16) & ~1, int(p[1], 16), p[3]))
syms.sort(); starts = [s[0] for s in syms]
data = open(samples, 'rb').read()
c = Counter()
for (w,) in struct.iter_unpack('<I', data):
    pc = w & ~1
    i = bisect.bisect_right(starts, pc) - 1
    name = syms[i][2] if i >= 0 and pc < syms[i][0] + max(syms[i][1], 1) else '?'
    c[name] += 1
n = sum(c.values())
for k, v in c.most_common(12):
    print(f'{v:7d} {100*v/n:5.1f}%  {k}')
