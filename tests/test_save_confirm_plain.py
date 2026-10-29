# -*- coding: utf-8 -*-
"""v3 保存确认放宽 + 100 家探针：行为级回归（不是字符串检查）。

覆盖两个曾漏网的 P0：
  P0-1 纯确认必须在 auth_guard 真正铸票处放行（否则 confirm 写盘后必失败）。
  P0-2 探针 100 家必须在 count_guard 有合法模式（sample 只能 1、explicit_small≤50）。
"""
import json
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import auth_guard  # noqa: E402
import count_guard  # noqa: E402
import rule_check  # noqa: E402
import save_budget  # noqa: E402
import save_plan as planlib  # noqa: E402


def _evidence(threshold=450, returned=10):
    return {"threshold_page": threshold, "pool_total": 9999,
            "evidence_mode": "strict",
            "page_rows": [{"page": threshold, "returned": returned}]}


# ---- TASK-20261027-count-card：真实链路夹具（prepare→present→confirm→auth）----

_CC_NOW = {"t": time.time()}


def _cc_budget():
    return {"budget_points": {"points": 10000, "source_ref": "user", "version": "v1"},
            "max_points": {"points": 18000, "source_ref": "account", "version": "v1"}}


def _cc_coeff():
    return {"estimated_emails_per_company": {"value": "1.5", "source_ref": "cal",
                                             "version": "v1", "kind": "calibrated_upper"},
            "estimated_points_per_email": {"value": "1.5", "source_ref": "cal",
                                           "version": "v1", "kind": "calibrated_upper"}}


def _cc_wire(n):
    w = dict(rule_check.FIXED_VALUES)
    w.update({
        "companyTags": ["ctag1"], "contactTags": ["ctag2"],
        "contactVerifyStatus": ["valid", "unkown"],
        "contactMaxCount": 3, "selectTotal": n,
        "filters": [], "filter": {}, "keyword": "caps maker",
        "logic": "and", "selectSort": {},
    })
    return w


def _ledger(n=20):
    return {"status": "ready", "org_hash": "org-demo", "round_id": "round-demo",
            "exec_quote_ref": "确认保存 前 20 家",
            "confirm_n": n, "n_cons": n, "n_est": n, "risk_ack": False,
            "b_plan": "10000", "spent_all": "0", "budget_left": "10000",
            "per_company_upper": "2.25", "batch_points_upper": "10000"}


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
                "dependency_sha256": "0" * 64, "quote": "确认"}
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
        plan["quote"] = "确认保存 前 200 家"
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


class PlainNumericCountTest(unittest.TestCase):
    """TASK-20261027 AC1：纯 ASCII 正整数才当数量候选，其余一律 None。"""

    def test_accepts_ascii_positive_int(self):
        self.assertEqual(9560, rule_check.plain_numeric_save_count("9560"))
        self.assertEqual(20, rule_check.plain_numeric_save_count(" 20 "))

    def test_rejects_non_positive_or_compound(self):
        for q in ("0", "-3", "2.5", "20 200", "３", "一百", "3家吗？",
                  "不确认 20", "确认 20", "", None, "1/2"):
            with self.subTest(quote=q):
                self.assertIsNone(rule_check.plain_numeric_save_count(q))


class CountCardChainTest(unittest.TestCase):
    """TASK-20261027：真实链路 prepare -> present -> confirm -> authorize（零网络）。

    覆盖 AC1-AC4：纯数字 N 仅在已展示卡上下文授权且 N=卡值；0/负/小数/多数字/
    疑问/否定拒；「1」与菜单 1 歧义隔离；未展示/过期/异计划/异 revision/
    卡 hash 篡改/依赖变化拒；confirm 失败不留 confirmed 假状态；带单位原话回归不破坏。
    """

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)
        ledger = _ledger(20)
        save_budget.append_ledger(
            self.root, org_hash="org-demo", project="op/prod", kind="plan",
            source_ref="确认保存 前 20 家", state="ready",
            payload={"confirm_n": 20, "b_plan": "10000", "n_cons": 20,
                     "n_est": 20, "batch_points_upper": "10000",
                     "spent_all": "0", "budget_left": "10000",
                     "per_company_upper": "2.25", "round_id": "round-demo",
                     "exec_quote_ref": "确认保存 前 20 家", "risk_ack": False})
        self.offline = {
            "count_evidence": _evidence(), "count_mode": "explicit_small",
            "budget_ledger": ledger,
            "selectTotal": 20, "explicit_count": 20,
            "sample_ack": "确认保存 前 20 家",
            "count_quote": "确认保存 前 20 家",
            "wire_payload": _cc_wire(20),
            "companyTags": ["ctag1"], "contactTags": ["ctag2"],
            "contactMaxCount": 3, "contactVerifyStatus": ["valid", "unkown"],
        }
        self.gate = {"ack": False}
        self._gate_patch = mock.patch.object(
            auth_guard, "_require_startup_ack",
            side_effect=self._gate_stub)
        self._gate_patch.start()
        self.addCleanup(self._gate_patch.stop)

    def _gate_stub(self):
        if not self.gate["ack"]:
            raise RuntimeError("开工门未放行（测试桩）")

    def _registry_stub(self):
        record = {"platform_product_id": "p1", "generation_id": "g1",
                  "segment_id": "s1", "inf_id": "i1",
                  "query_en": "caps maker", "query_en_sha256": "0" * 64,
                  "response_sha256": "0" * 64}
        return (mock.patch("segment_registry.validate_source",
                           return_value=record),
                mock.patch("segment_registry.load_selection",
                           return_value={}))

    def _prepare(self, revision=1, plan_id="plan-cc1"):
        # confirm/execute 会真实重跑 build_dependencies（读 audit manifest），
        # 夹具提供真实 manifest 文件；registry 校验放行，依赖快照按同一 stub 重建。
        manifest = self.root / "audit.json"
        manifest.write_text(json.dumps({"window": {"from": 1, "to": 3},
                                        "evidence_mode": "strict"},
                                       ensure_ascii=False), encoding="utf-8")
        real_build = planlib.build_dependencies

        def build_stub(root, plan):
            v, s = self._registry_stub()
            with v, s:
                return real_build(Path(root), plan)

        offline = dict(self.offline)
        offline["plan_id"] = plan_id
        offline["revision"] = revision
        offline["audit_manifest"] = str(manifest)
        v, s = self._registry_stub()
        with v, s, \
             mock.patch.object(planlib, "validate_offline_tags"), \
             mock.patch.object(planlib, "build_dependencies", return_value={}):
            draft = planlib.prepare_save(
                self.root, project="op/prod",
                source={"platform_product_id": "p1", "generation_id": "g1",
                        "segment_id": "s1", "keyword": "caps maker",
                        "audit_manifest": str(manifest)},
                audit={"path": str(manifest), "window": {}},
                budget=_cc_budget(), coefficients=_cc_coeff(),
                rule_excerpts=[], offline_input=offline,
                audit_manifest_path=str(manifest))
        deps = build_stub(self.root, draft)
        draft["dependencies"] = deps
        draft["dependency_sha256"] = rule_check.canonical_hash(deps)
        return planlib.write_draft(self.root, draft)

    def _present(self, draft_path):
        return planlib.present_card(self.root, draft_path, now=_CC_NOW["t"])

    def _confirm(self, draft_path, quote, ref, now=None):
        draft = planlib.load_plan(draft_path)
        v, s = self._registry_stub()
        with v, s:
            return planlib.confirm_plan(self.root, draft, quote=quote,
                                        quote_ref=ref,
                                        now=now if now is not None else _CC_NOW["t"],
                                        presentation=ref)

    def _authorize(self, confirmed):
        self.gate["ack"] = True
        committed = planlib.commit_confirmed(self.root, confirmed)
        final = dict(confirmed)
        final["status"] = "confirmed"
        self.assertEqual(True, committed.get("ok"), committed)
        return auth_guard.authorize_save_plan(
            "save", final["quote"], final["wire_payload"],
            plan=final, task="t-cc", root=self.root)

    # ---- AC1: 纯数字 N 仅在卡上下文授权 ----

    def test_numeric_n_equals_card_passes_and_binds_card(self):
        draft = self._prepare()
        card = self._present(draft)
        confirmed = self._confirm(draft, "20", card["card_ref"])
        # R2：库级 confirm 先落 confirmed_pending；commit 后才 confirmed
        self.assertEqual("confirmed_pending", confirmed["status"])
        committed = planlib.commit_confirmed(self.root, confirmed)
        self.assertEqual(True, committed.get("ok"), committed)
        on_disk = json.loads(
            Path(planlib.plan_path(self.root, confirmed["plan_id"],
                                   confirmed["revision"])).read_text("utf-8"))
        self.assertEqual("confirmed", on_disk["status"])
        self.assertEqual("card", on_disk["count_bound_by"])
        self.assertEqual(20, on_disk["count_bound_n"])
        res = self._authorize(confirmed)
        self.assertTrue(res.get("ok"), res)

    def test_numeric_n_mismatch_is_change_request_not_auth(self):
        draft = self._prepare()
        card = self._present(draft)
        with self.assertRaises(planlib.PlanError) as cm:
            self._confirm(draft, "9560", card["card_ref"])
        self.assertEqual("E_AUTH_COUNT_MISMATCH", cm.exception.code)

    def test_bad_numerics_rejected(self):
        draft = self._prepare()
        card = self._present(draft)
        for q in ("0", "-3", "2.5", "20 200", "3家吗？", "不确认 20", "一百"):
            with self.subTest(quote=q):
                with self.assertRaises(planlib.PlanError):
                    self._confirm(draft, q, card["card_ref"])

    def test_numeric_one_not_menu_shortcut(self):
        draft = self._prepare()
        card = self._present(draft)
        with self.assertRaises(planlib.PlanError) as cm:
            self._confirm(draft, "1", card["card_ref"])
        self.assertEqual("E_AUTH_COUNT_MISMATCH", cm.exception.code)

    # ---- AC2: presentation 引用与校验 ----

    def test_confirm_requires_presentation(self):
        draft = self._prepare()
        with self.assertRaises(planlib.PlanError) as cm:
            self._confirm(draft, "确认", "self-invented-ref")
        self.assertIn(cm.exception.code,
                      ("E_CARD_REQUIRED", "E_CARD_UNKNOWN"))

    def test_confirm_rejects_unknown_card(self):
        draft = self._prepare()
        self._present(draft)
        with self.assertRaises(planlib.PlanError) as cm:
            self._confirm(draft, "20", "card-unknown-0000")
        self.assertIn(cm.exception.code,
                      ("E_CARD_REQUIRED", "E_CARD_UNKNOWN"))

    def test_expired_card_rejected(self):
        draft = self._prepare()
        card = self._present(draft)
        later = _CC_NOW["t"] + 31 * 60
        with self.assertRaises(planlib.PlanError) as cm:
            self._confirm(draft, "20", card["card_ref"], now=later)
        self.assertIn(cm.exception.code,
                      ("E_CARD_EXPIRED", "E_PLAN_DEPENDENCY_CHANGED"))

    def test_wrong_plan_revision_rejected(self):
        d1 = self._prepare(plan_id="plan-a")
        d2 = self._prepare(plan_id="plan-b")
        card = self._present(d2)
        with self.assertRaises(planlib.PlanError) as cm:
            self._confirm(d1, "20", card["card_ref"])
        self.assertIn(cm.exception.code,
                      ("E_CARD_MISMATCH", "E_PLAN_REQUIRED", "E_CARD_UNKNOWN"))

    def test_tampered_card_hash_rejected(self):
        draft = self._prepare()
        card = self._present(draft)
        p = planlib.card_path(self.root, card["card_ref"])
        doc = json.loads(p.read_text(encoding="utf-8"))
        doc["card"]["n"] = 9560
        p.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
        with self.assertRaises(planlib.PlanError) as cm:
            self._confirm(draft, "9560", card["card_ref"])
        self.assertIn(cm.exception.code,
                      ("E_CARD_TAMPERED", "E_CARD_MISMATCH"))

    # ---- AC3: 铸票端再校验 ----

    def test_authorize_rejects_missing_card_binding_on_numeric(self):
        draft = self._prepare()
        confirmed = self._confirm(draft, "20",
                                  self._present(draft)["card_ref"])
        confirmed.pop("count_bound_by", None)
        res = self._authorize(confirmed)
        self.assertFalse(res.get("ok"), res)

    def test_confirm_failure_leaves_draft_unconfirmed(self):
        draft = self._prepare()
        card = self._present(draft)
        with self.assertRaises(planlib.PlanError):
            self._confirm(draft, "9560", card["card_ref"])
        doc = json.loads(Path(draft).read_text(encoding="utf-8"))
        self.assertEqual("draft", doc["status"])

    def test_explicit_count_quote_still_works(self):
        draft = self._prepare()
        card = self._present(draft)
        confirmed = self._confirm(draft, "确认保存 前 20 家", card["card_ref"])
        self.assertEqual("quote", confirmed["count_bound_by"])
        res = self._authorize(confirmed)
        self.assertTrue(res.get("ok"), res)

    # ---- AC4: 依赖变化 ----

    def test_dependency_change_rejects_confirm(self):
        draft = self._prepare()
        card = self._present(draft)
        doc = json.loads(Path(draft).read_text(encoding="utf-8"))
        doc["dependency_sha256"] = "0" * 64
        Path(draft).write_text(json.dumps(doc, ensure_ascii=False),
                               encoding="utf-8")
        with self.assertRaises(planlib.PlanError) as cm:
            self._confirm(draft, "20", card["card_ref"])
        self.assertEqual("E_PLAN_DEPENDENCY_CHANGED", cm.exception.code)


def _rewrite_card_resign(path, doc):
    """改卡后只重签卡体自 hash（content_sha256 与 card 保持一致），
    用于模拟「重签内容指纹但时间字段非法/缺失」的攻击面。"""
    doc["content_sha256"] = rule_check.canonical_hash(doc.get("card") or {})
    path.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")


def _ts_to_epoch(ts):
    import calendar as _cal
    import time as _time
    return _cal.timegm(_time.strptime(ts, "%Y-%m-%dT%H:%M:%SZ"))


class CardStrictExpiryTest(unittest.TestCase):
    """R2-AC1：卡时间元数据严格 fail-closed + 纳入内容指纹。

    三席复现缺陷：expires_at 缺失/空串/非法 → deadline=0 → 跳过过期校验放行；
    改远未来 2199 不重算 hash 也能过。红：全放行；绿：E_CARD_TAMPERED/EXPIRED。
    """

    def _carded_draft(self):
        case = CountCardChainTest()
        case.setUp()
        self.addCleanup(case._tmp.cleanup)
        self.addCleanup(case._gate_patch.stop)
        draft = case._prepare()
        card = case._present(draft)
        return case, draft, card

    def test_missing_expires_fail_closed(self):
        case, draft, card = self._carded_draft()
        p = planlib.card_path(case.root, card["card_ref"])
        doc = json.loads(p.read_text(encoding="utf-8"))
        doc.pop("expires_at", None)
        _rewrite_card_resign(p, doc)
        with self.assertRaises(planlib.PlanError) as cm:
            case._confirm(draft, "20", card["card_ref"])
        self.assertIn(cm.exception.code,
                      ("E_CARD_TAMPERED", "E_CARD_EXPIRED", "E_CARD_TIME_INVALID"))

    def test_empty_or_malformed_expires_fail_closed(self):
        for bad in ("", "not-a-time", "2199-01-01", None, 123):
            with self.subTest(expires=bad):
                case, draft, card = self._carded_draft()
                p = planlib.card_path(case.root, card["card_ref"])
                doc = json.loads(p.read_text(encoding="utf-8"))
                doc["expires_at"] = bad
                _rewrite_card_resign(p, doc)
                with self.assertRaises(planlib.PlanError) as cm:
                    case._confirm(draft, "20", card["card_ref"])
                self.assertIn(cm.exception.code,
                              ("E_CARD_TAMPERED", "E_CARD_EXPIRED", "E_CARD_TIME_INVALID"))

    def test_far_future_rewrite_without_rehash_rejected(self):
        """改远未来 2199 但不重算 content_sha256 → 拒（时间在指纹里，改必被察觉）。"""
        case, draft, card = self._carded_draft()
        p = planlib.card_path(case.root, card["card_ref"])
        doc = json.loads(p.read_text(encoding="utf-8"))
        doc["expires_at"] = "2199-01-01T00:00:00Z"
        doc["presented_at"] = "2199-01-01T00:00:00Z"
        p.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
        with self.assertRaises(planlib.PlanError) as cm:
            case._confirm(draft, "20", card["card_ref"])
        self.assertIn(cm.exception.code,
                      ("E_CARD_TAMPERED", "E_CARD_TIME_INVALID"))

    def test_ttl_cannot_exceed_plan_ttl_or_card_ttl(self):
        """卡有效期不得长于计划有效期与 CARD_TTL（时间顺序有效）。"""
        case, draft, card = self._carded_draft()
        p = planlib.card_path(case.root, card["card_ref"])
        doc = json.loads(p.read_text(encoding="utf-8"))
        draft_doc = json.loads(Path(draft).read_text(encoding="utf-8"))
        plan_deadline = _ts_to_epoch(draft_doc["expires_at"])
        card_deadline = _ts_to_epoch(doc["expires_at"])
        self.assertLessEqual(card_deadline, plan_deadline + 60,
                             "卡有效期不能比计划还长")
        self.assertLessEqual(card_deadline - _ts_to_epoch(doc["presented_at"]),
                             planlib.CARD_TTL_SECONDS + 60)

    def test_non_finite_now_rejected(self):
        case, draft, card = self._carded_draft()
        for bad in (float("nan"), float("inf"), -float("inf")):
            with self.subTest(now=bad):
                with self.assertRaises(planlib.PlanError) as cm:
                    case._confirm(draft, "20", card["card_ref"], now=bad)
                self.assertIn(cm.exception.code,
                              ("E_CARD_TIME_INVALID", "E_AUTH_COUNT_AMBIGUOUS"))

    def test_draft_expired_fail_closed_too(self):
        """draft 自身 expires_at 非法也 fail-closed（不能 deadline=0 跳过）。"""
        case, draft, card = self._carded_draft()
        doc = json.loads(Path(draft).read_text(encoding="utf-8"))
        doc["expires_at"] = "garbage"
        Path(draft).write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
        with self.assertRaises(planlib.PlanError) as cm:
            case._confirm(draft, "20", card["card_ref"])
        self.assertIn(cm.exception.code,
                      ("E_PLAN_DEPENDENCY_CHANGED", "E_CARD_TIME_INVALID"),
                      "draft 时间非法必须 fail-closed，不得 deadline=0 放行")


class CardPlainTextTest(unittest.TestCase):
    """R2-AC3：卡面白话化——正文只留数量/邮箱/点数/预算/回什么/下一步。"""

    def _presented(self):
        case = CountCardChainTest()
        case.setUp()
        self.addCleanup(case._tmp.cleanup)
        self.addCleanup(case._gate_patch.stop)
        draft = case._prepare()
        return case, draft, case._present(draft)

    def test_card_text_has_no_internal_ids(self):
        case, draft, card = self._presented()
        draft_doc = json.loads(Path(draft).read_text(encoding="utf-8"))
        text = card["card_text"]
        for token in (draft_doc["plan_id"], str(draft_doc["revision"]),
                      str(draft_doc.get("project") or ""),
                      card["card_ref"], card["content_sha256"],
                      str(draft_doc.get("wire_payload_sha256") or ""),
                      str(draft_doc.get("dependency_sha256") or "")):
            # 单个数字（如 revision=1）不作为泄漏判定：正常白话必含数字；
            # 只查非平凡内部标识（长度≥4 或含分隔符/前缀）。
            if token and (len(str(token)) >= 4 or "-" in str(token)):
                self.assertNotIn(str(token), text,
                                 "内部标识不得出现在用户卡面: %r" % token)
        self.assertNotIn(str(draft_doc.get("project") or ""), text)
        for needle in ("保存家数", "预计扣点", "预算上限", "回「确认」", "下一步"):
            self.assertIn(needle, text)

    def test_card_text_numbers_not_budget_as_cost(self):
        """budget_points 是预算上限材料，不得冒充预计扣点；来源不明写未知。"""
        case, draft, card = self._presented()
        draft_doc = json.loads(Path(draft).read_text(encoding="utf-8"))
        text = card["card_text"]
        self.assertIn("预计扣点", text)
        est = (draft_doc.get("computed") or {}).get("estimated_points")
        self.assertTrue(est and str(est) in text, "预计扣点应取 computed 值")

    def test_json_metadata_keeps_internal_fields(self):
        case, draft, card = self._presented()
        draft_doc = json.loads(Path(draft).read_text(encoding="utf-8"))
        doc = json.loads(Path(card["card_path"]).read_text(encoding="utf-8"))
        for key in ("card_ref", "content_sha256", "card"):
            self.assertIn(key, doc)
        self.assertEqual(draft_doc["plan_id"], doc["card"]["plan_id"])


class ProbeNotOneTest(unittest.TestCase):
    def test_sample_mode_still_one(self):
        got = count_guard.derive(_evidence(), _plan(), mode="sample")
        self.assertEqual(got["select_total"], 1)


if __name__ == "__main__":
    unittest.main()
