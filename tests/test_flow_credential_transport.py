import importlib.util
import json
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
FLOW = ROOT / "tools" / "flow_orchestrator.py"


class FlowCredentialTransportStaticTest(unittest.TestCase):
    def test_login_subprocess_uses_stdin_not_token_argv(self):
        source = FLOW.read_text(encoding="utf-8")
        self.assertIn('"--credentials-stdin"', source)
        self.assertIn("input=credentials_blob", source)
        self.assertNotIn('"check_login.py"), "--token", args.token', source)

    def test_api_uses_urllib_not_curl_header_argv(self):
        source = FLOW.read_text(encoding="utf-8")
        api_start = source.index("def api(")
        api_end = source.index("\nLOGIN_GUIDE_URL", api_start)
        api_source = source[api_start:api_end]
        self.assertIn("_urlrequest.Request", api_source)
        self.assertIn('"accesstoken": args.token', api_source)
        self.assertNotIn("subprocess", api_source)
        self.assertNotIn('"curl"', api_source)


if __name__ == "__main__":
    unittest.main()
