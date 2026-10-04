"""R17 stage 2: seeded random A32/T32 functions for the bolt_edge image.

Each function is generated as a small IR (forward-only CFG, so it always
terminates). The same IR yields both the assembly and an independent Python
model of the return value, so `bolt_edge all` results can be predicted
without running anything.

Blocks hold flag-free ALU operations on r0-r2 and end in one terminator:
return, forward branch, compare + conditional branch, a predicated group
(T32: IT block with a random then/else mask; A32: per-instruction
conditions), optionally ending in a predicated return, direct call (same or
other ISA), tail call, conditional tail call, or a 4-way switch (T32 TBB,
A32 `adr`+`ldr pc` table). Helpers (t_add5, t_add100, a_add7, a_add100) only
change r0, so r1/r2 survive calls.
"""
import random

M = 0xffffffff
HELPERS = {'t_add5': ('T32', 5), 't_add100': ('T32', 100),
           'a_add7': ('A32', 7), 'a_add100': ('A32', 100)}
CONDS = ['eq', 'ne', 'cs', 'cc', 'mi', 'pl', 'hi', 'ls', 'ge', 'lt', 'gt', 'le']
INVERSE = {'eq': 'ne', 'ne': 'eq', 'cs': 'cc', 'cc': 'cs', 'mi': 'pl', 'pl': 'mi',
           'hi': 'ls', 'ls': 'hi', 'ge': 'lt', 'lt': 'ge', 'gt': 'le', 'le': 'gt'}
OPS = ['add', 'sub', 'eor', 'orr', 'and']
REGS = ['r0', 'r1', 'r2']


def flags_of_cmp(a, imm):
    res = (a - imm) & M
    n = res >> 31
    z = res == 0
    c = a >= imm
    v = ((a ^ imm) & (a ^ res)) >> 31
    return n, z, c, v


def holds(cond, f):
    n, z, c, v = f
    return {'eq': z, 'ne': not z, 'cs': c, 'cc': not c, 'mi': n == 1, 'pl': n == 0,
            'hi': c and not z, 'ls': (not c) or z, 'ge': n == v, 'lt': n != v,
            'gt': (not z) and n == v, 'le': z or n != v}[cond]


def alu(op, a, b):
    return {'add': a + b, 'sub': a - b, 'eor': a ^ b, 'orr': a | b, 'and': a & b}[op] & M


class Func:
    def __init__(self, name, isa, rng):
        self.name, self.isa, self.rng = name, isa, rng
        self.k1, self.k2 = rng.randrange(256), rng.randrange(256)
        n = rng.randrange(4, 11)
        self.blocks = [self.block(i, n) for i in range(n)]
        self.frame = any(t[0] in ('call', 'tail') for _, t in self.blocks)
        if self.frame:  # a conditional tail call cannot pop the frame first
            # Keep the compare, branch to the next block instead.
            self.blocks = [(ops, ('cond', t[1], t[2], t[3], i + 1) if t[0] == 'ctc' else t)
                           for i, (ops, t) in enumerate(self.blocks)]

    def alu_op(self):
        r = self.rng
        src2 = r.choice(REGS) if r.random() < 0.3 else r.randrange(256)
        return (r.choice(OPS), r.choice(REGS), r.choice(REGS), src2)

    def block(self, i, n):
        r = self.rng
        ops = [self.alu_op() for _ in range(r.randrange(0, 4))]
        last = i == n - 1
        cmpv = (r.choice(REGS), r.randrange(256), r.choice(CONDS))
        kinds = ['ret', 'tail'] if last else \
            ['ret', 'br', 'cond', 'cond', 'pred', 'pred', 'call', 'tail', 'ctc'] + \
            (['switch'] if n - i - 1 >= 2 else [])
        kind = r.choice(kinds)
        if kind == 'br':
            return ops, ('br', r.randrange(i + 1, n))
        if kind == 'cond':
            return ops, ('cond',) + cmpv + (r.randrange(i + 1, n),)
        if kind == 'pred':
            size = r.randrange(1, 5)
            letters = 't' + ''.join(r.choice('te') for _ in range(size - 1))
            slots = [self.alu_op() for _ in range(size)]
            ret_last = r.random() < 0.35
            return ops, ('pred',) + cmpv + (letters, slots, ret_last)
        if kind in ('call', 'tail'):
            return ops, (kind, r.choice(list(HELPERS)))
        if kind == 'ctc':
            same = [h for h, (isa, _) in HELPERS.items() if isa == self.isa]
            return ops, ('ctc',) + cmpv + (r.choice(same),)
        if kind == 'switch':
            return ops, ('switch', [r.randrange(i + 1, n) for _ in range(4)])
        return ops, ('ret',)

    # ------------------------------------------------------------- model
    def model(self, x):
        regs = {'r0': x & M, 'r1': self.k1, 'r2': self.k2}
        i = 0
        while True:
            ops, t = self.blocks[i]
            for op, d, s, b in ops:
                regs[d] = alu(op, regs[s], regs[b] if isinstance(b, str) else b)
            k = t[0]
            if k == 'ret':
                return regs['r0']
            if k == 'br':
                i = t[1]
                continue
            if k in ('call', 'tail'):
                regs['r0'] = (regs['r0'] + HELPERS[t[1]][1]) & M
                if k == 'tail':
                    return regs['r0']
                i += 1
                continue
            if k == 'switch':
                i = t[1][regs['r0'] & 3]
                continue
            f = flags_of_cmp(regs[t[1]], t[2])
            c = holds(t[3], f)
            if k == 'cond':
                i = t[4] if c else i + 1
                continue
            if k == 'ctc':
                if c:
                    return (regs['r0'] + HELPERS[t[4]][1]) & M
                i += 1
                continue
            # pred: slots run when their letter matches the condition; a final
            # predicated return leaves with the value at that point.
            letters, slots, ret_last = t[4], t[5], t[6]
            for j, letter in enumerate(letters):
                active = c if letter == 't' else not c
                if ret_last and j == len(letters) - 1:
                    if active:
                        return regs['r0']
                    break
                if active:
                    op, d, s, b = slots[j]
                    regs[d] = alu(op, regs[s], regs[b] if isinstance(b, str) else b)
            i += 1

    # ------------------------------------------------------------- assembly
    def asm(self):
        T = self.isa == 'T32'
        w = '.w' if T else ''
        L = lambda j: f'.L{self.name}_{j}'
        out = [' .p2align 2', ' .thumb' if T else ' .arm', f' .global {self.name}',
               f' .type {self.name},%function']
        if T:
            out.append(' .thumb_func')
        out.append(f'{self.name}:')
        e = out.append

        def alu_text(op, d, s, b, cond=''):
            src = b if isinstance(b, str) else f'#{b}'
            return f' {op}{cond}{w} {d}, {s}, {src}'

        def ret_text(cond=''):
            return f' pop{cond} {{r4, pc}}' if self.frame else f' bx{cond} lr'

        def call_text(h):
            same = HELPERS[h][0] == self.isa
            return f' {"bl" if same else "blx"} {h}'

        if self.frame:
            e(' push {r4, lr}')
        e(f' mov{w} r1, #{self.k1}')
        e(f' mov{w} r2, #{self.k2}')
        for i, (ops, t) in enumerate(self.blocks):
            e(f'{L(i)}:')
            for op in ops:
                e(alu_text(*op))
            k = t[0]
            if k == 'ret':
                e(ret_text())
            elif k == 'br':
                e(f' b{w} {L(t[1])}')
            elif k == 'call':
                e(call_text(t[1]))
            elif k == 'tail':
                if self.frame:
                    e(' pop {r4, lr}')
                e(f' b{w} {t[1]}')
            elif k == 'switch':
                if T:
                    e(' and r3, r0, #3')
                    e(' tbb [pc, r3]')
                    e('1:')
                    e(' .byte ' + ', '.join(f'({L(j)}-1b)/2' for j in t[1]))
                    e(' .p2align 1')
                else:
                    e(' and r3, r0, #3')
                    e(' adr r12, 1f')
                    e(' ldr pc, [r12, r3, lsl #2]')
                    e('1:')
                    e(' .word ' + ', '.join(L(j) for j in t[1]))
            else:
                e(f' cmp {t[1]}, #{t[2]}')
                cond = t[3]
                if k == 'cond':
                    e(f' b{cond}{w} {L(t[4])}')
                elif k == 'ctc':
                    e(f' b{cond}{w} {t[4]}')
                else:
                    letters, slots, ret_last = t[4], t[5], t[6]
                    if T:
                        e(f' i{letters} {cond}')
                    for j, letter in enumerate(letters):
                        c = cond if letter == 't' else INVERSE[cond]
                        if ret_last and j == len(letters) - 1:
                            e(ret_text(c))
                        else:
                            e(alu_text(*slots[j], cond=c))
        e(f' .size {self.name},.-{self.name}')
        return '\n'.join(out)


def generate(seed=17, per_isa=24):
    """Return [(name, isa, asm_text, model)] for per_isa functions of each ISA."""
    rng = random.Random(seed)
    funcs = []
    for isa, tag in (('T32', 't'), ('A32', 'a')):
        for i in range(per_isa):
            f = Func(f'rand_{tag}_{i:02d}', isa, rng)
            funcs.append((f.name, isa, f.asm(), f.model))
    return funcs
