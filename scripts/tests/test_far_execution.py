"""Admissions for the QEMU far-call execution certificate."""
from pathlib import Path
import struct
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import verify_far_execution as gate


class FarExecutionTests(unittest.TestCase):
    def test_execution_needs_result_and_all_route_witnesses(self):
        required = {0x1000, 0x1100, 0x2102000}
        gate.check_execution(42, False, required, required)
        for code, timeout, pcs in [(41, False, required), (-11, False, required),
                                  (42, True, required), (42, False, {0x1000, 0x1100}),
                                  (42, False, set())]:
            with self.subTest(code=code, timeout=timeout, pcs=pcs), self.assertRaises(ValueError):
                gate.check_execution(code, timeout, pcs, required)

    def test_trace_reads_executed_guest_not_host_or_translated_addresses(self):
        text = ('Trace 0: 0x7fa123 [00000480/0000000002400010/00000000/00000200] _start\n'
                'Trace 0: 0x7fa456 [00000480/0000000004500030/00000000/00000200] far\n'
                '0x02400020: mov r0,r0\nIN: translated\n')
        self.assertEqual(gate.trace_pcs(text), {0x2400010, 0x4500030})

    def test_missing_qemu_cannot_pass_structural_gate(self):
        with patch.object(sys, 'argv', ['gate', '--toolchain', 'unused']), \
                patch.object(gate.shutil, 'which', return_value=None), \
                self.assertRaisesRegex(ValueError, 'qemu-arm required'):
            gate.main()

    def test_exit_and_one_visit_cannot_certify_all_seeds(self):
        outcome = dict(returncode=42, timed_out=False, pcs=[0x1000,0x1100,0x2102000],
                       visits={'0x1000':1,'0x1100':1,'0x2102000':1})
        with self.assertRaisesRegex(ValueError, 'seed execution'):
            gate.check_certificate(outcome, outcome['pcs'], outcome['pcs'][1:])
        outcome['visits'].update({'0x1100':5,'0x2102000':5})
        gate.check_certificate(outcome, outcome['pcs'], outcome['pcs'][1:])
        outcome['visits']['0x2102000'] = 6
        with self.assertRaisesRegex(ValueError, 'seed execution'):
            gate.check_certificate(outcome, outcome['pcs'], outcome['pcs'][1:])

    def route_fixture(self):
        start, stub, far = 0x2400010, 0x2400100, 0x4500030
        blob = bytearray(512)
        struct.pack_into('<I', blob, 24, start)
        struct.pack_into('<I', blob, 64, 0xeb000000 | (((stub-start-8)//4) & 0xffffff))
        def mov(base, imm):
            return base | (imm & 0xfff) | ((imm & 0xf000) << 4)
        struct.pack_into('<III', blob, 80, mov(0xe300c000, far & 0xffff),
                         mov(0xe340c000, far >> 16), 0xe12fff1c)
        mapping = {'_start': [0x10000, start, 4], 'far_away': [0x2110000, far, 12]}
        return blob, mapping, {start:64, stub:80}

    def test_route_checks_exact_destination_and_new_entry(self):
        blob, mapping, positions = self.route_fixture()
        with patch.object(gate, 'offset', side_effect=lambda b,a,n: positions[a]):
            self.assertEqual(gate.route(blob, mapping)['callee'], 0x4500030)
            damaged = bytearray(blob)
            damaged[80] ^= 1
            with self.assertRaisesRegex(ValueError, 'incorrect callee'):
                gate.route(damaged, mapping)
            # A32 BL includes the negative -32 MiB endpoint; it is not a far route.
            in_range = mapping['_start'][1] + 8 - 0x2000000
            mapping['far_away'][1] = in_range
            for position, base, imm in [(80,0xe300c000,in_range & 0xffff),
                                         (84,0xe340c000,in_range >> 16)]:
                struct.pack_into('<I', blob, position, base | (imm & 0xfff) | ((imm & 0xf000) << 4))
            with self.assertRaisesRegex(ValueError, 'direct BL range'):
                gate.route(blob, mapping)
            struct.pack_into('<I', blob, 24, 0x10000)
            with self.assertRaisesRegex(ValueError, 'rewritten caller'):
                gate.route(blob, mapping)

    def test_route_rejects_unmoved_and_extra_emitted_functions(self):
        blob, mapping, _ = self.route_fixture()
        mapping['unexpected'] = [1,2,4]
        with self.assertRaisesRegex(ValueError, 'selection'):
            gate.route(blob, mapping)
        del mapping['unexpected']
        mapping['far_away'][0] = mapping['far_away'][1]
        with self.assertRaisesRegex(ValueError, 'did not move'):
            gate.route(blob, mapping)


if __name__ == '__main__':
    unittest.main()
