import sys, unittest
from pathlib import Path
from unittest.mock import patch, MagicMock
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'tools'))
import platform_http

class TagMutationGuardTest(unittest.TestCase):
    def test_dangerous_paths_never_open_http(self):
        for path in ('tags/tag-delete','tags/folder-delete','contacts/contacts/update','contacts/contacts/batch-update'):
            with self.subTest(path=path), patch.object(platform_http, '_apply_test_base'), patch.object(platform_http.urllib.request, 'build_opener') as opener:
                with self.assertRaises(ValueError):
                    platform_http.post(path, {'tags': []}, 'fake', 'fake')
                opener.assert_not_called()

    def test_existing_safe_paths_are_allowed(self):
        for path in ('contacts/contacts/show','sequences/contact-add','sequences/sequence-save','tags/tag-save'):
            payload = {'type': 'contacts', 'id': 'tag-1', 'name': '测试标签'} if path == 'tags/tag-save' else {}
            with self.subTest(path=path), patch.object(platform_http, '_apply_test_base'), patch.object(platform_http.urllib.request, 'build_opener') as opener:
                response=MagicMock(); response.__enter__.return_value.read.return_value=b'{}'
                opener.return_value.open.return_value=response
                self.assertEqual('{}',platform_http.post(path, payload, 'fake', 'fake'))
                opener.return_value.open.assert_called_once()
