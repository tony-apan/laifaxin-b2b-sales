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


class SaveUXTest(unittest.TestCase):
    def test_s7_each_sample_has_rationale(self):
        text = (ROOT / "output-templates" / "S7-template-confirm.md").read_text(encoding="utf-8")
        self.assertIn("这封的用意", text)
        self.assertIn("没有说明的样稿不许发出去", text)

    def test_s6_requires_progress_broadcast(self):
        text = (ROOT / "output-templates" / "S6-count-report.md").read_text(encoding="utf-8")
        for needed in ("save_company_cli.py status", "--watch", "转播给用户", "数字未知", "不编造扣点"):
            self.assertIn(needed, text)


class AnnounceBeforeActTest(unittest.TestCase):
    def test_beginner_flow_has_rule(self):
        text = (ROOT / "specs" / "beginner-flow.md").read_text(encoding="utf-8")
        self.assertIn("先报后做", text)
        self.assertIn("最多扣多少点", text)

    def test_contract_has_rule(self):
        text = (ROOT / "specs" / "novice-flow-contract.md").read_text(encoding="utf-8")
        self.assertIn("先报后做", text)

class EntryOrderConnectFirstTest(unittest.TestCase):
    """2026-10-27 用户裁决：连接是第一业务动作；连接成功后才问昵称+产品并直出档案。"""

    def test_token_guide_shown_after_install_not_after_profile(self):
        text = (ROOT / "output-templates" / "T-token-guide.md").read_text(encoding="utf-8")
        self.assertNotIn("产品档案确认之后", text, "连接卡不得再以档案确认为前置")
        self.assertIn("安装自检通过后", text, "连接时机=安装自检通过后（第一业务动作）")

    def test_profile_after_connect_and_asks_customer_url(self):
        profile = (ROOT / "output-templates" / "S0-product-profile.md").read_text(encoding="utf-8")
        self.assertNotIn("我请您连接来发信账号", profile,
                         "档案卡不得再说『确认后连接』——连接已在其前完成")
        self.assertIn("目标客户", profile, "档案展示后须问有没有目标客户网址（客户，不是自己官网）")


if __name__ == "__main__":
    unittest.main()
