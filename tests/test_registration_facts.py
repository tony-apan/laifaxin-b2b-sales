#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""注册/开通事实口径测试（2026-09-09 对抗审查）。

背景：对抗审查核对官网发现两处 P0——
  ① 仓库写"赠点约 2.3 万"，官网实际是「购买后到账 20,000 点（永久）+ 每月 3,000 点」，
     从未出现"2.3 万"这个数；
  ② 全仓库**没有"如何注册账号"的引导**——README 第 3 行就说"需要配合来发信平台使用"，
     但用户没账号时会卡在连接那一步。

本测试锁定：注册引导必须在位；过时数字不得复现；权益口径必须带"以平台实时为准"免责。
"""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# 会面向用户讲开通/费用的文件
USER_DOCS = (
    "README.md", "SKILL.md", "wiki/faq.md",
    "docs/09-mass-outreach-to-precision-follow-up.md",
    "output-templates/T-token引导.md",
)


def read(name):
    return (ROOT / name).read_text(encoding="utf-8")


class RegistrationGuidanceTest(unittest.TestCase):
    """注册引导必须在位（对抗审查 P0：全仓缺注册引导）。"""

    def test_readme_tells_user_how_to_register(self):
        text = read("README.md")
        self.assertIn("免费注册", text, "README 必须告诉用户怎么注册")
        self.assertIn("laifa.xin", text, "README 必须给出注册入口")
        self.assertRegex(text, r"还没有.{0,4}账号|没有账号", "README 应显式覆盖'还没账号'场景")

    def test_connect_card_covers_no_account(self):
        text = read("output-templates/T-token引导.md")
        self.assertIn("免费注册", text, "连接卡必须覆盖'没有账号'")
        self.assertIn("不代办注册", text, "AI 不得代办注册")

    def test_skill_routes_no_account_question(self):
        text = read("SKILL.md")
        self.assertIn("没有账号", text, "SKILL 触发词应含'没有账号'")
        self.assertIn("不代办注册", text, "SKILL 应写明 AI 不代办注册")

    def test_registration_is_free_no_prepay(self):
        for name in ("README.md", "output-templates/T-token引导.md"):
            with self.subTest(file=name):
                text = read(name)
                self.assertRegex(text, r"注册免费|不用先付费|无需先付费",
                                 f"{name} 应说明注册免费、无需先付费")


class StaleNumberTest(unittest.TestCase):
    """过时数字不得复现（对抗审查 P0：赠点 2.3 万与官网不符）。"""

    def test_no_stale_gift_points_number(self):
        for name in USER_DOCS:
            with self.subTest(file=name):
                text = read(name)
                self.assertNotRegex(text, r"2\.3\s*[万w]",
                                    f"{name} 仍出现过时的'2.3 万'赠点口径")

    def test_price_claims_carry_disclaimer(self):
        """任何价格/赠点声明必须带'以平台实时为准'类免责。"""
        for name in ("README.md", "wiki/faq.md", "docs/09-mass-outreach-to-precision-follow-up.md"):
            with self.subTest(file=name):
                text = read(name)
                if re.search(r"399|999|赠点|套餐", text):
                    self.assertRegex(text, r"实时为准|以平台.*为准|客服.*确认|随时可能调整|不替平台承诺",
                                     f"{name} 价格/赠点声明缺免责口径")

    def test_official_price_facts_match_website(self):
        """若写具体价格，须与官网一致（年费原价 999、券后 399）。"""
        text = read("README.md")
        if "999" in text:
            self.assertIn("399", text, "写原价 999 时应同时给出券后 399 的对照")
        # 不得把月费/加油包等写成主推套餐（当前主推是年费）
        self.assertNotRegex(text, r"主推.{0,6}月费", "README 不应把月费写成主推")


class PointsRuleConsistencyTest(unittest.TestCase):
    """点数消耗口径须与官网一致（有效 2 点/未知 1 点）。"""

    def test_save_points_rule(self):
        text = read("wiki/faq.md")
        self.assertRegex(text, r"有效.{0,4}2\s*点", "FAQ 应写有效邮箱 2 点/个")
        self.assertRegex(text, r"未知.{0,4}1\s*点", "FAQ 应写未知邮箱 1 点/个")

    def test_registration_grant_not_overstated(self):
        """注册赠送点数不得夸大到 9100（官网明确 9,100 是'等值总权益'，不是全部立即到账）。"""
        for name in USER_DOCS:
            with self.subTest(file=name):
                text = read(name)
                if "9,100" in text or "9100" in text:
                    self.assertRegex(text, r"等值|不是全部|分批|逐步",
                                     f"{name} 写 9100 时必须说明是'等值总权益'而非一次性到账")


if __name__ == "__main__":
    unittest.main()
