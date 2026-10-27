
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""TASK-20261027-contact-tier-budget：档位真源 + 跨档校准 + 坏预算拒（先红后绿）。

AC1 档位唯一真源=wire.contactMaxCount；top 不一致拒；卡面写每司上限 N（3/6/9）。
AC2 校准按同档过滤；换档不清零 spent_all/预算；缺同档校准明确报需本档校准。
AC3 bootstrap/plan 全入口拒 0/负/非有限预算，不落污染行。
AC4 档位并入卡绑定：旧卡套新档位 → E_CARD_TAMPERED。
"""
import json
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import count_guard  # noqa: E402
import rule_check  # noqa: E402
import save_budget  # noqa: E402
import save_plan as planlib  # noqa: E402


def _evidence(threshold=450, returned=10):
    return {"threshold_page": threshold, "pool_total": 9999,
            "evidence_mode": "strict",
            "page_rows": [{"page": threshold, "returned": returned}]}


def _coeff(e="1.5", p="1.5"):
    return {"estimated_emails_per_company": {"value": e, "source_ref": "cal",
                                             "version": "v1", "kind": "calibrated_upper"},
            "estimated_points_per_email": {"value": p, "source_ref": "cal",
                                           "version": "v1", "kind": "calibrated_upper"}}


def _wire(n, tier=3):
    w = dict(rule_check.FIXED_VALUES)
    w.update({
        "companyTags": ["ctag1"], "contactTags": ["ctag2"],
        "contactVerifyStatus": ["valid", "unkown"],
        "contactMaxCount": tier, "selectTotal": n,
        "filters": [], "filter": {}, "keyword": "caps maker",
        "logic": "and", "selectSort": {},
    })
    return w


def _budget():
    return {"budget_points": {"points": 10000, "source_ref": "user", "version": "v1"},
            "max_points": {"points": 18000, "source_ref": "account", "version": "v1"}}


class TierTruthSourceTest(unittest.TestCase):
    """AC1：档位唯一真源=wire；top 不一致拒；draft 记录一致档位。"""

    def _offline(self, n=20, top_tier=None, wire_tier=3):
        offline = {
            "count_evidence": _evidence(), "count_mode": "explicit_small",
            "selectTotal": n, "explicit_count": n,
            "sample_ack": "确认保存 前 20 家",
            "count_quote": "确认保存 前 20 家",
            "wire_payload": _wire(n, tier=wire_tier),
            "companyTags": ["ctag1"], "contactTags": ["ctag2"],
            "contactVerifyStatus": ["valid", "unkown"],
        }
        if top_tier is not None:
            offline["contactMaxCount"] = top_tier
        return offline

    def _prepare(self, offline):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            manifest = root / "audit.json"
            manifest.write_text(json.dumps({"window": {"from": 1, "to": 3},
                                            "evidence_mode": "strict"}),
                                encoding="utf-8")
            with mock.patch("segment_registry.validate_source",
                            return_value={"platform_product_id": "p1",
                                          "generation_id": "g1",
                                          "segment_id": "s1"}), \
                 mock.patch("segment_registry.load_selection", return_value={}), \
                 mock.patch.object(planlib, "validate_offline_tags"), \
                 mock.patch.object(planlib, "build_dependencies", return_value={}):
                return root, planlib.prepare_save(
                    root, project="op/prod",
                    source={"platform_product_id": "p1", "generation_id": "g1",
                            "segment_id": "s1", "keyword": "caps maker",
                            "audit_manifest": str(manifest)},
                    audit={"path": str(manifest), "window": {}},
                    budget=_budget(), coefficients=_coeff(),
                    rule_excerpts=[], offline_input=offline,
                    audit_manifest_path=str(manifest))

    def test_top_wire_mismatch_rejected(self):
        with self.assertRaises(planlib.PlanError) as cm:
            self._prepare(self._offline(top_tier=3, wire_tier=9))
        self.assertEqual("E_CONTACT_TIER_MISMATCH", cm.exception.code)

    def test_default_tier_is_3_and_matches_wire(self):
        root, draft = self._prepare(self._offline(top_tier=None, wire_tier=3))
        self.assertEqual(3, draft["contactMaxCount"])

    def test_tier9_accepted_when_consistent(self):
        root, draft = self._prepare(self._offline(top_tier=9, wire_tier=9))
        self.assertEqual(9, draft["contactMaxCount"])

    def test_card_binds_tier_and_shows_plain_text(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            manifest = root / "audit.json"
            manifest.write_text("{}", encoding="utf-8")
            offline = self._offline(top_tier=9, wire_tier=9)
            with mock.patch("segment_registry.validate_source",
                            return_value={"platform_product_id": "p1",
                                          "generation_id": "g1",
                                          "segment_id": "s1"}), \
                 mock.patch("segment_registry.load_selection", return_value={}), \
                 mock.patch.object(planlib, "validate_offline_tags"), \
                 mock.patch.object(planlib, "build_dependencies", return_value={}):
                draft = planlib.prepare_save(
                    root, project="op/prod",
                    source={"platform_product_id": "p1", "generation_id": "g1",
                            "segment_id": "s1", "keyword": "caps maker"},
                    audit={"path": str(manifest), "window": {}},
                    budget=_budget(), coefficients=_coeff(),
                    rule_excerpts=[], offline_input=offline)
            path = planlib.write_draft(root, draft)
            card = planlib.present_card(root, path, now=time.time())
            self.assertIn("每家公司最多 9 个邮箱", card["card_text"])
            self.assertIn("3/6/9", card["card_text"])
            doc = json.loads(Path(card["card_path"]).read_text("utf-8"))
            self.assertEqual(9, doc["card"]["contactMaxCount"])

    def test_old_card_invalid_after_tier_change(self):
        """wire 档位变 → wire hash 变 → 旧卡 E_CARD_TAMPERED（依赖路径已有，卡体新增档位也须绑）。"""
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            manifest = root / "audit.json"
            manifest.write_text("{}", encoding="utf-8")

            def _draft(tier):
                offline = self._offline(top_tier=tier, wire_tier=tier)
                with mock.patch("segment_registry.validate_source",
                                return_value={"platform_product_id": "p1",
                                              "generation_id": "g1",
                                              "segment_id": "s1"}), \
                     mock.patch("segment_registry.load_selection", return_value={}), \
                     mock.patch.object(planlib, "validate_offline_tags"), \
                     mock.patch.object(planlib, "build_dependencies", return_value={}):
                    return planlib.prepare_save(
                        root, project="op/prod",
                        source={"platform_product_id": "p1", "generation_id": "g1",
                                "segment_id": "s1", "keyword": "caps maker"},
                        audit={"path": str(manifest), "window": {}},
                        budget=_budget(), coefficients=_coeff(),
                        rule_excerpts=[], offline_input=offline)

            d3 = _draft(3)
            p3 = planlib.write_draft(root, d3, str(root / "d3.json"))
            card3 = planlib.present_card(root, p3, now=time.time())
            # 手工构造同 plan_id/revision 但档位 9 的新计划，旧卡（绑 3）必须拒。
            d9 = _draft(9)
            d9["plan_id"] = d3["plan_id"]
            d9["revision"] = d3["revision"]
            p9 = planlib.write_draft(root, d9, str(root / "d9.json"))
            with mock.patch("segment_registry.validate_source",
                            return_value={"platform_product_id": "p1",
                                          "generation_id": "g1",
                                          "segment_id": "s1"}), \
                 mock.patch("segment_registry.load_selection", return_value={}):
                with self.assertRaises(planlib.PlanError) as cm:
                    planlib.confirm_plan(root, planlib.load_plan(p9), quote="确认",
                                         quote_ref=card3["card_ref"], now=time.time(),
                                         presentation=card3["card_ref"])
            self.assertIn(cm.exception.code,
                          ("E_CARD_TAMPERED", "E_CARD_MISMATCH",
                           "E_PLAN_DEPENDENCY_CHANGED"))


class BootstrapBadBudgetTest(unittest.TestCase):
    """AC3：0/负/非有限预算 → 明确错误码，绝不返回可执行 sample_ready。"""

    def test_zero_budget_rejected(self):
        with self.assertRaises(save_budget.BudgetError) as cm:
            save_budget.bootstrap_sample(b_plan="0", b_avail="0",
                                         sample_ack_quote="确认样本",
                                         sample_ack_ref="ref-1")
        self.assertEqual("E_BUDGET_EXHAUSTED", cm.exception.code)

    def test_negative_budget_rejected(self):
        with self.assertRaises(save_budget.BudgetError) as cm:
            save_budget.bootstrap_sample(b_plan="-5", b_avail="0",
                                         sample_ack_quote="确认样本",
                                         sample_ack_ref="ref-1")
        self.assertEqual("E_BUDGET_EXHAUSTED", cm.exception.code)

    def test_non_finite_budget_rejected(self):
        for bad in ("NaN", "Infinity", "-Infinity"):
            with self.subTest(bad=bad):
                with self.assertRaises(save_budget.BudgetError) as cm:
                    save_budget.bootstrap_sample(b_plan=bad, b_avail="0",
                                                 sample_ack_quote="确认样本",
                                                 sample_ack_ref="ref-1")
                self.assertIn(cm.exception.code,
                              ("E_BUDGET_EXHAUSTED", "E_BAD_INPUT"))

    def test_no_ledger_pollution_on_bad_budget(self):
        """完整 plan 入口拒坏预算时不得落 sample_ack/probe_level 污染行。"""
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            probe_row = {"kind": "probe", "org_hash": save_budget.org_hash("o1"),
                         "project": "p1", "payload": {"b_avail": "0",
                                                      "read_at": save_budget._iso(),
                                                      "source": save_budget.POINTS_SOURCE,
                                                      "source_kind": "points"}}
            save_budget.append_ledger(root, org_hash=probe_row["org_hash"],
                                      project="p1", kind="probe",
                                      source_ref=probe_row["payload"]["source"],
                                      payload=probe_row["payload"])
            with self.assertRaises(save_budget.BudgetError):
                save_budget.plan(root, project="p1", org="o1",
                                 b_plan="0", b_avail="0",
                                 read_at=probe_row["payload"]["read_at"],
                                 balance_source=save_budget.POINTS_SOURCE,
                                 sample_ack_quote="确认样本",
                                 sample_ack_ref="ref-1")
            rows = save_budget.read_ledger(root, "p1")
            for row in rows:
                self.assertNotIn(row.get("kind") + ":" + row.get("state", ""),
                                 ("sample_ack:sample_ready", "plan:probe_level"),
                                 "坏预算不得落 sample_ack/probe_level 污染行")


class CrossTierLedgerTest(unittest.TestCase):
    """AC2：校准按同档过滤；跨档 spent 累计不清零；缺同档校准明确报错。"""

    def _carry_row(self, root, project="p1", org="o1", tier=None,
                   cost="90", companies=20, contacts=60):
        bid = "b-%s-%s" % (tier, cost)
        payload = {"task_id": "t-%s" % bid, "b0_b_avail": "1000",
                   "b0_source": save_budget.POINTS_SOURCE, "exec_ack": True,
                   "exec_quote_ref": "q", "probe_level": None,
                   "sample_batch": False}
        if tier is not None:
            payload["contact_max_count"] = tier
        save_budget.append_ledger(root, org_hash=save_budget.org_hash(org),
                                  project=project, kind="batch_begin",
                                  source_ref="exec_ack", batch_id=bid,
                                  state="executing", payload=payload)
        save_budget.append_ledger(root, org_hash=save_budget.org_hash(org),
                                  project=project, kind="settle",
                                  source_ref="balance_diff", batch_id=bid,
                                  state="preliminary",
                                  payload={"task_id": "t-%s" % bid,
                                           "batch_cost_lo": cost,
                                           "company_save_count": str(companies),
                                           "contact_save_count": str(contacts),
                                           "cost_per_company_lo": "4.5",
                                           "emails_per_company": "3",
                                           "b0_b_avail": "1000",
                                           "b_settle": str(1000 - int(cost)),
                                           "exec_ack": True, "probe_level": None,
                                           "unresolved_upper": cost})
        save_budget.append_ledger(root, org_hash=save_budget.org_hash(org),
                                  project=project, kind="carry",
                                  source_ref="late_carryover", batch_id=bid,
                                  state="settled", late="0",
                                  external_risk="confirmed",
                                  payload={"batch_cost": cost,
                                           "company_save_count": str(companies),
                                           "contact_save_count": str(contacts),
                                           "exec_ack": True, "settle_ack": True,
                                           "settle_quote_ref": "q",
                                           "settled_at": save_budget._iso(),
                                           "probe_level": None,
                                           **({"contact_max_count": tier}
                                              if tier is not None else {})})

    def test_tier3_calibration_ignores_tier9_rows(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self._carry_row(root, tier=3, cost="90", companies=20, contacts=60)
            self._carry_row(root, tier=9, cost="900", companies=20, contacts=180)
            accounts = save_budget.round_accounts(root, project="p1", org="o1")
            self.assertEqual(Decimal("90"), accounts["spent_calib"] if False else accounts["spent_calib"])
            self.assertEqual(20, accounts["companies_calib"])
            # 换到 9 档视图：校准只用 9 档行
            accounts9 = save_budget.round_accounts(root, project="p1", org="o1",
                                                   contact_max_count=9)
            self.assertEqual(Decimal("900"), accounts9["spent_calib"])
            self.assertEqual(180, accounts9["emails_calib"])
            # 跨档累计不清零：spent_settled/spent_all 含两档全部
            self.assertEqual(Decimal("990"), accounts9["spent_all"])

    def test_tier9_without_matching_calibration_offers_tier9_probe(self):
        """ack-close 语义：3 档历史不能给 9 档校准，但 9 档必须能产本档探针提案。"""
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self._carry_row(root, tier=3, cost="90", companies=20, contacts=60)
            prop = save_budget.plan(root, project="p1", org="o1",
                                    b_plan="10000", b_avail="9000",
                                    read_at=save_budget._iso(),
                                    balance_source=save_budget.POINTS_SOURCE,
                                    contact_max_count=9)
            self.assertEqual("sample_needs_ack", prop["status"])
            self.assertEqual(9, prop["contact_max_count"])
            self.assertEqual(100, prop["sample_n"])
            self.assertTrue(prop["proposal_ref"])

    def test_legacy_untiered_history_counts_as_tier3(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self._carry_row(root, tier=None, cost="90", companies=20, contacts=60)
            accounts = save_budget.round_accounts(root, project="p1", org="o1")
            self.assertEqual(Decimal("90"), accounts["spent_calib"])
            accounts9 = save_budget.round_accounts(root, project="p1", org="o1",
                                                   contact_max_count=9)
            self.assertEqual(Decimal("0"), accounts9["spent_calib"])

    def test_ready_row_carries_tier_and_count_guard_checks_it(self):
        payload = save_budget.make_ready_row_payload(
            b_plan="10000", confirm_n=20, n_cons=20, n_est=20,
            risk_ack=False, cap_ack=False, exec_quote_ref="确认保存 前 20 家",
            batch_points_upper="90", round_id="round-demo",
            spent_all="0", budget_left="10000",
            per_company_upper="4.5", contact_max_count=9)
        self.assertEqual(9, payload["contact_max_count"])
        plan_doc = {"budget_points": "10000", "max_points": "10000",
                    "contactMaxCount": 9,
                    "budget_ledger": {**payload, "status": "ready",
                                      "org_hash": "org-demo"},
                    "estimation": _coeff(e="3", p="1.5")}
        got = count_guard.derive(_evidence(), plan_doc, mode="calibrated")
        self.assertEqual(20, got["select_total"])
        plan_doc["contactMaxCount"] = 3  # plan 与 ledger 档位不一致必须拒
        with self.assertRaises(count_guard.CountError) as cm:
            count_guard.derive(_evidence(), plan_doc, mode="calibrated")
        self.assertEqual("E_LEDGER_TIER_MISMATCH", cm.exception.code)

    def test_legacy_ledger_without_tier_only_usable_for_default_3(self):
        payload = save_budget.make_ready_row_payload(
            b_plan="10000", confirm_n=20, n_cons=20, n_est=20,
            risk_ack=False, cap_ack=False, exec_quote_ref="q",
            batch_points_upper="45", round_id="r", spent_all="0",
            budget_left="10000", per_company_upper="4.5")
        self.assertEqual(3, payload["contact_max_count"])  # 缺省=3（legacy）
        plan_doc = {"budget_points": "10000", "max_points": "10000",
                    "contactMaxCount": 9,
                    "budget_ledger": {**payload, "status": "ready",
                                      "org_hash": "org-demo"},
                    "estimation": _coeff(e="3", p="1.5")}
        with self.assertRaises(count_guard.CountError) as cm:
            count_guard.derive(_evidence(), plan_doc, mode="calibrated")
        self.assertEqual("E_LEDGER_TIER_MISMATCH", cm.exception.code)


from decimal import Decimal  # noqa: E402

if __name__ == "__main__":
    unittest.main()
