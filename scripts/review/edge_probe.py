#!/usr/bin/env python3
"""Deep-review differential probe for the AArch32 BOLT backend (diagnostic).

Each case is a small static ARM Linux program whose `_start` calls the case
function `t(i)` for i = 0..N-1, folds the results into a hash and writes the
4 hash bytes to stdout. The original and every BOLT rewrite (several option
sets) run under qemu-arm user mode; outputs must be identical. A case may
also be *rejected* by BOLT (clean BOLT-ERROR, no output file): that is safe
and recorded separately from a wrong result or a crash.

QEMU is a debug aid here; this is a review instrument, not certification.

usage: edge_probe.py <toolchain bin> <out dir> [case-name-substring]
"""
import json
import subprocess
import sys
from pathlib import Path

TC = Path(sys.argv[1])
OUT = Path(sys.argv[2])
ONLY = sys.argv[3] if len(sys.argv) > 3 else ''
OUT.mkdir(parents=True, exist_ok=True)

DRIVER = '''
 .syntax unified
 .text
 .arm
 .global _start
 .type _start,%function
_start:
 mov r4, #0          @ i
 mov r5, #0          @ hash
1:
 mov r0, r4
 blx t
 mov r1, #31
 mla r5, r5, r1, r0
 add r4, r4, #1
 cmp r4, #{n}
 blt 1b
 sub sp, sp, #8
 str r5, [sp]
 mov r0, #1
 mov r1, sp
 mov r2, #4
 mov r7, #4
 svc #0
 mov r0, #0
 mov r7, #1
 svc #0
 b .
 .size _start,.-_start
'''


def fn(name, isa, body, glob=True):
    tf = ' .thumb_func\n' if isa == 'thumb' else ''
    g = f' .global {name}\n' if glob else ''
    return f' .p2align 2\n .{isa}\n{g} .type {name},%function\n{tf}{name}:\n{body}\n .size {name},.-{name}\n'


CASES = {}

# --- inline tables ---------------------------------------------------------
CASES['t32_tbb_8way'] = (12, fn('t', 'thumb', '''
 cmp r0, #7
 bhi 9f
 tbb [pc, r0]
2:
 .byte (10f-2b)/2, (11f-2b)/2, (12f-2b)/2, (13f-2b)/2, (14f-2b)/2, (15f-2b)/2, (16f-2b)/2, (17f-2b)/2
 .p2align 1
10: movs r0, #3
 bx lr
11: movs r0, #5
 bx lr
12: movs r0, #7
 bx lr
13: movs r0, #11
 bx lr
14: movs r0, #13
 bx lr
15: movs r0, #17
 bx lr
16: movs r0, #19
 bx lr
17: movs r0, #23
 bx lr
9: movs r0, #99
 bx lr'''))
CASES['t32_tbh_adr_base'] = (6, fn('t', 'thumb', '''
 push {r4, lr}
 and r4, r0, #3
 adr.w r2, 1f
 tbh [pc, r4, lsl #1]
1:
 .hword (20f-1b)/2, (21f-1b)/2, (22f-1b)/2, (23f-1b)/2
20: ldrh r0, [r2]
 pop {r4, pc}
21: ldrh r0, [r2, #2]
 adds r0, #100
 pop {r4, pc}
22: movs r0, #7
 pop {r4, pc}
23: movs r0, #9
 pop {r4, pc}'''))
CASES['a32_ldr_pc_table'] = (6, fn('t', 'arm', '''
 and r2, r0, #3
 add r3, pc, #8
 mov r1, r0
 mov r0, #0
 ldr pc, [r3, r2, lsl #2]
 .word 1f, 2f, 3f, 4f
1: add r0, r1, #10
 bx lr
2: add r0, r1, #20
 bx lr
3: add r0, r1, #30
 bx lr
4: add r0, r1, #40
 bx lr'''))
CASES['a32_load_jump_O0'] = (6, fn('t', 'arm', '''
 sub sp, sp, #8
 str r0, [sp]
 and r0, r0, #3
 add r1, pc, #4
 ldr r0, [r1, r0, lsl #2]
 mov pc, r0
 .word 1f, 2f, 3f, 4f
1: ldr r0, [sp]
 add r0, r0, #1
 b 5f
2: ldr r0, [sp]
 add r0, r0, #2
 b 5f
3: ldr r0, [sp]
 add r0, r0, #3
 b 5f
4: ldr r0, [sp]
 add r0, r0, #4
5: add sp, sp, #8
 bx lr'''))
# Table that reads its own base register in a case (data use of the base).
CASES['a32_table_base_read_in_case'] = (6, fn('t', 'arm', '''
 and r2, r0, #3
 add r3, pc, #4
 nop
 ldr pc, [r3, r2, lsl #2]
 .word 1f, 2f, 3f, 4f
1: ldr r0, [r3]
 sub r0, r0, r3
 bx lr
2: mov r0, #2
 bx lr
3: mov r0, #3
 bx lr
4: mov r0, #4
 bx lr'''))

# --- IT blocks / predication ----------------------------------------------
CASES['t32_it_pred_return_call'] = (8, fn('t', 'thumb', '''
 push {r4, lr}
 mov r4, r0
 cmp r0, #3
 itt lo
 addlo r0, r0, #50
 poplo {r4, pc}
 cmp r4, #5
 it eq
 bleq helper
 adds r0, r4, #1
 pop {r4, pc}''') + fn('helper', 'thumb', ' movs r0, #77\n bx lr'))
CASES['t32_it_cond_tail_call'] = (6, fn('t', 'thumb', '''
 cmp r0, #2
 it hi
 bhi.w helper
 adds r0, #1000
 bx lr''') + fn('helper', 'thumb', ' lsls r0, r0, #2\n bx lr'))
CASES['a32_cond_return_call'] = (6, fn('t', 'arm', '''
 push {r4, lr}
 mov r4, r0
 cmp r0, #2
 addls r0, r0, #9
 popls {r4, pc}
 cmp r4, #4
 bleq helper
 add r0, r0, r4
 pop {r4, pc}''') + fn('helper', 'arm', ' mov r0, #33\n bx lr'))

# --- interworking, literal pools, calls -------------------------------------
CASES['interwork_blx_both_ways'] = (5, fn('t', 'thumb', '''
 push {r4, lr}
 blx armf
 adds r0, #1
 bl thf
 pop {r4, pc}''') + fn('armf', 'arm', ' add r0, r0, r0, lsl #1\n bx lr') +
    fn('thf', 'thumb', ' push {lr}\n blx armf2\n pop {pc}') + fn('armf2', 'arm', ' eor r0, r0, #0x55\n bx lr'))
CASES['interwork_tail_bx_reg'] = (5, fn('t', 'thumb', '''
 movw r1, :lower16:armf
 movt r1, :upper16:armf
 bx r1''') + fn('armf', 'arm', ' add r0, r0, #123\n bx lr'))
CASES['thumb_literal_pool'] = (4, fn('t', 'thumb', '''
 ldr r1, =0x12345678
 ldr r2, =0x0badf00d
 add r0, r0, r1
 eors r0, r2
 bx lr
 .ltorg'''))
CASES['arm_literal_pool_mid_function'] = (4, fn('t', 'arm', '''
 ldr r1, 1f
 b 2f
1: .word 0x13579bdf
2: add r0, r0, r1
 ldr r2, =0x2468ace0
 eor r0, r0, r2
 bx lr
 .ltorg'''))
CASES['fnptr_table_in_data'] = (6, fn('t', 'arm', '''
 and r1, r0, #3
 ldr r2, =ptrs
 ldr r2, [r2, r1, lsl #2]
 push {lr}
 blx r2
 pop {pc}
 .ltorg''') + fn('fa', 'arm', ' add r0, r0, #1\n bx lr') + fn('fb', 'thumb', ' adds r0, #2\n bx lr') +
    fn('fc', 'arm', ' add r0, r0, #3\n bx lr') + fn('fd', 'thumb', ' adds r0, #4\n bx lr') +
    ' .data\n .p2align 2\nptrs: .word fa, fb, fc, fd\n .text\n')
CASES['movw_movt_thumb_fnptr'] = (4, fn('t', 'arm', '''
 push {lr}
 movw r1, :lower16:tf
 movt r1, :upper16:tf
 blx r1
 pop {pc}''') + fn('tf', 'thumb', ' adds r0, #9\n bx lr'))
CASES['literal_pool_thumb_fnptr'] = (4, fn('t', 'arm', '''
 push {lr}
 ldr r1, =tf
 blx r1
 pop {pc}
 .ltorg''') + fn('tf', 'thumb', ' adds r0, #11\n bx lr'))
CASES['data_ptr_thumb_interior_entry'] = (4, fn('t', 'arm', '''
 push {lr}
 ldr r2, =iptr
 ldr r2, [r2]
 blx r2
 pop {pc}
 .ltorg''') + fn('tf2', 'thumb', ' adds r0, #1\n .global tf2_mid\n .thumb_func\ntf2_mid:\n adds r0, #5\n bx lr') +
    ' .data\n .p2align 2\niptr: .word tf2_mid\n .text\n')
CASES['a32_mov_lr_pc_call'] = (4, fn('t', 'arm', '''
 push {r4, lr}
 mov lr, pc
 b helper
 add r0, r0, #1
 pop {r4, pc}''') + fn('helper', 'arm', ' add r0, r0, #40\n bx lr'))
CASES['noreturn_call_at_end'] = (3, fn('t', 'thumb', '''
 cmp r0, #100
 bhi 1f
 adds r0, #5
 bx lr
1: bl die''') + fn('die', 'thumb', ' movs r0, #1\n movs r7, #1\n svc #0\n b die'))
CASES['t32_cbz_cbnz'] = (6, fn('t', 'thumb', '''
 cbz r0, 1f
 subs r1, r0, #3
 cbnz r1, 2f
 movs r0, #30
 bx lr
1: movs r0, #10
 bx lr
2: adds r0, #20
 bx lr'''))
CASES['ldrex_strex_local_loop'] = (4, fn('t', 'arm', '''
 ldr r2, =cell
1: ldrex r1, [r2]
 add r1, r1, r0
 strex r3, r1, [r2]
 cmp r3, #0
 bne 1b
 mov r0, r1
 bx lr
 .ltorg''') + ' .data\n .p2align 2\ncell: .word 5\n .text\n')
CASES['recursion_thumb'] = (6, fn('t', 'thumb', '''
 push {r4, lr}
 cmp r0, #1
 bls 1f
 mov r4, r0
 subs r0, #1
 bl t
 adds r0, r4
 pop {r4, pc}
1: movs r0, #1
 pop {r4, pc}'''))
# Identical functions (ICF) that both contain an inline table.
_tbl = '''
 and r2, r0, #3
 add r3, pc, #4
 nop
 ldr pc, [r3, r2, lsl #2]
 .word 1f, 2f, 3f, 4f
1: mov r0, #1
 bx lr
2: mov r0, #2
 bx lr
3: mov r0, #3
 bx lr
4: mov r0, #4
 bx lr'''
CASES['icf_twin_tables'] = (6, fn('t', 'arm', '''
 push {r4, lr}
 mov r4, r0
 bl ta
 mov r1, r0
 mov r0, r4
 push {r1}
 bl tb
 pop {r1}
 add r0, r0, r1, lsl #4
 pop {r4, pc}''') + fn('ta', 'arm', _tbl) + fn('tb', 'arm', _tbl))
CASES['thumb_conditional_tail_other_mode'] = (5, fn('t', 'thumb', '''
 cmp r0, #2
 bhs.w armt
 adds r0, #7
 bx lr''') + fn('armt', 'arm', ' mov r0, r0, lsl #3\n bx lr'))


# --- R27 extensions ---------------------------------------------------------
# Narrow Thumb branches (cbz 0..126 forward, b<cond>.n +-256, b.n +-2K) that
# block reordering can push out of range or make backward.
_pad = lambda k, ins: ''.join(f' {ins}\n' for _ in range(k))
CASES['t32_narrow_branch_range'] = (40, fn('t', 'thumb', ' cbz r0, 1f\n' + _pad(28, 'adds r0, #1') +
    ' b 4f\n1:\n movs r0, #77\n b 3f\n4:\n cmp r0, #30\n beq 2f\n' + _pad(100, 'adds r0, #3') +
    ' b 3f\n2:\n' + _pad(60, 'adds r0, #5') + '3:\n bx lr'))
# Identical Thumb twins and identical ARM twins reached only through a data
# table (ICF folds each pair; the data words must keep the right ISA bit).
_tw = lambda isa: (' adds r0, r0, #9\n lsls r0, r0, #1\n bx lr' if isa == 'thumb'
                   else ' add r0, r0, #9\n lsl r0, r0, #2\n bx lr')
CASES['icf_twins_via_data_table'] = (8, fn('t', 'arm', '''
 push {r4, lr}
 and r1, r0, #3
 ldr r2, =twins
 ldr r2, [r2, r1, lsl #2]
 blx r2
 pop {r4, pc}
 .ltorg''') + fn('ta', 'thumb', _tw('thumb')) + fn('tb', 'thumb', _tw('thumb')) +
    fn('aa', 'arm', _tw('arm')) + fn('ab', 'arm', _tw('arm')) +
    ' .data\n .p2align 2\ntwins: .word ta, ab, tb, aa\n .text\n')
# A hot table branch whose cases are cold: under the split option set the
# cases move to the cold fragment, far from the table.
CASES['t32_tbh_cold_cases_split'] = (6, fn('t', 'thumb', '''
 push {r4, lr}
 and r4, r0, #3
 cmp r0, #4
 bhs 9f
 tbh [pc, r4, lsl #1]
1:
 .hword (20f-1b)/2, (21f-1b)/2, (22f-1b)/2, (23f-1b)/2
20: movs r0, #31
 pop {r4, pc}
21: movs r0, #37
 pop {r4, pc}
22: movs r0, #41
 pop {r4, pc}
23: movs r0, #43
 pop {r4, pc}
9: adds r0, #50
 pop {r4, pc}'''))

OPTIONS = {
    'default': [],
    'reverse': ['--reorder-blocks=reverse'],
    'icf': ['-icf=all', '--reorder-functions=random'],
    'far': ['--pad-funcs-before=t:0x1100000'],
    # R27: only t's entry is sampled, so every other block of t is cold and
    # moves to t.cold (tables and their cases end up in different fragments).
    'split': ['-data=prof.fdata', '-split-functions', '-split-all-cold'],
    # R27: as 'split', on fill.exe: a profiled 1.1 MB filler function sits
    # between hot t and t.cold, so cross-fragment branches exceed Thumb
    # b<cond>.w (+-1 MB) but not b.w/bl (+-16 MB). (--pad-funcs-before cannot
    # model this: the emitter pads every fragment, LongJmp only the first.)
    'split-fill': ['-data=prof.fdata', '-split-functions', '-split-all-cold'],
    # R27: instrumented output must still compute the same results.
    'instrument': ['--instrument', '--instrument-calls=false',
                   '--arm-instrumentation-contract=privileged-single-core-no-fiq',
                   '--instrumentation-sleep-time=1',
                   '--runtime-instrumentation-lib=' + str(TC.parent / 'bolt-rt-baremetal-arm/libbolt_rt_baremetal.a')],
}

NL = chr(10)
# Never executed; only its size matters (ARM nops, 1.1 MB).
FILLER = (' .p2align 2' + NL + ' .arm' + NL + ' .global fill' + NL + ' .type fill,%function' + NL +
          'fill:' + NL + ' .rept 280000' + NL + ' nop' + NL + ' .endr' + NL + ' bx lr' + NL +
          ' .size fill,.-fill' + NL)


def sh(cmd, cwd, timeout=60):
    p = subprocess.run([str(x) for x in cmd], cwd=cwd, capture_output=True, timeout=timeout)
    return p.returncode, p.stdout, p.stderr.decode(errors='replace')


results = []
for name, (n, body) in CASES.items():
    if ONLY and ONLY not in name:
        continue
    d = OUT / name
    d.mkdir(exist_ok=True)
    (d / 'in.s').write_text(DRIVER.replace('{n}', str(n)) + body)
    (d / 'in.ld').write_text('ENTRY(_start)\nSECTIONS {\n  . = 0x10000;\n  .text : { *(.text*) }\n'
                             '  . = ALIGN(0x1000);\n  .data : { *(.data*) }\n}\n')
    (d / 'fill.s').write_text(DRIVER.replace('{n}', str(n)) + body + FILLER)
    bad = None
    for stem in ('in', 'fill'):
        rc, _, err = sh([TC / 'llvm-mc', '-triple=armv7-unknown-linux-gnueabi', '-arm-add-build-attributes',
                         '-filetype=obj', f'{stem}.s', '-o', f'{stem}.o'], d)
        if not rc:
            rc, _, err = sh([TC / 'ld.lld', '--emit-relocs', '-static', '-T', 'in.ld', f'{stem}.o',
                             '-o', f'{stem}.exe'], d)
        if rc:
            bad = err[-300:]
            break
    if bad:
        results.append(dict(case=name, opt='-', verdict='FIXTURE', detail=bad)); continue
    (d / 'prof.fdata').write_text('0 [unknown] 0 1 t 0 0 1000' + chr(10) +
                                  '0 [unknown] 0 1 fill 0 0 1000' + chr(10))
    rc, ref, err = sh(['qemu-arm', 'in.exe'], d)
    if rc or len(ref) != 4:
        results.append(dict(case=name, opt='-', verdict='FIXTURE', detail=f'original rc={rc} {err[-200:]}')); continue
    for opt, extra in OPTIONS.items():
        outf = d / f'{opt}.bolt'
        outf.unlink(missing_ok=True)
        try:
            exe = 'fill.exe' if opt == 'split-fill' else 'in.exe'
            rc, _, log = sh([TC / 'llvm-bolt', exe, '-o', outf.name, '--no-huge-pages', '-lite=0', *extra], d, 300)
        except subprocess.TimeoutExpired:
            results.append(dict(case=name, opt=opt, verdict='BOLT-HANG')); continue
        (d / f'{opt}.log').write_text(log)
        if rc != 0:
            err_line = next((l for l in log.splitlines() if 'ERROR' in l or 'Assertion' in l or 'UNREACHABLE' in l), log[-200:])
            verdict = 'REJECTED' if 'BOLT-ERROR' in log and rc in (1,) else 'BOLT-CRASH'
            results.append(dict(case=name, opt=opt, verdict=verdict, detail=err_line.strip()[:200])); continue
        try:
            rc2, got, err2 = sh(['qemu-arm', outf.name], d, 30)
        except subprocess.TimeoutExpired:
            results.append(dict(case=name, opt=opt, verdict='RUN-HANG')); continue
        if got == ref and rc2 == 0:
            results.append(dict(case=name, opt=opt, verdict='OK'))
        else:
            results.append(dict(case=name, opt=opt, verdict='WRONG',
                                detail=f'ref={ref.hex()} got={got.hex()} rc={rc2} {err2[-160:]}'))

(OUT / 'results.json').write_text(json.dumps(results, indent=1) + '\n')
from collections import Counter
print(Counter(r['verdict'] for r in results))
for r in results:
    if r['verdict'] != 'OK':
        print(f"{r['verdict']:10} {r['case']:36} {r['opt']:8} {r.get('detail', '')[:150]}")
