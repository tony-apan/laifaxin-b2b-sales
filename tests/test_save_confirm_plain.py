# -*- coding: utf-8 -*-
"""v3 保存确认放宽 + 100 家探针：行为级回归（不是字符串检查）。

覆盖两个曾漏网的 P0：
  P0-1 纯确认必须在 auth_guard 真正铸票处放行（否则 confirm 写盘后必失败）。
  P0-2 探针 100 家必须在 count_guard 有合法模式（sample 只能 1、explicit_small≤50）。
"""
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import auth_guard  # noqa: E402
import count_guard  # noqa: E402
import rule_check  # noqa: E402
import save_budget  # noqa: E402


def _evidence(threshold=450, returned=10):
    return {"threshold_page": threshold, "pool_total": 9999,
            "evidence_mode": "strict",
            "page_rows": [{"page": threshold, "returned": returned}]}


def _plan(budget="10000"):
    return {"budget_points": budget, "max_points": budget,
            "estimation": {
                "estimated_emails_per_company": {
                    "value": "1.5", "source_ref": "cal", "version": "v1",
                    "kind": "calibrated_upper"},
                "estimated_points_per_email": {
                    "value": "1.5", "source_ref": "cal", "version": "v1",
                    "kind": "calibrated_upper"},
            }}


class PlainConfirmTicketingTest(unittest.TestCase):
    """P0-1：纯确认要在铸票闸门放行，且必须带卡面绑定。"""

    def _confirmed_plan(self, bound=True):
        payload = {"selectTotal": 100}
        plan = {"status": "confirmed", "wire_payload": payload,
                "wire_payload_sha256": auth_guard.canonical_hash(payload),
                "dependency_sha256": "0" * 64}
        if bound:
            plan.update({"count_bound_by": "card", "count_bound_n": 100})
        return payload, plan

    def _authorize(self, quote, payload, plan, td):
        with mock.patch.object(auth_guard, "_require_startup_ack", lambda: None):
            return auth_guard.authorize_save_plan("save", quote, payload,
                                                  plan=plan, root=td)

    def test_plain_confirm_ticketed_with_card_binding(self):
        payload, plan = self._confirmed_plan(True)
        with tempfile.TemporaryDirectory() as td:
            res = self._authorize("确认", payload, plan, td)
        self.assertTrue(res.get("ok"), res)

    def test_plain_confirm_rejected_without_binding(self):
        payload, plan = self._confirmed_plan(False)
        with tempfile.TemporaryDirectory() as td:
            res = self._authorize("确认", payload, plan, td)
        self.assertFalse(res.get("ok"))
        self.assertEqual(res.get("code"), "E_AUTH_COUNT_AMBIGUOUS")

    def test_number_quote_still_checked(self):
        payload, plan = self._confirmed_plan(True)
        with tempfile.TemporaryDirectory() as td:
            res = self._authorize("确认保存 前 200 家", payload, plan, td)
        self.assertFalse(res.get("ok"))
        self.assertEqual(res.get("code"), "E_AUTH_COUNT_MISMATCH")


class ProbeModeTest(unittest.TestCase):
    """P0-2：探针 100 家必须有合法数量模式，而不是静默 1 家。"""

    def test_probe_mode_allows_100(self):
        got = count_guard.derive(_evidence(), _plan(), mode="probe",
                                 explicit_count=100,
                                 sample_ack="确认保存 前 100 家",
                                 quote="确认保存 前 100 家")
        self.assertEqual(got["select_total"], 100)

    def test_probe_requires_ack(self):
        with self.assertRaises(count_guard.CountError) as ctx:
            count_guard.derive(_evidence(), _plan(), mode="probe",
                               explicit_count=100)
        self.assertEqual(ctx.exception.code, "E_SAMPLE_ACK_REQUIRED")

    def test_probe_cap_100(self):
        with self.assertRaises(count_guard.CountError) as ctx:
            count_guard.derive(_evidence(), _plan(), mode="probe",
                               explicit_count=200,
                               sample_ack="x", quote="x")
        self.assertEqual(ctx.exception.code, "E_COUNT_EXPLICIT")

    def test_probe_level_is_idempotent(self):
        for _ in range(3):
            self.assertEqual(save_budget.next_probe_level(
                None, project="p", org="o", round_id="r"), 100)


class PlainConfirmWordsTest(unittest.TestCase):
    def test_accepts_user_words(self):
        for q in ("确认", "确认保存", "确认吧", "确定"):
            self.assertTrue(rule_check.is_plain_save_confirm(q), q)

    def test_rejects_loose_yes(self):
        for q in ("好", "好的", "ok", "yes", "确认激活", "确认 100 家", ""):
            self.assertFalse(rule_check.is_plain_save_confirm(q), q)


class ProbeNotOneTest(unittest.TestCase):
    def test_sample_mode_still_one(self):
        got = count_guard.derive(_evidence(), _plan(), mode="sample")
        self.assertEqual(got["select_total"], 1)


if __name__ == "__main__":
    unittest.main()
