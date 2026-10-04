"""Reject unsafe sparse copies and incomplete or contradictory Pi witnesses."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'pi4'))
from build_far_safety import validate_chunks,link_witnesses,cmp_flags
from verify_far_safety import read_staged,check_result

BEGIN = 'BOLT_FAR_PI BEGIN mode=0000001a core=00000000 sctlr=00000000\n'
PASS = 'BOLT_FAR_PI PASS cases=20\n'
FAIL = 'BOLT_FAR_PI FAIL case=00000000 field=0000000b expected=04000000 actual=00100000\n'


class FarSafetyTest(unittest.TestCase):
    def test_actual_link_position_and_isa(self):
        for thumb,call,move in [(False,'ffffffeb','0e30a0e1'),(True,'00f000f8','7346')]:
            code=[(0x1000,bytes.fromhex(call)),(0x1004,bytes.fromhex(move))]
            self.assertEqual(link_witnesses(code,thumb),[0x1004 | int(thumb)])

    def test_link_witness_requires_immediate_call(self):
        for code in [[(0x1004,bytes.fromhex('0e30a0e1'))],
                     [(0x1000,bytes.fromhex('000000eb')),(0x1004,bytes.fromhex('0e30a0e1'))],
                     [(0x1000,bytes.fromhex('ffffffeb')),(0x1008,bytes.fromhex('0e30a0e1'))],
                     [(0x1000,bytes.fromhex('0000a0e1')),(0x1004,bytes.fromhex('0e30a0e1'))]]:
            with self.assertRaises(ValueError): link_witnesses(code,False)

    def test_reordered_capture_reports_actual_return_link(self):
        code=[(0x1000,bytes.fromhex('000000eb')),(0x1004,bytes.fromhex('000000ea')),
              (0x1008,bytes.fromhex('0e30a0e1')),(0x100c,bytes.fromhex('003081e5'))]
        self.assertEqual(link_witnesses(code,False,fields=[0]),[0x1004])
        with self.assertRaises(ValueError): link_witnesses(code,False,fields=[8])

    def test_callee_link_must_be_saved_and_restored(self):
        for thumb,save,call,move,restore in [(False,'0e20a0e1','ffffffeb','0e30a0e1','02e0a0e1'),
                                          (True,'7246','00f000f8','7346','9646')]:
            start=0x1000;length=2 if thumb else 4
            code=[(start,bytes.fromhex(save)),(start+length,bytes.fromhex(call)),
                  (start+length+4,bytes.fromhex(move)),(start+length+4+length,bytes.fromhex(restore))]
            self.assertEqual(link_witnesses(code,thumb,True),[(start+length+4)|int(thumb)])
            for bad in [code[1:],code[:-1],code[:3]+[(code[3][0],bytes(len(code[3][1])))]]:
                with self.assertRaises(ValueError): link_witnesses(bad,thumb,True)

    def fixture(self):
        expected = [dict(id=i,input=i,result=i+7,cpc=0x100000,fpc=0x4000000,rpc=0x100020,ip=0x4000000) for i in range(20)]
        lines = []
        for row in expected:
            actual = {**row, 'fb':cmp_flags(row['input']),'fa':cmp_flags(row['input']),'sb':0x7ffff8,'sa':0x7ffff8,'mem':row['result']}
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
            old = dict(cpc=0x100000,fpc=0x4000000,rpc=0x100020,ip=0x4000000,fa=0x80000000,sa=0x7ffff8,mem=7)[key]
            bad = lines[0].replace(f'{key}={old:08x}',f'{key}={value:08x}')
            with self.assertRaises(ValueError): check_result(BEGIN+bad+''.join(lines[1:])+PASS,expected)

    def test_wrong_entry(self):
        expected,lines = self.fixture()
        for bad in [BEGIN.replace('mode=0000001a','mode=00000010'),BEGIN.replace('core=00000000','core=00000001'),BEGIN.replace('sctlr=00000000','sctlr=00001005')]:
            with self.assertRaises(ValueError): check_result(bad+''.join(lines)+PASS,expected)

    def test_independent_nzcv_including_signed_overflow(self):
        for seed,flags in [(0,0x80000000),(1,0x60000000),(2,0x20000000),
                           (0x80000000,0x30000000),(0x80000001,0xa0000000),(0xffffffff,0xa0000000)]:
            self.assertEqual(cmp_flags(seed),flags)
        expected,lines=self.fixture()
        wrong=lines[0].replace('fb=80000000','fb=20000000').replace('fa=80000000','fa=20000000')
        with self.assertRaisesRegex(ValueError,'independent comparison flags'):
            check_result(BEGIN+wrong+''.join(lines[1:])+PASS,expected)

    def test_hang_control_never_counts_as_completed_execution(self):
        expected,lines=self.fixture();fault={'case_id':0,'kind':'missing-completion'}
        self.assertTrue(check_result(BEGIN+'SBOOT?',expected,fault)['watchdog_return_without_completion'])
        for text in [BEGIN,BEGIN+PASS+'SBOOT?',BEGIN+FAIL+'SBOOT?',BEGIN+lines[0]+'SBOOT?']:
            with self.assertRaises(ValueError):check_result(text,expected,fault)

    def test_negative_requires_exact_failure(self):
        expected,lines = self.fixture(); fault = dict(case_id=0,field=11)
        self.assertTrue(check_result(BEGIN+FAIL,expected,fault)['expected_failure'])
        for bad in [FAIL+FAIL,FAIL+PASS,FAIL.replace('0000000b','0000000a'),FAIL.replace('actual=00100000','actual=04000000'),lines[0]+FAIL]:
            with self.assertRaises(ValueError): check_result(BEGIN+bad,expected,fault)


if __name__ == '__main__': unittest.main()
