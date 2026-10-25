#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""P0-A S10 票据门回归测试（静态红队：票据门曾经失效）。

旧缺陷：contact_add_authorized.py 调 save_guard.authorize_write(...) 却丢弃返回值；
save_guard 在无票/坏票时只返回 {"ok": False, "code": ...}（**不抛异常**），
随后代码照常调 sequences/contact-add 写平台 —— 票据门形同虚设。

本测试用假 curl 截获平台调用次数（PATH 注入），锁三件事：
  ①非 dry-run 缺 --auth-ticket → exit 2 且零平台调用（连只读查询都不发）
  ②坏票据 → exit 2 且**从未**调用 sequences/contact-add（写调用=0），只读查询照常发生
  ③合法票据 → 正常走到写调用 1 次并推进 record（避免修成死锁）
"""
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import save_plan  # noqa: E402
SEQ = "0123456789abcdef01234567"
ORG = "org-for-ticket-tests"
PROJECT = "tony/demo"
TAGS = ["tag-1"]
TASK = "task-1"
TOKEN = "web.laifaxin.com&1234567&secret-hash"

FAKE_CURL = r'''#!/usr/bin/env python3
import json, os, sys
argv = sys.argv[1:]
url = ""
for a in argv:
    if "/api/" in a:
        url = a
        break
path = url.split("/api/", 1)[1] if "/api/" in url else ""
log = os.environ.get("CURL_LOG", "")
if log:
    with open(log, "a", encoding="utf-8") as f:
        f.write(path + "\n")
responses = {
    "benefits/refine-data": {"success": True, "data": {"isOrg": True, "vip": 1, "monthlyLimit": 100, "dailyLimit": 10}},
    "sequences/sequence-list": {"success": True, "data": {"list": [{"id": "%(seq)s", "name": "英语-demo", "status": "inactive"}]}},
    "contacts/tags-list": {"success": True, "data": {"list": [{"id": "tag-1", "name": "英语-客户"}]}},
    "operation/backend-task-status": {"success": True, "data": {"status": "finished", "contactSaveCount": 5}},
    "contacts/contacts/show": {"success": True, "data": {"total": 5}},
    "sequences/contact-add": {"success": True, "data": {"add": 5}},
}
print(json.dumps(responses.get(path, {"success": False, "message": "unexpected " + path})))
'''



try:
    from gate_env import gate_test_env
except ImportError:
    from tests.gate_env import gate_test_env

class ContactAddTicketGateTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="s10ticket-"))
        self.repo = self.tmp / "repo"
        shutil.copytree(ROOT, self.repo, ignore=shutil.ignore_patterns(
            ".git", ".local", "runs", "__pycache__", "node_modules"))
        self.project_dir = self.repo / "runs" / "tony" / "demo"
        self.project_dir.mkdir(parents=True)
        self.record = self.project_dir / "operation-record.md"
        self.write_record("S9")
        self.plan = self.project_dir / "s5-plan-final.json"
        wire = {"contactTags": TAGS, "companyTags": ["tag-company"],
                "selectTotal": 5}
        plan = {"kind": "save_plan", "project": PROJECT, "plan_id": "plan-test", "revision": 1,
                "status": "confirmed", "selectTotal": 5,
                "wire_payload_sha256": save_plan.rule_check.canonical_hash(wire),
                "dependency_sha256": "0" * 64, "count_hash": "a" * 64,
                "wire_payload": wire}
        plan["binding_sha256"] = save_plan.binding_hash(plan)
        self.plan.write_text(json.dumps(plan, ensure_ascii=False), encoding="utf-8")
        self.bin = self.tmp / "bin"
        self.bin.mkdir()
        self.log = self.tmp / "curl.log"
        fake = self.bin / "curl"
        if os.name == "nt":
            raise unittest.SkipTest("Windows 无扩展名 fake curl（离线平台仿真仅 POSIX）；Windows 用真机 smoke 覆盖")
        fake.write_text(FAKE_CURL % {"seq": SEQ}, encoding="utf-8")
        fake.chmod(0o755)
        self.env = os.environ.copy()
        self.env.update(gate_test_env())
        self.env["PATH"] = str(self.bin) + os.pathsep + self.env.get("PATH", "")
        self.env["CURL_LOG"] = str(self.log)
        self.approval = self.mint_approval()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def write_record(self, status):
        self.record.write_text(
            "---\n"
            "operator_key: tony\n"
            "product_key: demo\n"
            "project: tony/demo\n"
            f"status: {status}\n"
            f"sequence_id: {SEQ}\n"
            "---\n", encoding="utf-8")

    def status(self):
        for line in self.record.read_text(encoding="utf-8").splitlines():
            if line.startswith("status:"):
                return line.split(":", 1)[1].strip().strip('"')
        return ""

    def binding(self):
        return {"project": PROJECT,
                "org_sha256": hashlib.sha256(ORG.encode()).hexdigest(),
                "seq": SEQ, "tags": sorted(TAGS), "task": TASK}

    def mint_approval(self):
        params = self.tmp / "params.json"
        params.write_text(json.dumps(self.binding()), encoding="utf-8")
        r = subprocess.run(
            [sys.executable, str(self.repo / "tools" / "approval.py"), "grant",
             "--project", PROJECT, "--state", "S10_加联系人",
             "--quote", "确认加入联系人", "--params-file", str(params)],
            capture_output=True, text=True, cwd=self.repo,
            env=self.env, timeout=60, encoding="utf-8", errors="replace")
        self.assertEqual(0, r.returncode, r.stdout + r.stderr)
        m = re.search(r"凭证已铸造: (ap-[0-9a-f]+)", r.stdout)
        self.assertIsNotNone(m, r.stdout + r.stderr)
        return m.group(1)

    def mint_ticket(self):
        payload = {"seqId": SEQ, "tags": TAGS, "views": []}
        r = subprocess.run(
            [sys.executable, str(self.repo / "tools" / "auth_guard.py"), "authorize",
             "--action", "sequence", "--quote", "给序列加 5 个联系人",
             "--payload-json", json.dumps(payload)],
            capture_output=True, text=True, cwd=self.repo,
            env=self.env, timeout=60, encoding="utf-8", errors="replace")
        self.assertEqual(0, r.returncode, r.stdout + r.stderr)
        ticket = json.loads(r.stdout)
        return self.repo / ".local" / "auth" / ("ticket-" + ticket["nonce"] + ".json")

    def run_add(self, *extra):
        return subprocess.run(
            [sys.executable, str(self.repo / "tools" / "contact_add_authorized.py"),
             "--token", TOKEN, "--org", ORG, "--seq", SEQ, "--tags", ",".join(TAGS),
             "--task", TASK, "--project", PROJECT, "--record", str(self.record),
             "--plan", str(self.plan),
             "--approval", self.approval, *extra],
            capture_output=True, text=True, cwd=self.repo, env=self.env, timeout=180, encoding="utf-8", errors="replace")

    def calls(self):
        if not self.log.exists():
            return []
        return [line for line in self.log.read_text(encoding="utf-8").splitlines() if line]

    # ---------- ① 无票：任何联网之前拒绝 ----------
    def test_missing_ticket_rejected_before_any_network(self):
        r = self.run_add()
        self.assertEqual(2, r.returncode, r.stdout + r.stderr)
        self.assertIn("--auth-ticket", r.stdout + r.stderr)
        self.assertIn("缺票据", r.stdout + r.stderr)
        self.assertEqual([], self.calls(), "缺票据必须在任何平台调用之前拒绝（只读也不能发）")
        self.assertEqual("S9", self.status())

    # ---------- ② 坏票：绝不写平台 ----------
    def test_bad_ticket_never_calls_contact_add(self):
        bad = self.tmp / "bad-ticket.json"
        bad.write_text("{}", encoding="utf-8")
        bad.chmod(0o600)  # 权限合格、内容不合格 → 走 E_AUTH_BAD_TICKET（缺字段）
        r = self.run_add("--auth-ticket", str(bad))
        self.assertEqual(2, r.returncode, r.stdout + r.stderr)
        self.assertIn("写票据校验未通过", r.stdout)
        self.assertEqual("S9", self.status(), "坏票不得推进本地状态")
        calls = self.calls()
        self.assertTrue(calls, "坏票场景仍应先做只读守卫（便于定位失败原因）")
        self.assertNotIn("sequences/contact-add", calls,
                         "★坏票时写调用必须为 0（旧缺陷：丢弃返回值后照常写平台）")

    # ---------- ③ 好票：正常路径不因新闸门死锁 ----------
    def test_good_ticket_calls_contact_add_exactly_once(self):
        ticket = self.mint_ticket()
        r = self.run_add("--auth-ticket", str(ticket))
        self.assertEqual(0, r.returncode, r.stdout + r.stderr)
        self.assertIn("contact-add 成功", r.stdout)
        self.assertEqual("S10", self.status(), "成功后应推进 record → S10")
        self.assertEqual(1, self.calls().count("sequences/contact-add"),
                         "合法票据应恰好写一次（不多写、不空转）")

    # ---------- 静态：返回值必须被检查 ----------
    def test_source_checks_authorize_write_result(self):
        src = (ROOT / "tools" / "contact_add_authorized.py").read_text(encoding="utf-8")
        self.assertIn("authz = save_guard.authorize_write(", src)
        self.assertIn('not authz.get("ok")', src, "必须检查授权返回值 ok")
        self.assertIn("sys.exit(2)", src)
        # argparse 必填或显式校验：非 dry-run 缺票必须提前拒绝
        self.assertRegex(src, r"not args\.auth_ticket|required=True",
                         "非 dry-run 缺 --auth-ticket 必须被拒绝（必填或显式校验）")


if __name__ == "__main__":
    unittest.main()
