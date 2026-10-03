#!/usr/bin/env python3
"""Build a fixed-load Pi fixture that enters BOLT's actual runtime startup."""
import argparse
import json
from pathlib import Path
import re
import struct
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
from profile_identity import elf_metadata, sha256


def require(value, message):
    if not value:
        raise ValueError(message)


def address_offset(sections, address, size=4):
    matches = [s for s in sections if 'physical' in s and
               s['address'] <= address and address + size <= s['address'] + s['size']]
    require(len(matches) == 1, 'ambiguous/unloaded address')
    s = matches[0]
    return s['offset'] + address - s['address']


def trampoline(blob, sections, address):
    off = address_offset(sections, address, 12)
    a, b, c = struct.unpack_from('<III', blob, off)
    require(a & 0xfff0f000 == 0xe300c000 and b & 0xfff0f000 == 0xe340c000
            and c == 0xe12fff1c, 'expected ARM MOVW/MOVT/BX startup route')
    imm = lambda x: ((x >> 4) & 0xf000) | (x & 0xfff)
    return imm(a) | (imm(b) << 16)


def check_image(elf, raw, row):
    blob = elf.read_bytes()
    sections, symbols = elf_metadata(blob)
    loaded = [s for s in sections if 'physical' in s]
    base = min(s['physical'] for s in loaded)
    end = max(s['physical'] + s['size'] for s in loaded)
    require(base == 0x8000 and end < 0x700000, 'wrong fixed-load region')
    data = raw.read_bytes()
    require(len(data) == end - base, 'wrong raw image size')
    for s in loaded:
        require(s['address'] == s['physical'], 'fixture requires V=P')
        require(data[s['address'] - base:s['address'] - base + s['size']] ==
                blob[s['offset']:s['offset'] + s['size']], 'ELF/raw mismatch')
    entry = struct.unpack_from('<I', blob, 24)[0]
    require(entry == row['entry'], 'ELF entry changed')
    require(struct.unpack_from('<I', blob, address_offset(sections, row['boot_pointer']))[0]
            == entry, 'boot shim does not enter actual ELF entry')
    if row['instrumented']:
        require(entry % 4 == 0 and trampoline(blob, sections, entry) == row['trampoline'],
                'wrong ARM runtime entry route')
        require(trampoline(blob, sections, row['trampoline']) == row['thumb_entry'],
                'wrong Thumb destination/ISA bit')
        require(row['thumb_entry'] & 1, 'missing Thumb bit')
        require(row['thumb_entry'] != row['original_thumb_entry'], 'entry was not rewritten')
    return sections, symbols


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', required=True, type=Path)
    parser.add_argument('--toolchain', required=True, type=Path)
    args = parser.parse_args()
    tc = args.toolchain.resolve()
    args.out.mkdir(parents=True, exist_ok=True)
    out = Path(tempfile.mkdtemp(prefix='build-', dir=args.out.resolve()))

    def run(name, cmd):
        p = subprocess.run([str(x) for x in cmd], capture_output=True, text=True)
        (out / (name + '.log')).write_text(p.stdout + p.stderr)
        require(p.returncode == 0, name + ': ' + (p.stdout + p.stderr)[-2400:])
        return p.stdout

    (out / 'start.s').write_text('''.syntax unified
.arch armv7-a
.section .text.boot,"ax",%progbits
.arm
.global boot_shim
.type boot_shim,%function
boot_shim:
 cpsid if
 ldr sp,=0x00800000
 // Arm the watchdog before entering the route, including faulty payloads.
 ldr r0,=0xfe100000
 ldr r1,=0x5a030000
 str r1,[r0,#0x24]
 ldr r1,[r0,#0x1c]
 bic r1,r1,#0xff000000
 bic r1,r1,#0x30
 orr r1,r1,#0x20
 orr r1,r1,#0x5a000000
 str r1,[r0,#0x1c]
 movw r4,#0x5678
 movt r4,#0x1234
 mov r0,#0xa0000000
 msr APSR_nzcvq,r0
 ldr r12,boot_entry
 bx r12
.size boot_shim,.-boot_shim
.global boot_entry
.type boot_entry,%object
boot_entry: .word _start
.size boot_entry,4
.ltorg
.text
.thumb
.balign 4
.global _start
.type _start,%function
.thumb_func
_start:
 mov.w r0,r4
 mrs r1,cpsr
 mov r2,sp
 push {r4,lr}
 bl report_entry
 pop {r4,pc}
.size _start,.-_start
.arm
.balign 4
.global report_entry
.type report_entry,%function
report_entry:
 mov r3,lr
 b report
.size report_entry,.-report_entry
.data
.balign 4
.global counter_address
.type counter_address,%object
counter_address: .word 0
.size counter_address,4
''')
    (out / 'main.c').write_text('''#include <stdint.h>
extern volatile uint32_t counter_address;
#define REG(a) (*(volatile uint32_t *)(a))
static void text(const char *s) {
 while (*s) { while (REG(0xfe201018u)&32) {} REG(0xfe201000u)=*s++; }
}
static void hex(uint32_t v) {
 const char *digits="0123456789abcdef";
 char b[9];
 for (unsigned i=0;i<8;++i) b[i]=digits[(v>>(28-i*4))&15];
 b[8]=0; text(b);
}
void report(uint32_t marker, uint32_t cpsr, uint32_t sp, uint32_t link) {
 uint32_t count=counter_address ? *(volatile uint32_t *)counter_address : 1;
 uint32_t high=counter_address ? *(volatile uint32_t *)(counter_address+4) : 0;
 uint32_t mpidr;
 __asm__ volatile("mrc p15,0,%0,c0,c0,5":"=r"(mpidr));
 text("START_STATE "); hex(marker); text(" "); hex(cpsr); text(" "); hex(sp);
 text(" "); hex(mpidr); text(" "); hex(count); text(" "); hex(high);
 text(" "); hex(link); text("\\r\\n");
 // Thumb MRS reads the current flags/control fields with T masked out.
 // The Thumb BLX return link independently records the caller's ISA.
 if (marker==0x12345678 && (cpsr&0xf00000c0)==0xa00000c0 && (link&1) &&
     ((cpsr&31)==0x13 || (cpsr&31)==0x1a || (cpsr&31)==0x1f) &&
     sp==0x00800000 && (mpidr&0xffffff)==0 && count==1 && high==0)
  text("BOLT_THUMB_START PASS\\r\\n");
 else text("BOLT_THUMB_START FAIL\\r\\n");
 while (REG(0xfe201018u)&8) {}
 for (;;) __asm__ volatile("wfe");
}
''')
    (out / 'link.ld').write_text('ENTRY(_start)\nSECTIONS { . = 0x8000; .text : { *(.text.boot) *(.text*) } .rodata : { *(.rodata*) } .data : { *(.data*) } /DISCARD/ : { *(.ARM.exidx*) *(.ARM.extab*) *(.comment) } }\n')
    run('mc', [tc/'llvm-mc', '-triple=armv7-none-eabi', '-arm-add-build-attributes',
               '-filetype=obj', out/'start.s', '-o', out/'start.o'])
    run('compile', [tc/'clang', '--target=arm-none-eabi', '-march=armv7-a', '-marm',
                    '-mfloat-abi=soft', '-ffreestanding', '-fno-builtin', '-fno-stack-protector',
                    '-fno-unwind-tables', '-fno-asynchronous-unwind-tables', '-O2',
                    '-c', out/'main.c', '-o', out/'main.o'])
    run('link', [tc/'ld.lld', '--emit-relocs', '-T', out/'link.ld', out/'start.o',
                 out/'main.o', '-o', out/'baseline.elf'])
    original = (out/'baseline.elf').read_bytes()
    _, syms = elf_metadata(original)
    objects = {s['name']:s['address'] for s in syms}
    rows = {}
    for name, options in [('baseline', None), ('normal', []), ('reverse', ['--reorder-blocks=reverse'])]:
        elf = out/(name+'.elf')
        if options is not None:
            log = run(name+'-instrument', [tc/'llvm-bolt', out/'baseline.elf', '-o', elf,
                '--no-huge-pages', '-lite=0', '--instrument', '--instrument-calls=false',
                '--arm-instrumentation-contract=privileged-single-core-no-fiq',
                '--instrumentation-sleep-time=1', '--runtime-instrumentation-lib='+str(tc.parent/'bolt-rt-baremetal-arm/libbolt_rt_baremetal.a'),
                '--funcs=_start', *options])
            require(re.findall(r'Total number of counters: (\d+)', log) == ['1'], 'expected one entry counter')
        before = elf.read_bytes()
        (out/(name+'.unpatched.elf')).write_bytes(before)
        blob = bytearray(before)
        sections, syms = elf_metadata(blob)
        symbols = {s['name']:s['address'] | int(s['thumb']) for s in syms}
        entry = struct.unpack_from('<I', blob, 24)[0]
        patches = []
        for address, value in [(objects['boot_entry'], entry), (objects['counter_address'],
                next(s['address'] for s in sections if s['name']=='.bolt.instr.counters') if options is not None else 0)]:
            offset = address_offset(sections, address)
            patches.append(dict(address=address, before=struct.unpack_from('<I', blob, offset)[0], after=value))
            struct.pack_into('<I', blob, offset, value)
        elf.write_bytes(blob)
        row = dict(instrumented=options is not None, entry=entry, boot_pointer=objects['boot_entry'],
                   original_thumb_entry=objects['_start']|1, patches=patches,
                   thumb_size=next(s['size'] for s in syms if s['name']=='_start'),
                   unmodified_bolt_sha256=sha256(out/(name+'.unpatched.elf')))
        if options is not None:
            row.update(trampoline=symbols['__bolt_start_trampoline'], thumb_entry=symbols['_start'])
        run(name+'-objcopy', [tc/'llvm-objcopy', '-O', 'binary', elf, out/(name+'.bin')])
        check_image(elf, out/(name+'.bin'), row)
        rows[name] = row
    files = {p.name:sha256(p) for p in out.iterdir() if p.is_file()}
    manifest = dict(schema=1, kind='pi-thumb-startup', variants=rows, files=files,
                    tool_sha256=sha256(tc/'llvm-bolt'), builder_sha256=sha256(Path(__file__)),
                    scope='Actual ARM runtime entry and trampoline to rewritten Thumb entry; one exact counter, Thumb return link, NZCV, R4, SP and quiet core-zero contract. Boot shim changes only the entry pointer and counter metadata; ELF entry and emitted code are retained.')
    (out/'build.json').write_text(json.dumps(manifest, indent=2)+'\n')
    print(out, flush=True)


if __name__ == '__main__':
    main()
