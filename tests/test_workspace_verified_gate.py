#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""工作空间落点校验：未判定时必须 fail-closed（三审 S2-1）。"""
import importlib.util
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
SPEC = importlib.util.spec_from_file_location("_workspace_guard", ROOT / "tools" / "workspace_guard.py")


class WorkspaceVerifiedGateTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.wg = importlib.util.module_from_spec(SPEC)
        SPEC.loader.exec_module(cls.wg)

    def setUp(self):
        self._orig_verify = self.wg.verify_workspace
        self._orig_mode = self.wg._is_test_mode
        self.addCleanup(self._restore)

    def _restore(self):
        self.wg.verify_workspace = self._orig_verify
        self.wg._is_test_mode = self._orig_mode

    def _fake(self, **result):
        base = {"ok": False, "verified": False, "blocked": False, "reason": "平台未返回 isOrg", "observed": {}}
        base.update(result)
        self.wg.verify_workspace = lambda token, org: base

    def test_unverified_space_fails_closed_in_production(self):
        self._fake()
        self.wg._is_test_mode = lambda: False
        with self.assertRaises(SystemExit) as ctx:
            self.wg.preflight("token", "org", what="激活序列", require_verified=True)
        self.assertEqual(5, ctx.exception.code, "未判定必须 exit 5（不能当成功）")

    def test_unverified_space_only_warns_in_test_mode(self):
        self._fake()
        self.wg._is_test_mode = lambda: True
        self.assertEqual("", self.wg.preflight("token", "org", what="激活序列", require_verified=True))

    def test_verified_space_records_fingerprint(self):
        self._fake(verified=True, ok=True, reason="工作空间已校验",
                   observed={"is_org": True, "vip": 2, "monthly_limit": 10000, "daily_limit": 500})
        self.wg._is_test_mode = lambda: False
        self.assertTrue(self.wg.preflight("token", "org", require_verified=True))

    def test_explicit_mismatch_still_exit_1(self):
        self._fake(blocked=True, reason="org 与 token 不一致")
        self.wg._is_test_mode = lambda: False
        with self.assertRaises(SystemExit) as ctx:
            self.wg.preflight("token", "org", require_verified=True)
        self.assertEqual(1, ctx.exception.code)


if __name__ == "__main__":
    unittest.main()
