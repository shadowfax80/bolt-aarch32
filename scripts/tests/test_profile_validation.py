"""Negative artifact and workload gates, with serial/tool observations mocked."""
import contextlib
import importlib.util
import io
import json
import pathlib
import struct
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts/pi4'))
sys.path.insert(0, str(ROOT / 'scripts'))


def load(name, relative):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


gate = load('validation_gate', 'scripts/pi4/passes_check.py')
dump = load('validation_dump', 'scripts/ram-dump-to-fdata.py')
samples = load('validation_samples', 'scripts/samples_to_fdata.py')
identity = load('validation_identity', 'scripts/profile_identity.py')
collector = load('validation_collector', 'scripts/pi4/pi4_sample_profile.py')
overlay_replay = load('validation_overlay_replay', 'scripts/verify-atfe-overlays.py')


class ValidationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = pathlib.Path(self.temp.name)

    def blob(self, value):
        path = self.base / 'input.bin'
        path.write_bytes(value)
        return str(path)

    def complete_results(self):
        return ''.join(f'bolt_bench: {name} sink=0x1234\n' for name in gate.EXPECTED_WORKLOADS)

    def test_complete_workloads_and_identical_duplicates(self):
        text = self.complete_results() + 'bolt_bench: hot_loop sink=0x00001234\n'
        self.assertEqual(len(gate.parse_results(text)), 18)

    def test_incomplete_conflicting_and_unexpected_results(self):
        for text in ('bolt_bench: hot_loop sink=0x1234\n',
                     self.complete_results().replace('bolt_bench: stair sink=0x1234\n', ''),
                     self.complete_results() + 'bolt_bench: hot_loop acc=0x5678\n',
                     self.complete_results() + 'bolt_bench: unknown acc=0x1234\n',
                     self.complete_results() + 'bolt_bench: memcpy FAIL: destination mismatch\n'):
            with self.subTest(text=text[-60:]), self.assertRaises(ValueError):
                gate.parse_results(text)

    def test_nonzero_child_fails_even_with_complete_results(self):
        observation = subprocess.CompletedProcess([], 7, self.complete_results().encode())
        with patch.object(gate, 'run_bounded', return_value=observation), contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit):
                gate.results('fake.bin')

    def test_counter_high_word_and_zero_count(self):
        path = self.blob(struct.pack('<IIQQ', 2, 0, 0x100000007, 0xffffffffffffffff))
        self.assertEqual(dump.load_counters(path, 0x8000, 0x8008, 0x8000), [0x100000007, 0xffffffffffffffff])
        path = self.blob(struct.pack('<II', 0, 0))
        self.assertEqual(dump.load_counters(path, 0, 8, 0), [])

    def test_counter_truncation_and_misplaced_addresses(self):
        path = self.blob(struct.pack('<IIQ', 2, 0, 7))
        for base, locations, count in ((0, 8, 0), (0, -1, 0), (1, 8, 0), (0, 8, 14), (0, 99, 0)):
            with self.subTest(args=(base, locations, count)), self.assertRaises(ValueError):
                dump.load_counters(path, base, locations, count)
        path = self.blob(struct.pack('<II', 0xffffffff, 0))
        with self.assertRaises(ValueError):
            dump.load_counters(path, 0, 8, 0)

    def test_truncated_note(self):
        with self.assertRaises(ValueError):
            dump.parse_tables_note(b'\0' * 8, 0, 12)
        note = struct.pack('<III', 0, 24, 0) + struct.pack('<III', 0, 0, 0)
        with self.assertRaises(ValueError):
            dump.parse_tables_note(note, 0, len(note))

    def test_late_metadata_failure_does_not_publish_partial_profile(self):
        elf = self.base / 'input.elf'; elf.write_bytes(b'fixture')
        output = self.base / 'profile.fdata'; output.write_text('previous verified profile')
        counter_file = self.blob(struct.pack('<IIQ', 1, 0, 7))
        valid_edge = struct.pack('<II', 0, 1) + struct.pack('<IIIIIII', 0, 0, 0, 0, 4, 1, 0) + struct.pack('<II', 0, 0)
        ctx = dump.ProfileWriterContext(valid_edge + b'\x01', b'leaf\0')
        args = ['converter', '--elf', str(elf), '--dump', counter_file, '-o', str(output), '--debug-unbound']
        stdout = io.StringIO()
        with patch.object(sys, 'argv', args), patch.object(dump, 'section_info', return_value=(0, 0, 0)), \
             patch.object(dump, 'parse_tables_note', return_value=ctx), \
             patch.object(dump, 'getter_address', side_effect=[8, 0]), contextlib.redirect_stdout(stdout):
            with self.assertRaises(struct.error):
                dump.main()
        self.assertEqual(output.read_text(), 'previous verified profile')
        self.assertEqual(stdout.getvalue(), '')

    def test_samples_reject_empty_and_partial_words(self):
        for data in (b'', b'abc', struct.pack('<I', 0x1001) + b'x'):
            with self.subTest(data=data), self.assertRaises(ValueError):
                samples.load_samples(self.blob(data))
        self.assertEqual(samples.load_samples(self.blob(struct.pack('<II', 0x1001, 0x2000))), (0x1001, 0x2000))

    def test_failed_perf2bolt_preserves_previous_profile(self):
        path = self.blob(struct.pack('<I', 0x1001))
        output = self.base / 'profile.fdata'; output.write_text('verified')
        def fail(cmd, **kwargs):
            pathlib.Path(cmd[cmd.index('-o') + 1]).write_text('partial')
            return subprocess.CompletedProcess(cmd, 1, '', 'rejected')
        with patch.object(sys, 'argv', ['converter', 'image.elf', path, '-o', str(output), '--debug-unbound']), \
             patch.object(samples.subprocess, 'run', side_effect=fail), contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit):
                samples.main()
        self.assertEqual(output.read_text(), 'verified')
        self.assertFalse(pathlib.Path(str(output) + '.preagg').exists())

    def test_successful_perf2bolt_publishes_profile(self):
        path = self.blob(struct.pack('<III', 0x1001, 0x1000, 0x2000))
        output = self.base / 'profile.fdata'
        def succeed(cmd, **kwargs):
            self.assertEqual(pathlib.Path(cmd[cmd.index('-p') + 1]).read_text(), 'S 1000 2\nS 2000 1\n')
            pathlib.Path(cmd[cmd.index('-o') + 1]).write_text('no_lbr\n1 test 0 3\n')
            return subprocess.CompletedProcess(cmd, 0, '', '')
        with patch.object(sys, 'argv', ['converter', 'image.elf', path, '-o', str(output), '--debug-unbound']), \
             patch.object(samples.subprocess, 'run', side_effect=succeed), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(samples.main(), 0)
        self.assertEqual(output.read_text(), 'no_lbr\n1 test 0 3\n')
        self.assertFalse(json.loads(pathlib.Path(str(output) + '.manifest.json').read_text())['verified_binding'])

    def graph_function(self, edges, leaves=()):
        return dump.FunctionDescription(len(leaves), list(leaves), len(edges), list(edges), 0, [], 0, [])

    def edge(self, source, target, counter):
        return dump.EdgeDescription(dump.Location(0, 0), source, dump.Location(0, 4), target, counter)

    def test_valid_inferred_tree_and_sparse_node_ids(self):
        f = self.graph_function([self.edge(0, 0xffffffff, dump.INFERRED)], [dump.InstrumentedNode(0xffffffff, 0)])
        ctx = dump.ProfileWriterContext(b'', b'function\0')
        dump.validate_function(ctx, f, [7])
        self.assertEqual(dump.Graph(f, [7], {}).edge_freqs, [7])
        dump.validate_function(ctx, f, [0])
        self.assertEqual(dump.Graph(f, [0], {}).edge_freqs, [0])

    def test_inferred_cycles_parents_unmeasured_exits_and_duplicates(self):
        ctx = dump.ProfileWriterContext(b'', b'function\0')
        cases = [self.graph_function([self.edge(0, 1, dump.INFERRED), self.edge(1, 0, dump.INFERRED)]),
                 self.graph_function([self.edge(0, 2, dump.INFERRED), self.edge(1, 2, dump.INFERRED)], [dump.InstrumentedNode(2, 0)]),
                 self.graph_function([self.edge(0, 1, dump.INFERRED)]),
                 self.graph_function([self.edge(0, 1, 0), self.edge(0, 1, 0)]),
                 self.graph_function([self.edge(0, 1, 0)], [dump.InstrumentedNode(1, dump.INFERRED)])]
        for f in cases:
            with self.subTest(function=f), self.assertRaises(ValueError):
                dump.validate_function(ctx, f, [0])

    def test_negative_inferred_flow_is_not_clamped(self):
        f = self.graph_function([self.edge(0, 2, dump.INFERRED), self.edge(1, 2, 1)], [dump.InstrumentedNode(2, 0)])
        with self.assertRaisesRegex(ValueError, 'negative inferred'):
            dump.validate_function(dump.ProfileWriterContext(b'', b'function\0'), f, [3, 7])

    def test_leaf_name_and_string_boundary_cannot_be_guessed(self):
        ctx = dump.ProfileWriterContext(b'', b'first\0second\0')
        f = self.graph_function([], [dump.InstrumentedNode(0, 0)])
        with self.assertRaisesRegex(ValueError, 'function identity'):
            dump.validate_function(ctx, f, [7])
        for offset in (1, 99):
            with self.subTest(offset=offset), self.assertRaises(ValueError):
                dump.serialize_loc(ctx.strings, dump.Location(offset, 0))

    def identity_fixture(self):
        names = b'\0.text\0.bss\0.shstrtab\0.strtab\0.symtab\0'
        strings = b'\0foo\0bolt_sample_buf\0'
        symtab = bytes(16) + struct.pack('<IIIBBH', 1, 0x8001, 8, 2, 0, 1)
        symtab += struct.pack('<IIIBBH', 5, 0x9000, 0x80000, 1, 0, 2)
        blob = bytearray(0x400)
        blob[:16] = b'\x7fELF\x01\x01\x01' + bytes(9)
        struct.pack_into('<HHIIIIIHHHHHH', blob, 16, 2, 40, 1, 0x8001, 52, 0x200, 0, 52, 32, 1, 40, 6, 3)
        struct.pack_into('<8I', blob, 52, 1, 0x100, 0x8000, 0x8000, 8, 8, 5, 4)
        blob[0x100:0x108] = b'abcdefgh'
        blob[0x120:0x120 + len(names)] = names
        blob[0x160:0x160 + len(strings)] = strings
        blob[0x180:0x180 + len(symtab)] = symtab
        headers = [(0, 0, 0, 0, 0, 0, 0, 0, 0, 0),
                   (1, 1, 6, 0x8000, 0x100, 8, 0, 0, 2, 0),
                   (7, 8, 3, 0x9000, 0x108, 0x80000, 0, 0, 4, 0),
                   (12, 3, 0, 0, 0x120, len(names), 0, 0, 1, 0),
                   (22, 3, 0, 0, 0x160, len(strings), 0, 0, 1, 0),
                   (30, 2, 0, 0, 0x180, len(symtab), 4, 1, 4, 16)]
        for i, header in enumerate(headers):
            struct.pack_into('<10I', blob, 0x200 + i * 40, *header)
        elf = self.base / 'source.elf'; elf.write_bytes(blob)
        binary = self.base / 'image.bin'; binary.write_bytes(b'abcdefgh')
        tools = self.base / 'tools'; tools.mkdir()
        for name in ('llvm-bolt', 'perf2bolt', 'llvm-objcopy'):
            (tools / name).write_bytes(name.encode())
        patches = self.base / 'patches'; patches.mkdir()
        (patches / '0001.patch').write_text('test patch')
        build = identity.seal_samples(elf, binary, tools, patches)
        return elf, binary, tools, build

    def test_sampling_seal_checks_actual_elf_binary_and_buffer(self):
        elf, binary, tools, build = self.identity_fixture()
        identity.check_build(build, binary, elf)
        self.assertEqual(build['functions'][0]['address'], 0x8000)
        self.assertTrue(build['functions'][0]['thumb'])
        binary.write_bytes(b'abcdefg!')
        with self.assertRaises(ValueError):
            identity.check_build(build, binary, elf)
        with self.assertRaises(ValueError):
            identity.seal_samples(elf, binary, tools, self.base / 'patches')
        for malformed in (elf.read_bytes()[:51], elf.read_bytes().replace(b'\x7fELF\x01\x01', b'\x7fELF\x01\x02', 1)):
            with self.assertRaises(ValueError):
                identity.elf_metadata(malformed)

    def test_stale_capture_and_profile_rejected(self):
        elf, binary, tools, build = self.identity_fixture()
        payload = self.base / 'samples'; payload.write_bytes(struct.pack('<I', 0x8001))
        manifest = self.base / 'capture.json'
        identity.write_json(manifest, dict(schema=1, kind='pi-pc-capture', verified_binding=True,
                                          payload_sha256=identity.sha256(payload), build=build))
        identity.check_capture(manifest, payload, elf, 'pi-pc-capture')
        payload.write_bytes(struct.pack('<I', 0x8003))
        with self.assertRaises(ValueError):
            identity.check_capture(manifest, payload, elf, 'pi-pc-capture')
        profile = self.base / 'profile.fdata'; profile.write_text('no_lbr\n1 foo 0 1\n')
        identity.write_json(str(profile) + '.manifest.json', dict(schema=1, kind='bolt-profile',
                            verified_binding=True, profile_type='pc-samples', build=build,
                            capture_manifest_sha256='a' * 64, perf2bolt_sha256=build['tools']['perf2bolt'],
                            source_elf_sha256=identity.sha256(elf), profile_sha256=identity.sha256(profile)))
        identity.check_profile(elf, profile)
        profile.write_text('no_lbr\n1 foo 0 2\n')
        with self.assertRaises(ValueError):
            identity.check_profile(elf, profile)

    def test_sample_locations_bound_to_source_ranges(self):
        elf, binary, tools, build = self.identity_fixture()
        profile = self.base / 'profile.fdata'
        profile.write_text('no_lbr\n1 foo/1 6 2\n')
        identity.validate_sample_fdata(profile, build['functions'])
        for body in ('1 foo 8 1', '1 missing 0 1', '1 foo/bad 0 1', '1 foo 0 0', '0 8000 0 1', ''):
            profile.write_text('no_lbr\n' + body + '\n')
            with self.subTest(body=body), self.assertRaises(ValueError):
                identity.validate_sample_fdata(profile, build['functions'])
        profile.write_text('no_lbr\n1 foo/1 0 1\n')
        with self.assertRaises(ValueError):
            identity.validate_sample_fdata(profile, build['functions'] * 2)

    def test_unbound_samples_rejected_before_perf2bolt_or_publication(self):
        payload = self.blob(struct.pack('<I', 0x1001))
        output = self.base / 'profile.fdata'; output.write_text('previous')
        with patch.object(sys, 'argv', ['converter', 'image.elf', payload, '-o', str(output)]), \
             patch.object(samples.subprocess, 'run') as run:
            with self.assertRaises(OSError):
                samples.main()
            run.assert_not_called()
        self.assertEqual(output.read_text(), 'previous')

    def test_explicit_profile_scope_records_exclusions_and_still_bounds_selected_locations(self):
        elf, binary, tools, build = self.identity_fixture()
        profile = self.base / 'profile.fdata'
        original = 'no_lbr\n1 foo 0 3\n1 unbounded_assembly 4 2\n'
        profile.write_text(original)
        with self.assertRaises(ValueError):
            identity.validate_sample_fdata(profile, build['functions'])
        self.assertEqual(profile.read_text(), original)
        scope = identity.validate_sample_fdata(profile, build['functions'], ['foo'])
        self.assertEqual(scope['excluded_profile_counts'], {'unbounded_assembly': 2})
        self.assertEqual(profile.read_text(), 'no_lbr\n1 foo 0 3\n')
        for body, names in (('1 foo 8 3\n1 unbounded 0 2\n', ['foo']),
                            ('1 unbounded 0 2\n', ['foo']),
                            ('1 foo 0 3\n', ['unknown']), ('1 foo 0 3\n', ['foo', 'foo'])):
            profile.write_text('no_lbr\n' + body)
            with self.subTest(body=body), self.assertRaises(ValueError):
                identity.validate_sample_fdata(profile, build['functions'], names)

    def test_bound_conversion_and_late_bad_location_preserve_existing_profile(self):
        elf, binary, tools, build = self.identity_fixture()
        payload = self.base / 'capture.samples'; payload.write_bytes(struct.pack('<I', 0x8001))
        capture_path = str(payload) + '.manifest.json'
        identity.write_json(capture_path, dict(schema=1, kind='pi-pc-capture', verified_binding=True,
                                              payload_sha256=identity.sha256(payload), build=build))
        output = self.base / 'bound.fdata'
        result = ['no_lbr\n1 foo 0 1\n']
        def convert(cmd, **kwargs):
            pathlib.Path(cmd[cmd.index('-o') + 1]).write_text(result[0])
            return subprocess.CompletedProcess(cmd, 0, '', '')
        args = ['converter', str(elf), str(payload), '-o', str(output), '--toolchain', str(tools)]
        with patch.object(sys, 'argv', args), patch.object(samples.subprocess, 'run', side_effect=convert), \
             contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(samples.main(), 0)
            identity.check_profile(elf, output)
            previous = output.read_bytes()
            previous_identity = pathlib.Path(str(output) + '.manifest.json').read_bytes()
            result[0] = 'no_lbr\n1 foo 8 1\n'
            with self.assertRaisesRegex(ValueError, 'outside'):
                samples.main()
            self.assertEqual(output.read_bytes(), previous)
            self.assertEqual(pathlib.Path(str(output) + '.manifest.json').read_bytes(), previous_identity)
        (tools / 'perf2bolt').write_bytes(b'changed tool')
        with patch.object(sys, 'argv', args), patch.object(samples.subprocess, 'run') as run:
            with self.assertRaisesRegex(ValueError, 'toolchain'):
                samples.main()
            run.assert_not_called()

    def test_failed_sampling_child_preserves_payload_and_identity(self):
        elf, binary, tools, build = self.identity_fixture()
        identity.write_json(str(binary) + '.manifest.json', build)
        output = self.base / 'capture.samples'; output.write_bytes(b'previous payload')
        sidecar = pathlib.Path(str(output) + '.manifest.json'); sidecar.write_text('previous identity')
        args = ['collector', str(binary), str(output), '--elf', str(elf)]
        child = subprocess.CompletedProcess([], 7, b'failed boot')
        with patch.object(sys, 'argv', args), patch.object(collector, 'run_bounded', return_value=child):
            with self.assertRaises(SystemExit):
                collector.main()
        self.assertEqual(output.read_bytes(), b'previous payload')
        self.assertEqual(sidecar.read_text(), 'previous identity')
        self.assertEqual(len(list(self.base.glob('pi-samples-*/capture.log'))), 1)

    def sample_capture_text(self):
        import bolt_dump_reassemble as wire
        blob = struct.pack('<II', 0x8001, 0)
        return ('bolt_bench: hot_loop sink=0x1234\nbolt_sample: on, every 20000 cycles\n'
                'bolt_sample: 1 samples (1 taken) buf=0x9000 bytes=0x4\n'
                'bolt_sample: cpu 1; PMU interrupts per core: 0 1 0 0\n'
                'BOLT_DUMP_BEGIN addr=9000 size=8\n'
                f'BOLT_DUMP seq=0 off=0 len=8 crc={wire.checksum(blob):x} data={blob.hex()}\n'
                'BOLT_DUMP_END seq=1 total=8\n')

    def test_capture_rejects_wrong_range_saturation_incomplete_workload_and_pmu(self):
        text = self.sample_capture_text()
        buffer = dict(address=0x9000, size=8)
        payload, observed = collector.validate_capture(text, buffer, 'hot_loop', 1, 20000)
        self.assertEqual(payload, struct.pack('<I', 0x8001))
        self.assertEqual(observed['workload_core'], 1)
        cases = [text.replace('1 samples (1 taken)', '2 samples (2 taken)'),
                 text.replace('1 samples (1 taken)', '1 samples (2 taken)'),
                 text.replace('buf=0x9000', 'buf=0x9004'),
                 text.replace('addr=9000', 'addr=9004'),
                 text.replace('BOLT_DUMP_END seq=1', 'BOLT_DUMP_END seq=2'),
                 text.replace('cpu 1;', 'cpu 5;'),
                 text.replace('0 1 0 0', '0 0 0 0'),
                 text.replace('bolt_bench: hot_loop sink=0x1234\n', ''),
                 text + 'bolt_bench: hot_loop pmu INVALID (migrated)\n']
        for candidate in cases:
            with self.subTest(candidate=candidate), self.assertRaises(ValueError):
                collector.validate_capture(candidate, buffer, 'hot_loop', 1, 20000)
        with self.assertRaises(ValueError):
            collector.validate_capture(text, buffer, 'hot_loop', 2, 20000)

    def test_all_repetitions_count_final_sinks_not_duplicate_acc_reports(self):
        text = self.sample_capture_text().replace('bolt_bench: hot_loop sink=0x1234\n', '')
        one_run = self.complete_results() + 'bolt_bench: composite acc=0x1234\nbolt_bench: stair acc=0x1234\n'
        text = one_run * 2 + text
        buffer = dict(address=0x9000, size=8)
        _, observations = collector.validate_capture(text, buffer, 'all', 2, 20000)
        self.assertEqual(len(observations['workload_results']), 18)
        with self.assertRaises(ValueError):
            collector.validate_capture(text, buffer, 'all', 3, 20000)

    def replay_fixture(self):
        source = self.base / 'source'; source.mkdir()
        overlay_replay.git(source, 'init', '-q')
        overlay_replay.git(source, 'config', 'core.autocrlf', 'false')
        original = source / 'code.txt'; original.write_bytes(b'start\none\nend\n')
        overlay_replay.git(source, 'add', 'code.txt')
        overlay_replay.git(source, '-c', 'user.name=Test', '-c', 'user.email=test@localhost', 'commit', '-qm', 'base')
        base = overlay_replay.git(source, 'rev-parse', 'HEAD').decode().strip()
        patches = self.base / 'series'; patches.mkdir()
        original.write_bytes(b'start\ntwo\nend\n')
        (patches / '0001.patch').write_bytes(overlay_replay.git(source, 'diff', '--', 'code.txt'))
        overlay_replay.git(source, 'add', 'code.txt')
        overlay_replay.git(source, '-c', 'user.name=Test', '-c', 'user.email=test@localhost', 'commit', '-qm', 'first')
        original.write_bytes(b'start\nthree\nend\n')
        (patches / '0002.patch').write_bytes(overlay_replay.git(source, 'diff', '--', 'code.txt'))
        return source, base, patches

    def test_clean_overlay_replay_preserves_live_source_and_rejects_changed_content(self):
        source, base, patches = self.replay_fixture()
        before = (source / 'code.txt').read_bytes()
        result = overlay_replay.replay(source, base, patches, self.base / 'replay')
        self.assertTrue(result['success'])
        self.assertTrue(result['live_source_preserved'])
        self.assertEqual((source / 'code.txt').read_bytes(), before)
        # The same filename with changed patch content cannot inherit success.
        patch = patches / '0002.patch'
        patch.write_bytes(patch.read_bytes().replace(b'+three', b'+changed'))
        changed = overlay_replay.replay(source, base, patches, self.base / 'changed-replay')
        self.assertFalse(changed['success'])
        self.assertNotEqual(result['source_identity_sha256'], changed['source_identity_sha256'])
        self.assertEqual(changed['mismatched_source_files'], ['code.txt'])
        self.assertEqual((source / 'code.txt').read_bytes(), before)

    def test_overlay_replay_rejects_uncovered_source_and_unsafe_destinations(self):
        source, base, patches = self.replay_fixture()
        (source / 'extra-code.c').write_bytes(b'extra source')
        result = overlay_replay.replay(source, base, patches, self.base / 'uncovered-replay')
        self.assertFalse(result['success'])
        self.assertEqual(result['uncovered_source_changes'], ['extra-code.c'])
        with self.assertRaises(ValueError):
            overlay_replay.replay(source, base, patches, source / 'replay')
        with self.assertRaises(ValueError):
            overlay_replay.replay(source, base, patches, self.base / 'uncovered-replay')
        for path in ('../outside', '/outside', 'C:/outside', '.git/config', 'nested/.git/config', 'nested\\outside'):
            with self.subTest(path=path), self.assertRaises(ValueError):
                overlay_replay.safe_path(path)

    def test_publication_rolls_back_payload_when_sidecar_replace_fails(self):
        a, b = self.base / 'profile', self.base / 'identity'
        a.write_bytes(b'old profile'); b.write_bytes(b'old identity')
        replace = identity.os.replace
        calls = [0]
        def fail_once(source, target):
            calls[0] += 1
            if calls[0] == 2:
                raise OSError('late sidecar publication failure')
            return replace(source, target)
        with patch.object(identity.os, 'replace', side_effect=fail_once), self.assertRaises(OSError):
            identity.publish_files({a: b'new profile', b: b'new identity'})
        self.assertEqual(a.read_bytes(), b'old profile')
        self.assertEqual(b.read_bytes(), b'old identity')

    def test_counter_profile_consumer_checks_offsets_even_with_matching_hashes(self):
        elf, binary, tools, build = self.identity_fixture()
        digest = 'a' * 64
        _, symbols = identity.elf_metadata(elf.read_bytes())
        owner = {k: symbols[0][k] for k in ('name', 'address', 'size', 'thumb')}
        counter_build = dict(schema=1, kind='arm-counter-build', verified_binding=True,
            artifacts=dict(original=identity.sha256(elf), elf=digest, mapping=digest, image=digest, replay=digest),
            tools={name: digest for name in ('llvm-bolt', 'llvm-readelf', 'llvm-nm', 'llvm-objdump', 'llvm-objcopy')},
            patches={'test.patch': digest}, source_identity_sha256=digest, metadata=dict(owners=[owner]))
        profile = self.base / 'counter.fdata'
        for offset in ('0', '7', '8', '-1'):
            profile.write_text(f'1 foo {offset} 1 foo 0 0 7\n')
            identity.write_json(str(profile) + '.manifest.json', dict(schema=1, kind='bolt-profile',
                profile_type='arm-counters', verified_binding=True, source_elf_sha256=identity.sha256(elf),
                profile_sha256=identity.sha256(profile), build=counter_build, capture_manifest_sha256=digest))
            if offset in ('0', '7'):
                identity.check_profile(elf, profile)
            else:
                with self.assertRaises(ValueError):
                    identity.check_profile(elf, profile)
        functions = [s for s in symbols if s['kind'] == 2]
        identity.validate_counter_fdata(f'1 foo 0 1 foo 0 0 {(1 << 64) - 1}\n', functions)
        with self.assertRaises(ValueError):
            identity.validate_counter_fdata(f'1 foo 0 1 foo 0 0 {1 << 64}\n', functions)
        with self.assertRaises(ValueError):
            identity.validate_counter_fdata('1 foo/1 0 1 foo/1 0 0 1\n', functions + functions)

    def test_failed_counter_child_preserves_payload_and_identity(self):
        counter_collector = load('failed_counter_collector', 'scripts/pi4/pi4_bolt_profile.py')
        elf, binary, tools, _ = self.identity_fixture()
        build = dict(schema=1, artifacts=dict(image=identity.sha256(binary)),
                     metadata=dict(counter_layout=dict(address=0x9000, size=8, count_address=0x9000, count=1)))
        identity.write_json(str(binary) + '.manifest.json', build)
        output = self.base / 'counters.bin'; output.write_bytes(b'previous payload')
        sidecar = pathlib.Path(str(output) + '.manifest.json'); sidecar.write_bytes(b'previous identity')
        args = ['collector', str(binary), str(output), '--elf', str(elf), '--original', str(elf),
                '--function-map', 'map', '--source-replay', 'replay']
        child = subprocess.CompletedProcess([], 7, b'failed boot')
        with patch.object(sys, 'argv', args), patch.object(counter_collector, 'check_build'), \
                patch.object(counter_collector, 'run_bounded', return_value=child):
            with self.assertRaises(SystemExit):
                counter_collector.main()
        self.assertEqual(output.read_bytes(), b'previous payload')
        self.assertEqual(sidecar.read_bytes(), b'previous identity')

    def test_owner_hint_cannot_override_named_descriptor_locations(self):
        f = self.graph_function([self.edge(0, 1, 0)])
        ctx = dump.ProfileWriterContext(b'', b'function\0')
        with self.assertRaisesRegex(ValueError, 'explicit owner'):
            dump.validate_function(ctx, f, [7], owner_name='other')
        leaf = self.graph_function([], [dump.InstrumentedNode(0, 0)])
        dump.validate_function(dump.ProfileWriterContext(b'', b''), leaf, [7], owner_name='function')

    def test_counter_wire_rejects_wrong_range_duplicate_and_bad_crc(self):
        counter_collector = load('bound_counter_collector', 'scripts/pi4/pi4_bolt_profile.py')
        import bolt_dump_reassemble as wire
        blob = bytes(8)
        line = f'BOLT_DUMP seq=0 off=0 len=8 crc={wire.checksum(blob):x} data={blob.hex()}\n'
        text = 'BOLT_DUMP_BEGIN addr=9000 size=8\n' + line + 'BOLT_DUMP_END seq=1 total=8\n'
        self.assertEqual(counter_collector.validate_dump(text, dict(address=0x9000, size=8)), blob)
        for bad in (text.replace('addr=9000', 'addr=9004'), text.replace(line, line + line),
                    text.replace(f'crc={wire.checksum(blob):x}', f'crc={wire.checksum(blob) ^ 1:x}'), text.replace('seq=1 total', 'seq=2 total'),
                    text.replace('total=8', 'total=7'), line + text.replace(line, '')):
            with self.assertRaises(ValueError):
                counter_collector.validate_dump(bad, dict(address=0x9000, size=8))


if __name__ == '__main__':
    unittest.main()
