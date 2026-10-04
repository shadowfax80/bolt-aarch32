"""Negative gates for redirect selection, artifacts and observed execution."""
import importlib.util
import contextlib
import io
import json
from pathlib import Path
import struct
import sys
import tempfile
import subprocess
import unittest
from unittest.mock import patch, MagicMock

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / 'scripts'), str(ROOT / 'scripts/pi4')]
import full_image_verify as gate
import full_image_build as builder
import qemu_bench_oracle
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

    def test_redirect_replaces_whole_instructions(self):
        # PUSH (two bytes), MOVW (four): four-byte replacement splits MOVW.
        with self.assertRaisesRegex(SystemExit,'split'):
            redirect.require_whole_redirect_prefix(bytes.fromhex('10b540f20100'),0,6,True)
        for code,thumb in [('10b500bf',True),('40f20100',True),('10402de9',False)]:
            redirect.require_whole_redirect_prefix(bytes.fromhex(code),0,4,thumb)
        for off,size in [(0,2),(2,4),(-1,4)]:
            with self.assertRaises(SystemExit):
                redirect.require_whole_redirect_prefix(b'1234',off,size,True)

    def test_split_prefix_allowed_only_when_unreferenced(self):
        # R13: PUSH (2) + MOVW (4). Allowed with allow_split; reports the split.
        self.assertTrue(redirect.require_whole_redirect_prefix(bytes.fromhex('10b540f20100'),0,6,True,allow_split=True))
        self.assertFalse(redirect.require_whole_redirect_prefix(bytes.fromhex('10b500bf'),0,4,True,allow_split=True))
        with self.assertRaisesRegex(SystemExit,'split'):  # too small to hold the split instruction
            redirect.require_whole_redirect_prefix(bytes.fromhex('10b540f2'),0,4,True,allow_split=True)
        entry,size=0x1000,0x40
        refs=[(0x1010,0x1002),(0x2000,0x1000),(0x2000,0x1001),(0x2000,0x1004),(0x2004,0x1003)]
        self.assertEqual(redirect.split_prefix_reachable(refs,entry,size),[(0x2004,0x1003)])
        self.assertEqual(redirect.split_prefix_reachable([(0x2000,0x1002)],entry,size),[(0x2000,0x1002)])
        self.assertEqual(redirect.split_prefix_reachable([(0x1004,0x1002),(0x3000,0x1000)],entry,size),[])

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
        digest = 'a' * 64
        source_digest = gate.sha256(self.out / 'baseline.elf')
        functions = [dict(name='function', address=0x1000, size=8, thumb=False, kind=2)]
        build = dict(schema=1, kind='pi-sampling-build', elf_sha256=source_digest,
                     source_elf_sha256=source_digest, binary_sha256=digest, functions=functions,
                     tools={n: digest for n in ('llvm-bolt', 'perf2bolt', 'llvm-objcopy')}, patches={'test.patch': digest})
        identity = dict(schema=1, kind='bolt-profile', verified_binding=True,
                        profile_type='pc-samples', build=build, capture_manifest_sha256=digest, perf2bolt_sha256=digest,
                        profile_sha256=gate.sha256(profile), source_elf_sha256=gate.sha256(self.out / 'baseline.elf'))
        sidecar.write_text(json.dumps(identity))
        manifest['profile'] = dict(profile_sha256=gate.sha256(profile), manifest_sha256=gate.sha256(sidecar))
        with patch.object(gate, 'loadable_sections', return_value=self.sections), patch('profile_identity.elf_metadata', return_value=([], identity['build']['functions'])):
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
        text = 'bolt_sample: on, every 20000 cycles\n' + text
        text += 'bolt_sample: cpu 0; PMU interrupts per core: 1 0 0 0\n'
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

    def test_dump_framing_cannot_certify_duplicate_or_out_of_order_data(self):
        text, manifest = self.sample_fixture()
        line = next(line + '\n' for line in text.splitlines() if line.startswith('BOLT_DUMP seq='))
        for bad in (text.replace(line, line + line), text.replace('total=00000040', 'total=00000004'),
                    line + text.replace(line, ''), text + 'BOLT_DUMP seq=invalid\n',
                    text.replace(line, line.rstrip() + ' junk\n')):
            with self.subTest(bad=bad[-150:]), self.assertRaises(ValueError):
                gate.execution_evidence(bad, manifest, ['function'])

    def test_subset_cannot_hide_an_unobserved_selected_redirect(self):
        text, manifest = self.sample_fixture()
        manifest['redirected'].append(dict(name='unobserved', output=0x3000, output_size=8, thumb=True))
        for required in (['function'], ['function', 'unobserved'], ['function', 'function']):
            with self.subTest(required=required), self.assertRaises(ValueError):
                gate.execution_evidence(text, manifest, required)

    def test_unaligned_arm_pc_is_not_execution_evidence(self):
        text, manifest = self.sample_fixture(pc=0x2002)
        manifest['redirected'][0]['thumb'] = False
        with self.assertRaisesRegex(ValueError, 'no rewritten execution'):
            gate.execution_evidence(text, manifest, ['function'])

    def run_mock_full_gate(self, mutate=None, child_returncode=0):
        manifest = self.artifact_fixture()
        manifest['sample_buffer'] = dict(address=0x4000, size=64)
        (self.out / 'full_manifest.json').write_text(json.dumps(manifest))
        text, _ = self.sample_fixture(pc=manifest['redirected'][0]['output'])
        calls = []
        def child(command, timeout):
            calls.append(command)
            if mutate:
                mutate(command, len(calls))
            return subprocess.CompletedProcess(command, child_returncode, text.encode())
        with patch.object(sys, 'argv', ['verify', str(self.out), '--repeat', '1']), \
             patch.dict(qemu_bench_oracle.CONTRACTS,{manifest['input_sha256']:{'platform':'pi4','name':'synthetic host oracle'}}), \
             patch.object(qemu_bench_oracle,'reference_results',return_value={k:'0x00000001' for k in gate.parse_results.__globals__['EXPECTED_WORKLOADS']}), \
             patch.object(gate, 'loadable_sections', return_value=self.sections), \
             patch.object(gate, 'run_bounded', side_effect=child), contextlib.redirect_stdout(io.StringIO()):
            result = gate.main()
        return result, calls

    def test_unreviewed_pi_input_rejects_before_upload(self):
        manifest=self.artifact_fixture()
        (self.out/'full_manifest.json').write_text(json.dumps(manifest))
        with patch.object(sys,'argv',['verify',str(self.out)]), \
             patch.object(gate,'loadable_sections',return_value=self.sections), \
             patch.object(gate,'run_bounded') as upload,self.assertRaisesRegex(ValueError,'no reviewed'):
            gate.main()
        upload.assert_not_called()
        self.assertFalse(list(self.out.glob('pi-verify-*')))

    def test_full_gate_snapshots_uploads_and_records_exact_coverage(self):
        result, calls = self.run_mock_full_gate()
        self.assertEqual(result, 0)
        self.assertEqual(len(calls), 2)
        self.assertEqual(Path(calls[0][2]).name, 'baseline.bin')
        self.assertNotEqual(Path(calls[0][2]), self.out / 'baseline.bin')
        report = json.loads(next(self.out.glob('pi-verify-*/verification.json')).read_text())
        self.assertEqual(report['selected_functions'], ['function'])
        self.assertEqual(report['redirected_functions'], ['function'])
        self.assertEqual(report['expected_workload_results'], report['workload_results'])
        self.assertEqual(report['manifest_sha256'], gate.sha256(self.out / 'full_manifest.json'))

    def test_environment_loader_is_snapshotted_and_bound_to_evidence(self):
        loader = self.out / 'loader.img'; loader.write_bytes(b'loader fixture')
        with patch.dict(gate.os.environ, {'PI4_FAST_LOADER': str(loader)}):
            result, calls = self.run_mock_full_gate()
        self.assertEqual(result, 0)
        for command in calls:
            upload = Path(command[command.index('--fast-loader') + 1])
            self.assertNotEqual(upload, loader)
            self.assertEqual(upload.read_bytes(), loader.read_bytes())
        report = json.loads(next(self.out.glob('pi-verify-*/verification.json')).read_text())
        self.assertEqual(report['fast_loader_sha256'], gate.sha256(loader))

    def test_changed_manifest_cannot_be_certified_with_old_in_memory_ranges(self):
        def mutate(command, number):
            if number == 2:
                p = self.out / 'full_manifest.json'
                p.write_text(p.read_text() + '\n')
        with self.assertRaisesRegex(ValueError, 'manifest changed'):
            self.run_mock_full_gate(mutate)
        self.assertFalse(list(self.out.glob('pi-verify-*/verification.json')))

    def test_changed_upload_copy_cannot_be_certified(self):
        def mutate(command, number):
            if number == 2:
                Path(command[2]).write_bytes(b'corrupt upload')
        with self.assertRaisesRegex(ValueError, 'upload copy changed'):
            self.run_mock_full_gate(mutate)
        self.assertFalse(list(self.out.glob('pi-verify-*/verification.json')))

    def test_failed_child_with_complete_output_never_publishes_execution(self):
        with self.assertRaisesRegex(ValueError, 'child failed'):
            self.run_mock_full_gate(child_returncode=7)
        self.assertFalse(list(self.out.glob('pi-verify-*/verification.json')))

    def test_legacy_arm_and_thumb_hooks_reject_before_modification(self):
        for hook in (redirect.fix.patch_orgtext_counter_hook_arm32, redirect.fix.patch_orgtext_counter_hook_thumb):
            data = bytearray(bytes(32)); original = bytes(data)
            with self.assertRaisesRegex(SystemExit, 'unsupported'):
                hook(data, 'nm', {}, 'original', ['f'], {'f': [0]}, 0x1000)
            self.assertEqual(bytes(data), original)

    def test_restoration_rejects_mismatch_and_preserves_existing_file(self):
        original, candidate = self.out / 'source.elf', self.out / 'candidate.elf'
        original.write_bytes(b'abcdefgh'); candidate.write_bytes(b'previous')
        before = {'.text': (0x1000, 0, 8)}
        for after in ({'.bolt.org.text': (0x1000, 0, 4)}, {'.bolt.org.text': (0x1004, 0, 8)},
                      {'.bolt.org.text': (0x1000, 4, 8)}, {}):
            with patch.object(sys, 'argv', ['fix', str(candidate), '--original', str(original)]), \
                 patch.object(redirect.fix, 'sections', side_effect=[after, before]), self.assertRaises(SystemExit):
                redirect.fix.main()
            self.assertEqual(candidate.read_bytes(), b'previous')

    def test_watchdog_cleanup_failure_must_fail_the_serial_child(self):
        import pi4_run
        image = self.out / 'image.bin'; image.write_bytes(b'fixture')
        fake_port = MagicMock()
        with patch.object(sys, 'argv', ['serial-run', str(image), '--post-jump-baud', '115200', '--wdog', '5', 'bolt_bench all']), \
             patch.object(pi4_run, 'resolve_port', return_value='COM5'), \
             patch.object(pi4_run.serial, 'Serial', return_value=fake_port), \
             patch.object(pi4_run, 'send_image'), patch.object(pi4_run, 'Console'), \
             patch.object(pi4_run, 'run_command', side_effect=[True, True, True, False]), self.assertRaises(SystemExit) as raised:
            pi4_run.main()
        self.assertEqual(raised.exception.code, 1)


if __name__ == '__main__':
    unittest.main()
