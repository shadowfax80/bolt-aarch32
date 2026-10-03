"""Reject unsafe sparse copies and incomplete or contradictory Pi witnesses."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'pi4'))
from build_far_safety import validate_chunks
from verify_far_safety import read_staged,check_result

BEGIN = 'BOLT_FAR_PI BEGIN mode=0000001a core=00000000 sctlr=00000000\n'
PASS = 'BOLT_FAR_PI PASS cases=20\n'
FAIL = 'BOLT_FAR_PI FAIL case=00000000 field=0000000b expected=04000000 actual=00100000\n'


class FarSafetyTest(unittest.TestCase):
    def fixture(self):
        expected = [dict(id=i,input=i,result=i+7,cpc=0x100000,fpc=0x4000000,rpc=0x100020,ip=0x4000000) for i in range(20)]
        lines = []
        for row in expected:
            actual = {**row, 'fb':0x20000000,'fa':0x20000000,'sb':0x7ffff8,'sa':0x7ffff8,'mem':row['result']}
            lines.append('BOLT_FAR_PI CASE '+' '.join(f'{k}={v:08x}' for k,v in actual.items())+'\n')
        return expected,lines

    def test_safe_ranges(self):
        validate_chunks([dict(address=0x100000,size=4096),dict(address=0x4000000,size=10)])

    def test_protected_overlap_and_bounds(self):
        for rows in ([dict(address=a,size=s)] for a,s in [(0x8000,4),(0x6fffff,2),(0x800000,4),(0x2000000,4),(0x20fffff,2),(0xfffffff,2),(0x100000,0),(0x100000,4097)]):
            with self.assertRaises(ValueError): validate_chunks(rows)
        with self.assertRaises(ValueError):
            validate_chunks([dict(address=0x100000,size=8),dict(address=0x100004,size=8)])

    def test_staged_cross_chunk_bytes(self):
        self.assertEqual(read_staged([dict(address=10,data=b'ab'),dict(address=12,data=b'cd')],11,3),b'bcd')

    def test_staged_gap_and_ambiguity(self):
        for rows in ([dict(address=10,data=b'ab'),dict(address=13,data=b'cd')],
                     [dict(address=10,data=b'ab'),dict(address=11,data=b'cd')]):
            with self.assertRaises(ValueError): read_staged(rows,10,4)

    def test_complete_witnesses(self):
        expected,lines = self.fixture()
        self.assertEqual(len(check_result(BEGIN+''.join(lines)+PASS,expected)['cases']),20)

    def test_missing_duplicate_reordered_and_malformed(self):
        expected,lines = self.fixture()
        for bad in [lines[:-1],lines+lines[:1],lines[::-1],[lines[0].replace('cpc=','cpc=?')]+lines[1:]]:
            with self.assertRaises(ValueError): check_result(BEGIN+''.join(bad)+PASS,expected)
        for bad in [BEGIN+BEGIN+''.join(lines)+PASS,BEGIN+''.join(lines)+PASS+PASS,BEGIN+''.join(lines),BEGIN+''.join(lines)+PASS+FAIL]:
            with self.assertRaises(ValueError): check_result(bad,expected)

    def test_wrong_live_state(self):
        expected,lines = self.fixture()
        for key,value in [('cpc',0x100004),('fpc',0x100000),('rpc',0x100024),('ip',0xa5a5a5a5),('fa',0x60000000),('sa',0x7ffff0),('mem',8)]:
            old = dict(cpc=0x100000,fpc=0x4000000,rpc=0x100020,ip=0x4000000,fa=0x20000000,sa=0x7ffff8,mem=7)[key]
            bad = lines[0].replace(f'{key}={old:08x}',f'{key}={value:08x}')
            with self.assertRaises(ValueError): check_result(BEGIN+bad+''.join(lines[1:])+PASS,expected)

    def test_wrong_entry(self):
        expected,lines = self.fixture()
        for bad in [BEGIN.replace('mode=0000001a','mode=00000010'),BEGIN.replace('core=00000000','core=00000001'),BEGIN.replace('sctlr=00000000','sctlr=00001005')]:
            with self.assertRaises(ValueError): check_result(bad+''.join(lines)+PASS,expected)

    def test_negative_requires_exact_failure(self):
        expected,lines = self.fixture(); fault = dict(case_id=0,field=11)
        self.assertTrue(check_result(BEGIN+FAIL,expected,fault)['expected_failure'])
        for bad in [FAIL+FAIL,FAIL+PASS,FAIL.replace('0000000b','0000000a'),FAIL.replace('actual=00100000','actual=04000000'),lines[0]+FAIL]:
            with self.assertRaises(ValueError): check_result(BEGIN+bad,expected,fault)


if __name__ == '__main__': unittest.main()
