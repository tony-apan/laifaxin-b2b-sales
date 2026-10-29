#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""TASK-20261028-interface-A 永久回归：S12 否定/条件/修改句先于正向词。

覆盖 A3：
  - "确认激活，别开始"/"先别开始，确认激活" 在签发 CLI 与执行函数均拒绝、0审批；
  - 条件/等待/修改句同样拒绝；
  - "确认激活 不锈钢-S04""我考虑清楚了，确认激活" 等合法场景不得误杀。
"""
import ast
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT))

from approval import confirm_quote_ok  # noqa: E402
import tests.test_s12_resume as s12_resume  # noqa: E402


def _execution_check_confirm():
    """按 AST 抽取 activate_sequence.check_confirm，避免 import 触发 CLI 副作用。"""
    src = (ROOT / "tools/activate_sequence.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    fn = next(n for n in tree.body
              if isinstance(n, ast.FunctionDef) and n.name == "check_confirm")
    mod = ast.fix_missing_locations(ast.Module(body=[fn], type_ignores=[]))
    import approval
    env = {"_re": re, "confirm_quote_ok": confirm_quote_ok,
           "authorize_quote": approval.authorize_quote, "reservation": approval.reservation}
    exec(compile(mod, "activate_sequence.py", "exec"), env)
    return env["check_confirm"]


class S12SigningRejectsMixedIntentTest(unittest.TestCase):
    """复用现有 S12 临时仓库夹具，不修改其文件。"""

    def setUp(self):
        self.case = s12_resume.ResumeS12Test(
            methodName="test_explicit_activation_issues_schema_bound_approval_and_keeps_s11")
        self.case.setUp()
        self.addCleanup(self.case.doCleanups)

    def test_negated_start_quote_issues_no_credential(self):
        rc, out = self.case.run_tty("确认激活，别开始")
        self.assertNotEqual(0, rc, out)
        self.assertEqual([], self.case.approval_rows(), "否定开始指令不得签发 S12 凭证")

    def test_wait_before_start_quote_issues_no_credential(self):
        rc, out = self.case.run_tty("先别开始，确认激活")
        self.assertNotEqual(0, rc, out)
        self.assertEqual([], self.case.approval_rows())

    def test_conditional_quote_issues_no_credential(self):
        rc, out = self.case.run_tty("确认激活，等我确认后再开始")
        self.assertNotEqual(0, rc, out)
        self.assertEqual([], self.case.approval_rows())

    def test_clean_activation_quotes_not_false_killed(self):
        rc, out = self.case.run_tty("确认激活 不锈钢-S04")
        self.assertNotEqual(0, rc, out)
        rows = self.case.approval_rows()
        self.assertEqual([], rows, "无可信目标名称不得签发审批")

    def test_uncertain_activation_quotes_issue_no_credential(self):
        for quote in ("大概可以，确认激活", "不太确定，确认激活", "可能可以，确认激活"):
            with self.subTest(quote=quote):
                rc, out = self.case.run_tty(quote)
                self.assertNotEqual(0, rc, out)
                self.assertEqual([], self.case.approval_rows(), quote)

    def test_considered_clear_quote_not_false_killed(self):
        rc, out = self.case.run_tty("我考虑清楚了，确认激活")
        self.assertEqual(0, rc, out)
        self.assertEqual(1, len(self.case.approval_rows()))


class S12ExecutionRejectsMixedIntentTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.check = staticmethod(_execution_check_confirm())

    def test_negated_start_rejected(self):
        for quote in ("确认激活，别开始", "确认激活;别开始", "确认激活。先等等",
                      "先别开始，确认激活", "确认激活，不要开始",
                      "确认激活，先等等", "确认激活，等我确认后再开始",
                      "确认激活,等我确认后再开始"):
            with self.subTest(quote=quote):
                ok, why = self.check(quote, "激活", required_phrase="确认激活", sequence_name="不锈钢-S04")
                self.assertFalse(ok, quote)
                self.assertTrue(why)

    def test_uncertain_activation_rejected(self):
        for quote in ("大概可以，确认激活", "不太确定，确认激活", "可能可以，确认激活"):
            with self.subTest(quote=quote):
                ok, why = self.check(quote, "激活", required_phrase="确认激活", sequence_name="不锈钢-S04")
                self.assertFalse(ok, quote)
                self.assertTrue(why)

    def test_modification_after_confirmation_rejected(self):
        ok, why = self.check("确认激活，改成明天开始", "激活", required_phrase="确认激活")
        self.assertFalse(ok)
        self.assertTrue(why)

    def test_clean_quotes_not_false_killed(self):
        for quote in ("确认激活", "确认激活 不锈钢-S04", "我考虑清楚了，确认激活"):
            with self.subTest(quote=quote):
                ok, why = self.check(quote, "激活", required_phrase="确认激活", sequence_name="不锈钢-S04")
                self.assertTrue(ok, f"{quote}: {why}")


if __name__ == "__main__":
    unittest.main()
