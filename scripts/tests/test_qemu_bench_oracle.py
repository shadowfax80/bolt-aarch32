"""Baseline equality cannot substitute for the independent arithmetic contract."""
from pathlib import Path
import sys,unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from qemu_bench_oracle import CONTRACTS,reference_results,check_results


class BenchOracleTests(unittest.TestCase):
    def test_all_eighteen_and_closed_form_values(self):
        values=reference_results()
        self.assertEqual(len(values),18)
        self.assertEqual(values['hot_loop'],f'0x{(1000000*999999//2)&0xffffffff:08x}')
        self.assertEqual(values['hot_cold'],'0x00000000')
        self.assertEqual(values['far_call'],f'0x{0x12345678^0xa53c79d1:08x}')
        self.assertEqual(check_results(next(iter(CONTRACTS)),values)['matched_workloads'],18)

    def test_shared_wrong_result_rejects(self):
        expected=reference_results();image=next(iter(CONTRACTS))
        for name in expected:
            wrong={**expected,name:f'0x{int(expected[name],16)^1:08x}'}
            # Both baseline and candidate can agree with these wrong values.
            with self.subTest(name=name),self.assertRaisesRegex(ValueError,'oracle mismatch'):
                check_results(image,wrong)

    def test_missing_extra_and_unreviewed_image_reject(self):
        expected=reference_results();image=next(iter(CONTRACTS))
        for values in [{k:v for k,v in expected.items() if k!='memcpy'},dict(expected,unknown='0x00000000')]:
            with self.assertRaises(ValueError):check_results(image,values)
        with self.assertRaisesRegex(ValueError,'no reviewed'):
            check_results('0'*64,expected)
        with self.assertRaisesRegex(ValueError,'no reviewed'):
            check_results(image,expected,'pi4')


if __name__=='__main__':unittest.main()
