# -*- coding: utf-8 -*-
"""回归：确认卡话术是「回 1」时，S7/S9/S10 的纯数字 1 必须能铸造审批凭证。

2026-10-26 真机卡点：建序列按卡让用户回 1，approval.py 却只认 S7 的数字，
导致合法确认被拒。S5 仍要求「确认保存 前 N 家」这类带数量的原话（避免只回数字漏掉数量）。
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
from approval import confirm_quote_ok, numeric_confirm_quote


class NumericConfirmQuoteTest(unittest.TestCase):
    def test_s7_s9_s10_accept_plain_one(self):
        for state in ("S7_模板预览", "S9_序列配置", "S10_加联系人"):
            with self.subTest(state=state):
                self.assertTrue(numeric_confirm_quote("1", state))
                self.assertTrue(numeric_confirm_quote("①", state))

    def test_other_states_reject_plain_one(self):
        for state in ("S5_保存参数", "S12_激活", "S2_客群确认"):
            with self.subTest(state=state):
                self.assertFalse(numeric_confirm_quote("1", state))

    def test_numeric_only_for_positive_one(self):
        self.assertFalse(numeric_confirm_quote("2", "S9_序列配置"))
        self.assertFalse(numeric_confirm_quote("0", "S9_序列配置"))
        self.assertFalse(numeric_confirm_quote("", "S9_序列配置"))

    def test_phrase_confirm_still_works_for_s9(self):
        self.assertTrue(confirm_quote_ok("确认建序列"))
        self.assertTrue(numeric_confirm_quote("1", "S9_序列配置"))


if __name__ == "__main__":
    unittest.main()
