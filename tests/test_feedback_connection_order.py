import sys, unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import browser_login as b

class ConnectOrderTest(unittest.TestCase):
    def test_existing_session_first(self):
        with patch.object(b,'load_ready',return_value=('web.laifaxin.com','fake','fake')) as existing, patch.object(b,'execute') as visible:
            code, result=b.connect_preferred()
            self.assertEqual(0,code); self.assertEqual('session',result['source']); existing.assert_called_once(); visible.assert_not_called()

    def test_no_session_tries_visible_before_manual(self):
        with patch.object(b,'load_ready',side_effect=FileNotFoundError()), patch.object(b,'execute',return_value=(0,{'workspace':'verified'})) as visible:
            code,result=b.connect_preferred()
            self.assertEqual(0,code); self.assertEqual('visible',result['source']); visible.assert_called_once()

    def test_visible_failure_offers_manual_with_reason(self):
        with patch.object(b,'load_ready',side_effect=FileNotFoundError()), patch.object(b,'execute',side_effect=b.Failure(11,'launch','E_LAUNCH')):
            code,result=b.connect_preferred()
            self.assertNotEqual(0,code); self.assertEqual('manual',result['next']); self.assertEqual('unknown',result['window_opened']); self.assertEqual('E_LAUNCH',result['reason'])

    def test_awaiting_login_does_not_request_manual(self):
        with patch.object(b,'load_ready',side_effect=b.SessionError('E_NO_SESSION','missing')), patch.object(b,'execute',side_effect=b.Failure(10,'read','E_NO_TOKEN')):
            code,result=b.connect_preferred()
            self.assertNotEqual(0,code); self.assertEqual('awaiting_login',result['next']); self.assertNotEqual('manual',result['next'])

    def test_conflict_stops_without_manual_or_launch(self):
        with patch.object(b,'load_ready',side_effect=b.SessionError('E_VERIFY_TRANSIENT','temporary')), patch.object(b,'execute') as visible:
            code,result=b.connect_preferred()
            self.assertNotEqual(0,code); self.assertEqual('stop',result['next']); visible.assert_not_called()
