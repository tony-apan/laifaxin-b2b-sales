import importlib.util
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import approval
from tests.test_confirmation_intent_regressions import R3ReselectListConfirmTest

class QuoteStorageTest(unittest.TestCase):
    def test_exact_quote_roundtrip_and_legacy_row(self):
        import tempfile
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as tmp:
            ledger=Path(tmp)/'approvals.tsv'
            ledger.write_text('id\tproject_id\tstate\tdecision\tuser_quote\tmemo\ttime\tstatus\nold\tp\tS9\tconfirm\t旧确认\th\tt\tconfirmed\n',encoding='utf-8-sig')
            quote='  原话\t含制表\n第二行  ' + '长'*1100
            with patch.object(approval,'APPROVALS',ledger):
                aid=approval.record('p','S9','confirm',quote,'hash')
                rows=approval._rows()
                self.assertEqual('旧确认',rows[0]['user_quote'])
                self.assertEqual(quote,next(row for row in rows if row['id']==aid)['user_quote'])
                approval._main(['demote-migrated','--confirm','MIGRATION-DEMOTE'])
                rows=approval._rows()
                self.assertEqual('旧确认',rows[0]['user_quote'])
                self.assertEqual(quote,next(row for row in rows if row['id']==aid)['user_quote'])

class RealProfileQuoteTest(unittest.TestCase):
    def test_original_quote_survives_profile_roundtrip(self):
        import tempfile, subprocess
        from tests.test_confirmation_intent_regressions import ProductProfileMixedIntentTest
        fixture=ProductProfileMixedIntentTest()
        with tempfile.TemporaryDirectory() as tmp:
            profile, env=fixture._init_profile(tmp)
            quote='  确认\t\n  ' + '。'*600
            result=fixture._confirm(profile, quote, env)
            self.assertEqual(0,result.returncode,result.stdout+result.stderr)
            from profile_utils import read_profile
            metadata, _ = read_profile(profile)
            self.assertEqual(quote, json.loads(metadata['confirm_quote_json']))

class WebsiteQuoteTest(unittest.TestCase):
    def setUp(self):
        from tests.test_website_profile import WebsiteProfileTest
        self.case=WebsiteProfileTest(methodName='test_base_hash_drift')
        self.case.setUp()
        self.addCleanup(self.case.tearDown)

    def test_selection_commands_never_approve_existing_patch(self):
        for i, quote in enumerate(('全部导入','只要公司资料','只要产品资料','只保存事实')):
            with self.subTest(quote=quote):
                patch=self.case.make_patch(name=f'p{i}.json')
                before=patch.read_bytes()
                result=self.case.approve(patch,quote=quote)
                self.assertNotEqual(0,result.returncode,result.stdout+result.stderr)
                self.assertEqual(before,patch.read_bytes())

    def test_confirmation_preserves_raw_quote(self):
        patch=self.case.make_patch()
        quote='  确认\t\n ' + '。'*600
        result=self.case.approve(patch,quote=quote)
        self.assertEqual(0,result.returncode,result.stdout+result.stderr)
        self.assertEqual(quote,json.loads(patch.read_text())['approval']['approved_quote'])

class PublicTicketTest(unittest.TestCase):
    def test_direct_save_authorize_cannot_swap_original_quote(self):
        import tempfile
        from unittest.mock import patch
        import auth_guard
        payload={'selectTotal':100}
        plan={'status':'confirmed','quote':'确认','wire_payload':payload,'count_bound_by':'card','count_bound_n':100}
        with tempfile.TemporaryDirectory() as tmp, patch.object(auth_guard,'_require_startup_ack',lambda:None):
            result=auth_guard.authorize('save','确认保存前100家，换一批',payload,plan=plan,root=tmp)
            self.assertFalse(result['ok'], result)

class LegacyQuotePrefixTest(unittest.TestCase):
    def test_legacy_quote_that_looks_encoded_remains_literal(self):
        import tempfile
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as tmp:
            ledger=Path(tmp)/'approvals.tsv'
            ledger.write_text('id\tproject_id\tstate\tdecision\tuser_quote\tmemo\ttime\tstatus\nap-1\tp\tS9\tconfirm\t@quote-json-v1:"hello"\th\tt\tconfirmed\n',encoding='utf-8-sig')
            with patch.object(approval,'APPROVALS',ledger):
                self.assertEqual('@quote-json-v1:"hello"',approval._rows()[0]['user_quote'])

class QuoteContractTest(unittest.TestCase):
    def test_state_and_binding_closed_set(self):
        cases = [
            ('确认，换一批','S9',{},False), ('确认，重选一批','S9',{},False),
            ('确认，重新挑一批','S9',{},False), ('确认，名单要重新选','S9',{},False),
            ('确认，认证改成暂无','PROFILE',{},False), ('确认保存前5家，邮箱改成6个','S5',{'count':5},False),
            ('确认激活，别开始','S12',{},False), ('确认，任意尾随','S9',{},False),
            ('1','UNKNOWN',{},False), ('20','S5',{},False), ('1','S5',{'count':20},False),
            ('确认，产品是不锈钢杯','PROFILE',{},False),
            ('确认，产品是不锈钢杯','PROFILE',{'product_name':'不锈钢杯'},True),
            ('确认激活 不锈钢-S04','S12',{},False),
            ('确认激活 不锈钢-S04','S12',{'sequence_name':'不锈钢-S04'},True),
            ('确认，产品是杯子？','PROFILE',{'product_name':'杯子？'},False),
            ('确认激活 杯子？','S12',{'sequence_name':'杯子？'},False),
            ('确认激活？','S12',{},False), ('确认激活','S12',{},True),
            ('我考虑清楚了，确认激活','S12',{},True), ('1','S9',{},True),
            ('确认','S9',{},True), ('1','S8',{},True), ('1，修改模板','S8',{},False), ('20','S5',{'count':20},True),
        ]
        for quote,state,binding,expected in cases:
            with self.subTest(quote=quote,state=state):
                self.assertEqual(expected, approval.authorize_quote(quote,state,binding))

class BundleQuoteBindingTest(R3ReselectListConfirmTest):
    def test_modified_quote_cannot_create_s10_approval(self):
        path, doc = self.case.prepare()
        result = self.case.confirm(path, doc, quote='1')
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        bundle = json.loads(Path(path).read_text())
        bundle['confirmation']['quote'] = '确认，换一批'
        Path(path).write_text(json.dumps(bundle, ensure_ascii=False), encoding='utf-8')
        before = list(self.case.approval_rows())
        result = self.case.cli('execute', '--bundle', path, creds=__import__('tests.test_sequence_contact_bundle', fromlist=['CREDS']).CREDS)
        self.assertNotEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertEqual(before, list(self.case.approval_rows()))
        self.assertEqual([], self.case.stub.calls('sequences/sequence-create'))

class RealBundleR4Test(R3ReselectListConfirmTest):
    def test_unbounded_reselection_keeps_prepared_and_no_approval(self):
        for quote in ('确认，换一批','确认，重选一批','确认，重新挑一批','确认，任意尾随'):
            with self.subTest(quote=quote):
                path,doc=self.case.prepare()
                before=list(self.case.approval_rows())
                result=self.case.confirm(path,doc,quote=quote)
                self.assertNotEqual(0,result.returncode,result.stdout+result.stderr)
                self.assertEqual('prepared',json.loads(Path(path).read_text())['status'])
                self.assertEqual(before,list(self.case.approval_rows()))
                self.assertEqual([],self.case.stub.log)
