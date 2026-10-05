"""R28 reproducer: an A32 `ldr pc` inline table in an ARM function, in
different surroundings. Reports the parity of the re-emitted table words."""
import re
import subprocess
import sys
from pathlib import Path

TC = Path('/home/user/bolt-aarch32/build-atfe/bin')
OUT = Path(sys.argv[1] if len(sys.argv) > 1 else '/home/user/r28')
OUT.mkdir(parents=True, exist_ok=True)

SW = r'''
 .arm
 .global sw
 .type sw,%function
 .p2align 2
sw:
 and r2, r0, #3
 add r3, pc, #0
 ldr pc, [r3, r2, lsl #2]
 .word 1f, 2f, 3f, 4f
1:
 add r0, r0, #1
 bx lr
2:
 add r0, r0, #2
 bx lr
3:
 add r0, r0, #3
 bx lr
4:
 add r0, r0, #4
 bx lr
 .size sw,.-sw
'''
THUMB_START = r'''
 .syntax unified
 .text
 .thumb
 .global _start
 .type _start,%function
 .thumb_func
_start:
 blx sw
 b _start
 .size _start,.-_start
'''
ARM_START = r'''
 .syntax unified
 .text
 .arm
 .global _start
 .type _start,%function
_start:
 bl sw
 b _start
 .size _start,.-_start
'''
THUMB_HELPER = r'''
 .thumb
 .global th
 .type th,%function
 .thumb_func
th:
 adds r0, r0, #1
 bx lr
 .size th,.-th
'''
CASES = {
    'arm-only': ARM_START + SW,
    'thumb-caller': THUMB_START + SW,
    'thumb-before': THUMB_START + THUMB_HELPER + SW,
    'thumb-after': THUMB_START + SW + THUMB_HELPER,
}
LD = 'ENTRY(_start)\nSECTIONS {\n  . = 0x8000;\n  .text : { *(.text*) }\n}\n'


def run(cmd):
    p = subprocess.run([str(c) for c in cmd], cwd=OUT, capture_output=True, text=True)
    return p.returncode, p.stdout + p.stderr


bad = 0
for name, src in CASES.items():
    (OUT / f'{name}.s').write_text(src)
    (OUT / 'in.ld').write_text(LD)
    rc, log = run([TC / 'llvm-mc', '-arm-add-build-attributes', '-filetype=obj',
                   '-triple=armv7-unknown-linux-gnueabi', f'{name}.s', '-o', f'{name}.o'])
    assert rc == 0, log
    rc, log = run([TC / 'ld.lld', '--emit-relocs', '-T', 'in.ld', f'{name}.o', '-o', f'{name}.exe'])
    assert rc == 0, log
    for mode, extra in (('default', []), ('reverse', ['--reorder-blocks=reverse'])):
        rc, log = run([TC / 'llvm-bolt', f'{name}.exe', '-o', f'{name}.{mode}.bolt', '-lite=0', *extra])
        if rc:
            print(f'{name}/{mode}: llvm-bolt failed: {log[-300:]}')
            bad += 1
            continue
        _, nm = run([TC / 'llvm-nm', f'{name}.{mode}.bolt'])
        sw = next(int(l.split()[0], 16) for l in nm.splitlines() if l.endswith(' sw'))
        _, dis = run([TC / 'llvm-objdump', '-d', f'{name}.{mode}.bolt'])
        words = [int(m, 16) for m in re.findall(r'^\s*[0-9a-f]+:\s+(?:[0-9a-f]{2} ){4}\s*\.word\s+0x([0-9a-f]+)', dis, re.M)]
        words = [w for w in words if sw <= (w & ~1) < sw + 0x100]
        odd = [hex(w) for w in words if w & 1]
        print(f"{'FAIL' if odd or len(words) != 4 else 'ok  '} {name}/{mode}: sw@{sw:#x} words {[hex(w) for w in words]}")
        bad += bool(odd) or len(words) != 4
sys.exit(1 if bad else 0)
