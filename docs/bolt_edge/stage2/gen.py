#!/usr/bin/env python3
"""Generate the R17 `bolt_edge` LK app, its project and its manifest.

One source of truth: every case is defined here once, as assembly or C plus
an independent Python model of what it returns. The generator writes

  overlay/lk/files/app/bolt_edge/   LK app (console command `bolt_edge all`)
  overlay/lk/files/project/rpi4-bolt-edge.mk
  docs/bolt_edge/manifest.json      expected admission + expected sinks

`bolt_edge all` prints `bolt_edge: <case> sink=0x%08x` for every case. A sink
is FNV-1a over the case's 32-bit results for INPUTS (little-endian words);
`manifest.json` holds the values computed from the Python models, never from
a run. Expected admission is the design intent ("rewrite" or "reject:<class>"),
checked against BOLT's admission report. See docs/R17_BOLT_EDGE_PLAN.md.

Usage: python3 scripts/bolt_edge/gen.py [--check]
  --check  regenerate in memory and fail if the committed files differ.
"""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / 'overlay/lk/files/app/bolt_edge'
PROJECT = ROOT / 'overlay/lk/files/project/rpi4-bolt-edge.mk'
MANIFEST = ROOT / 'docs/bolt_edge/manifest.json'

M = 0xffffffff
INPUTS = [0, 1, 2, 3, 4, 5, 6, 8, 9, 15, 16, 255,
          0x7fffffff, 0x80000000, 0xfffffffe, 0xffffffff]
NORETURN_TRIGGER = 0xdead0000          # never in INPUTS: noreturn paths stay cold
assert NORETURN_TRIGGER not in INPUTS


def u(v):
    return v & M


def s32(v):
    v &= M
    return v - (1 << 32) if v & 0x80000000 else v


def sink(values):
    h = 0x811c9dc5
    for v in values:
        for b in u(v).to_bytes(4, 'little'):
            h = u((h ^ b) * 16777619)
    return h


# ---------------------------------------------------------------- assembly
asm = []          # assembly text blocks
cases = []        # dict(name, isa, area, model, admission, functions, note)
helpers = {}      # function name -> expected admission


def fn(name, isa, body, size=True, align=True, glob=True):
    """Emit one assembly function."""
    lines = []
    if align:
        lines.append(' .p2align 2')
    lines.append(' .arm' if isa == 'A32' else ' .thumb')
    if glob:
        lines.append(f' .global {name}')
    lines.append(f' .type {name},%function')
    if isa == 'T32':
        lines.append(' .thumb_func')
    lines.append(f'{name}:')
    lines += [' ' + l if not l.endswith(':') else l for l in body.strip().split('\n')]
    if size:
        lines.append(f' .size {name},.-{name}')
    asm.append('\n'.join(lines))


def case(name, isa, area, model, admission='rewrite', functions=None, note=''):
    cases.append(dict(name=name, isa=isa, area=area, model=model,
                      admission=admission, functions=functions or {name: admission},
                      note=note))


# Helpers (called by cases; must be rewritten).
fn('t_add5', 'T32', 'adds r0, #5\nbx lr')
fn('t_add100', 'T32', 'adds r0, #100\nbx lr')
fn('a_add7', 'A32', 'add r0, r0, #7\nbx lr')
fn('a_add100', 'A32', 'add r0, r0, #100\nbx lr')
for h in ('t_add5', 't_add100', 'a_add7', 'a_add100'):
    helpers[h] = 'rewrite'

# Interworking: calls and tail calls in every ISA direction.
fn('iw_a_call_t', 'A32', 'push {r4, lr}\nblx t_add5\npop {r4, pc}')
case('iw_a_call_t', 'A32', 'interworking', lambda x: x + 5)
fn('iw_t_call_a', 'T32', 'push {r4, lr}\nblx a_add7\npop {r4, pc}')
case('iw_t_call_a', 'T32', 'interworking', lambda x: x + 7)
fn('iw_a_tail_a', 'A32', 'add r0, r0, #1\nb a_add7')
case('iw_a_tail_a', 'A32', 'interworking', lambda x: x + 8)
fn('iw_t_tail_t', 'T32', 'adds r0, #1\nb.w t_add5')
case('iw_t_tail_t', 'T32', 'interworking', lambda x: x + 6)
fn('iw_t_tail_a', 'T32', 'adds r0, #1\nb.w a_add7')
case('iw_t_tail_a', 'T32', 'interworking', lambda x: x + 8,
     note='cross-ISA tail call: ld.lld inserts an interworking thunk')
fn('iw_a_tail_t', 'A32', 'add r0, r0, #1\nb t_add5')
case('iw_a_tail_t', 'A32', 'interworking', lambda x: x + 6,
     note='cross-ISA tail call: ld.lld inserts an interworking thunk')

# IT blocks: all 15 masks. r1 accumulates predicated adds; cond is x >u 8.
VALS = [1, 16, 256, 4096]
for pat in ['t', 'tt', 'te', 'ttt', 'tte', 'tet', 'tee', 'tttt', 'ttte',
            'ttet', 'ttee', 'tett', 'tete', 'teet', 'teee']:
    body = ['movs r1, #0', 'cmp r0, #8', f'i{pat} hi']
    for i, l in enumerate(pat):
        body.append(f'add{"hi" if l == "t" else "ls"}.w r1, r1, #{VALS[i]}')
    body += ['add r0, r0, r1', 'bx lr']
    name = 'it_mask_' + pat
    fn(name, 'T32', '\n'.join(body))

    def model(x, pat=pat):
        c = x > 8
        return x + sum(VALS[i] for i, l in enumerate(pat) if (l == 't') == c)
    case(name, 'T32', 'it-mask', model)

# IT control transfers (R4, R6) and A32 BL<c>.
fn('it_ret', 'T32', 'cmp r0, #3\nit eq\nbxeq lr\nadds r0, #9\nbx lr')
case('it_ret', 'T32', 'it-transfer', lambda x: x if x == 3 else x + 9)
fn('it_pop_ret', 'T32', 'push {r4, lr}\ncmp r0, #5\nitt ne\nmovne r0, #1\npopne {r4, pc}\nmovs r0, #2\npop {r4, pc}')
case('it_pop_ret', 'T32', 'it-transfer', lambda x: 1 if x != 5 else 2)
fn('it_ite_ret', 'T32', 'cmp r0, #9\nite eq\nmoveq r0, #3\nbxne lr\nadds r0, #4\nbx lr')
case('it_ite_ret', 'T32', 'it-transfer', lambda x: 7 if x == 9 else x)
fn('it_call', 'T32', 'push {r4, lr}\ncmp r0, #0\nit ne\nblne t_add5\nadds r0, #1\npop {r4, pc}')
case('it_call', 'T32', 'it-transfer', lambda x: x + 6 if x != 0 else 1)
fn('it_callx', 'T32', 'push {r4, lr}\ncmp r0, #4\nit gt\nblxgt a_add7\nadds r0, #1\npop {r4, pc}')
case('it_callx', 'T32', 'it-transfer', lambda x: x + 8 if s32(x) > 4 else x + 1)
fn('it_ctc', 'T32', 'cmp r0, #3\nit lt\nblt.w t_add5\nb.w t_add100')
case('it_ctc', 'T32', 'it-transfer', lambda x: x + 5 if s32(x) < 3 else x + 100)
fn('t_ctc', 'T32', 'cmp r0, #3\nbne.w t_add5\nb.w t_add100')
case('t_ctc', 'T32', 'it-transfer', lambda x: x + 5 if x != 3 else x + 100)
fn('a_ctc', 'A32', 'cmp r0, #3\nblt a_add7\nb a_add100')
case('a_ctc', 'A32', 'it-transfer', lambda x: x + 7 if s32(x) < 3 else x + 100)
fn('a_bleq', 'A32', 'push {r4, lr}\ncmp r0, #0\nbleq a_add7\nadd r0, r0, #1\npop {r4, pc}')
case('a_bleq', 'A32', 'it-transfer', lambda x: 8 if x == 0 else x + 1)

# Noreturn chains (R5): only the returning path runs.
for isa, p in (('T32', 't'), ('A32', 'a')):
    fn(f'nr_halt_{p}', isa, f'1:\nwfi\nb 1b')
    helper = 't_add5' if isa == 'T32' else 'a_add7'
    call = 'bl' if isa == 'T32' else 'bl'
    fn(f'nr_fatal_{p}', isa, f'push {{r4, lr}}\n{call} {helper}\n{call} nr_halt_{p}')
    add3 = 'adds r0, #3' if isa == 'T32' else 'add r0, r0, #3'
    fn(f'nr_user_{p}', isa, f'movw r1, #0\nmovt r1, #0xdead\ncmp r0, r1\nbeq 1f\n{add3}\nbx lr\n1:\nbl nr_fatal_{p}')
    case(f'nr_user_{p}', isa, 'noreturn', lambda x: x + 3,
         functions={f'nr_user_{p}': 'rewrite', f'nr_fatal_{p}': 'rewrite',
                    f'nr_halt_{p}': 'rewrite'})

# Real fallthrough into the next function: must reject.
fn('ft_into_next', 'T32', 'adds r0, #1', size=True)
fn('ft_next', 'T32', 'adds r0, #2\nbx lr', align=False)
case('ft_into_next', 'T32', 'fallthrough', lambda x: x + 3,
     admission='reject:fallthrough',
     functions={'ft_into_next': 'reject:fallthrough', 'ft_next': 'rewrite'})

# Data in code.
fn('lit_a', 'A32', 'ldr r1, =0x12345678\nadd r0, r0, r1\nbx lr\n.ltorg')
case('lit_a', 'A32', 'data-in-code', lambda x: x + 0x12345678)
fn('lit_t', 'T32', 'ldr r1, =0x0badf00d\nadds r0, r0, r1\nbx lr\n.p2align 2\n.ltorg')
case('lit_t', 'T32', 'data-in-code', lambda x: x + 0x0badf00d)
fn('t_tbb', 'T32', '''and r1, r0, #3
tbb [pc, r1]
1:
.byte (10f-1b)/2, (11f-1b)/2, (12f-1b)/2, (13f-1b)/2
.p2align 1
10:
movs r0, #11
bx lr
11:
movs r0, #22
bx lr
12:
movs r0, #33
bx lr
13:
movs r0, #44
bx lr''')
case('t_tbb', 'T32', 'data-in-code', lambda x: [11, 22, 33, 44][x & 3])
fn('t_tbh', 'T32', '''and r1, r0, #3
tbh [pc, r1, lsl #1]
1:
.short (10f-1b)/2, (11f-1b)/2, (12f-1b)/2, (13f-1b)/2
10:
movs r0, #100
bx lr
11:
movs r0, #200
bx lr
12:
mov.w r0, #300
bx lr
13:
mov.w r0, #400
bx lr''')
case('t_tbh', 'T32', 'data-in-code', lambda x: [100, 200, 300, 400][x & 3])
fn('t_adr_tbh', 'T32', '''and r3, r0, #3
adr.w r2, 1f
tbh [pc, r3, lsl #1]
1:
.short (10f-1b)/2, (11f-1b)/2, (12f-1b)/2, (13f-1b)/2
10:
movs r0, #1
bx lr
11:
movs r0, #2
bx lr
12:
movs r0, #3
bx lr
13:
movs r0, #4
bx lr''')
case('t_adr_tbh', 'T32', 'data-in-code', lambda x: (x & 3) + 1,
     admission='reject:pc-read', note='vsnprintf pattern; becomes rewrite when R12 lands')
fn('a_add_pc_switch', 'A32', '''and r1, r0, #3
add pc, pc, r1, lsl #2
nop
b 10f
b 11f
b 12f
b 13f
10:
mov r0, #5
bx lr
11:
mov r0, #6
bx lr
12:
mov r0, #7
bx lr
13:
mov r0, #8
bx lr''')
case('a_add_pc_switch', 'A32', 'data-in-code', lambda x: (x & 3) + 5,
     admission='reject:pc-write')

# Entries and symbols.
fn('short16', 'T32', 'adds r0, #2\nbx lr')
case('short16', 'T32', 'entries', lambda x: x + 2,
     note='16-bit first instruction: rewritten, not redirectable until R13')
asm.append(' .global t_alias\n .type t_alias,%function\n .set t_alias, t_add5')
case('t_alias', 'T32', 'entries', lambda x: x + 5,
     functions={'t_alias': 'alias'}, note='alias of t_add5')
fn('size0_t', 'T32', 'adds r0, #9\nbx lr', size=False)
case('size0_t', 'T32', 'entries', lambda x: x + 9, note='no .size')

# Must-reject guard and state cases.
fn('a_pcread', 'A32', 'mov r1, pc\nsub r1, r1, pc\nadd r0, r0, r1\nbx lr')
case('a_pcread', 'A32', 'guards', lambda x: x - 4, admission='reject:pc-read')
fn('t_excl', 'T32', '''push {r4, lr}
sub sp, #8
str r0, [sp]
mov r2, sp
1:
ldrex r1, [r2]
adds r1, #1
strex r3, r1, [r2]
cmp r3, #0
bne 1b
ldr r0, [sp]
add sp, #8
pop {r4, pc}''')
case('t_excl', 'T32', 'guards', lambda x: x + 1, note='local LDREX/STREX loop')
fn('a_carry', 'A32', 'adds r1, r0, r0\nadc r0, r0, #0\nbx lr')
case('a_carry', 'A32', 'flags', lambda x: x + (x >> 31))
fn('t_carry', 'T32', 'adds r1, r0, r0\nadc r0, r0, #0\nbx lr')
case('t_carry', 'T32', 'flags', lambda x: x + (x >> 31))

# ---------------------------------------------------------------- C cases
DUP = {'a': (3, 1, 0x55), 'b': (5, 2, 0xaa)}
dup_src = {}
for k, (mul, add, xor) in DUP.items():
    dup_src[f'edge_dup_{k}.c'] = (
        '#include <stdint.h>\n'
        f'static __attribute__((noinline)) uint32_t dup(uint32_t x) {{ return x * {mul}u + {add}u; }}\n'
        f'uint32_t edge_dup_{k}(uint32_t x) {{ return dup(x) ^ 0x{xor:x}u; }}\n')
    case(f'edge_dup_{k}', 'C', 'entries',
         lambda x, mul=mul, add=add, xor=xor: u(u(x * mul + add) ^ xor),
         note='static helper `dup` duplicated across files (dup/1, dup/2)')

C_VARIANTS = {'arm_o2': '__attribute__((target("arm")))',
              'thumb_o2': '__attribute__((target("thumb")))',
              'thumb_os': '__attribute__((target("thumb"), minsize))',
              'arm_o0': '__attribute__((target("arm"), optnone, noinline))'}


def c_template(v, attr):
    return f'''{attr} uint32_t c_switch_{v}(uint32_t x) {{
    switch (x & 7) {{
    case 0: return x + 3;
    case 1: return x * 5;
    case 2: return x ^ 0x5a5a5a5au;
    case 3: return x - 11;
    case 4: return (x << 3) | 1;
    case 5: return x >> 2;
    case 6: return ~x;
    default: return 77;
    }}
}}
{attr} uint32_t c_loop_{v}(uint32_t x) {{
    uint32_t acc = 0;
    for (uint32_t i = 0; i < 16; i++) acc += i ^ x;
    return acc;
}}
{attr} __attribute__((noinline)) static uint32_t fib_{v}(uint32_t n) {{
    return n < 2 ? n : fib_{v}(n - 1) + fib_{v}(n - 2);
}}
{attr} uint32_t c_fib_{v}(uint32_t x) {{ return fib_{v}(x & 15); }}
{attr} static uint32_t op0_{v}(uint32_t x) {{ return x + 1; }}
{attr} static uint32_t op1_{v}(uint32_t x) {{ return x * 3; }}
{attr} static uint32_t op2_{v}(uint32_t x) {{ return x ^ 0xffu; }}
{attr} static uint32_t op3_{v}(uint32_t x) {{ return x >> 1; }}
static uint32_t (*const ops_{v}[4])(uint32_t) = {{op0_{v}, op1_{v}, op2_{v}, op3_{v}}};
{attr} uint32_t c_indirect_{v}(uint32_t x) {{ return ops_{v}[x & 3](x); }}
{attr} uint32_t c_noret_{v}(uint32_t x) {{
    if (x == 0x{NORETURN_TRIGGER:x}u)
        panic("bolt_edge: noreturn path taken\\n");
    return x * 7;
}}
'''


C_INCLUDES = ['#include <stdint.h>', '#include <stdlib.h>', '#include <lk/debug.h>', '']
c_body = list(C_INCLUDES)
for v, attr in C_VARIANTS.items():
    c_body.append(c_template(v, attr))

# Whole-module -marm / -mthumb builds of the same cases (submodules
# app/bolt_edge/marm and app/bolt_edge/mthumb), at -O2, -Os and -O0.
FLAG_MODULES = {'marm': '-marm', 'mthumb': '-mthumb'}
FLAG_OPTS = {'o2': '', 'os': '__attribute__((minsize))',
             'o0': '__attribute__((optnone, noinline))'}
flag_src = {}
for flag in FLAG_MODULES:
    body = list(C_INCLUDES)
    for opt, attr in FLAG_OPTS.items():
        body.append(c_template(f'{flag}_{opt}', attr))
    flag_src[flag] = '\n'.join(body)


def c_switch(x):
    return u([x + 3, x * 5, x ^ 0x5a5a5a5a, x - 11, (x << 3) | 1, x >> 2, ~x, 77][x & 7])


def fib(n):
    a, b = 0, 1
    for _ in range(n):
        a, b = b, a + b
    return a


for v in [*C_VARIANTS, *(f'{f}_{o}' for f in FLAG_MODULES for o in FLAG_OPTS)]:
    isa = 'C-' + v
    case(f'c_switch_{v}', isa, 'compiler', c_switch)
    case(f'c_loop_{v}', isa, 'compiler', lambda x: u(sum(i ^ x for i in range(16))))
    case(f'c_fib_{v}', isa, 'compiler', lambda x: fib(x & 15))
    case(f'c_indirect_{v}', isa, 'compiler',
         lambda x: u([x + 1, x * 3, x ^ 0xff, x >> 1][x & 3]))
    case(f'c_noret_{v}', isa, 'compiler', lambda x: u(x * 7),
         note='noreturn panic path not taken')

# ---------------------------------------------------------------- stage 2
# Seeded random A32/T32 functions (scripts/bolt_edge/rand.py): IR-generated
# assembly and models, same manifest format.
sys.path.insert(0, str(Path(__file__).resolve().parent))
import rand  # noqa: E402

RAND_SEED, RAND_PER_ISA = 17, 24
for rname, risa, rasm, rmodel in rand.generate(RAND_SEED, RAND_PER_ISA):
    asm.append(rasm)
    case(rname, risa, 'random', rmodel, note=f'rand.py seed {RAND_SEED}')

# ---------------------------------------------------------------- outputs
HEADER = '/* Generated by scripts/bolt_edge/gen.py -- do not edit. */\n'


def render():
    files = {}
    files['cases.S'] = (HEADER.replace('/*', '@').replace(' */', '') +
                        ' .syntax unified\n .arch armv7-a\n .text\n\n' +
                        '\n\n'.join(asm) + '\n')
    files['edge_c.c'] = HEADER + '\n'.join(c_body)
    files.update({k: HEADER + v for k, v in dup_src.items()})
    for flag, opt in FLAG_MODULES.items():
        files[f'{flag}/edge_cflag.c'] = HEADER + flag_src[flag]
        files[f'{flag}/rules.mk'] = f'''# Generated by scripts/bolt_edge/gen.py -- do not edit.
# Whole-module {opt} build of the bolt_edge C cases.
LOCAL_DIR := $(GET_LOCAL_DIR)

MODULE := $(LOCAL_DIR)

MODULE_SRCS += $(LOCAL_DIR)/edge_cflag.c

MODULE_COMPILEFLAGS += {opt} -mfpu=none

include make/module.mk
'''
    decl = ''.join(f'uint32_t {c["name"]}(uint32_t);\n' for c in cases)
    table = ''.join(f'    {{"{c["name"]}", {c["name"]}}},\n' for c in cases)
    inputs = ', '.join(f'0x{x:08x}u' for x in INPUTS)
    files['cases.inc'] = (HEADER + decl + '\nstatic const struct bolt_edge_case cases[] = {\n'
                          + table + '};\n\nstatic const uint32_t inputs[] = {' + inputs + '};\n')
    files['bolt_edge.c'] = HEADER + r'''#include <lk/console_cmd.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

struct bolt_edge_case {
    const char *name;
    uint32_t (*fn)(uint32_t);
};

#include "cases.inc"

/* FNV-1a over the little-endian results, as in docs/bolt_edge/manifest.json. */
static uint32_t run_case(const struct bolt_edge_case *c) {
    uint32_t h = 0x811c9dc5u;
    for (size_t i = 0; i < sizeof(inputs) / sizeof(inputs[0]); i++) {
        uint32_t v = c->fn(inputs[i]);
        for (int b = 0; b < 4; b++) {
            h ^= (v >> (8 * b)) & 0xff;
            h *= 16777619u;
        }
    }
    return h;
}

static int cmd_bolt_edge(int argc, const console_cmd_args *argv) {
    unsigned n = 0;
    for (size_t i = 0; i < sizeof(cases) / sizeof(cases[0]); i++) {
        if (argc > 1 && strcmp(argv[1].str, "all") && strcmp(argv[1].str, cases[i].name))
            continue;
        printf("bolt_edge: %s sink=0x%08x\n", cases[i].name, run_case(&cases[i]));
        n++;
    }
    printf("bolt_edge: done %u cases\n", n);
    return 0;
}

STATIC_COMMAND_START
STATIC_COMMAND("bolt_edge", "R17 edge-case workloads: bolt_edge all|<case>", &cmd_bolt_edge)
STATIC_COMMAND_END(bolt_edge);
'''
    files['rules.mk'] = '''# Generated by scripts/bolt_edge/gen.py -- do not edit.
LOCAL_DIR := $(GET_LOCAL_DIR)

MODULE := $(LOCAL_DIR)

MODULE_DEPS += lib/console \
	$(LOCAL_DIR)/marm \
	$(LOCAL_DIR)/mthumb

MODULE_SRCS += \\
	$(LOCAL_DIR)/bolt_edge.c \\
	$(LOCAL_DIR)/cases.S \\
	$(LOCAL_DIR)/edge_c.c \\
	$(LOCAL_DIR)/edge_dup_a.c \\
	$(LOCAL_DIR)/edge_dup_b.c \\

# No FPU/NEON anywhere (project rule).
MODULE_COMPILEFLAGS += -mfpu=none

include make/module.mk
'''
    project = '''# Generated by scripts/bolt_edge/gen.py -- do not edit.
# rpi4-bolt-test plus the R17 bolt_edge app (bolt_bench keeps wdog/sample/dump).
LOCAL_DIR := $(GET_LOCAL_DIR)

TARGET := rpi4

MODULES += \\
	app/shell \\
	app/bolt_bench \\
	app/bolt_edge
'''
    manifest = dict(
        schema=1, generator='scripts/bolt_edge/gen.py', command='bolt_edge all',
        output_line='bolt_edge: <case> sink=0x%08x', sink='FNV-1a 32 over LE results for inputs',
        inputs=[f'0x{x:08x}' for x in INPUTS], noreturn_trigger=f'0x{NORETURN_TRIGGER:08x}',
        helpers=helpers,
        cases=[dict(name=c['name'], isa=c['isa'], area=c['area'], admission=c['admission'],
                    functions=c['functions'], note=c['note'],
                    expected_sink=f'0x{sink([u(c["model"](x)) for x in INPUTS]):08x}')
               for c in cases])
    return files, project, json.dumps(manifest, indent=1) + '\n'


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument('--check', action='store_true')
    a = ap.parse_args()
    files, project, manifest = render()
    targets = {APP / k: v for k, v in files.items()}
    targets[PROJECT] = project
    targets[MANIFEST] = manifest
    if a.check:
        stale = [str(p.relative_to(ROOT)) for p, v in targets.items()
                 if not p.exists() or p.read_text(encoding='utf-8').replace('\r\n', '\n') != v]
        if stale:
            sys.exit('stale generated files: ' + ', '.join(stale))
        print(f'up to date: {len(cases)} cases')
        return
    for p, v in targets.items():
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(v, encoding='utf-8', newline='\n')
    print(f'wrote {len(targets)} files; {len(cases)} cases')


if __name__ == '__main__':
    main()
