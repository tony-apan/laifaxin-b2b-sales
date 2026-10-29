#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""TASK-20261028-interface-A 永久回归：确认夹带修改意图 / 联合卡三数与加人前核对。

覆盖：
  A1 产品资料：认证X + "确认，但认证改成暂无" 必须拒确认、保留 draft/字段、exit 非0；
     正常"确认"和含"不锈钢"的正常句子不得误杀。
  A2 联合卡：5人卡 + "确认，但人数改成25" 必须保持 prepared、0审批、0平台写；
     回"1"仍按原规则确认。
  A4 保存卡：卡N=20 + "确认保存前20家，邮箱改成6个" 必须拒、保持 draft、不铸票；
     纯确认/卡面N/数字仍按原规则。
  A5 机器出卡：分开"已保存公司数"与"拟加入联系人数"，名单人数加入前核对；
     未知/不一致在写前拒绝（不伪造三数相等）。
"""
import hashlib
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT))

import approval  # noqa: E402
import auth_guard  # noqa: E402
import save_plan  # noqa: E402
import sequence_contact_bundle as bundle  # noqa: E402
import tests.test_save_confirm_plain as save_confirm_plain  # noqa: E402
import tests.test_sequence_contact_bundle as bundle_cli_tests  # noqa: E402


def _sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class ProductProfileMixedIntentTest(unittest.TestCase):
    """A1：资料确认夹带字段修改必须整句拒绝，不能只认"确认"两字。"""

    def _init_profile(self, tmp):
        profile = Path(tmp) / "product-profile.md"
        env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
        init = subprocess.run(
            [sys.executable, str(ROOT / "tools/product_profile.py"), "init",
             "--profile", str(profile), "--operator-key", "probe", "--product-key", "widget"],
            cwd=ROOT, env=env, text=True, capture_output=True, timeout=60)
        self.assertEqual(0, init.returncode, init.stdout + init.stderr)
        text = profile.read_text(encoding="utf-8")
        old = ("## ⑤ 规格/认证（型号/标准号/证书/参数——有来源才写）\n"
               "- 内容：（待补）\n- source: none\n- confidence: low")
        new = ("## ⑤ 规格/认证（型号/标准号/证书/参数——有来源才写）\n"
               "- 内容：认证X\n- source: 用户\n- confidence: high")
        self.assertIn(old, text)
        profile.write_text(text.replace(old, new), encoding="utf-8")
        return profile, env

    def _confirm(self, profile, quote, env):
        return subprocess.run(
            [sys.executable, str(ROOT / "tools/product_profile.py"), "confirm",
             "--profile", str(profile), "--by", "Tony", "--quote", quote],
            cwd=ROOT, env=env, text=True, capture_output=True, timeout=60)

    def test_mixed_field_change_keeps_draft_and_fields(self):
        with tempfile.TemporaryDirectory() as tmp:
            profile, env = self._init_profile(tmp)
            before = profile.read_bytes()
            r = self._confirm(profile, "确认，但认证改成暂无", env)
            self.assertNotEqual(0, r.returncode, r.stdout + r.stderr)
            self.assertIn("修改", r.stdout + r.stderr)
            self.assertEqual(before, profile.read_bytes(), "拒绝时不得改写档案")
            text = profile.read_text(encoding="utf-8")
            self.assertIn("status: draft", text)
            self.assertIn("- 内容：认证X", text)
            self.assertNotIn("status: confirmed", text)

    def test_clean_confirm_and_stainless_text_not_false_killed(self):
        with tempfile.TemporaryDirectory() as tmp:
            profile, env = self._init_profile(tmp)
            text = profile.read_text(encoding="utf-8")
            text = text.replace("## ② 产品线（品类/子品类/SKU/成分配比）\n- 内容：（待补）", "## ② 产品线（品类/子品类/SKU/成分配比）\n- 内容：不锈钢杯")
            profile.write_text(text, encoding="utf-8")
            r = self._confirm(profile, "确认，产品是不锈钢杯", env)
            self.assertEqual(0, r.returncode, r.stdout + r.stderr)
            self.assertIn("status: confirmed", profile.read_text(encoding="utf-8"))

    def test_plain_confirm_still_accepted(self):
        with tempfile.TemporaryDirectory() as tmp:
            profile, env = self._init_profile(tmp)
            r = self._confirm(profile, "确认", env)
            self.assertEqual(0, r.returncode, r.stdout + r.stderr)


class BundleFixture(unittest.TestCase):
    """A2/A5：进程内最小联合卡夹具；不触网、不写仓库审批账本。"""

    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.tmp = Path(self.tmpdir.name)
        self._old_kb = bundle.KB
        bundle.KB = self.tmp
        self._old_approvals = approval.APPROVALS
        self._old_used = approval.USED_LEDGER
        approval.APPROVALS = self.tmp / "approvals.tsv"
        approval.USED_LEDGER = self.tmp / "approvals-used.tsv"
        self.addCleanup(self._restore)
        self.path = self._make_bundle()

    def _restore(self):
        bundle.KB = self._old_kb
        approval.APPROVALS = self._old_approvals
        approval.USED_LEDGER = self._old_used
        self.tmpdir.cleanup()

    def _make_bundle(self):
        tmap = self.tmp / "tmap.json"
        tmap.write_text("{}", encoding="utf-8")
        tmeta = self.tmp / "tmap.meta.json"
        tmeta.write_text(json.dumps({"tmap_sha256": _sha(tmap)}), encoding="utf-8")
        profile = self.tmp / "product-profile.md"
        profile.write_text("---\nstatus: confirmed\n---\n", encoding="utf-8")
        record = self.tmp / "operation-record.md"
        record.write_text("---\nstatus: S8\n---\n", encoding="utf-8")
        wire = {"contactTags": ["tag-1"], "companyTags": ["ctag"], "selectTotal": 5}
        plan = {"kind": "save_plan", "project": "op/prod", "plan_id": "p", "revision": 1,
                "status": "confirmed", "selectTotal": 5,
                "wire_payload_sha256": save_plan.rule_check.canonical_hash(wire),
                "dependency_sha256": "0" * 64, "count_hash": "a" * 64, "wire_payload": wire}
        plan["binding_sha256"] = save_plan.binding_hash(plan)
        s5 = self.tmp / "s5-plan.json"
        s5.write_text(json.dumps(plan), encoding="utf-8")
        d = {
            "kind": "sequence_contact_bundle", "project": "op/prod",
            "org_sha256": hashlib.sha256(b"org").hexdigest(), "status": "prepared",
            "deps": {
                "record": {"path": str(record)},
                "tmap": {"path": str(tmap), "sha256": _sha(tmap)},
                "tmap_meta": {"path": str(tmeta), "sha256": _sha(tmeta)},
                "profile": {"path": str(profile), "sha256": _sha(profile)},
                "s5_plan": {"path": str(s5), "sha256": _sha(s5),
                            "binding_sha256": plan["binding_sha256"]},
            },
            "s9": {"name": "不锈钢-客户-12轮", "from_name": "Tony", "tz": "America/New_York",
                   "max_per_day": 30000, "per_domain": 5, "tmap_sha256": _sha(tmap),
                   "profile": {"sha256": _sha(profile), "status": "confirmed", "version": "1"},
                   "rules": {"steps": 12, "waits": "x", "tz": "America/New_York",
                             "daily_limit": "30000/5", "not_sent_tags": "询盘/不发"}},
            "s10": {"tags": ["tag-1"], "task": "task-1", "expected_contacts": 5,
                    "saved_companies": 5, "seq": bundle.SYMBOL},
            "steps": {},
        }
        d["plan_hash"] = auth_guard.bundle_plan_hash(d)
        path = bundle._dir() / f"bundle-{d['plan_hash'][:12]}.json"
        path.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
        return path

    def _present(self):
        bundle.present(Namespace(bundle=str(self.path), ttl_seconds=60))
        cards = sorted(bundle._dir().glob("card-*.json"))
        self.assertTrue(cards, "present 必须出卡")
        return cards[-1]

    def _approval_rows(self):
        if not approval.APPROVALS.exists():
            return []
        return [line for line in approval.APPROVALS.read_text(encoding="utf-8-sig").splitlines()[1:]
                if line.strip()]


class BundleMixedIntentTest(BundleFixture):
    def test_mixed_people_change_keeps_prepared_zero_approval(self):
        card = self._present()
        before = self.path.read_bytes()
        with self.assertRaises(SystemExit) as cm:
            bundle.confirm(Namespace(bundle=str(self.path), card=str(card),
                                     quote="确认，但人数改成25"))
        self.assertNotEqual(0, cm.exception.code)
        self.assertEqual(before, self.path.read_bytes(), "拒绝时不得改写联合计划")
        doc = json.loads(self.path.read_text(encoding="utf-8"))
        self.assertEqual("prepared", doc["status"])
        self.assertEqual([], self._approval_rows(), "修改意图不得铸任何审批")

    def test_bare_people_number_change_rejected(self):
        card = self._present()
        for quote in ("确认，25人", "确认，加5个", "确认;但人数改成25", "确认。人数改成25"):
            with self.subTest(quote=quote):
                with self.assertRaises(SystemExit) as cm:
                    bundle.confirm(Namespace(bundle=str(self.path), card=str(card),
                                             quote=quote))
                self.assertNotEqual(0, cm.exception.code)
                self.assertEqual("prepared",
                                 json.loads(self.path.read_text(encoding="utf-8"))["status"])
                self.assertEqual([], self._approval_rows())

    def test_plain_one_still_confirms(self):
        card = self._present()
        bundle.confirm(Namespace(bundle=str(self.path), card=str(card), quote="1"))
        doc = json.loads(self.path.read_text(encoding="utf-8"))
        self.assertEqual("confirmed", doc["status"])
        self.assertEqual(1, len(self._approval_rows()))


class R3ReselectListConfirmTest(unittest.TestCase):
    """R3：真实 CLI prepare→present→confirm，'确认，名单要重新选' 不得批准旧名单。"""

    def setUp(self):
        self.case = bundle_cli_tests.BundleTest(
            methodName="test_one_quote_two_bound_actions_success_report_and_no_activation")
        self.case.setUp()
        self.addCleanup(self.case.doCleanups)

    def test_reselect_list_quote_keeps_prepared_zero_new_approval(self):
        path, doc = self.case.prepare()
        rows_before = list(self.case.approval_rows())
        c = self.case.confirm(path, doc, quote="确认，名单要重新选")
        self.assertNotEqual(0, c.returncode, c.stdout + c.stderr)
        after = json.loads(Path(path).read_text(encoding="utf-8"))
        self.assertEqual("prepared", after.get("status"), "重选名单请求不得把计划置 confirmed")
        self.assertEqual(rows_before, list(self.case.approval_rows()), "不得新增任何审批")
        self.assertEqual([], [x for x in self.case.approval_rows()
                              if str(x.get("state", "")).startswith(("S9", "S10"))])
        self.assertEqual([], self.case.stub.log, "确认阶段不得产生平台调用/写")

    def test_plain_one_still_confirms(self):
        path, doc = self.case.prepare()
        c = self.case.confirm(path, doc, quote="1")
        self.assertEqual(0, c.returncode, c.stdout + c.stderr)
        after = json.loads(Path(path).read_text(encoding="utf-8"))
        self.assertEqual("confirmed", after.get("status"))


class BundleCardContractTest(BundleFixture):
    def test_card_separates_units_and_marks_list_unverified(self):
        card = self._present()
        text = json.loads(card.read_text(encoding="utf-8"))["plan_hash"]
        self.assertTrue(text)
        # 直接看用户可见卡片文本，不是卡文件 JSON
        buf = io.StringIO()
        old = sys.stdout
        sys.stdout = buf
        try:
            bundle.present(Namespace(bundle=str(self.path), ttl_seconds=60))
        finally:
            sys.stdout = old
        shown = buf.getvalue()
        self.assertIn("计划保存", shown, "卡面只能写计划公司数，不能冒称实际已保存")
        self.assertIn("5 家", shown, "计划公司数（selectTotal）必须来自保存计划")
        self.assertNotIn("已保存", shown, "没有 S6 完成回执时不得说已保存")
        self.assertIn("本次要加", shown)
        self.assertIn("5 人", shown)
        # 固定展示标签与模板同源：只锁这两处固定文案，不扫描用户自定义名称。
        self.assertIn("新建一条跟进计划", shown)
        self.assertNotIn("新建一条发信序列", shown)
        self.assertNotIn("建好后序列", shown)
        self.assertIn("建好后这条跟进计划", shown)
        self.assertIn("名单", shown)
        self.assertIn("加入前", shown)
        self.assertIn("核对", shown)
        self.assertIn("未知", shown)
        self.assertIn("不加", shown)
        self.assertNotIn("已保存 5 = 名单 5", shown, "不得伪造三数相等")
        self.assertNotIn("三数核对一致", shown, "不得宣称已核对通过")
        shown_lines = [line.strip() for line in shown.splitlines() if line.strip()]
        line1 = next(line for line in shown_lines if line.startswith("回「1」"))
        line2 = next(line for line in shown_lines if line.startswith("回「2」"))
        self.assertNotEqual(line1, line2, "回 1 与回 2 必须各自独立成行")
        self.assertNotIn("回「2」", line1)
        self.assertIn("直接说", shown)
        for banned in ("S9", "S10", "selectTotal", "sha256", "hash"):
            self.assertNotIn(banned, shown, banned)

    def test_precheck_unknown_or_mismatch_blocks_before_contact_write(self):
        self.assertTrue(hasattr(bundle, "ensure_contacts_ready"),
                        "功能缺失：加人前名单人数核对函数不存在（A5）")
        calls = []

        def fake_api(path, payload, timeout=50):
            calls.append((path, payload))
            if path != "contacts/contacts/show":
                return {}
            return {"data": {"total": fake_api.total}}

        fake_api.total = None
        buf = io.StringIO()
        old = sys.stdout
        sys.stdout = buf
        try:
            with self.assertRaises(SystemExit) as cm:
                bundle.ensure_contacts_ready({"s10": {"tags": ["tag-1"], "expected_contacts": 5}},
                                             fake_api)
        finally:
            sys.stdout = old
        self.assertNotEqual(0, cm.exception.code)
        self.assertIn("未知", buf.getvalue())

        fake_api.total = 4
        with self.assertRaises(SystemExit) as cm2:
            bundle.ensure_contacts_ready({"s10": {"tags": ["tag-1"], "expected_contacts": 5}},
                                         fake_api)
        self.assertNotEqual(0, cm2.exception.code)

        fake_api.total = 5
        self.assertEqual(5, bundle.ensure_contacts_ready(
            {"s10": {"tags": ["tag-1"], "expected_contacts": 5}}, fake_api))
        src = (ROOT / "tools/sequence_contact_bundle.py").read_text(encoding="utf-8")
        self.assertLess(src.index("ensure_contacts_ready(d, api)"),
                        src.index('"S10_加联系人"'),
                        "名单核对必须在铸 S10 审批之前")


class BundlePreAddReadbackZeroWriteTest(BundleFixture):
    """A5 负例：加人前回读未知/不一致 → 在铸 S10 审批与 contact-add 之前非零退出。"""

    def _doc(self):
        d = json.loads(self.path.read_text(encoding="utf-8"))
        d["org_sha256"] = hashlib.sha256(b"org").hexdigest()
        d["steps"] = {"create": "done", "seq_id": "a" * 24}
        d["receipt"] = {"seq_id": "a" * 24}
        d["s10"]["expected_contacts"] = 5
        return d

    def _execute_with_total(self, total):
        current = json.loads(self.path.read_text(encoding="utf-8"))
        if current.get("status") == "prepared":
            card = self._present()
            bundle.confirm(Namespace(bundle=str(self.path), card=str(card), quote="1"))
        d = self._doc()
        rows_before = list(self._approval_rows())
        seen = []
        import platform_http

        def fake_post(path, payload, token, org, timeout=50):
            seen.append(path)
            if path == "contacts/contacts/show":
                return json.dumps({"data": {"total": total}})
            return json.dumps({})

        with mock.patch.object(bundle, "check_deps", lambda doc: None), \
             mock.patch.object(bundle, "acquire_scope_lock", lambda p: True), \
             mock.patch.object(bundle, "release_scope_lock", lambda p: None), \
             mock.patch("credential_input.parse_credentials", return_value=("T", "org")), \
             mock.patch.object(sys, "stdin", SimpleNamespace(buffer=io.BytesIO(b""))), \
             mock.patch.object(platform_http, "post", side_effect=fake_post):
            with self.assertRaises(SystemExit) as cm:
                bundle._execute_locked(Namespace(bundle=str(self.path)), d)
        return cm.exception.code, seen, d, rows_before

    def test_unknown_or_mismatch_rejected_before_s10_approval_and_contact_add(self):
        for total in (None, 4):
            with self.subTest(total=total):
                code, seen, d, rows_before = self._execute_with_total(total)
                self.assertNotEqual(0, code)
                self.assertEqual(rows_before, self._approval_rows(), "执行期间不得新增审批")
                self.assertNotIn("sequences/contact-add", seen, "不得发起加人写请求")
                self.assertNotIn("sequences/sequence-create", seen)
                self.assertEqual({"contacts/contacts/show"}, set(seen),
                                 "只允许名单只读回读，不得有任何平台桩写")
                # 本用例夹具预置 create=done（序列已存在），使用点失配必须标 partial，
                # 不能再说 prepared/零写；首次真实路径的 0 写由 R2 首次执行用例覆盖。
                self.assertEqual("partial", d["status"])


class SavePlanMixedIntentTest(unittest.TestCase):
    """A4：保存卡确认夹带邮箱/参数修改，必须在写盘/铸票前拒绝。"""

    def setUp(self):
        self.case = save_confirm_plain.CountCardChainTest(
            methodName="test_numeric_n_equals_card_passes_and_binds_card")
        self.case.setUp()
        self.addCleanup(self.case.doCleanups)

    def test_mixed_email_change_keeps_draft_no_ticket(self):
        draft = self.case._prepare()
        card = self.case._present(draft)
        before = Path(draft).read_bytes()
        for quote in ("确认保存前20家，邮箱改成6个",
                      "确认保存 前 20 家，邮箱改成6个",
                      "确认保存前20家，邮箱改6个",
                      "确认，但人数改成25",
                      "确认，人数改25"):
            with self.subTest(quote=quote):
                with self.assertRaises(save_plan.PlanError) as cm:
                    self.case._confirm(draft, quote, card["card_ref"])
                self.assertEqual("E_CONFIRM_MODIFICATION", cm.exception.code)
                self.assertEqual(before, Path(draft).read_bytes(), "拒绝时 draft 不得改写")
                self.assertEqual("draft", json.loads(Path(draft).read_text("utf-8"))["status"])
        final = Path(save_plan.plan_path(self.case.root, "plan-cc1", 1))
        self.assertEqual("draft", json.loads(final.read_text("utf-8"))["status"],
                         "确认被拒不得落 confirmed 计划")

    def test_one_and_plain_confirm_not_treated_as_modification(self):
        for quote in ("1", "20", "确认", "确认保存 前 20 家"):
            with self.subTest(quote=quote):
                self.assertFalse(approval.reservation(quote)[0], quote)

    def test_plain_confirm_and_card_number_still_pass(self):
        draft = self.case._prepare()
        card = self.case._present(draft)
        for quote in ("确认", "20", "确认保存 前 20 家"):
            with self.subTest(quote=quote):
                confirmed = self.case._confirm(draft, quote, card["card_ref"])
                self.assertEqual("confirmed_pending", confirmed["status"])
                # 复位，供下一条纯确认继续验证
                p = Path(draft)
                doc = json.loads(p.read_text("utf-8"))
                doc["status"] = "draft"
                p.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")


class ProfileContrastChangeTest(unittest.TestCase):
    """GLM 疑点：无标点/空格转折 + “要换掉”必须在真实资料确认入口拒绝。"""

    def test_contrast_company_name_change_rejected(self):
        case = ProductProfileMixedIntentTest(methodName="test_plain_confirm_still_accepted")
        with tempfile.TemporaryDirectory() as tmp:
            profile, env = case._init_profile(tmp)
            before = profile.read_bytes()
            for quote in ("确认 不过公司名要换掉", "确认不过公司名要换掉"):
                with self.subTest(quote=quote):
                    r = case._confirm(profile, quote, env)
                    self.assertNotEqual(0, r.returncode, r.stdout + r.stderr)
                    self.assertEqual(before, profile.read_bytes(), "拒绝时不得改写档案")
                    self.assertIn("status: draft", profile.read_text(encoding="utf-8"))


class R2BundleFirstExecuteTest(unittest.TestCase):
    """A-R2-1/2：真实首次 prepare→present→confirm→execute，steps={}。"""

    def setUp(self):
        self.case = bundle_cli_tests.BundleTest(
            methodName="test_one_quote_two_bound_actions_success_report_and_no_activation")
        self.case.setUp()
        self.addCleanup(self.case.doCleanups)

    def _prepared(self):
        path, doc = self.case.prepare()
        self.assertEqual({}, doc.get("steps"), "首次执行必须是 steps={}，不得预种 create=done")
        c = self.case.confirm(path, doc)
        self.assertEqual(0, c.returncode, c.stdout + c.stderr)
        return path

    def _execute(self, path):
        return self.case.cli("execute", "--bundle", path, creds=bundle_cli_tests.CREDS)

    def _rows(self):
        return self.case.approval_rows()

    def test_first_execute_mismatch_rejects_before_any_write(self):
        path = self._prepared()
        rows_before = list(self._rows())
        self.assertEqual(1, len([x for x in rows_before
                                 if str(x.get("state", "")).startswith("S9")]),
                         "确认阶段应已有 1 条 S9 审批")
        orig = self.case.stub.route
        self.case.stub.route = lambda p, pl: ({"success": True, "data": {"total": 4}}
                                               if p == "contacts/contacts/show" else orig(p, pl))
        e = self._execute(path)
        out = e.stdout + e.stderr
        self.assertNotEqual(0, e.returncode, out)
        self.assertEqual([], [x for x in self.case.stub.log
                              if not str(x[0]).startswith("contacts/contacts/show")],
                         "名单未知/失配时不得有任何平台写或建序列调用")
        self.assertEqual(0, len(self.case.stub.calls("sequences/sequence-create")))
        self.assertEqual(0, len(self.case.stub.calls("sequences/contact-add")))
        self.assertEqual(rows_before, list(self._rows()), "执行阶段不得新增审批/票")
        self.assertEqual([], [x for x in self._rows() if str(x.get("state", "")).startswith("S10")])
        final = json.loads(Path(path).read_text(encoding="utf-8"))
        self.assertEqual({}, final.get("steps"), "未写前拒不得留下 create_attempted/seq_id")
        self.assertEqual("confirmed", final.get("status"), "未发生的写不得报 partial/executed")

    def test_late_change_keeps_seq_marks_partial_then_resumes_without_recreate(self):
        path = self._prepared()
        orig = self.case.stub.route
        phase = {"late": False}

        def route(p, pl):
            if p == "contacts/contacts/show":
                return {"success": True, "data": {"total": 4 if phase["late"] else 5}}
            if p == "sequences/sequence-create":
                phase["late"] = True
            return orig(p, pl)

        self.case.stub.route = route
        e = self._execute(path)
        out = e.stdout + e.stderr
        self.assertNotEqual(0, e.returncode, out)
        self.assertIn("部分完成", out)
        self.assertIn("序列已建", out)
        self.assertEqual(1, len(self.case.stub.calls("sequences/sequence-create")), "首次只建一次")
        self.assertEqual(0, len(self.case.stub.calls("sequences/contact-add")))
        self.assertEqual([], [x for x in self._rows() if str(x.get("state", "")).startswith("S10")])
        self.assertEqual([], self.case.stub.calls("sequences/sequence-active"), "不得激活")
        first = json.loads(Path(path).read_text(encoding="utf-8"))
        self.assertEqual("partial", first.get("status"))
        self.assertEqual("done", first.get("steps", {}).get("create"))
        seq = first.get("steps", {}).get("seq_id")
        self.assertTrue(seq)

        phase["late"] = False
        e2 = self._execute(path)
        out2 = e2.stdout + e2.stderr
        self.assertNotEqual(0, e2.returncode, out2)  # 未给 manifest → S11 pending exit 4
        self.assertEqual(1, len(self.case.stub.calls("sequences/sequence-create")),
                         "恢复原包不得重复 create")
        self.assertEqual(1, len(self.case.stub.calls("sequences/contact-add")))
        self.assertEqual([], self.case.stub.calls("sequences/sequence-active"))
        second = json.loads(Path(path).read_text(encoding="utf-8"))
        self.assertEqual(seq, second.get("steps", {}).get("seq_id"))
        self.assertEqual("done", second.get("steps", {}).get("contact"))
        self.assertEqual("executed", second.get("status"))
        self.assertEqual(1, len([x for x in self._rows()
                                 if str(x.get("state", "")).startswith("S10")]))


if __name__ == "__main__":
    unittest.main()
