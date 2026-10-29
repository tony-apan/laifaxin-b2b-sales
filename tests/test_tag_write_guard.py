import sys, unittest
from pathlib import Path
from unittest.mock import patch, MagicMock
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
import tag_write_guard
import platform_http

class TagWriteGuardTest(unittest.TestCase):
    def test_dangerous_path_variants_rejected(self):
        for path in ('tags/tag-delete','/api/tags/tag-delete/','TAGS/TAG-DELETE','tags/folder-delete','contacts/contacts/update','contacts/contacts/batch-update','api/contacts/contacts/batch-update','tags//tag-delete','tags/../tags/tag-delete','tags/%74ag-delete','tags/tag-delete?x=1'):
            with self.subTest(path=path), self.assertRaises(ValueError):
                tag_write_guard.check_send(path, {'tags': []})

    def test_safe_paths_allowed(self):
        for path in ('contacts/tags-list','contacts/tags-add','contacts/tags-dirs','tags/tag-add','tags/folder-add','tags/folder-list','tags/tag-fav-delete','contacts/contacts/show','contacts/contacts/save','sequences/contact-add'):
            with self.subTest(path=path):
                self.assertIsNone(tag_write_guard.check_send(path, {}))

    def test_unknown_tag_and_contact_writes_default_rejected(self):
        for path in ('tags/tag-wipe','tags/tag-purge','contacts/tags-reset','contacts/contacts/replace','contacts/contacts/delete','tags/unknown-write'):
            with self.subTest(path=path), self.assertRaises(ValueError):
                tag_write_guard.check_send(path, {})

    def test_unknown_append_create_attach_rejected_before_http_open(self):
        for path in ('contacts/tags-append','contacts/tags-create','contacts/tags-attach'):
            with self.subTest(path=path), patch.object(platform_http,'_apply_test_base'), patch.object(platform_http.urllib.request,'build_opener') as opener:
                with self.assertRaises(ValueError):
                    platform_http.post(path, {'tags':['t']}, 'fake', 'fake')
                opener.assert_not_called()

    def test_all_actual_sender_paths_still_allowed(self):
        import re
        names=('platform_http','tag_add','build_sequence','contact_add_authorized','activate_sequence','gen_templates','rebuild_templates','verify_sequence','flow_orchestrator','save_company_cli','search_company','save_budget','company_page_report','workspace_guard','resolve_schedule','seed_resolve','segments_infer','tag_check','verify_exclude','wait_save_done','audit_company','find_critical','find_threshold')
        paths=set()
        for name in names:
            text=(ROOT/'tools'/(name+'.py')).read_text(encoding='utf-8')
            paths.update(re.findall(r'(?:api|_api)\(\s*["\']([^"\']+)["\']', text))
            paths.update(re.findall(r'laifaxin\.com/api/([A-Za-z0-9_/-]+)', text))
        paths.update({'account/current','benefits/refine-data','refine/company-save','operation/backend-task-status','contacts/contacts/save','contacts/contacts/show'})
        for path in sorted(paths):
            with self.subTest(path=path):
                self.assertIsNone(tag_write_guard.check_send(path, {}))

    def test_tag_save_only_exact_rename_fields(self):
        self.assertIsNone(tag_write_guard.check_send('tags/tag-save', {'type':'company','id':'a'*24,'name':'新名'}))
        for payload in ({'type':'company','id':'a'*24,'name':'新名','tags':[]},
                        {'type':'company','id':'','name':'新名'},
                        {'type':'company','id':'a'*24,'name':''},
                        {'type':'company','id':'a'*24,'name':None},
                        {'type':'company','id':'a'*24}):
            with self.subTest(payload=payload), self.assertRaises(ValueError):
                tag_write_guard.check_send('tags/tag-save', payload)
        with self.assertRaises(ValueError):
            tag_write_guard.check_send('contacts/tags-save', {'type':'company','id':'a','name':'n'})

    def test_contact_add_views_empty_not_blocked(self):
        self.assertIsNone(tag_write_guard.check_send('sequences/contact-add', {'seqId':'a'*24,'tags':['t'],'views':[]}))

    def test_platform_http_danger_never_opens(self):
        for path in ('tags/tag-delete','tags/folder-delete','contacts/contacts/update','contacts/contacts/batch-update'):
            with self.subTest(path=path), patch.object(platform_http,'_apply_test_base'), patch.object(platform_http.urllib.request,'build_opener') as opener:
                with self.assertRaises(ValueError):
                    platform_http.post(path, {'tags': [], 'selectOption': 'all'}, 'fake', 'fake')
                opener.assert_not_called()

    def test_active_senders_are_wired_before_send(self):
        for rel in ('tools/platform_http.py','tools/tag_add.py','tools/build_sequence.py','tools/contact_add_authorized.py','tools/activate_sequence.py','tools/gen_templates.py','tools/rebuild_templates.py','tools/verify_sequence.py','tools/flow_orchestrator.py','tools/save_company_cli.py','tools/search_company.py','tools/save_budget.py','tools/company_page_report.py','tools/workspace_guard.py','tools/resolve_schedule.py','tools/seed_resolve.py','tools/segments_infer.py','tools/tag_check.py','tools/verify_exclude.py','tools/wait_save_done.py','tools/audit_company.py','tools/find_critical.py','tools/find_threshold.py'):
            with self.subTest(rel=rel):
                text=(ROOT/rel).read_text(encoding='utf-8')
                self.assertIn('tag_write_guard', text, rel)
                self.assertIn('check_send(', text, rel)
                guard=text.index('check_send(')
                token = '_OPENER.open(' if rel.endswith('company_page_report.py') else ('build_opener(' if rel.endswith('platform_http.py') else ('subprocess.run(' if 'subprocess.run(' in text else 'urlopen('))
                self.assertLess(guard, text.index(token), rel+' 必须先过 guard 再发送')

    def test_explicit_fixture_copies_include_guard_dependency(self):
        for path in (ROOT/'tests').glob('test_*.py'):
            text=path.read_text(encoding='utf-8')
            copies_named_tools = ('shutil.copy2(TOOLS / name' in text or 'shutil.copy2(ROOT / "tools" / name' in text)
            if not copies_named_tools or 'workspace_guard.py' not in text:
                continue
            with self.subTest(test=path.name):
                self.assertIn('tag_write_guard.py', text, path.name+' 临时复制 workspace_guard 时必须带 tag_write_guard')

    def test_platform_http_valid_rename_is_sent(self):
        with patch.object(platform_http,'_apply_test_base'), patch.object(platform_http.urllib.request,'build_opener') as opener:
            response=MagicMock(); response.__enter__.return_value.read.return_value=b'{}'
            opener.return_value.open.return_value=response
            payload={'type':'contacts','id':'tag-1','name':'测试标签'}
            self.assertEqual('{}',platform_http.post('tags/tag-save',payload,'fake','fake'))
            opener.return_value.open.assert_called_once()

if __name__=='__main__':
    unittest.main()
