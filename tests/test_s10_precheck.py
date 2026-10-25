#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""S10 加人前只读预检回归（任务C）：人数为 0 / 标签缺失 → 中文 exit 2 且不写平台。

背景：S10 预检此前只有"标签联系人>0"的裸判断（exit 1、无白话明细），
用户看不到"本客群标签下人数、预计加人量、去重说明、序列未激活"；
缺标签还被当成"尽力而为"放行。本测试锁死：
  ① 人数为 0 → exit 2 + 中文白话 + 绝不调用 sequences/contact-add
  ② 标签缺失（tags-list 查不到）→ exit 2 + 中文白话 + 不写平台
  ③ 正常路径（dry-run 与正式）打印四项白话明细；dry-run 不写平台
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
SEQ = "0123456789abcdef01234567"
ORG = "org-for-precheck-tests"
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
    "contacts/tags-list": {"success": True, "data": {"list": %(tags)s}},
    "operation/backend-task-status": {"success": True, "data": {"status": "finished", "contactSaveCount": (None if __import__("os").environ.get("FAKE_SAVED", "5") == "None" else int(__import__("os").environ.get("FAKE_SAVED", "5")))}},
    "contacts/contacts/show": {"success": True, "data": {"total": %(total)d}},
    "sequences/contact-add": {"success": True, "data": {"add": %(total)d}},
}
print(json.dumps(responses.get(path, {"success": False, "message": "unexpected " + path})))
'''



try:
    from gate_env import gate_test_env
except ImportError:
    from tests.gate_env import gate_test_env

class S10PrecheckTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="s10pre-"))
        self.repo = self.tmp / "repo"
        shutil.copytree(ROOT, self.repo, ignore=shutil.ignore_patterns(
            ".git", ".local", "runs", "__pycache__", "node_modules"))
        self.project_dir = self.repo / "runs" / "tony" / "demo"
        self.project_dir.mkdir(parents=True)
        self.record = self.project_dir / "operation-record.md"
        self.write_record("S9")
        self.bin = self.tmp / "bin"
        self.bin.mkdir()
        self.log = self.tmp / "curl.log"
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

    def install_curl(self, total, tags=None):
        tags = tags if tags is not None else [{"id": "tag-1", "name": "英语-客户"}]
        fake = self.bin / "curl"
        if os.name == "nt":
            raise unittest.SkipTest("Windows 无扩展名 fake curl（离线平台仿真仅 POSIX）；Windows 用真机 smoke 覆盖")
        fake.write_text(FAKE_CURL % {"seq": SEQ, "tags": json.dumps(tags), "total": total},
                        encoding="utf-8")
        fake.chmod(0o755)

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
             "--approval", self.approval, *extra],
            capture_output=True, text=True, cwd=self.repo, env=self.env, timeout=180, encoding="utf-8", errors="replace")

    def calls(self):
        if not self.log.exists():
            return []
        return [line for line in self.log.read_text(encoding="utf-8").splitlines() if line]

    # ---------- ① 人数为 0：中文 exit 2，绝不写平台 ----------
    def test_zero_contacts_rejected_exit2_without_write(self):
        self.install_curl(total=0)
        bad_ticket = self.tmp / "bad-ticket.json"
        bad_ticket.write_text("{}", encoding="utf-8")
        bad_ticket.chmod(0o600)
        r = self.run_add("--auth-ticket", str(bad_ticket))
        out = r.stdout + r.stderr
        self.assertEqual(2, r.returncode, out)
        self.assertIn("S10 加人前预检未通过", out)
        self.assertIn("人数为 0", out)
        self.assertIn("不写平台", out)
        self.assertNotIn("sequences/contact-add", self.calls(),
                         "★人数为 0 时写调用必须为 0")
        self.assertEqual("S9", self.status(), "预检拒绝不得推进本地状态")

    # ---------- ② 标签缺失：中文 exit 2，不写平台 ----------
    def test_missing_tag_rejected_exit2_without_write(self):
        self.install_curl(total=5, tags=[{"id": "tag-other", "name": "英语-其他"}])
        bad_ticket = self.tmp / "bad-ticket.json"
        bad_ticket.write_text("{}", encoding="utf-8")
        bad_ticket.chmod(0o600)
        r = self.run_add("--auth-ticket", str(bad_ticket))
        out = r.stdout + r.stderr
        self.assertEqual(2, r.returncode, out)
        self.assertIn("缺标签", out)
        self.assertIn("tag-1", out)
        self.assertNotIn("sequences/contact-add", self.calls())

    # ---------- ③ dry-run 可看：四项白话明细 + 不写平台 ----------
    def test_dry_run_prints_plain_precheck(self):
        self.install_curl(total=5)
        r = self.run_add("--dry-run")
        out = r.stdout + r.stderr
        self.assertEqual(0, r.returncode, out)
        for must in ("S10 加人前只读预检", "本客群标签下人数: 5 人", "预计加人量: 5 人",
                     "去重说明", "未激活", "[dry-run]"):
            self.assertIn(must, out, f"dry-run 预检缺「{must}」")
        self.assertNotIn("sequences/contact-add", self.calls(),
                         "dry-run 不得写平台")

    # ---------- ⑤ 人数硬对账：contactSaveCount ≠ 标签人数 → exit 2，不写平台 ----------
    def test_saved_count_mismatch_blocks_before_write(self):
        self.install_curl(total=5)
        self.env["FAKE_SAVED"] = "4"  # 任务说存了 4，标签下却有 5 人
        ticket = self.mint_ticket()
        r = self.run_add("--auth-ticket", str(ticket))
        out = r.stdout + r.stderr
        self.assertEqual(2, r.returncode, out)
        self.assertIn("S10 人数对账不通过", out)
        self.assertIn("contactSaveCount=4", out)
        self.assertIn("标签人数=5", out)
        self.assertNotIn("sequences/contact-add", self.calls(),
                         "★人数对账不通过时写调用必须为 0")
        self.assertEqual("S9", self.status(), "对账失败不得推进状态")

    def test_missing_saved_count_fails_closed(self):
        self.install_curl(total=5)
        self.env["FAKE_SAVED"] = "None"
        ticket = self.mint_ticket()
        r = self.run_add("--auth-ticket", str(ticket))
        out = r.stdout + r.stderr
        self.assertEqual(2, r.returncode, out)
        self.assertIn("没返回 contactSaveCount", out)
        self.assertNotIn("sequences/contact-add", self.calls())

    # ---------- ④ 正式路径也打印预检明细（防只对 dry-run 生效） ----------
    def test_formal_run_prints_plain_precheck_then_writes_once(self):
        self.install_curl(total=5)
        ticket = self.mint_ticket()
        r = self.run_add("--auth-ticket", str(ticket))
        out = r.stdout + r.stderr
        self.assertEqual(0, r.returncode, out)
        for must in ("S10 加人前只读预检", "本客群标签下人数: 5 人", "预计加人量: 5 人",
                     "去重说明", "未激活"):
            self.assertIn(must, out, f"正式路径预检缺「{must}」")
        self.assertEqual(1, self.calls().count("sequences/contact-add"))
        self.assertEqual("S10", self.status())


if __name__ == "__main__":
    unittest.main()
