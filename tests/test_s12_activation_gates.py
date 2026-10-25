#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""第 7 关激活前结构闸门（三审 S0-1/S1-1/S1-2）端到端回归。

覆盖：上限实读 30000/5、notSentTags 必须是「询盘/不发」真实标签名、
12 步模板必须真实在模板库且步长正确、只读接口读失败必须 fail-closed。
用 activate_sequence.py --check-structure 真跑工具（只读，不激活、不写任何状态）。
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SEQ = "a" * 24
TOKEN = "fake-token-for-offline-test"
ORG = "fake-org-for-offline-test"

FAKE_CURL = r'''#!/usr/bin/env python3
import json, os, sys
from pathlib import Path
from urllib.parse import urlparse

mode = os.environ.get("LFX_FAKE_MODE", "good")
args = sys.argv[1:]
url = next((a for a in args if a.startswith("http://") or a.startswith("https://")), "")
path = urlparse(url).path
payload = {}
if "-d" in args:
    try:
        payload = json.loads(args[args.index("-d") + 1])
    except Exception:
        payload = {}
log = Path(os.environ.get("LFX_FAKE_CURL_LOG", "/dev/null"))
with log.open("a", encoding="utf-8") as fh:
    fh.write(json.dumps({"path": path}, ensure_ascii=False) + "\n")

def steps(ids):
    waits = [("minute", 30), ("day", 5), ("day", 15)] + [("day", 30)] * 9
    return [{"step": i + 1, "template_ids": [ids[i]], "wait_mode": waits[i][0], "wait_time": waits[i][1]} for i in range(12)]

good_templates = [f"{i + 0x300:024x}" for i in range(12)]
if path == "/api/sequences/sequence-details":
    rules = {"max_emails_per_day": 30000, "domain_emails_per_day": 5,
             "notSentTags": ["000000000000000000000043", "000000000000000000000044"]}
    if mode == "bad_limits":
        rules["max_emails_per_day"] = 1000
    if mode == "bad_tags":
        rules["notSentTags"] = ["000000000000000000000043", "000000000000000000000045"]
    out = {"success": True, "data": {"rules": rules}}
elif path == "/api/contacts/tags-list":
    if mode == "tags_read_fail":
        out = {"success": False, "message": "boom"}
    else:
        out = {"success": True, "data": {"list": [
            {"id": "000000000000000000000043", "name": "询盘"},
            {"id": "000000000000000000000044", "name": "不发"},
            {"id": "000000000000000000000045", "name": "VIP"},
        ]}}
elif path == "/api/sequences/step-list":
    ids = list(good_templates)
    if mode == "bad_template":
        ids[3] = "f" * 24
    out = {"success": True, "data": steps(ids)}
elif path == "/api/mailbox/templates-list":
    if int(payload.get("current", 1)) > 1:
        out = {"success": True, "data": {"list": []}}
    else:
        out = {"success": True, "data": {"list": [{"_id": t} for t in good_templates]}}
elif path == "/api/sequences/sequence-list":
    out = {"success": True, "data": {"list": [{"id": "a" * 24, "status": "inactive", "active": False}]}}
else:
    out = {"success": True, "data": {}}
print(json.dumps(out))
'''

@unittest.skipUnless(sys.platform != "win32", "fake curl shim 依赖 POSIX 可执行脚本")
class ActivationStructureGateTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.bin = Path(self.tmp.name) / "bin"
        self.bin.mkdir()
        curl = self.bin / "curl"
        if os.name == "nt":
            raise unittest.SkipTest("Windows 无扩展名 fake curl（离线平台仿真仅 POSIX）；Windows 用真机 smoke 覆盖")
        curl.write_text(FAKE_CURL, encoding="utf-8")
        curl.chmod(0o755)
        self.log = Path(self.tmp.name) / "curl.log"

    def _run(self, mode):
        env = dict(os.environ)
        env.update({
            "PATH": str(self.bin) + os.pathsep + env.get("PATH", ""),
            "LFX_GATE_TEST_MODE": "1",
            "LFX_FAKE_MODE": mode,
            "LFX_FAKE_CURL_LOG": str(self.log),
            "PYTHONIOENCODING": "utf-8",
        })
        return subprocess.run(
            [sys.executable, str(ROOT / "tools" / "activate_sequence.py"),
             "--check-structure", "--token", TOKEN, "--org", ORG, "--seq", SEQ],
            cwd=str(ROOT), capture_output=True, text=True, env=env, timeout=60,
        encoding="utf-8", errors="replace")

    def test_good_structure_passes(self):
        r = self._run("good")
        self.assertEqual(0, r.returncode, r.stdout + r.stderr)
        self.assertIn("激活前结构闸门通过", r.stdout)
        self.assertIn("contacts/tags-list", self.log.read_text(encoding="utf-8"))

    def test_wrong_daily_limit_blocks(self):
        r = self._run("bad_limits")
        self.assertEqual(2, r.returncode, r.stdout + r.stderr)
        self.assertIn("max_emails_per_day", r.stdout)
        self.assertIn("不得激活", r.stdout)

    def test_wrong_tag_identity_blocks(self):
        r = self._run("bad_tags")
        self.assertEqual(2, r.returncode, r.stdout + r.stderr)
        self.assertIn("标签名", r.stdout)
        self.assertIn("不得激活", r.stdout)

    def test_template_not_in_library_blocks(self):
        r = self._run("bad_template")
        self.assertEqual(2, r.returncode, r.stdout + r.stderr)
        self.assertIn("不在邮件模板库", r.stdout)

    def test_tag_list_read_failure_fails_closed(self):
        r = self._run("tags_read_fail")
        self.assertEqual(2, r.returncode, r.stdout + r.stderr)
        self.assertIn("contacts/tags-list 读取失败", r.stdout)


class ApprovalSingleUseLedgerTest(unittest.TestCase):
    """三审 S1-5：同一 S12 凭证只允许成功激活一次。"""

    @classmethod
    def setUpClass(cls):
        import importlib.util
        spec = importlib.util.spec_from_file_location("_lfx_approval_gate", ROOT / "tools" / "approval.py")
        cls.mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.mod)

    def test_mark_then_used_and_idempotent(self):
        aid = "ap-offline-single-use-test"
        self.mod.mark_approval_used(aid, "tony/demo", "S12", SEQ)
        self.assertTrue(self.mod.is_approval_used(aid))
        before = self.mod.USED_LEDGER.read_text(encoding="utf-8")
        self.mod.mark_approval_used(aid, "tony/demo", "S12", SEQ)
        self.assertEqual(before, self.mod.USED_LEDGER.read_text(encoding="utf-8"), "重复登记必须幂等")
        self.assertFalse(self.mod.is_approval_used("ap-never-used-xyz"))
