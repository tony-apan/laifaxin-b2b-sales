#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""TASK-20261027-contact-tier-ledger-close：写侧闭环红用例（begin→settle→carry→round_accounts→plan）。

不 mock 预算/账簿函数；settle 的平台读用本地替身 http（余额序列+任务状态），
真实走 begin_batch/_settle_locked/carry/round_accounts/plan 全链。
"""
import json
import sys
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import save_budget  # noqa: E402


def _fake_http(balance_seq, task_payload):
    """本地替身：read_balance 轮询序列 + _read_task 状态。不 mock 预算函数。"""
    calls = {"i": 0}

    def http(endpoint, payload=None):
        if endpoint == "account/current":
            i = min(calls["i"], len(balance_seq) - 1)
            calls["i"] += 1
            return {"success": True,
                    "data": {"creditCount": balance_seq[i]}}
        if endpoint == "operation/backend-task-status":
            return {"success": True, "data": task_payload}
        raise AssertionError("unexpected endpoint %r" % endpoint)
    return http


class WriteSideTierChainTest(unittest.TestCase):
    def _chain(self, root, project="p1", org="o1", tier=9, cost=90,
               companies=20, contacts=180, task_id=None, begin_kwargs=None):
        task_id = task_id or ("task-%s-%s" % (tier, cost))
        kw = dict(project=project, org=org, task_id=task_id,
                  b0={"b_avail": "1000", "source": save_budget.POINTS_SOURCE},
                  exec_quote="确认执行", exec_quote_ref="ref-exec")
        if begin_kwargs:
            kw.update(begin_kwargs)
        got = save_budget.begin_batch(root, contact_max_count=tier, **kw)
        self.assertEqual(tier, got["contact_max_count"])
        begin_rows = [r for r in save_budget.read_ledger(root, project)
                      if r.get("kind") == "batch_begin"
                      and r.get("batch_id") == got["batch_id"]]
        self.assertEqual(tier, (begin_rows[-1].get("payload") or {})
                         .get("contact_max_count"))
        http = _fake_http([1000, 1000 - cost, 1000 - cost, 1000 - cost],
                          {"finished": True, "status": "finished",
                           "companySaveCount": companies,
                           "contactSaveCount": contacts})
        settled = save_budget._settle_locked(
            root, project=project, org=org, token="tk", task_id=task_id,
            http=http, clock=lambda: 0.0, sleep=lambda s: None,
            settle_stable_seconds=0.0, batch_id=got["batch_id"])
        settle_rows = [r for r in save_budget.read_ledger(root, project)
                       if r.get("kind") == "settle"
                       and r.get("batch_id") == got["batch_id"]
                       and r.get("state") == "preliminary"]
        self.assertEqual(tier, (settle_rows[-1].get("payload") or {})
                         .get("contact_max_count"))
        carried = save_budget.carry(root, project=project, org=org,
                                    batch_id=got["batch_id"],
                                    b_after=str(1000 - cost),
                                    settle_quote="确认结算",
                                    settle_quote_ref="ref-settle")
        self.assertEqual(tier, carried["contact_max_count"])
        return got["batch_id"]

    def test_real_write_chain_produces_tiered_calibration(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            # 先真实 3 档链
            self._chain(root, tier=3, cost=30, companies=20, contacts=60,
                        task_id="task-t3")
            # 再真实 9 档链
            self._chain(root, tier=9, cost=90, companies=20, contacts=180,
                        task_id="task-t9")
            # 3 档视图：只用 3 档校准；spent_all 全档累计
            a3 = save_budget.round_accounts(root, project="p1", org="o1",
                                            contact_max_count=3)
            self.assertEqual(Decimal("30"), a3["spent_calib"])
            self.assertEqual(60, a3["emails_calib"])
            # 9 档视图：只用 9 档校准；跨档累计不清零
            a9 = save_budget.round_accounts(root, project="p1", org="o1",
                                            contact_max_count=9)
            self.assertEqual(Decimal("90"), a9["spent_calib"])
            self.assertEqual(180, a9["emails_calib"])
            self.assertEqual(Decimal("120"), a9["spent_all"])
            # 真实 plan：9 档校准可推导
            probe_row = {"b_avail": "1000", "read_at": save_budget._iso(),
                         "source": save_budget.POINTS_SOURCE,
                         "source_kind": "points"}
            save_budget.append_ledger(root, org_hash=save_budget.org_hash("o1"),
                                      project="p1", kind="probe",
                                      source_ref=probe_row["source"],
                                      payload=probe_row)
            result = save_budget.plan(root, project="p1", org="o1",
                                      b_plan="2000", b_avail="1000",
                                      read_at=probe_row["read_at"],
                                      balance_source=save_budget.POINTS_SOURCE,
                                      contact_max_count=9,
                                      target_companies=5)
            self.assertEqual(9, result["contact_max_count"])
            ready = save_budget.make_ready_row_payload(
                b_plan=result["b_plan"], confirm_n=5, n_cons=5, n_est=5,
                risk_ack=False, cap_ack=False, exec_quote_ref="q",
                batch_points_upper=result["batch_points_upper"],
                round_id=result["round_id"],
                spent_all=result["spent_all"],
                budget_left=result["budget_left"],
                per_company_upper=result["per_company_upper"],
                contact_max_count=9)
            self.assertEqual(9, ready["contact_max_count"])

    def test_begin_rejects_bad_tier_values(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            for bad in (9.9, "9", True, None if False else 4, 0, -3):
                with self.subTest(bad=bad):
                    with self.assertRaises(save_budget.BudgetError):
                        save_budget.begin_batch(
                            root, project="p1", org="o1", task_id="t-bad",
                            b0={"b_avail": "1000",
                                "source": save_budget.POINTS_SOURCE},
                            exec_quote="q", exec_quote_ref="r",
                            contact_max_count=bad)

    def test_settle_inherits_tier_from_begin_not_caller(self):
        """settle 不接受调用者档位参数：tier 只来自对应 begin 行。"""
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            save_budget.begin_batch(
                root, project="p1", org="o1", task_id="t-inc",
                b0={"b_avail": "1000", "source": save_budget.POINTS_SOURCE},
                exec_quote="q", exec_quote_ref="r", contact_max_count=3)
            http = _fake_http([1000, 970, 970, 970],
                              {"finished": True, "status": "finished",
                               "companySaveCount": 10,
                               "contactSaveCount": 30})
            settled = save_budget._settle_locked(
                root, project="p1", org="o1", token="tk", task_id="t-inc",
                http=http, clock=lambda: 0.0, sleep=lambda s: None,
                settle_stable_seconds=0.0)
            self.assertEqual(3, settled["contact_max_count"])

    def test_carry_inherits_tier_from_settle(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            save_budget.begin_batch(
                root, project="p1", org="o1", task_id="t-carry",
                b0={"b_avail": "1000", "source": save_budget.POINTS_SOURCE},
                exec_quote="q", exec_quote_ref="r", contact_max_count=6)
            http = _fake_http([1000, 960, 960, 960],
                              {"finished": True, "status": "finished",
                               "companySaveCount": 10,
                               "contactSaveCount": 60})
            save_budget._settle_locked(
                root, project="p1", org="o1", token="tk", task_id="t-carry",
                http=http, clock=lambda: 0.0, sleep=lambda s: None,
                settle_stable_seconds=0.0)
            rows = [r for r in save_budget.read_ledger(root, "p1")
                    if r.get("kind") == "settle" and r.get("state") == "preliminary"]
            bid = rows[-1]["batch_id"]
            carried = save_budget.carry(root, project="p1", org="o1",
                                        batch_id=bid, b_after="960",
                                        settle_quote="q", settle_quote_ref="r")
            self.assertEqual(6, carried["contact_max_count"])
            carry_rows = [r for r in save_budget.read_ledger(root, "p1")
                          if r.get("kind") == "carry"
                          and r.get("batch_id") == bid]
            self.assertEqual(6, (carry_rows[-1].get("payload") or {})
                             .get("contact_max_count"))


class ProbeProposalBindingTest(unittest.TestCase):
    """AC3：sample_ready 必须绑定此前持久化的 probe 提案 ref。"""

    def test_ready_requires_persisted_matching_proposal(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            probe_row = {"b_avail": "5000", "read_at": save_budget._iso(),
                         "source": save_budget.POINTS_SOURCE,
                         "source_kind": "points"}
            save_budget.append_ledger(root, org_hash=save_budget.org_hash("o1"),
                                      project="p1", kind="probe",
                                      source_ref=probe_row["source"],
                                      payload=probe_row)
            # 第一步：不带 ack → 生成并持久化 probe 提案（真实用户流）
            proposal = save_budget.plan(root, project="p1", org="o1",
                                        b_plan="5000", b_avail="5000",
                                        read_at=probe_row["read_at"],
                                        balance_source=save_budget.POINTS_SOURCE)
            self.assertEqual("sample_needs_ack", proposal["status"])
            ref = proposal["proposal_ref"]
            # 任意非空 ack 不再 ready：ref 必须匹配已持久化提案
            with self.assertRaises(save_budget.BudgetError):
                save_budget.plan(root, project="p1", org="o1",
                                 b_plan="5000", b_avail="5000",
                                 read_at=probe_row["read_at"],
                                 balance_source=save_budget.POINTS_SOURCE,
                                 sample_ack_quote="确认样本",
                                 sample_ack_ref="任意字符串")
            # 匹配的 ref 才 sample_ready
            got = save_budget.plan(root, project="p1", org="o1",
                                   b_plan="5000", b_avail="5000",
                                   read_at=probe_row["read_at"],
                                   balance_source=save_budget.POINTS_SOURCE,
                                   sample_ack_quote="确认",
                                   sample_ack_ref=ref)
            self.assertEqual("sample_ready", got["status"])

    def test_stale_tier_proposal_not_ready(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            probe_row = {"b_avail": "5000", "read_at": save_budget._iso(),
                         "source": save_budget.POINTS_SOURCE,
                         "source_kind": "points"}
            save_budget.append_ledger(root, org_hash=save_budget.org_hash("o1"),
                                      project="p1", kind="probe",
                                      source_ref=probe_row["source"],
                                      payload=probe_row)
            save_budget.append_ledger(
                root, org_hash=save_budget.org_hash("o1"), project="p1",
                kind="plan", source_ref="bootstrap_sample",
                state="probe_proposal", payload={
                    "round_id": "r-1", "probe_level": 100, "sample_n": 100,
                    "b_plan": "5000", "contact_max_count": 3,
                    "risk_notice": "风险", "proposal_ref": "prop-3"})
            # 9 档请求不能拿 3 档旧提案 ready
            with self.assertRaises(save_budget.BudgetError):
                save_budget.plan(root, project="p1", org="o1",
                                 b_plan="5000", b_avail="5000",
                                 read_at=probe_row["read_at"],
                                 balance_source=save_budget.POINTS_SOURCE,
                                 contact_max_count=9,
                                 sample_ack_quote="确认样本",
                                 sample_ack_ref="prop-3")


if __name__ == "__main__":
    unittest.main()


class AckSemanticsTest(unittest.TestCase):
    """TASK-20261027-ack-close：否定原话不得记 ack；数字必须=提案 N。"""

    def _proposal(self, root):
        probe_row = {"b_avail": "5000", "read_at": save_budget._iso(),
                     "source": save_budget.POINTS_SOURCE,
                     "source_kind": "points"}
        save_budget.append_ledger(root, org_hash=save_budget.org_hash("o1"),
                                  project="p1", kind="probe",
                                  source_ref=probe_row["source"],
                                  payload=probe_row)
        return save_budget.plan(root, project="p1", org="o1",
                                b_plan="5000", b_avail="5000",
                                read_at=probe_row["read_at"],
                                balance_source=save_budget.POINTS_SOURCE)

    def _kinds_states(self, root):
        return [(r.get("kind"), r.get("state"))
                for r in save_budget.read_ledger(root, "p1")]

    def test_negative_quotes_never_ready_and_no_pollution(self):
        for bad in ("不要", "不确认", "取消", "等等", "确认吗", "是否保存", "确认？"):
            with self.subTest(bad=bad):
                with tempfile.TemporaryDirectory() as td:
                    root = Path(td)
                    prop = self._proposal(root)
                    ref = prop["proposal_ref"]
                    before = set(self._kinds_states(root))
                    with self.assertRaises(save_budget.BudgetError):
                        save_budget.plan(root, project="p1", org="o1",
                                         b_plan="5000", b_avail="5000",
                                         read_at=None,
                                         balance_source=save_budget.POINTS_SOURCE,
                                         sample_ack_quote=bad,
                                         sample_ack_ref=ref)
                    after = set(self._kinds_states(root))
                    self.assertEqual(before, after,
                                     "否定原话不得追加 sample_ack/probe_level 行")

    def test_plain_confirm_and_exact_n_still_ready(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            prop = self._proposal(root)
            ref = prop["proposal_ref"]
            n = prop["sample_n"]
            for quote in ("确认", "确定"):
                with self.subTest(quote=quote):
                    probe_row = {"b_avail": "5000",
                                 "read_at": save_budget._iso(),
                                 "source": save_budget.POINTS_SOURCE,
                                 "source_kind": "points"}
                    save_budget.append_ledger(
                        root, org_hash=save_budget.org_hash("o1"),
                        project="p1", kind="probe",
                        source_ref=probe_row["source"], payload=probe_row)
                    got = save_budget.plan(root, project="p1", org="o1",
                                           b_plan="5000", b_avail="5000",
                                           read_at=probe_row["read_at"],
                                           balance_source=save_budget.POINTS_SOURCE,
                                           sample_ack_quote=quote,
                                           sample_ack_ref=ref)
                    self.assertEqual("sample_ready", got["status"])
            # 纯数字 = 提案 N 也算肯定授权
            got = save_budget.plan(root, project="p1", org="o1",
                                   b_plan="5000", b_avail="5000",
                                   read_at=None,
                                   balance_source=save_budget.POINTS_SOURCE,
                                   sample_ack_quote=str(n),
                                   sample_ack_ref=ref)
            self.assertEqual("sample_ready", got["status"])

    def test_number_one_is_not_consent_for_n100(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            prop = self._proposal(root)
            self.assertEqual(100, prop["sample_n"])
            with self.assertRaises(save_budget.BudgetError):
                save_budget.plan(root, project="p1", org="o1",
                                 b_plan="5000", b_avail="5000",
                                 read_at=None,
                                 balance_source=save_budget.POINTS_SOURCE,
                                 sample_ack_quote="1",
                                 sample_ack_ref=prop["proposal_ref"])


class Tier9ProbeReachabilityTest(unittest.TestCase):
    """ack-close AC2 可达性：只有 3 档已结转历史时，9 档必须能产本档 100 探针提案。"""

    def test_tier3_history_then_tier9_proposal_flow(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            got = save_budget.begin_batch(
                root, project="p1", org="o1", task_id="t3",
                b0={"b_avail": "5000", "source": save_budget.POINTS_SOURCE},
                exec_quote="q", exec_quote_ref="r", contact_max_count=3)

            def _http(bal, comp, cont):
                seq = {"i": 0}

                def http(endpoint, payload=None):
                    if endpoint == "account/current":
                        i = min(seq["i"], len(bal) - 1)
                        seq["i"] += 1
                        return {"success": True,
                                "data": {"creditCount": bal[i]}}
                    return {"success": True, "data": {
                        "finished": True, "status": "finished",
                        "companySaveCount": comp, "contactSaveCount": cont}}
                return http

            save_budget._settle_locked(
                root, project="p1", org="o1", token="tk", task_id="t3",
                http=_http([5000, 4970, 4970, 4970], 20, 60),
                clock=lambda: 0.0, sleep=lambda s: None,
                settle_stable_seconds=0.0, batch_id=got["batch_id"])
            save_budget.carry(root, project="p1", org="o1",
                              batch_id=got["batch_id"], b_after="4970",
                              settle_quote="q", settle_quote_ref="r")
            a3 = save_budget.round_accounts(root, project="p1", org="o1",
                                            contact_max_count=3)
            self.assertEqual(1, a3["clean_count"])
            a9 = save_budget.round_accounts(root, project="p1", org="o1",
                                            contact_max_count=9)
            self.assertEqual(0, a9["clean_count"])
            probe_row = {"b_avail": "4970", "read_at": save_budget._iso(),
                         "source": save_budget.POINTS_SOURCE,
                         "source_kind": "points"}
            save_budget.append_ledger(root, org_hash=save_budget.org_hash("o1"),
                                      project="p1", kind="probe",
                                      source_ref=probe_row["source"],
                                      payload=probe_row)
            prop = save_budget.plan(root, project="p1", org="o1",
                                    b_plan="5000", b_avail="4970",
                                    read_at=probe_row["read_at"],
                                    balance_source=save_budget.POINTS_SOURCE,
                                    contact_max_count=9)
            self.assertEqual("sample_needs_ack", prop["status"])
            self.assertEqual(100, prop["sample_n"])
            self.assertEqual(9, prop["contact_max_count"])
            ready = save_budget.plan(root, project="p1", org="o1",
                                     b_plan="5000", b_avail="4970",
                                     read_at=None,
                                     balance_source=save_budget.POINTS_SOURCE,
                                     contact_max_count=9,
                                     sample_ack_quote="确认",
                                     sample_ack_ref=prop["proposal_ref"])
            self.assertEqual("sample_ready", ready["status"])


# ===== R2：A 耗尽新档 / B 错档卡 canonical / C 余额 finite =====
import subprocess  # noqa: E402
import time  # noqa: E402
from unittest import mock  # noqa: E402

import count_guard  # noqa: E402
import rule_check  # noqa: E402
import save_plan as planlib  # noqa: E402

sys.path.insert(0, str(ROOT / "tests"))
import test_contact_tier_budget as tb  # noqa: E402


def _probe_row(root, bal="1000", org="o1"):
    row = {"b_avail": bal, "read_at": save_budget._iso(),
           "source": save_budget.POINTS_SOURCE, "source_kind": "points"}
    save_budget.append_ledger(root, org_hash=save_budget.org_hash(org),
                              project="p1", kind="probe",
                              source_ref=row["source"], payload=row)
    return row


class R2ExhaustedTierTest(unittest.TestCase):
    """R2-A：BPlan 被全档 spent_all 耗尽后，新档不得再产 probe 提案或 ack。"""

    def _spend(self, root, task, cost, tier=3):
        got = save_budget.begin_batch(
            root, project="p1", org="o1", task_id=task,
            b0={"b_avail": "5000", "source": save_budget.POINTS_SOURCE},
            exec_quote="q", exec_quote_ref="r", contact_max_count=tier)
        seq = {"i": 0}
        bal = [5000, 5000 - cost, 5000 - cost, 5000 - cost]

        def http(endpoint, payload=None):
            if endpoint == "account/current":
                i = min(seq["i"], len(bal) - 1)
                seq["i"] += 1
                return {"success": True, "data": {"creditCount": bal[i]}}
            return {"success": True, "data": {
                "finished": True, "status": "finished",
                "companySaveCount": 20, "contactSaveCount": 60}}
        save_budget._settle_locked(
            root, project="p1", org="o1", token="tk", task_id=task,
            http=http, clock=lambda: 0.0, sleep=lambda s: None,
            settle_stable_seconds=0.0, batch_id=got["batch_id"])
        save_budget.carry(root, project="p1", org="o1",
                          batch_id=got["batch_id"], b_after=str(5000 - cost),
                          settle_quote="q", settle_quote_ref="r")

    def _plan(self, root, **kw):
        base = dict(project="p1", org="o1", b_plan="1000", b_avail="1000",
                    read_at=None, balance_source=save_budget.POINTS_SOURCE)
        base.update(kw)
        return save_budget.plan(root, **base)

    def test_tier9_refused_after_budget_exhausted_no_pollution(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            row = _probe_row(root)
            prop3 = self._plan(root, read_at=row["read_at"])
            ready3 = self._plan(root, read_at=row["read_at"],
                                sample_ack_quote="确认",
                                sample_ack_ref=prop3["proposal_ref"])
            self.assertEqual("sample_ready", ready3["status"])
            self._spend(root, "t-all", 1000, tier=3)
            before = [(r["kind"], r["state"])
                      for r in save_budget.read_ledger(root, "p1")]
            with self.assertRaises(save_budget.BudgetError) as cm:
                self._plan(root, b_avail="5000", contact_max_count=9)
            self.assertEqual("E_BUDGET_EXHAUSTED", cm.exception.code)
            after = [(r["kind"], r["state"])
                     for r in save_budget.read_ledger(root, "p1")]
            self.assertEqual(before, after, "耗尽后不得落新提案/ack/probe_level")

    def test_proposal_bound_to_remaining_and_invalidated_by_spend(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            row = _probe_row(root)
            p9 = self._plan(root, read_at=row["read_at"], contact_max_count=9)
            self._spend(root, "t-part", 300, tier=3)
            with self.assertRaises(save_budget.BudgetError):
                self._plan(root, b_avail="4700", contact_max_count=9,
                           sample_ack_quote="确认",
                           sample_ack_ref=p9["proposal_ref"])
            fresh = self._plan(root, b_avail="4700", contact_max_count=9)
            self.assertNotEqual(p9["proposal_ref"], fresh["proposal_ref"])
            self.assertIn("700", fresh["risk_notice"])
            self.assertEqual(100, fresh["sample_n"])
            ready = self._plan(root, b_avail="4700", contact_max_count=9,
                               sample_ack_quote="确认",
                               sample_ack_ref=fresh["proposal_ref"])
            self.assertEqual("sample_ready", ready["status"])


class R2TierCanonicalTest(unittest.TestCase):
    """R2-B：wire 唯一真源；错档 draft 出卡前/授权落盘前拒，canonical 无污染。"""

    def _prepare(self, root, tier, top="same"):
        manifest = root / "audit.json"
        manifest.write_text("{}", encoding="utf-8")
        offline = {
            "count_evidence": tb._evidence(), "count_mode": "explicit_small",
            "selectTotal": 20, "explicit_count": 20,
            "sample_ack": "确认保存 前 20 家", "count_quote": "确认保存 前 20 家",
            "wire_payload": tb._wire(20, tier=tier),
            "companyTags": ["ctag1"], "contactTags": ["ctag2"],
            "contactVerifyStatus": ["valid", "unkown"],
        }
        if top == "same":
            offline["contactMaxCount"] = tier
        elif top is not None:
            offline["contactMaxCount"] = top
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
                budget=tb._budget(), coefficients=tb._coeff(),
                rule_excerpts=[], offline_input=offline)

    def test_wrong_tier_draft_refused_everywhere_without_pollution(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            good = self._prepare(root, 9)
            good_path = planlib.write_draft(root, good)
            card = planlib.present_card(root, good_path, now=time.time())
            cards_dir = root / ".local" / "guard_v2" / "cards"
            cards_before = sorted(p.name for p in cards_dir.glob("*.json"))
            bad = dict(good)
            bad["contactMaxCount"] = 3  # 旧版 top3/wire9
            bad_path = str(root / "bad.json")
            Path(bad_path).write_text(json.dumps(bad, ensure_ascii=False),
                                      encoding="utf-8")
            with self.assertRaises(planlib.PlanError) as cm:
                planlib.present_card(root, bad_path, now=time.time())
            self.assertEqual("E_CONTACT_TIER_MISMATCH", cm.exception.code)
            proc = subprocess.run(
                [sys.executable, str(TOOLS / "save_company_cli.py"), "present",
                 "--root", str(root), "--plan", bad_path],
                capture_output=True, text=True)
            self.assertEqual(2, proc.returncode, proc.stdout + proc.stderr)
            self.assertIn("E_CONTACT_TIER_MISMATCH", proc.stdout)
            with mock.patch("segment_registry.validate_source",
                            return_value={"platform_product_id": "p1",
                                          "generation_id": "g1",
                                          "segment_id": "s1"}), \
                 mock.patch("segment_registry.load_selection", return_value={}):
                with self.assertRaises(planlib.PlanError) as cm2:
                    planlib.confirm_plan(
                        root, planlib.load_plan(bad_path), quote="确认",
                        quote_ref=card["card_ref"], now=time.time(),
                        presentation=card["card_ref"])
            self.assertEqual("E_CONTACT_TIER_MISMATCH", cm2.exception.code)
            on_disk = json.loads(Path(good_path).read_text(encoding="utf-8"))
            self.assertEqual("draft", on_disk["status"])
            self.assertEqual(cards_before,
                             sorted(p.name for p in cards_dir.glob("*.json")))
            self.assertEqual([], list(root.glob(".local/**/*ticket*")))

    def test_prepare_requires_strict_int_equal_top(self):
        for top, wire in ((9, 3), (3.0, 3), (True, 3), ("3", 3)):
            with self.subTest(top=top, wire=wire):
                with tempfile.TemporaryDirectory() as td:
                    with self.assertRaises(planlib.PlanError) as cm:
                        self._prepare(Path(td), wire, top=top)
                    self.assertEqual("E_CONTACT_TIER_MISMATCH", cm.exception.code)

    def test_tiers_3_6_9_present_show_wire_tier(self):
        for tier in (3, 6, 9):
            with self.subTest(tier=tier):
                with tempfile.TemporaryDirectory() as td:
                    root = Path(td)
                    draft = self._prepare(root, tier)
                    path = planlib.write_draft(root, draft)
                    card = planlib.present_card(root, path, now=time.time())
                    self.assertIn("每家公司最多 %d 个邮箱" % tier,
                                  card["card_text"])

    def test_check_save_and_validate_plan_recheck_tier(self):
        payload = tb._wire(20, tier=9)
        plan_doc = {"status": "confirmed", "wire_payload": payload,
                    "contactMaxCount": 3, "estimation": tb._coeff()}
        with self.assertRaises(rule_check.RuleCheckError) as cm:
            rule_check.check_save(payload, plan_doc)
        self.assertEqual("E_CONTACT_TIER_MISMATCH", cm.exception.code)
        with self.assertRaises(count_guard.CountError) as cm2:
            count_guard.validate_plan({
                "contactMaxCount": 3,
                "wire_payload": {"selectTotal": 5, "contactMaxCount": 9}})
        self.assertEqual("E_CONTACT_TIER_MISMATCH", cm2.exception.code)


class R2BalanceFiniteTest(unittest.TestCase):
    """R2-C：余额非有限/负/非数字明确拒；points 0 不 ready；view_quota 0 不等于点数 0。"""

    def test_bad_balance_rejected_without_pollution(self):
        for bad in ("NaN", "Infinity", "-Infinity", "abc", "-5", -5,
                    float("nan")):
            with self.subTest(bad=bad):
                with tempfile.TemporaryDirectory() as td:
                    root = Path(td)
                    _probe_row(root)
                    before = [(r["kind"], r["state"])
                              for r in save_budget.read_ledger(root, "p1")]
                    with self.assertRaises(save_budget.BudgetError):
                        save_budget.plan(
                            root, project="p1", org="o1", b_plan="1000",
                            b_avail=bad, read_at=None,
                            balance_source=save_budget.POINTS_SOURCE)
                    after = [(r["kind"], r["state"])
                             for r in save_budget.read_ledger(root, "p1")]
                    self.assertEqual(before, after)

    def test_helper_rejects_bad_balance(self):
        with self.assertRaises(save_budget.BudgetError):
            save_budget.bootstrap_sample(b_plan="1000", b_avail="NaN")

    def test_points_zero_refused_view_quota_zero_not_points(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            with self.assertRaises(save_budget.BudgetError) as cm:
                save_budget.plan(root, project="p1", org="o1", b_plan="1000",
                                 b_avail="0", read_at=None,
                                 balance_source=save_budget.POINTS_SOURCE)
            self.assertEqual("E_BUDGET_EXHAUSTED", cm.exception.code)
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            got = save_budget.plan(root, project="p1", org="o1",
                                   b_plan="1000", b_avail="0", read_at=None,
                                   balance_source=save_budget.QUOTA_SOURCE)
            self.assertEqual("sample_needs_ack", got["status"])
