#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""S9+S10 联合确认：真实联合 CLI + 本地 loopback 平台 HTTP 替身（不 mock 审批/票据/门禁）。"""
import hashlib, json, os, shutil, subprocess, sys, tempfile, threading, unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools")); sys.path.insert(0, str(ROOT / "tests"))
import auth_guard  # noqa: E402
import save_plan  # noqa: E402
from gate_env import gate_test_env  # noqa: E402
import test_sequence_closure_hardening as H  # noqa: E402

SEQ = "000000000000000000000047"; TAG = "tag-1"; TASK = "task-1"
TOKEN = H.TOKEN; ORG = H.ORG
CREDS = f"accesstoken={TOKEN}\norgId={ORG}\n"


class Stub:
    def __init__(self, tmap_ids, repo_glob="/NOPE/"):
        self.log, self.fail_contact, self.created, self.active = [], False, False, False
        self.save_count, self.status_mode, self.contact_count, self.leaks, self.summary_mode = 5, "normal", 0, [], "ok"
        self.tmap_ids = tmap_ids; self.repo_glob = repo_glob; me = self  # repo_glob 必须落到实例上，否则机器上存在带 TOKEN 的进程时 do_POST 抛 AttributeError 断连
        class Hd(BaseHTTPRequestHandler):
            def log_message(self, *a): pass
            def do_POST(self):
                n = int(self.headers.get("Content-Length") or 0); pl = json.loads(self.rfile.read(n) or b"{}")
                path = self.path.split("/api/", 1)[1]; me.log.append((path, pl, dict(self.headers)))
                try:
                    ps = subprocess.run(["ps", "-axww", "-o", "command="], capture_output=True, text=True).stdout
                    hits = [l for l in ps.splitlines() if TOKEN in l and me.repo_glob in l and "unittest" not in l]
                    if hits: me.leaks.append((path, [h[:300] for h in hits[:2]]))
                except OSError: pass
                out = me.route(path, pl); b = json.dumps(out, ensure_ascii=False).encode()
                self.send_response(200); self.send_header("Content-Type", "application/json"); self.end_headers(); self.wfile.write(b)
        self.srv = HTTPServer(("127.0.0.1", 0), Hd); self.url = f"http://127.0.0.1:{self.srv.server_port}"
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()

    def calls(self, p): return [c for c in self.log if c[0] == p]

    def route(self, p, pl):
        ok = lambda d: {"success": True, "data": d}
        if p == "benefits/refine-data": return ok({"isOrg": True, "vip": 1, "monthlyLimit": 100, "dailyLimit": 10})
        if p == "settings/sequence/schedule-list": return ok({"list": [{"id": "000000000000000000000045", "name": "US work hours", "time_zone": "America/New_York", "isDefault": True}]})
        if p == "contacts/tags-list": return ok({"list": [{"id": TAG, "name": "英语-客户"}, {"id": "000000000000000000000043", "name": "询盘"}, {"id": "000000000000000000000044", "name": "不发"}]})
        if p == "sequences/sequence-list":
            return ok({"list": [{"id": SEQ, "name": H.SEQ_NAME, "status": ("active" if self.active else "inactive") if self.status_mode == "normal" else self.status_mode if self.status_mode == "active" else None}] if self.created else []})
        if p == "sequences/sequence-create": self.created = True; return ok({"id": SEQ})
        if p == "sequences/sequence-save": return ok({})
        if p == "sequences/sequence-summary":
            if self.summary_mode == "missing": return ok({})
            if self.summary_mode == "string": return ok({"contactsCount": "5"})
            if self.summary_mode == "foreign": return ok({"id": "f" * 24, "contactsCount": self.contact_count})
            if self.summary_mode == "fail": return {"success": False, "message": "x"}
            return ok({"id": pl.get("id"), "contactsCount": self.contact_count})
        if p == "sequences/sequence-details": return ok({"contactCount": 99, "rules": {"otherReplayValue": "nothing", "max_emails_per_day": 30000, "domain_emails_per_day": 5, "notSentTags": ["000000000000000000000043", "000000000000000000000044"]}})
        if p == "sequences/step-create": return ok({"id": "x"})
        if p == "sequences/step-list": return ok([dict(s) for s in [r[1] for r in self.log if r[0] == "sequences/step-create"]])
        if p == "mailbox/templates-list": return ok({"list": [{"_id": i} for i in self.tmap_ids]})
        if p == "operation/backend-task-status": return ok({"status": "finished", "contactSaveCount": self.save_count})
        if p == "contacts/contacts/show": return ok({"total": 5})
        if p == "sequences/contact-add": return {"success": False, "message": "boom"} if self.fail_contact else (setattr(self, "contact_count", 5) or ok({"add": 5}))
        if p == "sequences/sequence-active": self.active = True; return ok({})
        return {"success": False, "message": "unexpected " + p}


class BundleTest(H._RepoCase):
    def setUp(self):
        super().setUp()
        mapping = self.write_tmap(); self.stub = Stub(list(mapping.values()), repo_glob=str(self.repo))
        self.env["LFX_BUNDLE_TEST_BASE_URL"] = self.stub.url
        self.env.pop("LFX_FAKE_CURL_LOG", None)
        for d in self.bin.iterdir(): d.unlink()  # 联合链不得依赖 curl 子进程
        wire = {"contactTags": [TAG], "companyTags": ["tc"], "selectTotal": 5}
        plan = {"kind": "save_plan", "project": H.PROJECT, "plan_id": "p", "revision": 1, "status": "confirmed", "selectTotal": 5,
                "wire_payload_sha256": save_plan.rule_check.canonical_hash(wire), "dependency_sha256": "0" * 64,
                "count_hash": "a" * 64, "wire_payload": wire}
        plan["binding_sha256"] = save_plan.binding_hash(plan)
        self.plan = self.project_dir / "s5-plan.json"; self.plan.write_text(json.dumps(plan), encoding="utf-8")

    def tearDown(self): self.stub.srv.shutdown(); super().tearDown()

    def cli(self, *a, creds=None):
        return subprocess.run([sys.executable, str(self.repo / "tools/sequence_contact_bundle.py"), *map(str, a)], input=creds, cwd=self.repo,
                              env=self.env, text=True, capture_output=True, timeout=180, encoding="utf-8", errors="replace")

    def prepare(self, **kw):
        a = dict(name=H.SEQ_NAME, expected=5, task=TASK); a.update(kw)
        r = self.cli("prepare", "--project", H.PROJECT, "--org", ORG, "--record", self.record, "--tmap", self.tmap, "--profile", self.profile,
                     "--name", a["name"], "--from-name", "Tony", "--s5-plan", self.plan, "--task", a["task"], "--expected-contacts", a["expected"])
        self.assertEqual(0, r.returncode, r.stdout + r.stderr)
        path = [l for l in r.stdout.splitlines() if ".json" in l][0].split(": ", 1)[1].strip()
        return path, json.loads(Path(path).read_text(encoding="utf-8"))

    def present(self, path, *extra):
        return self.cli("present", "--bundle", path, *extra)

    def card_of(self, r):
        for l in r.stdout.splitlines():
            if l.startswith("卡文件: "): return l.split(": ", 1)[1].strip()
        return None

    def confirm(self, path, doc=None, quote="1", ttl=None):
        pr = self.present(path, *(["--ttl-seconds", str(ttl)] if ttl else []))
        if pr.returncode != 0: return pr
        self.last_card = self.card_of(pr)
        return self.cli("confirm", "--bundle", path, "--card", self.last_card, "--quote", quote)

    def test_child_reaches_loopback_stub_even_with_unrelated_token_process_present(self):
        # 回归：机器上存在 argv 含 TOKEN 的无关进程时，桩的 ps 扫描不得崩溃（曾因 Stub 缺 repo_glob 断连→build_sequence 吞成"接口无返回"→exit 1）
        decoy = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(120)", TOKEN])
        try:
            path, doc = self.prepare(); c = self.confirm(path, doc); self.assertEqual(0, c.returncode, c.stdout + c.stderr)
            e = self.cli("execute", "--bundle", path, creds=CREDS); out = e.stdout + e.stderr
            self.assertEqual(4, e.returncode, out)
            self.assertNotIn("接口无返回", out)
            self.assertGreaterEqual(len(self.stub.calls("settings/sequence/schedule-list")), 1, "子进程必须真的打到 loopback 桩")
            self.assertEqual(1, len(self.stub.calls("sequences/sequence-create")))
            self.assertEqual([], self.stub.leaks, "无关 decoy 进程不应被判为本用例泄漏")
        finally:
            decoy.kill(); decoy.wait()

    def test_one_quote_two_bound_actions_success_report_and_no_activation(self):
        path, doc = self.prepare(); c = self.confirm(path, doc); self.assertEqual(0, c.returncode, c.stdout + c.stderr)
        rows = self.approval_rows(); self.assertEqual(1, len([r for r in rows if r["state"].startswith("S9")]))
        self.assertEqual([], [r for r in rows if r["state"].startswith("S10")], "S10 审批在 seq 回读后才铸")
        e = self.cli("execute", "--bundle", path, creds=CREDS); out = e.stdout + e.stderr
        self.assertEqual(4, e.returncode, out)
        rows = self.approval_rows()
        s10 = [r for r in rows if r["state"].startswith("S10")]; self.assertEqual(1, len(s10)); self.assertEqual("1", s10[0]["decision"] if False else s10[0].get("user_quote") or s10[0].get("quote_text") or list(s10[0].values())[4])
        self.assertEqual(1, len(self.stub.calls("sequences/contact-add")))
        self.assertEqual({"seqId": SEQ, "tags": [TAG], "views": []}, self.stub.calls("sequences/contact-add")[0][1])
        self.assertEqual([], self.stub.calls("sequences/sequence-active"), "激活必须 0")
        self.assertIn("仍未激活", out); self.assertIn("https://web.laifaxin.com/marketing/sequences", out); self.assertIn(H.SEQ_NAME, out)
        self.assertNotIn(TOKEN, out); self.assertEqual("S10", self.record_status())
        self.assertTrue(all({k.lower(): v for k, v in c[2].items()}.get("accesstoken") == TOKEN for c in self.stub.log), "凭据走进程内 HTTP header")

    def test_changed_config_or_stale_hash_rejected_zero_write(self):
        path, doc = self.prepare(); d = json.loads(Path(path).read_text(encoding="utf-8")); d["s9"]["name"] = "改过-英语-12轮4封-x"
        Path(path).write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
        c = self.confirm(path, doc); self.assertNotEqual(0, c.returncode); self.assertEqual([], self.approval_rows())
        e = self.cli("execute", "--bundle", path, creds=CREDS); self.assertNotEqual(0, e.returncode); self.assertEqual([], self.stub.log)

    def test_non_affirmative_quote_mints_nothing(self):
        path, doc = self.prepare(); c = self.confirm(path, doc, quote="先不要"); self.assertNotEqual(0, c.returncode); self.assertEqual([], self.approval_rows())

    def test_create_ok_contact_fail_then_rerun_does_not_recreate(self):
        path, doc = self.prepare(); self.assertEqual(0, self.confirm(path, doc).returncode)
        self.stub.fail_contact = True
        e = self.cli("execute", "--bundle", path, creds=CREDS); self.assertNotEqual(0, e.returncode); self.assertIn("部分完成", e.stdout + e.stderr)
        d = json.loads(Path(path).read_text(encoding="utf-8")); self.assertEqual(SEQ, d["steps"]["seq_id"]); self.assertEqual("partial", d["status"])
        self.assertEqual(1, len(self.stub.calls("sequences/sequence-create")))
        self.stub.fail_contact = False
        e2 = self.cli("execute", "--bundle", path, creds=CREDS)
        self.assertEqual(3, e2.returncode, "已发出但失败(sending)→回读0也不得重放")
        self.assertEqual(1, len(self.stub.calls("sequences/sequence-create")), "重跑不得再 create")
        self.assertEqual(1, len(self.stub.calls("sequences/contact-add")), "不得重放")
        self.assertEqual([], self.stub.calls("sequences/sequence-active"))
        d = json.loads(Path(path).read_text(encoding="utf-8")); self.assertEqual("partial", d["status"])


    # ---------- 运行态收口负例 ----------
    def _go(self, quote="1"):
        path, doc = self.prepare(); c = self.confirm(path, doc, quote); return path, doc, c

    def assert_zero_write(self, extra_ok=()):
        w = [c[0] for c in self.stub.log if c[0].startswith(("sequences/sequence-create", "sequences/contact-add", "sequences/step-create", "sequences/sequence-save"))]
        self.assertEqual([], w)

    def test_confirm_without_card_rejected(self):
        path, doc = self.prepare()
        r = self.cli("confirm", "--bundle", path, "--quote", "1")
        self.assertNotEqual(0, r.returncode, r.stdout + r.stderr); self.assertEqual([], self.approval_rows())

    def test_expired_card_rejected(self):
        import time
        path, doc = self.prepare(); pr = self.present(path, "--ttl-seconds", "1"); self.assertEqual(0, pr.returncode, pr.stdout + pr.stderr)
        time.sleep(2.2); r = self.cli("confirm", "--bundle", path, "--card", self.card_of(pr), "--quote", "1")
        self.assertNotEqual(0, r.returncode); self.assertIn("过期", r.stdout + r.stderr); self.assertEqual([], self.approval_rows())

    def test_card_is_plain_language_and_activation_quote_rejected(self):
        path, doc = self.prepare(); pr = self.present(path); card = pr.stdout.split("卡文件:")[0]
        for bad in ("S9", "S10", "hash", "标签id", "seqId", "sha256"): self.assertNotIn(bad, card)
        for q in ("确认激活", "激活", "不要", "可以吗？"):
            r = self.cli("confirm", "--bundle", path, "--card", self.card_of(pr), "--quote", q)
            self.assertNotEqual(0, r.returncode, q); self.assertEqual([], self.approval_rows(), q)

    def test_s5_plan_changed_after_confirm_blocks_execute_zero_write(self):
        path, doc, c = self._go(); self.assertEqual(0, c.returncode, c.stdout + c.stderr)
        p = json.loads(self.plan.read_text(encoding="utf-8")); p["wire_payload"]["selectTotal"] = 9; self.plan.write_text(json.dumps(p), encoding="utf-8")
        e = self.cli("execute", "--bundle", path, creds=CREDS); self.assertNotEqual(0, e.returncode); self.assert_zero_write()
        self.assertEqual([], self.stub.log, "依赖重验必须在任何平台调用之前")

    def test_tmap_changed_after_confirm_blocks_execute(self):
        path, doc, c = self._go(); self.assertEqual(0, c.returncode)
        self.tmap.write_text(self.tmap.read_text(encoding="utf-8") + " ", encoding="utf-8")
        e = self.cli("execute", "--bundle", path, creds=CREDS); self.assertNotEqual(0, e.returncode); self.assertEqual([], self.stub.log)

    def test_forged_seq_in_bundle_refused_no_contact_write(self):
        path, doc, c = self._go(); self.stub.save_count = 4  # 加人对账失败 → 0写部分完成
        e = self.cli("execute", "--bundle", path, creds=CREDS); self.assertNotEqual(0, e.returncode)
        d = json.loads(Path(path).read_text(encoding="utf-8")); d["steps"]["seq_id"] = "0" * 23 + "9"; Path(path).write_text(json.dumps(d), encoding="utf-8")
        self.stub.save_count = 5
        e2 = self.cli("execute", "--bundle", path, creds=CREDS); self.assertNotEqual(0, e2.returncode, e2.stdout)
        self.assertEqual([], self.stub.calls("sequences/contact-add")); self.assertEqual(1, len(self.stub.calls("sequences/sequence-create")))

    def test_save_count_mismatch_zero_write_then_resume_creates_once(self):
        path, doc, c = self._go(); self.stub.save_count = 4
        e = self.cli("execute", "--bundle", path, creds=CREDS); self.assertNotEqual(0, e.returncode); self.assertIn("部分完成", e.stdout + e.stderr)
        self.assertEqual([], self.stub.calls("sequences/contact-add"))
        self.stub.save_count = 5
        e2 = self.cli("execute", "--bundle", path, creds=CREDS); self.assertEqual(4, e2.returncode, e2.stdout + e2.stderr)
        self.assertEqual(1, len(self.stub.calls("sequences/sequence-create"))); self.assertEqual(1, len(self.stub.calls("sequences/contact-add")))
        self.assertIn("终检未完成", e2.stdout + e2.stderr, "S11 未收口不得报全完成")

    def test_active_or_unknown_status_blocks_contact_add(self):
        for mode in ("active", "unknown"):
            self.stub.status_mode = mode; self.stub.log.clear(); self.stub.created = False
            for f in (self.repo / ".local").glob("bundle/*"): f.unlink()
            path, doc, c = self._go()
            e = self.cli("execute", "--bundle", path, creds=CREDS); self.assertNotEqual(0, e.returncode, mode)
            self.assertEqual([], self.stub.calls("sequences/contact-add"), mode); self.assertEqual([], self.stub.calls("sequences/sequence-active"))

    def test_uncertain_add_readback_done_when_count_matches_and_receipt_machine_read(self):
        path, doc, c = self._go(); self.stub.fail_contact = True
        e = self.cli("execute", "--bundle", path, creds=CREDS); self.assertNotEqual(0, e.returncode)
        self.stub.fail_contact = False; self.stub.contact_count = 5  # 平台回读已有 5 人
        e2 = self.cli("execute", "--bundle", path, creds=CREDS); self.assertEqual(4, e2.returncode, e2.stdout + e2.stderr)
        self.assertEqual(1, len(self.stub.calls("sequences/contact-add")), "已加且吻合 → 记完成,不重放")

    def test_credentials_not_in_child_argv_env_or_output_and_no_activation(self):
        path, doc, c = self._go(); e = self.cli("execute", "--bundle", path, creds=CREDS)
        self.assertEqual(4, e.returncode, e.stdout + e.stderr); self.assertEqual([], self.stub.leaks, "子进程 argv/env 不得含 token")
        self.assertNotIn(TOKEN, e.stdout + e.stderr); self.assertEqual([], self.stub.calls("sequences/sequence-active"))
        self.assertNotIn(TOKEN, Path(path).read_text(encoding="utf-8"))

    def test_redirect_is_not_followed(self):
        sink = Stub([]); redir = []
        class R(BaseHTTPRequestHandler):
            def log_message(self, *a): pass
            def do_POST(self):
                self.send_response(302); self.send_header("Location", sink.url + "/api/x"); self.end_headers()
        srv = HTTPServer(("127.0.0.1", 0), R); threading.Thread(target=srv.serve_forever, daemon=True).start()
        # R2c 起 post() 对"无 env 的裸 override"也会清掉，故本用例必须带齐 LFX_BUNDLE_TEST_BASE_URL+gate 票据
        env = dict(self.env); env["LFX_BUNDLE_TEST_BASE_URL"] = "http://127.0.0.1:%d" % srv.server_port
        code = ("import sys;sys.path.insert(0,'tools');import api_base_url,platform_http;"
                "api_base_url.install_test_override('http://127.0.0.1:%d');print(repr(platform_http.post('a/b',{},'T','O')))" % srv.server_port)
        r = subprocess.run([sys.executable, "-c", code], cwd=ROOT, env=env, text=True, capture_output=True, timeout=30)
        srv.shutdown(); sink.srv.shutdown()
        self.assertEqual("''", r.stdout.strip(), r.stdout + r.stderr); self.assertEqual([], sink.log, "3xx 外带 sink 必须 0")


    # ---------- 最终收口负例 ----------
    def test_prepare_runs_without_fcntl_and_stale_lock_refused(self):
        poison = self.tmp / "nofcntl"; poison.mkdir(); (poison / "fcntl.py").write_text('raise ImportError("no fcntl on windows")\n', encoding="utf-8")
        env = dict(self.env); env["PYTHONPATH"] = str(poison) + os.pathsep + env.get("PYTHONPATH", "")
        r = subprocess.run([sys.executable, str(self.repo / "tools/sequence_contact_bundle.py"), "prepare", "--project", H.PROJECT, "--org", ORG,
                            "--record", self.record, "--tmap", self.tmap, "--profile", self.profile, "--name", H.SEQ_NAME, "--from-name", "Tony",
                            "--s5-plan", self.plan, "--task", TASK, "--expected-contacts", "5"], cwd=self.repo, env=env, text=True,
                           capture_output=True, timeout=60, encoding="utf-8", errors="replace")
        self.assertEqual(0, r.returncode, r.stdout + r.stderr)
        path, doc = self.prepare(); self.assertEqual(0, self.confirm(path, doc).returncode)
        Path(str(path) + ".lock").write_text('{"pid": 1}', encoding="utf-8")  # 模拟崩溃残留锁
        e = self.cli("execute", "--bundle", path, creds=CREDS)
        self.assertEqual(3, e.returncode, e.stdout + e.stderr); self.assertEqual([], self.stub.log, "残留锁必须 fail-closed 且不得删锁重进")

    def test_release_denies_fabricated_or_stale_evidence(self):
        path, doc = self.prepare(); self.assertEqual(0, self.confirm(path, doc).returncode)
        d = json.loads(Path(path).read_text(encoding="utf-8"))
        pay = {"seqId": "0" * 24, "tags": d["s10"]["tags"], "views": []}
        self.assertFalse(auth_guard.release_bundle_payload_after_zero({**d, "steps": {"seq_id": "0" * 24, "contact_readback": {"seq": "0" * 24, "count": 0}}}, pay).get("ok"), "没有发送回执的裸dict自报0不得释放")
        d2 = json.loads(Path(path).read_text(encoding="utf-8")); d2["steps"] = {"seq_id": "0" * 24, "contact_state": "rejected", "contact_readback": {"seq": "0" * 24, "count": 0}}
        Path(path).write_text(json.dumps(d2), encoding="utf-8")
        r = auth_guard.release_bundle_payload_after_zero(d2, pay)  # 计划hash已破
        self.assertFalse(r.get("ok"), r)

    def test_uncertain_send_not_replayed_even_on_zero_readback(self):
        path, doc = self.prepare(); self.assertEqual(0, self.confirm(path, doc).returncode)
        self.stub.fail_contact = True
        e = self.cli("execute", "--bundle", path, creds=CREDS); self.assertNotEqual(0, e.returncode)
        self.stub.fail_contact = False  # 但上一次是"发出后结果不确定"
        e2 = self.cli("execute", "--bundle", path, creds=CREDS)
        self.assertEqual(1, len(self.stub.calls("sequences/contact-add")), "结果不确定(sending)即使回读0也不得重放")
        d = json.loads(Path(path).read_text(encoding="utf-8")); self.assertEqual("partial", d["status"])

    def test_report_lists_receipt_values(self):
        path, doc = self.prepare(); self.assertEqual(0, self.confirm(path, doc).returncode)
        e = self.cli("execute", "--bundle", path, creds=CREDS); out = e.stdout + e.stderr
        self.assertEqual(4, e.returncode, out)
        for kw in ("预计 5 人", "实际新增", TASK, "终检未完成", "仍未激活"):
            self.assertIn(kw, out, kw)


    # ================= R2 =================
    def test_r2_ac1_override_without_valid_test_ticket_rejected_before_opener(self):
        from unittest.mock import patch
        import platform_http as ph
        for ticket_ok, url in ((False, "http://127.0.0.1:1"), (True, "https://web.laifaxin.com"), (True, "http://example.com:80"), (True, "not a url")):
            with patch.dict(os.environ, {"LFX_BUNDLE_TEST_BASE_URL": url}), \
                 patch.object(auth_guard, "_test_mode_allowed", return_value=ticket_ok), \
                 patch.object(ph.urllib.request, "build_opener") as op:
                with self.assertRaises(Exception, msg=(ticket_ok, url)):
                    ph.post("sequences/sequence-summary", {}, "T", "O")
                self.assertEqual(0, op.call_count, (ticket_ok, url))
                self.assertEqual(0, op.return_value.open.call_count, (ticket_ok, url))

    def test_r2_ac1_stale_override_in_process_cannot_leak_to_next_call(self):
        import api_base_url, platform_http as ph
        from unittest.mock import patch
        api_base_url.install_test_override("http://127.0.0.1:9")
        try:
            with patch.dict(os.environ, {"LFX_BUNDLE_TEST_BASE_URL": "http://127.0.0.1:9"}), \
                 patch.object(auth_guard, "_test_mode_allowed", return_value=False), \
                 patch.object(ph.urllib.request, "build_opener") as op:
                with self.assertRaises(Exception): ph.post("a/b", {}, "T", "O")
                self.assertEqual(0, op.call_count)
        finally:
            api_base_url.clear_test_override()

    def test_r2c_residual_override_cannot_survive_into_non_test_call(self):
        # 边界席两步场景：①测试模式+有效票据时 override 已安装 ②删 env、gate=False 后，
        # post 必须回到生产域名（不得再出现 127.0.0.1），且 override 已被清除。
        import api_base_url, platform_http as ph
        from unittest.mock import patch
        api_base_url.install_test_override("http://127.0.0.1:9")
        try:
            with patch.object(auth_guard, "_test_mode_allowed", return_value=False),                  patch.object(ph.urllib.request, "build_opener") as op:
                saved = os.environ.pop("LFX_BUNDLE_TEST_BASE_URL", None)
                try:
                    ph.post("sequences/sequence-create", {}, "T", "O")
                    sent = op.return_value.open.call_args[0][0].full_url
                    self.assertTrue(sent.startswith("https://web.laifaxin.com/"), sent)
                    self.assertNotIn("127.0.0.1", sent, "残留 override 不得把非测试调用留在 loopback")
                    self.assertEqual(api_base_url.PRODUCTION_BASE_URL, api_base_url.get_base_url(), "override 必须已被清除")
                finally:
                    if saved is not None: os.environ["LFX_BUNDLE_TEST_BASE_URL"] = saved
        finally:
            api_base_url.clear_test_override()

    def test_r2_ac2_total_uses_summary_contactsCount_not_details(self):
        path, doc = self.prepare(); self.assertEqual(0, self.confirm(path, doc).returncode)
        self.stub.contact_count = 5
        e = self.cli("execute", "--bundle", path, creds=CREDS); out = e.stdout + e.stderr
        self.assertEqual(4, e.returncode, out)
        self.assertTrue(self.stub.calls("sequences/sequence-summary"), "必须调用 sequence-summary")
        self.assertIn("当前总人数=5", out); self.assertIn("本次新增", out); self.assertNotIn("99", out)

    def _unknown_summary(self, mode):
        self.stub.summary_mode = mode
        path, doc, c = self._go()
        e = self.cli("execute", "--bundle", path, creds=CREDS); out = e.stdout + e.stderr
        self.assertNotEqual(0, e.returncode, mode)
        self.assertIn("未知", out, mode)
        self.assertNotIn("吻合）", out.replace("不吻合", ""), mode)
        self.assertEqual(1, len(self.stub.calls("sequences/contact-add")), mode)
        self.cli("execute", "--bundle", path, creds=CREDS)
        self.assertEqual(1, len(self.stub.calls("sequences/contact-add")), "未知不得当0释放: " + mode)
        self.assertNotIn("s11_finalized_at", self.record.read_text(encoding="utf-8"))

    def test_r2_ac2_unknown_summary_missing(self): self._unknown_summary("missing")
    def test_r2_ac2_unknown_summary_string_type(self): self._unknown_summary("string")
    def test_r2_ac2_unknown_summary_foreign_identity(self): self._unknown_summary("foreign")
    def test_r2_ac2_unknown_summary_platform_fail(self): self._unknown_summary("fail")

    def test_r2_ac3_pending_s11_exit4_machine_readable_reason_and_one_next_step(self):
        path, doc = self.prepare(); self.assertEqual(0, self.confirm(path, doc).returncode)
        e = self.cli("execute", "--bundle", path, creds=CREDS); out = e.stdout + e.stderr
        self.assertEqual(4, e.returncode, out)
        d = json.loads(Path(path).read_text(encoding="utf-8"))
        self.assertEqual("pending", d["s11"]["state"]); self.assertTrue(d["s11"]["reasons"]); self.assertTrue(d.get("simulation"))
        self.assertIn("建计划/加人已完成，终检未完成", out); self.assertEqual(1, out.count("唯一下一步"))
        self.assertNotIn("s11_finalized_at", self.record.read_text(encoding="utf-8"))

    def _s11_fixture(self, mode="live", missing=None):
        from profile_utils import profile_gate
        sha = profile_gate(self.profile)[3]
        texts = {"sequence": f"序列 {SEQ} 状态=inactive\n步骤数: 12\n全部12步均绑定模板\n",
                 "exclude": "含4区=0\n排除生效\n", "diff": "模板数: 48\n最大相似度 0.41\n差异≥30%达标\n",
                 "panel": "标签 客群 保存 模板 配额 审查 已核对\n"}
        ev = {}
        for k, v in texts.items():
            if k == missing: continue
            p = self.project_dir / f"ev-{k}.txt"; p.write_text(v, encoding="utf-8")
            ev[k] = {"path": str(p), "sha256": hashlib.sha256(p.read_bytes()).hexdigest(), "status": "pass"}
        from datetime import datetime
        man = {"evidence_mode": mode, "project": H.PROJECT, "seq": SEQ, "profile_sha256": sha, "org_sha256": hashlib.sha256(ORG.encode()).hexdigest(),
               "generated_at": datetime.now().isoformat(timespec="seconds"), "evidence": ev}
        mp = self.project_dir / "s11-manifest.json"; mp.write_text(json.dumps(man), encoding="utf-8"); return mp

    def test_r2_ac3_finalize_wired_to_real_finalize_run_with_live_schema_fixture(self):
        path, doc = self.prepare(); self.assertEqual(0, self.confirm(path, doc).returncode)
        self.assertEqual(4, self.cli("execute", "--bundle", path, creds=CREDS).returncode)
        mp = self._s11_fixture()
        f = self.cli("finalize", "--bundle", path, "--manifest", mp, creds=CREDS); out = f.stdout + f.stderr
        self.assertEqual(0, f.returncode, out); self.assertIn("模拟环境", out)
        rec = self.record.read_text(encoding="utf-8"); self.assertIn("status: S11", rec); self.assertIn("s11_finalized_at", rec)
        self.assertEqual("done", json.loads(Path(path).read_text(encoding="utf-8"))["s11"]["state"])

    def test_r2_ac3_execute_with_manifest_auto_calls_finalize_run_and_marks_simulation(self):
        path, doc = self.prepare(); self.assertEqual(0, self.confirm(path, doc).returncode)
        mp = self._s11_fixture()
        e = self.cli("execute", "--bundle", path, "--manifest", mp, creds=CREDS); out = e.stdout + e.stderr
        self.assertEqual(0, e.returncode, out); self.assertIn("模拟环境", out); self.assertEqual([], self.stub.calls("sequences/sequence-active"))
        self.assertIn("status: S11", self.record.read_text(encoding="utf-8"))
        d = json.loads(Path(path).read_text(encoding="utf-8")); self.assertEqual("done", d["s11"]["state"]); self.assertTrue(d["s11"]["simulation"])

    def test_r2_ac3_execute_with_simulation_manifest_stays_pending_exit4(self):
        path, doc = self.prepare(); self.assertEqual(0, self.confirm(path, doc).returncode)
        e = self.cli("execute", "--bundle", path, "--manifest", self._s11_fixture("simulation"), creds=CREDS); out = e.stdout + e.stderr
        self.assertEqual(4, e.returncode, out); self.assertIn("终检未完成", out)
        self.assertNotIn("s11_finalized_at", self.record.read_text(encoding="utf-8"))
        self.assertEqual("pending", json.loads(Path(path).read_text(encoding="utf-8"))["s11"]["state"])

    def test_r2_ac3_finalize_rejects_non_live_or_missing_evidence_without_writing_s11(self):
        path, doc = self.prepare(); self.assertEqual(0, self.confirm(path, doc).returncode)
        self.assertEqual(4, self.cli("execute", "--bundle", path, creds=CREDS).returncode)
        for mode, miss in (("simulation", None), ("live", "diff")):
            mp = self._s11_fixture(mode, miss)
            f = self.cli("finalize", "--bundle", path, "--manifest", mp, creds=CREDS)
            self.assertNotEqual(0, f.returncode, mode)
            self.assertNotIn("s11_finalized_at", self.record.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
