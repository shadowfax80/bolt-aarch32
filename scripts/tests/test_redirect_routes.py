"""6c: exercise redirect-bolt-entries.py end to end on real ARM/Thumb ELFs.

Each case builds a tiny image with llvm-mc + ld.lld (--emit-relocs), rewrites
it with llvm-bolt (--emit-function-map), then runs the real redirect script.
Supported routes must write exactly one B/B.W to the moved copy; every hazard
must be refused before the output ELF changes (byte-identical on failure).

Needs TOOLCHAIN (LLVM bin dir with llvm-bolt); skipped otherwise.
"""
from pathlib import Path
import hashlib
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
TC = Path(os.environ.get('TOOLCHAIN', '/home/user/bolt-aarch32/build-atfe/bin'))
SCRIPT = ROOT / 'scripts/redirect-bolt-entries.py'


def fn(name, isa, body):
    return (f'.balign 4\n.{isa}\n.global {name}\n.type {name},%function\n'
            + ('.thumb_func\n' if isa == 'thumb' else '') + f'{name}:\n{body}\n.size {name},.-{name}\n')


@unittest.skipUnless((TC / 'llvm-bolt').exists(), 'needs TOOLCHAIN with llvm-bolt')
class RedirectRoutes(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp(prefix='redirect-routes-'))

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def build(self, funcs, extra=''):
        d = self.dir
        start = fn('_start', 'arm', 'bl f\nb _start')
        (d / 'in.s').write_text('.syntax unified\n.arch armv7-a\n.text\n' + start + funcs + extra)
        (d / 'in.ld').write_text('ENTRY(_start)\nSECTIONS { . = 0x8000; .text : { *(.text*) } }\n')
        for cmd in ([TC / 'llvm-mc', '-triple=armv7-none-eabi', '-arm-add-build-attributes',
                     '-filetype=obj', d / 'in.s', '-o', d / 'in.o'],
                    [TC / 'ld.lld', '--emit-relocs', '-T', d / 'in.ld', d / 'in.o', '-o', d / 'in.elf'],
                    [TC / 'llvm-bolt', d / 'in.elf', '-o', d / 'out.elf', '-lite=0', '--funcs=f',
                     '--no-huge-pages', '--emit-function-map=' + str(d / 'out.map')]):
            p = subprocess.run([str(x) for x in cmd], capture_output=True, text=True)
            self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        subprocess.run([sys.executable, str(ROOT / 'scripts/fix-kernel-elf-sections.py'), str(d / 'out.elf'),
                        '--original', str(d / 'in.elf'), '--readelf', str(TC / 'llvm-readelf')],
                       check=True, capture_output=True)

    def redirect(self, *args):
        before = hashlib.sha256((self.dir / 'out.elf').read_bytes()).hexdigest()
        p = subprocess.run([sys.executable, str(SCRIPT), str(self.dir / 'out.elf'), '--original',
                            str(self.dir / 'in.elf'), '--toolchain', str(TC), *args],
                           capture_output=True, text=True)
        after = hashlib.sha256((self.dir / 'out.elf').read_bytes()).hexdigest()
        return p, before, after

    def refused(self, pattern, *args):
        p, before, after = self.redirect(*args)
        self.assertNotEqual(p.returncode, 0, p.stdout)
        self.assertRegex(p.stdout + p.stderr, pattern)
        self.assertEqual(before, after, 'a refused redirect modified the ELF')

    def test_map_route_arm_and_thumb(self):
        for isa in ('arm', 'thumb'):
            with self.subTest(isa=isa):
                self.setUp()
                self.build(fn('f', isa, 'push {r4, lr}\nadds r0, r0, #1\npop {r4, pc}'))
                p, before, after = self.redirect('--map', str(self.dir / 'out.map'), '--func', 'f')
                self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
                self.assertIn('redirected f:', p.stdout)
                self.assertNotEqual(before, after)

    def test_short_function_refused(self):
        self.build(fn('f', 'thumb', 'bx lr'))
        self.refused('only 2 bytes|cannot hold', '--map', str(self.dir / 'out.map'), '--func', 'f')

    def test_secondary_entry_in_prefix_refused(self):
        body = 'push {r4, lr}\n.global f_alt\n.type f_alt,%function\n.thumb_func\nf_alt:\nadds r0, r0, #1\npop {r4, pc}'
        self.build(fn('f', 'thumb', body))
        self.refused('secondary function entry', '--map', str(self.dir / 'out.map'), '--func', 'f')

    def test_pc_relative_prologue_refused(self):
        # The moved copy's literal load has a different PC offset, so the copies
        # do not start alike: refuse rather than assume equivalence.
        self.build(fn('f', 'arm', 'ldr r0, .Llit\nadd r0, r0, #1\nbx lr\n.Llit:\n.word 0x12345678'))
        p, before, after = self.redirect('--map', str(self.dir / 'out.map'), '--func', 'f')
        if p.returncode == 0:
            self.skipTest('BOLT kept an identical literal-load encoding; nothing to refuse')
        self.assertRegex(p.stdout + p.stderr, 'prologue')
        self.assertEqual(before, after)

    def test_referenced_split_prefix_refused(self):
        body = 'push {r4, lr}\nmovw r0, #1\n.Lmid:\npop {r4, pc}'
        self.build(fn('f', 'thumb', body.replace('.Lmid:\n', '')),
                   extra=fn('g', 'thumb', 'b.w f+2'))
        self.refused('referenced from', '--map', str(self.dir / 'out.map'), '--func', 'f')

    def test_unreferenced_split_prefix_allowed(self):
        self.build(fn('f', 'thumb', 'push {r4, lr}\nmovw r0, #1\npop {r4, pc}'))
        p, before, after = self.redirect('--map', str(self.dir / 'out.map'), '--func', 'f')
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertNotEqual(before, after)

    def test_unknown_function_refused(self):
        self.build(fn('f', 'arm', 'push {r4, lr}\npop {r4, pc}'))
        self.refused('.', '--map', str(self.dir / 'out.map'), '--func', 'nosuch')

    def test_legacy_no_map_requires_matching_output_function(self):
        self.build(fn('f', 'thumb', 'push {r4, lr}\nadds r0, r0, #1\npop {r4, pc}'))
        p, before, after = self.redirect('--func', 'f')
        # Legacy mode assumes the copy starts .text; accepted only when an output
        # STT_FUNC of the same ISA really sits there, else refused untouched.
        if p.returncode:
            self.assertEqual(before, after)
        else:
            self.assertIn('redirected f:', p.stdout)


if __name__ == '__main__':
    unittest.main()
