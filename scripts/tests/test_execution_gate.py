"""Negative gates for redirect selection, artifacts and observed execution."""
import importlib.util
import contextlib
import io
import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / 'scripts'), str(ROOT / 'scripts/pi4')]
import full_image_verify as gate
import full_image_build as builder
from bolt_dump_reassemble import checksum

redirect = builder.redirect


class ExecutionGateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.out = Path(self.temp.name)

    def test_all_missing_selection_never_redirects_everything(self):
        entries = {'kept': (0x1000, 0x2000, 8)}
        with self.assertRaises(SystemExit):
            redirect.select_entries(entries, 'missing', allow_missing=True)
        self.assertEqual(redirect.select_entries(entries, 'kept,missing', True), entries)
        for names in ('', 'kept,kept', 'kept,'):
            with self.subTest(names=names), self.assertRaises(SystemExit):
                redirect.select_entries(entries, names)
        with self.assertRaises(SystemExit):
            redirect.select_entries({}, None)

    def test_redirect_bounds(self):
        self.assertEqual(redirect.bounded_offset((0x1000, 16, 8), 0x1004, 4, 24), 20)
        for address, length, file_size in ((0xffe, 4, 24), (0x1006, 4, 24), (0x1004, 4, 23), (0x1000, 0, 24)):
            with self.subTest(address=address), self.assertRaises(SystemExit):
                redirect.bounded_offset((0x1000, 16, 8), address, length, file_size)

    def test_invalid_map_ranges(self):
        path = self.out / 'map'
        for row in ('f -1 2000 8', 'f 1000 100000000 8', 'f 1000 2000 0', 'f 1000 2000 8\nf 1000 2000 8'):
            path.write_text(row)
            with self.subTest(row=row), self.assertRaises(SystemExit):
                redirect.read_map(path)

    def test_elf_function_state_bit(self):
        text = ' 1: 00001001 8 FUNC GLOBAL DEFAULT 1 thumb\n 2: 00002000 4 FUNC LOCAL DEFAULT 1 arm\n'
        with patch.object(redirect.subprocess, 'run') as run:
            run.return_value.stdout = text
            self.assertEqual(redirect.function_symbols('readelf', 'image'), {'thumb': [(0x1000, 8, True)], 'arm': [(0x2000, 4, False)]})

    def test_independent_branch_decode(self):
        for thumb, source, target in ((True, 0x1002, 0x9004), (True, 0x9002, 0x1000), (False, 0x1000, 0x9004), (False, 0x9000, 0x1000)):
            branch = redirect.branch_bytes(thumb, source, target)
            self.assertEqual(gate.branch_target(branch, source, thumb), target)
        for branch, thumb in ((b'\0' * 4, True), (b'\0' * 4, False), (struct.pack('<I', 0xeb000001), False)):
            with self.assertRaises(ValueError):
                gate.branch_target(branch, 0x1000, thumb)

    def artifact_fixture(self):
        source, target = 0x80001000, 0x80002000
        branch = redirect.branch_bytes(False, source, target)
        self.sections = [dict(name='.bolt.org.text', address=source, physical=0x1000, offset=0, size=4, flags=6),
                         dict(name='.text', address=target, physical=0x2000, offset=8, size=4, flags=6)]
        for name, data in {'baseline.elf': b'original', 'baseline.bin': b'original code',
                           'baseline_full.elf': branch + b'gap!' + b'body',
                           'baseline_full.bin': branch + b'\0' * (4096 - 4) + b'body', 'full.funcmap': b'map'}.items():
            (self.out / name).write_bytes(data)
        row = dict(name='function', input=source, output=target, output_size=4)
        manifest = dict(schema=1, input_sha256=gate.sha256(self.out / 'baseline.elf'),
                        baseline_binary_sha256=gate.sha256(self.out / 'baseline.bin'), elf_sha256=gate.sha256(self.out / 'baseline_full.elf'),
                        binary_sha256=gate.sha256(self.out / 'baseline_full.bin'), map_sha256=gate.sha256(self.out / 'full.funcmap'),
                        emitted=[row], redirected=[dict(**row, thumb=False, branch_hex=branch.hex())])
        return manifest

    def test_stale_artifact_rejected(self):
        manifest = self.artifact_fixture()
        with patch.object(gate, 'loadable_sections', return_value=self.sections):
            gate.check_artifacts(self.out, manifest)
            (self.out / 'baseline.bin').write_bytes(b'other build')
            with self.assertRaisesRegex(ValueError, 'does not match'):
                gate.check_artifacts(self.out, manifest)

    def test_missing_redirect_even_with_consistent_hash_rejected(self):
        manifest = self.artifact_fixture()
        data = bytearray((self.out / 'baseline_full.bin').read_bytes()); data[:4] = b'old!'
        (self.out / 'baseline_full.bin').write_bytes(data)
        manifest['binary_sha256'] = gate.sha256(self.out / 'baseline_full.bin')
        with patch.object(gate, 'loadable_sections', return_value=self.sections), self.assertRaisesRegex(ValueError, 'redirect bytes'):
            gate.check_artifacts(self.out, manifest)

    def test_full_gate_rejects_stale_or_unbound_profile(self):
        manifest = self.artifact_fixture()
        profile = self.out / 'profile.fdata'
        sidecar = self.out / 'profile.fdata.manifest.json'
        profile.write_text('no_lbr\n1 function 0 1\n')
        identity = dict(schema=1, kind='bolt-profile', verified_binding=True,
                        profile_sha256=gate.sha256(profile), source_elf_sha256=gate.sha256(self.out / 'baseline.elf'))
        sidecar.write_text(json.dumps(identity))
        manifest['profile'] = dict(profile_sha256=gate.sha256(profile), manifest_sha256=gate.sha256(sidecar))
        with patch.object(gate, 'loadable_sections', return_value=self.sections):
            gate.check_artifacts(self.out, manifest)
            identity['verified_binding'] = False
            sidecar.write_text(json.dumps(identity))
            manifest['profile']['manifest_sha256'] = gate.sha256(sidecar)
            with self.assertRaisesRegex(ValueError, 'unbound'):
                gate.check_artifacts(self.out, manifest)
            profile.write_text('changed profile')
            with self.assertRaisesRegex(ValueError, 'changed after'):
                gate.check_artifacts(self.out, manifest)

    def sample_fixture(self, pc=0x2001, kept=1, taken=1, address=0x4000):
        manifest = dict(sample_buffer=dict(address=0x4000, size=64), redirected=[dict(name='function', output=0x2000, output_size=8, thumb=True)])
        raw = struct.pack('<I', pc) + b'\0' * 60
        text = ''.join(f'bolt_bench: {name} sink=0x1\n' for name in gate.parse_results.__globals__['EXPECTED_WORKLOADS'])
        text += f'bolt_sample: {kept} samples ({taken} taken) buf=0x{address:x} bytes=0x{kept*4:x}\n'
        text += f'BOLT_DUMP_BEGIN addr=00004000 size=00000040\nBOLT_DUMP seq=00000000 off=00000000 len=0040 crc={checksum(raw):08x} data={raw.hex()}\nBOLT_DUMP_END seq=00000001 total=00000040\n'
        return text, manifest

    def test_pc_execution_observed(self):
        text, manifest = self.sample_fixture()
        result = gate.execution_evidence(text, manifest, ['function'])
        self.assertEqual(result['redirected_coverage'][0]['pc_samples'], 1)

    def test_original_pc_wrong_isa_or_no_pc_fails(self):
        for pc in (0x1001, 0x2000, 0x3001):
            text, manifest = self.sample_fixture(pc)
            with self.subTest(pc=pc), self.assertRaisesRegex(ValueError, 'no rewritten execution'):
                gate.execution_evidence(text, manifest, ['function'])

    def test_truncated_saturated_misplaced_or_corrupt_dump_fails(self):
        cases = [self.sample_fixture(kept=1, taken=2), self.sample_fixture(address=0x4004),
                 self.sample_fixture(kept=16, taken=16)]
        text, manifest = self.sample_fixture()
        cases += [(text.replace('BOLT_DUMP_END', 'missing_end'), manifest),
                  (text.replace('data=', 'data=ff'), manifest),
                  (text.replace('off=00000000', 'off=00000001'), manifest)]
        for text, manifest in cases:
            with self.subTest(text=text[-120:]), self.assertRaises(ValueError):
                gate.execution_evidence(text, manifest, ['function'])

    def test_section_size_mismatch_fails_restoration(self):
        original, candidate = self.out/'original', self.out/'candidate'
        original.write_bytes(b'abcd'); candidate.write_bytes(b'abcd')
        with patch.object(builder.redirect.fix, 'sections', side_effect=[{'.text': (0x1000, 0, 4)}, {'.bolt.org.text': (0x1000, 0, 3)}]), self.assertRaises(ValueError):
            builder.check_restoration(original, candidate, self.out)

    def test_late_invalid_redirect_does_not_modify_elf(self):
        original, candidate, mapping = self.out/'original', self.out/'candidate', self.out/'map'
        original.write_bytes(b'01234567' * 4)
        data = b'01234567' * 16
        candidate.write_bytes(data)
        mapping.write_text('first 1000 2000 8\nsecond 1008 2008 ff\n')
        before = {'.text': (0x1000, 0, 32)}
        after = {'.bolt.org.text': (0x1000, 0, 32), '.text': (0x2000, 64, 32)}
        nm = {'first': (0x1000, 8), 'second': (0x1008, 8)}
        input_funcs = {'first': [(0x1000, 8, True)], 'second': [(0x1008, 8, True)]}
        output_funcs = {'first': [(0x2000, 8, True)], 'second': [(0x2008, 8, True)]}
        with patch.object(sys, 'argv', ['redirect', str(candidate), '--original', str(original), '--map', str(mapping)]), \
             patch.object(redirect.fix, 'sections', side_effect=[after, before]), \
             patch.object(redirect, 'nm_symbols', return_value=nm), \
             patch.object(redirect, 'function_symbols', side_effect=[input_funcs, output_funcs]), \
             contextlib.redirect_stdout(io.StringIO()), self.assertRaises(SystemExit):
            redirect.main()
        self.assertEqual(candidate.read_bytes(), data)

    def test_full_builder_rejects_selection_and_profile_overrides(self):
        for flags in (['--funcs-file=functions'], ['-emit-function-map=other'], ['--instrument-calls'], ['-data', 'stale'],
                      ['--use-old-text'], ['--use-old-text=false'], ['--hot-functions-at-end']):
            with self.subTest(flags=flags), patch.object(sys, 'argv', ['builder', str(self.out), '--redirect-functions', 'first', '--', *flags]), \
                 contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                builder.main()


if __name__ == '__main__':
    unittest.main()
