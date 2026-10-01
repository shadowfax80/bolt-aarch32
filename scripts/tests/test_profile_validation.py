"""Negative artifact and workload gates, with serial/tool observations mocked."""
import contextlib
import importlib.util
import io
import pathlib
import struct
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts/pi4'))


def load(name, relative):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


gate = load('validation_gate', 'scripts/pi4/passes_check.py')
dump = load('validation_dump', 'scripts/ram-dump-to-fdata.py')
samples = load('validation_samples', 'scripts/samples_to_fdata.py')


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
        valid_leaf = struct.pack('<IIIIII', 1, 0, 0, 0, 0, 0)
        ctx = dump.ProfileWriterContext(valid_leaf + b'\x01', b'leaf\0')
        args = ['converter', '--elf', str(elf), '--dump', counter_file, '-o', str(output)]
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
        with patch.object(sys, 'argv', ['converter', 'image.elf', path, '-o', str(output)]), \
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
        with patch.object(sys, 'argv', ['converter', 'image.elf', path, '-o', str(output)]), \
             patch.object(samples.subprocess, 'run', side_effect=succeed), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(samples.main(), 0)
        self.assertEqual(output.read_text(), 'no_lbr\n1 test 0 3\n')


if __name__ == '__main__':
    unittest.main()
