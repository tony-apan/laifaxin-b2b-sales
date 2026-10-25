#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""保存数量推导闸门回归：50 不能绕过，末页/预算/样本/一致性都要拒。"""
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import count_guard  # noqa: E402
import rule_check  # noqa: E402
import save_plan  # noqa: E402


def evidence(threshold=450, pool=9999, returned=10, mode="strict"):
    return {"threshold_page": threshold, "pool_total": pool,
            "evidence_mode": mode,
            "page_rows": [{"page": threshold, "returned": returned}]}


def ledger(n=4444):
    return {"status": "ready", "org_hash": "org-demo", "round_id": "round-demo",
            "exec_quote_ref": "确认保存",
            "confirm_n": n, "n_cons": n, "n_est": n,
            "b_plan": "10000", "spent_all": "0", "budget_left": "10000",
            "per_company_upper": "2.25", "batch_points_upper": "10000"}


def plan(budget="10000", cap="10000", e="1.5", p="1.5"):
    return {"budget_points": budget, "max_points": cap,
            "budget_ledger": ledger(),
            "estimation": {
                "estimated_emails_per_company": {
                    "value": e, "source_ref": "cal", "version": "v1",
                    "kind": "calibrated_upper"},
                "estimated_points_per_email": {
                    "value": p, "source_ref": "cal", "version": "v1",
                    "kind": "calibrated_upper"},
            }}


def bound(ev, **kwargs):
    p = plan()
    d = count_guard.derive(ev, p, **kwargs)
    p.update({
        "count_evidence": ev,
        "count_mode": kwargs.get("mode"),
        "explicit_count": kwargs.get("explicit_count"),
        "sample_ack": kwargs.get("sample_ack", ""),
        "count_quote": kwargs.get("quote", ""),
        "selectTotal": d["select_total"],
        "derived_select_total": d["select_total"],
        "count_hash": d["count_hash"],
        "budget_ledger": p["budget_ledger"],
        "budget_ledger_hash": d["ledger_hash"],
        "wire_payload": {"selectTotal": d["select_total"]},
    })
    p["estimation"]["selectTotal"] = d["select_total"]
    return p, d


class CountGuardTest(unittest.TestCase):
    def test_450_pages_10k_budget_is_4444(self):
        d = count_guard.derive(evidence(), plan(), mode="calibrated")
        self.assertEqual(4444, d["select_total"])
        self.assertEqual(9999, d["points"])

    def test_live_manifest_aliases(self):
        ev = {"evidence_mode": "live",
              "boundary": {"critical_page": 450},
              "data": {"total": 9999},
              "window": {"page_rows": [
                  {"page": 450, "matched": 9, "total": 10}]}}
        d = count_guard.derive(ev, plan(), mode="calibrated")
        self.assertEqual(4444, d["select_total"])

    def test_partial_last_page_caps_y(self):
        d = count_guard.derive(evidence(returned=4), plan(), mode="calibrated")
        self.assertEqual(4494, d["y"])
        self.assertEqual(4444, d["select_total"])  # 预算仍封顶

    def test_pool_total_caps_count(self):
        d = count_guard.derive(evidence(pool=4497), plan(), mode="calibrated")
        self.assertEqual(4497, d["y"])
        self.assertEqual(4444, d["select_total"])  # 预算仍封顶

    def test_sample_is_one_when_uncalibrated(self):
        d = count_guard.derive(evidence(), plan(), mode="sample")
        self.assertEqual(1, d["select_total"])

    def test_explicit_20_with_ack_is_allowed(self):
        d = count_guard.derive(evidence(), plan(), mode="explicit_small",
                               explicit_count=20, sample_ack="yes",
                               quote="先存 20 家")
        self.assertEqual(20, d["select_total"])

    def test_explicit_50_without_ack_is_rejected(self):
        with self.assertRaises(count_guard.CountError) as cm:
            count_guard.derive(evidence(), plan(), mode="explicit_small",
                               explicit_count=50)
        self.assertEqual("E_SAMPLE_ACK_REQUIRED", cm.exception.code)

    def test_manual_50_is_rejected_as_derived_mismatch(self):
        p, _ = bound(evidence(), mode="calibrated")
        p["selectTotal"] = 50
        p["wire_payload"]["selectTotal"] = 50
        p["derived_select_total"] = 50
        p["estimation"]["selectTotal"] = 50
        with self.assertRaises(count_guard.CountError) as cm:
            count_guard.validate_plan(p)
        self.assertEqual("E_SELECT_TOTAL_DERIVED_MISMATCH", cm.exception.code)

    def test_wire_mismatch_is_rejected(self):
        p, _ = bound(evidence(), mode="calibrated")
        p["wire_payload"]["selectTotal"] = 50
        with self.assertRaises(count_guard.CountError) as cm:
            count_guard.validate_plan(p)
        self.assertEqual("E_SELECT_TOTAL_DERIVED_MISMATCH", cm.exception.code)

    def test_legacy_evidence_mode_is_rejected(self):
        with self.assertRaises(count_guard.CountError) as cm:
            count_guard.derive(evidence(mode="loose"), plan(), mode="calibrated")
        self.assertEqual("E_COUNT_EVIDENCE_MODE", cm.exception.code)

    def test_user_estimate_is_not_a_ceiling(self):
        p = plan()
        p["estimation"]["estimated_emails_per_company"]["kind"] = "user_estimate"
        with self.assertRaises(count_guard.CountError) as cm:
            count_guard.derive(evidence(), p, mode="calibrated")
        self.assertEqual("E_COUNT_COEFFICIENT", cm.exception.code)

    def test_zero_budget_is_budget_exhausted(self):
        with self.assertRaises(count_guard.CountError) as cm:
            count_guard.derive(evidence(), plan(budget="0"), mode="calibrated")
        self.assertEqual("E_BUDGET_EXHAUSTED", cm.exception.code)

    def test_hash_tamper_is_rejected(self):
        p, _ = bound(evidence(), mode="calibrated")
        p["count_hash"] = "0" * 64
        with self.assertRaises(count_guard.CountError) as cm:
            count_guard.validate_plan(p)
        self.assertEqual("E_COUNT_HASH_MISMATCH", cm.exception.code)

    def test_risk_ack_allows_confirmed_above_cons(self):
        p = plan()
        p["budget_ledger"] = ledger(2)
        p["budget_ledger"].update({"n_cons": 1, "n_est": 2, "risk_ack": True,
                                   "batch_points_upper": "100"})
        d = count_guard.derive(evidence(), p, mode="calibrated")
        self.assertEqual(2, d["select_total"])

    def test_negative_spent_ledger_is_rejected(self):
        p = plan()
        p["budget_ledger"]["spent_all"] = "-10000"
        p["budget_ledger"]["budget_left"] = "20000"
        with self.assertRaises(count_guard.CountError) as cm:
            count_guard.derive(evidence(), p, mode="calibrated")
        self.assertEqual("E_LEDGER_INVALID", cm.exception.code)

    def test_producer_ready_row_is_accepted(self):
        import save_budget
        p = plan()
        p["budget_ledger"] = save_budget.make_ready_row_payload(
            b_plan="10000", confirm_n=4444, n_cons=4444, n_est=4444,
            risk_ack=False, cap_ack=False, exec_quote_ref="确认保存",
            batch_points_upper="10000", round_id="round-demo",
            spent_all="0", budget_left="10000", per_company_upper="2.25")
        p["budget_ledger"].update({"status": "ready", "org_hash": "org-demo"})
        d = count_guard.derive(evidence(), p, mode="calibrated")
        self.assertEqual(4444, d["select_total"])

    def test_ledger_upper_below_plan_cost_is_rejected(self):
        p = plan()
        p["budget_ledger"]["per_company_upper"] = "1.0"
        with self.assertRaises(count_guard.CountError) as cm:
            count_guard.derive(evidence(), p, mode="calibrated")
        self.assertEqual("E_LEDGER_UPPER_TOO_LOW", cm.exception.code)

    def test_sourced_budget_docs_pass(self):
        p = plan(budget={"points": 10000, "source_ref": "user", "version": "v1"},
                 cap={"points": 18000, "source_ref": "account", "version": "v1"})
        d = count_guard.derive(evidence(), p, mode="calibrated")
        self.assertEqual(4444, d["select_total"])

    def test_bound_plan_passes(self):
        p, d = bound(evidence(), mode="calibrated")
        again = count_guard.validate_plan(p)
        self.assertEqual(d["select_total"], again["select_total"])


def _wire(n):
    w = dict(rule_check.FIXED_VALUES)
    w.update({
        "companyTags": ["c1"], "contactTags": ["t1"],
        "contactVerifyStatus": ["valid", "unkown"],
        "contactMaxCount": 3, "selectTotal": n,
        "filters": [], "filter": {}, "keyword": "caps maker",
        "logic": "and", "selectSort": {},
    })
    return w


class PrepareIntegrationTest(unittest.TestCase):
    def _prepare(self, select_total, wire_total):
        coeff = {
            "estimated_emails_per_company": {
                "value": 1.5, "source_ref": "cal", "version": "v1",
                "kind": "calibrated_upper"},
            "estimated_points_per_email": {
                "value": 1.5, "source_ref": "cal", "version": "v1",
                "kind": "calibrated_upper"},
        }
        budget = {
            "budget_points": {"points": 10000, "source_ref": "user", "version": "v1"},
            "max_points": {"points": 18000, "source_ref": "account", "version": "v1"},
        }
        import save_budget
        offline = {
            "count_evidence": evidence(), "count_mode": "calibrated",
            "budget_ledger": ledger(),
            "selectTotal": select_total, "wire_payload": _wire(wire_total),
            "companyTags": ["c1"], "contactTags": ["t1"],
            "contactMaxCount": 3, "contactVerifyStatus": ["valid", "unkown"],
        }
        with tempfile.TemporaryDirectory() as td:
            save_budget.append_ledger(
                Path(td), org_hash="org-demo", project="p/demo", kind="plan",
                source_ref="确认保存", state="ready",
                payload={"confirm_n": 4444, "b_plan": "10000", "n_cons": 4444,
                         "n_est": 4444, "batch_points_upper": "10000",
                         "spent_all": "0", "budget_left": "10000",
                         "per_company_upper": "2.25", "round_id": "round-demo",
                         "exec_quote_ref": "确认保存"})
            with mock.patch.object(save_plan, "validate_offline_tags"), \
                 mock.patch("segment_registry.validate_source"), \
                 mock.patch.object(save_plan, "build_dependencies", return_value={}):
                return save_plan.prepare_save(
                    Path(td), project="p/demo",
                    source={"platform_product_id": "p1", "generation_id": "g1",
                            "segment_id": "s1", "keyword": "caps maker"},
                    audit={"path": "x", "window": {}}, budget=budget,
                    coefficients=coeff, rule_excerpts=[], offline_input=offline)

    def test_prepare_derives_4444(self):
        draft = self._prepare(4444, 4444)
        self.assertEqual(4444, draft["selectTotal"])
        self.assertEqual(4444, draft["derived_select_total"])
        self.assertTrue(draft["count_hash"])

    def test_prepare_rejects_manual_50(self):
        with self.assertRaises(save_plan.PlanError) as cm:
            self._prepare(50, 50)
        self.assertEqual("E_SELECT_TOTAL_DERIVED_MISMATCH", cm.exception.code)


if __name__ == "__main__":
    unittest.main()
