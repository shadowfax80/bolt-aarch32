import sys
from pathlib import Path
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'pi4'))
from verify_inline_safety import check_result

BEGIN='BOLT_INLINE_STATE BEGIN mode=0000001a core=00000000\n'
PASS='BOLT_INLINE_STATE PASS cases=55\n'
FAIL='BOLT_INLINE_STATE FAIL case=00000000 field=00000000 expected=00000012 actual=00000013\n'

class ResultTests(unittest.TestCase):
    def test_complete(self):
        self.assertEqual(check_result(BEGIN+PASS),dict(passed=True,cases=55))
    def test_fault(self):
        self.assertTrue(check_result(BEGIN+FAIL,dict(case_id=0,field=0))['expected_failure'])
    def test_incomplete(self):
        for text in [BEGIN,BEGIN+PASS.replace('55','54'),PASS,BEGIN+FAIL,BEGIN+PASS+PASS,BEGIN+BEGIN+PASS]:
            with self.subTest(text=text),self.assertRaises(ValueError):check_result(text)
    def test_fault_wrong_location(self):
        for text in [BEGIN+PASS,BEGIN+FAIL.replace('case=00000000','case=00000001'),BEGIN+FAIL+PASS]:
            with self.subTest(text=text),self.assertRaises(ValueError):check_result(text,dict(case_id=0,field=0))
    def test_bad_markers(self):
        for text in [BEGIN+PASS+'BOLT_INLINE_STATE FAIL corrupt\n',BEGIN+PASS+'BOLT_INLINE_STATE PASS corrupt\n',BEGIN+PASS+'BOLT_INLINE_STATE BEGIN corrupt\n']:
            with self.subTest(text=text),self.assertRaises(ValueError):check_result(text)

if __name__=='__main__':unittest.main()
