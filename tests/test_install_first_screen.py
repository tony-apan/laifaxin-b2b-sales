#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""安装首屏口径（2026-10-23 用户裁决）：刚装好直接问昵称+产品，不出菜单、不要数字。"""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def read(rel):
    return (ROOT / rel).read_text(encoding="utf-8")


def blocks(text):
    return re.findall(r"```[a-zA-Z]*\n(.*?)```", text, re.S)


class InstallFirstScreenTest(unittest.TestCase):
    def test_install_report_asks_two_things_not_menu(self):
        text = read("output-templates/S0-install-report.md")
        new_user = text.split("## 话术（新用户", 1)[1].split("## 话术（老用户", 1)[0]
        self.assertIn("怎么称呼您", new_user, "新用户话术必须问昵称")
        self.assertIn("卖什么产品", new_user, "新用户话术必须问产品")
        self.assertNotIn("回复数字", new_user, "新用户话术不得要求回数字")
        self.assertNotIn("开始新的获客项目", new_user, "新用户话术不得列出任务菜单")

    def test_task_menu_is_history_only(self):
        text = read("output-templates/S0-task-menu.md")
        self.assertIn("有旧项目", text)
        self.assertNotIn("## 无旧项目时", text, "新用户不应再看到任务菜单")

    def test_readme_says_two_things_first(self):
        text = read("README.md")
        self.assertIn("先问你两样", text, "README 应写清装完先问昵称+产品")
        self.assertNotIn("6. 最后只问我：“安装完成。你现在想做什么？”", text, "旧口径已废弃")

    def test_rules_and_skill_share_new_rule(self):
        for name in ("RULES.md", "SKILL.md"):
            text = read(name)
            with self.subTest(file=name):
                self.assertIn("不展示菜单", text, f"{name} 应写清新用户不展示菜单")
                self.assertIn("昵称 + 产品", text, f"{name} 应写清只问昵称+产品")

    def test_onboard_check_no_menu_for_new_users(self):
        source = read("tools/onboard_check.py")
        self.assertRegex(source, r"本次未检测到旧项目.*?不展示菜单", "onboard_check 新用户分支不得输出菜单")
        self.assertIn("S0-opening-questions.md C1 只问两样", source)

    def test_opening_gate_contract(self):
        import sys
        sys.path.insert(0, str(ROOT / "tools"))
        import opening_gate
        decision = opening_gate.decide_opening([])
        self.assertEqual("new", decision["mode"])
        self.assertEqual(["昵称", "产品"], decision["ask"])
        self.assertEqual([], decision["options"])


if __name__ == "__main__":
    unittest.main()