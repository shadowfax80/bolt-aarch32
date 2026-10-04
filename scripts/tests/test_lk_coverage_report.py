"""A diagnostic must be complete and bound to the input before it supplies skips."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lk_coverage_report import read_admission_report


class AdmissionReportTests(unittest.TestCase):
    def fixture(self):
        return dict(schema=1, kind='aarch32-admission-diagnostic', complete=True,
                    execution_verified=False, input_sha256='a'*64,
                    admitted=1, rejected=1, not_analyzed=1,
                    functions=[dict(name='good', address=0x8000, isa='A32', status='admitted'),
                               dict(name='bad/1', address=0x8008, isa='T32', status='rejected',
                                    stage='cfg', reason='unmodeled fallthrough'),
                               dict(name='selected_out', address=0x8010, isa='A32', status='not-analyzed')])

    def parse(self, report, expected='a'*64):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'report.json';p.write_text(json.dumps(report),encoding='utf-8')
            return read_admission_report(p,expected)

    def test_only_rejections_supply_explicit_skips(self):
        self.assertEqual(self.parse(self.fixture()),(['bad/1'],{'bad/1':'unmodeled fallthrough'}))

    def test_failures_and_certificates_cannot_supply_skips(self):
        for key, value in [('schema',2),('schema',True),('kind','certificate'),('complete',False),
                           ('execution_verified',True),('input_sha256','b'*64),
                           ('admitted',2),('rejected',True),('not_analyzed',0),('functions',None)]:
            with self.subTest(key=key):
                r=self.fixture();r[key]=value
                with self.assertRaises(ValueError):self.parse(r)
        for malformed in [None, [], 1, 'report']:
            with self.subTest(malformed=malformed):
                with self.assertRaises(ValueError):self.parse(malformed)
        for malformed in [None, [], 1, 'function']:
            with self.subTest(row=malformed):
                r=self.fixture();r['functions'][1]=malformed
                with self.assertRaises(ValueError):self.parse(r)

    def test_ambiguous_and_unframed_names_reject(self):
        for key,value in [('name','good'),('name','bad,good'),('name','bad\ngood'),
                          ('address',0x8000),('address',-1),('address',True),
                          ('address',0x100000000),('isa','unknown'),('status','rewritten'),
                          ('stage','emission'),('reason','')]:
            with self.subTest(key=key,value=value):
                r=self.fixture();r['functions'][1][key]=value
                with self.assertRaises(ValueError):self.parse(r)

    def test_shared_duplicate_is_not_an_extra_function(self):
        r=self.fixture();r['functions'].append(copy.deepcopy(r['functions'][1]));r['rejected']=2
        with self.assertRaises(ValueError):self.parse(r)


if __name__=='__main__':unittest.main()
