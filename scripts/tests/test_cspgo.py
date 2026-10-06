"""Negative format/transport tests for the bare-metal IR/CSPGO pipeline."""
import importlib.util
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
sys.path.insert(0, str(ROOT / 'scripts/pi4'))
import pgo_profile
import pi4_pgo_collect as collect
from bolt_dump_reassemble import checksum


def show(level='IR', functions=2, count=20):
    return f'Instrumentation level: {level}\nFunctions shown: {functions}\nMaximum function count: 0\nMaximum internal block count: {count}\n'


class ProfileTests(unittest.TestCase):
    def validate(self, kind, ordinary, cs):
        with patch.object(subprocess, 'run', side_effect=[
            subprocess.CompletedProcess([], 0, ordinary), subprocess.CompletedProcess([], 0, cs)]):
            return pgo_profile.validate_profile('input', 'llvm-profdata', kind)

    def test_merged_requires_both_trained_levels(self):
        self.validate('merged', show(), show())
        for ordinary, cs in ((show(functions=0, count=0), show()), (show(), show(count=0))):
            with self.assertRaises(ValueError):
                self.validate('merged', ordinary, cs)

    def test_frontend_cannot_be_used_as_ir(self):
        with self.assertRaises(ValueError):
            self.validate('ir', show('Front-end'), show('Front-end'))
        self.validate('frontend', show('Front-end'), show('Front-end'))

    def test_ir_and_cs_cannot_be_substituted(self):
        with self.assertRaises(ValueError):
            self.validate('cs', show(), show(functions=0, count=0))
        with self.assertRaises(ValueError):
            self.validate('ir', show(functions=0, count=0), show())

    def test_baseline_must_not_already_use_cs_records(self):
        self.validate('ir-only', show(), show(functions=0, count=0))
        with self.assertRaises(ValueError):
            self.validate('ir-only', show(), show())

    def test_unknown_tool_output_fails_closed(self):
        with self.assertRaises(ValueError):
            self.validate('ir', 'unknown output', show())

    def test_pinned_ir_tool_reports_entry_metadata(self):
        self.validate('ir-only', show('IR  entry_first = 0  instrument_loop_entries = 0'),
                      show('IR  entry_first = 0  instrument_loop_entries = 0', functions=0, count=0))


class TransportTests(unittest.TestCase):
    def stream(self, blob=bytes(range(80))):
        text = f'bolt_pgo_dump: addr=80000000 size={len(blob):08x}\nBOLT_DUMP_BEGIN addr=80000000 size={len(blob):08x}\n'
        for seq, off in enumerate(range(0, len(blob), 64)):
            part = blob[off:off + 64]
            text += f'BOLT_DUMP seq={seq:08x} off={off:08x} len={len(part):08x} crc={checksum(part):08x} data={part.hex()}\n'
        text += f'BOLT_DUMP_END seq={(len(blob)+63)//64:08x} total={len(blob):08x}\n'
        return text

    def test_complete_verified_profile(self):
        self.assertEqual(collect.extract_profile(self.stream(), (0x80000000, 80)), bytes(range(80)))

    def test_missing_duplicate_and_wrong_footer(self):
        text = self.stream()
        for invalid in (text.split('BOLT_DUMP_END')[0], text + text, text.replace('total=00000050', 'total=00000051')):
            with self.subTest(invalid=invalid[-100:]), self.assertRaises(ValueError):
                collect.extract_profile(invalid, (0x80000000, 80))

    def test_training_requires_command_and_completion(self):
        text = ('$ bolt_bench stair\nbolt_bench: stair done (10 cycles)\n'
                'bolt_bench: stair pmu inst=20 l1i_refill=1 l1d_refill=0 br_mispred=0\n'
                'bolt_bench: stair acc=0x1234\n$ bolt_pgo_dump\n')
        self.assertEqual(collect.training_results(text, ['stair']), [{'stair': '0x00001234'}])
        for invalid in (text.replace('acc=', 'sink='), text.replace('$ bolt_bench stair', '$ bolt_bench composite'),
                        text.replace('$ bolt_pgo_dump', 'bolt_bench: stair acc=0x1234\n$ bolt_pgo_dump'),
                        text.replace('$ bolt_pgo_dump', 'bolt_bench: stair FAIL bad result\n$ bolt_pgo_dump')):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                collect.training_results(invalid, ['stair'])

    def test_corruption_overlap_and_changed_buffer(self):
        text = self.stream()
        for invalid in (text.replace('data=00', 'data=ff'), text.replace('off=00000040', 'off=00000000'),
                        text.replace('bolt_pgo_dump: addr=80000000', 'bolt_pgo_dump: addr=80000004')):
            with self.subTest(invalid=invalid[-100:]), self.assertRaises(ValueError):
                collect.extract_profile(invalid, (0x80000000, 80))


if __name__ == '__main__':
    unittest.main()
