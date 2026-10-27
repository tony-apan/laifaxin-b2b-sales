# -*- coding: utf-8 -*-
"""批2-B 守卫：连接首选自动化 + 先报后做（2026-10-27 用户裁决）。"""
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


class ConnectCardTest(unittest.TestCase):
    def setUp(self):
        self.text = (ROOT / "output-templates" / "T-token-guide.md").read_text(encoding="utf-8")

    def test_auto_login_is_default(self):
        self.assertIn("首选：自动连接", self.text)
        self.assertIn("browser_login.py", self.text)
        self.assertIn("禁止一上来就让用户贴控制台代码", self.text)

    def test_manual_path_kept_as_fallback(self):
        for needed in ("控制台", "accesstoken", "orgId"):
            self.assertIn(needed, self.text)


class AnnounceBeforeActTest(unittest.TestCase):
    def test_beginner_flow_has_rule(self):
        text = (ROOT / "specs" / "beginner-flow.md").read_text(encoding="utf-8")
        self.assertIn("先报后做", text)
        self.assertIn("最多扣多少点", text)

    def test_contract_has_rule(self):
        text = (ROOT / "specs" / "novice-flow-contract.md").read_text(encoding="utf-8")
        self.assertIn("先报后做", text)


if __name__ == "__main__":
    unittest.main()
