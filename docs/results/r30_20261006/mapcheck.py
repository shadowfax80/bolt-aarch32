"""Mapping-symbol consistency of a BOLT output vs its input (R30 check).

1. every STT_FUNC symbol in an executable section starts in its own state
   (state = last $a/$t/$d at or below the address, in the same section);
2. the original section decodes exactly like the input .text, except at
   instructions whose bytes differ (patched entries).
"""
import re, subprocess, sys
T = '/home/user/bolt-aarch32/build-atfe/bin/'


def syms(f):
    out = subprocess.run([T + 'llvm-readelf', '-s', '-W', f], capture_output=True, text=True, check=True).stdout
    res = []
    for line in out.splitlines():
        p = line.split()
        if len(p) >= 8 and p[0].endswith(':') and p[0][:-1].isdigit() and p[6].isdigit():
            res.append((int(p[1], 16), p[3], int(p[6]), p[7]))
    return res


def check_funcs(f):
    s = syms(f)
    marks = {}
    for a, t, ndx, n in s:
        if re.fullmatch(r'\$[atd](\..*)?', n):
            marks.setdefault(ndx, []).append((a, n[1]))
    for v in marks.values():
        v.sort()
    bad = []
    nf = 0
    for a, t, ndx, n in s:
        if t != 'FUNC' or ndx not in marks:
            continue
        nf += 1
        want = 't' if a & 1 else 'a'
        base = a & ~1
        state = None
        for ma, mk in marks[ndx]:
            if ma > base:
                break
            if ma == base and state is not None and mk != want and state == want:
                continue
            state = mk
        # several marks at one address: accept if any of them matches
        same = {mk for ma, mk in marks[ndx] if ma == base}
        if state != want and want not in same:
            bad.append((hex(base), n, want, state))
    return nf, bad


def dis(f, section):
    out = subprocess.run([T + 'llvm-objdump', '-d', '--no-show-raw-insn', '-j', section, f],
                         capture_output=True, text=True, check=True).stdout
    res = {}
    for line in out.splitlines():
        m = re.match(r'\s*([0-9a-f]+):\s+(.*)', line)
        if m:
            res[int(m.group(1), 16)] = re.sub(r'\s*@.*$', '', m.group(2)).split('<')[0].strip()
    return res


inp, outp = sys.argv[1], sys.argv[2]
for f in (inp, outp):
    nf, bad = check_funcs(f)
    print(f'{f}: {nf} functions, {len(bad)} start in the wrong state', bad[:8])
a = dis(inp, '.text')
b = dis(outp, '.bolt.org.text')
diff = [x for x in sorted(set(a) | set(b)) if a.get(x) != b.get(x)]
print(f'original section: {len(a)} input insns, {len(b)} output insns, {len(diff)} decode differently')
for x in diff[:12]:
    print(f'  {x:08x}: {a.get(x)!r} -> {b.get(x)!r}')
