#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""工作空间落点校验的对抗性测试：确凿误路由必须阻断，探测不到必须"未校验"而非"已通过"。"""
import io
import json
import os
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
sys.path.insert(0, str(TOOLS))

import workspace_guard  # noqa: E402


ENTERPRISE_ORG = "9900000001"  # 虚构示例值
UID = "10086"
TOKEN = f"web.laifaxin.com&{UID}&secret-hash"


def response(is_org, **extra):
    data = {"isOrg": is_org, "vip": 2, "dailyLimit": 500, "monthlyLimit": 10000}
    data.update(extra)
    return {"success": True, "data": data}


class VerifyWorkspaceTest(unittest.TestCase):
    def check(self, org, payload):
        return workspace_guard.verify_workspace(TOKEN, org, probe=lambda t, o: payload)

    def test_personal_space_self_consistent(self):
        result = self.check(UID, response(False))
        self.assertTrue(result["ok"])
        self.assertTrue(result["verified"])
        self.assertFalse(result["blocked"])

    def test_enterprise_space_self_consistent(self):
        result = self.check(ENTERPRISE_ORG, response(True))
        self.assertTrue(result["ok"])
        self.assertTrue(result["verified"])
        self.assertFalse(result["blocked"])

    def test_enterprise_org_silently_routed_to_personal_is_blocked(self):
        """核心缺陷复现：给了企业 orgId，平台却按个人空间处理——必须阻断。"""
        result = self.check(ENTERPRISE_ORG, response(False))
        self.assertTrue(result["blocked"], "声明企业 orgId 但平台判个人空间，必须阻断")
        self.assertFalse(result["ok"])
        self.assertIn("个人空间", result["reason"])

    def test_enterprise_flag_with_uid_org_is_contradiction(self):
        result = self.check(UID, response(True))
        self.assertTrue(result["blocked"])
        self.assertIn("自相矛盾", result["reason"])

    def test_missing_is_org_is_unverified_not_pass(self):
        result = self.check(ENTERPRISE_ORG, {"success": True, "data": {"vip": 2}})
        self.assertFalse(result["ok"])
        self.assertFalse(result["verified"])
        self.assertFalse(result["blocked"])
        self.assertIn("未校验", result["reason"])

    def test_probe_failure_is_unverified_not_pass(self):
        for payload in (None, {"success": False, "message": "未登录"}):
            with self.subTest(payload=payload):
                result = self.check(ENTERPRISE_ORG, payload)
                self.assertFalse(result["verified"])
                self.assertFalse(result["blocked"])
                self.assertFalse(result["ok"])

    def test_missing_org_is_blocked_never_falls_back(self):
        result = workspace_guard.verify_workspace(TOKEN, "", probe=lambda t, o: response(False))
        self.assertTrue(result["blocked"])
        self.assertIn("orgId", result["reason"])

    def test_bool_like_is_org_values(self):
        self.assertTrue(self.check(ENTERPRISE_ORG, response(1))["ok"])
        self.assertTrue(self.check(ENTERPRISE_ORG, response(0))["blocked"])

    def test_fingerprint_changes_with_workspace_identity(self):
        personal = self.check(UID, response(False))
        enterprise = self.check(ENTERPRISE_ORG, response(True))
        self.assertNotEqual(workspace_guard.fingerprint(personal["observed"]),
                            workspace_guard.fingerprint(enterprise["observed"]))
        # 同一空间不同配额 → 指纹也不同（配额变化说明换了账号/空间）
        other = self.check(ENTERPRISE_ORG, response(True, monthlyLimit=50000))
        self.assertNotEqual(workspace_guard.fingerprint(enterprise["observed"]),
                            workspace_guard.fingerprint(other["observed"]))


class PreflightTest(unittest.TestCase):
    def test_preflight_blocks_bad_routing(self):
        with mock.patch.object(workspace_guard, "verify_workspace",
                               return_value={"ok": False, "verified": True, "blocked": True,
                                             "reason": "落点错", "observed": {}}):
            with self.assertRaises(SystemExit) as ctx:
                workspace_guard.preflight(TOKEN, ENTERPRISE_ORG, what="建标签")
            self.assertEqual(ctx.exception.code, 1)

    def test_preflight_dry_run_skips_network(self):
        called = []
        with mock.patch.object(workspace_guard, "verify_workspace", side_effect=lambda *a, **k: called.append(1)):
            self.assertEqual("", workspace_guard.preflight(TOKEN, ENTERPRISE_ORG, dry_run=True))
        self.assertEqual([], called, "dry-run 不应联网")

    def test_preflight_unverified_continues_without_claiming_pass(self):
        with mock.patch.object(workspace_guard, "verify_workspace",
                               return_value={"ok": False, "verified": False, "blocked": False,
                                             "reason": "平台未返回 isOrg", "observed": {}}):
            out = io.StringIO()
            with mock.patch("sys.stdout", out):
                self.assertEqual("", workspace_guard.preflight(TOKEN, ENTERPRISE_ORG))
            self.assertIn("未校验", out.getvalue())


class WorkspaceGuardCliTest(unittest.TestCase):
    """CLI 走 curl 子进程——用假 curl 验证参数形状与退出码。"""

    def run_cli(self, fake_body, args=None):
        with tempfile.TemporaryDirectory() as tmp:
            bin_dir = Path(tmp) / "bin"
            bin_dir.mkdir()
            log = Path(tmp) / "curl.log"
            fake = bin_dir / "curl"
            fake.write_text(
                "#!/bin/sh\nprintf '%s\\n' \"$@\" > \"$CURL_LOG\"\nprintf '%s' " + json.dumps(fake_body) + "\n",
                encoding="utf-8",
            )
            fake.chmod(fake.stat().st_mode | stat.S_IXUSR)
            env = os.environ.copy()
            env["PATH"] = str(bin_dir) + os.pathsep + env.get("PATH", "")
            env["CURL_LOG"] = str(log)
            result = subprocess.run(
                [sys.executable, str(TOOLS / "workspace_guard.py"), *(args or ["--token", TOKEN, "--org", ENTERPRISE_ORG])],
                capture_output=True, text=True, env=env, timeout=30,
            )
            argv = log.read_text(encoding="utf-8").splitlines() if log.exists() else []
            return result, argv

    def test_cli_sends_uid_in_header_not_url(self):
        """★2026-09-11：工作空间靠 header `uid` 传输，URL 里不得再出现 uid（query 无效且会误导）。"""
        result, argv = self.run_cli(json.dumps(response(True)))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        url = next(a for a in argv if a.startswith("https://"))
        self.assertNotIn("uid=", url, "URL 不应带 uid（平台只认 header）")
        self.assertNotIn("secret-hash", url, "token 不得进 URL")
        # header 形态： -H Content-Type ... / -H accesstoken: ... / -H uid: <org>
        headers = [argv[i + 1] for i, a in enumerate(argv) if a == "-H"]
        self.assertIn("Content-Type: application/json", headers)
        self.assertIn(f"uid: {ENTERPRISE_ORG}", headers, "工作空间必须放 header uid")
        self.assertTrue(any("accesstoken:" in h for h in headers))
        self.assertNotIn(f"uid: {TOKEN}", headers, "header uid 不能误用 token")

    def test_cli_blocks_misrouted_workspace(self):
        result, _ = self.run_cli(json.dumps(response(False)))
        self.assertEqual(result.returncode, 1)
        self.assertIn("个人空间", result.stderr)

    def test_cli_require_verified_blocks_unknown(self):
        body = json.dumps({"success": True, "data": {"vip": 2}})
        lenient, _ = self.run_cli(body)
        self.assertEqual(lenient.returncode, 4, "无法校验应返回 4（未校验），不是 0")
        strict, _ = self.run_cli(body, ["--token", TOKEN, "--org", ENTERPRISE_ORG, "--require-verified"])
        self.assertEqual(strict.returncode, 1)


if __name__ == "__main__":
    unittest.main()


class WriteToolsPreflightCoverageTest(unittest.TestCase):
    """静态核对：所有会写平台的脚本都必须调用 preflight（防漏网）。"""

    WRITE_TOOLS = (
        "gen_templates.py", "tag_add.py", "save_first_n.py", "contact_add.py",
        "build_sequence.py", "activate_sequence.py", "rebuild_templates.py",
        "delete_all_products.py", "flow_orchestrator.py", "segments_infer.py",
    )

    def test_every_write_tool_calls_preflight(self):
        for name in self.WRITE_TOOLS:
            with self.subTest(tool=name):
                source = (TOOLS / name).read_text(encoding="utf-8")
                self.assertIn("preflight(", source, f"{name} 必须做工作空间落点校验")
                self.assertIn("workspace_guard", source, f"{name} 必须导入 workspace_guard")

    def test_preflight_runs_before_first_write_call(self):
        """preflight 必须出现在第一个平台写接口之前（否则校验来不及挡）。"""
        write_markers = ("template-add", "company-save", "contact-add", "step-create",
                         "sequence-save", "sequence-create", "tag-add", "template-delete",
                         "step-save", "product-delete", "inference-product-add",
                         "sequence-active", "tag-add")
        for name in self.WRITE_TOOLS:
            with self.subTest(tool=name):
                source = (TOOLS / name).read_text(encoding="utf-8")
                preflight_at = source.find("preflight(")
                self.assertGreater(preflight_at, -1, f"{name} 缺 preflight")
                writes = [source.find(f'"{m}"') for m in write_markers if source.find(f'"{m}"') > -1]
                writes = [w for w in writes if w > 0]
                if writes:
                    self.assertLess(preflight_at, min(writes),
                                    f"{name}: preflight 必须早于第一个写接口调用")
