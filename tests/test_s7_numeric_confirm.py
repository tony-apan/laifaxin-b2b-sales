#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""S7 数字确认端到端回归（2026-10-23 三审 K 余项）：用户回「1」只对 S7 模板确认有效。

锁死：
  ① approval.py grant --state S7_... --quote 1 → 允许（S7 卡允许数字确认）
  ② 非 S7 节点（S2/S5/S9/S10）--quote 1 → 拒绝（必须明确确认词，防手滑）
  ③ S7 用明确确认词也允许（两条路径都通）
"""
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROJECT = "tony/demo"


class S7NumericConfirmTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="s7num-"))
        self.repo = self.tmp / "repo"
        shutil.copytree(ROOT, self.repo, ignore=shutil.ignore_patterns(
            ".git", ".local", "runs", "__pycache__", ".pytest_cache"))
        self.env = __import__("os").environ.copy()
        self.env["LFX_GATE_TEST_MODE"] = "1"
        self.env["PYTHONDONTWRITEBYTECODE"] = "1"

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def grant(self, state, quote):
        return subprocess.run(
            [sys.executable, str(self.repo / "tools" / "approval.py"), "grant",
             "--project", PROJECT, "--state", state, "--quote", quote, "--params", "{}"],
            capture_output=True, text=True, cwd=self.repo, env=self.env, timeout=60, encoding="utf-8", errors="replace")

    def test_s7_accepts_bare_number(self):
        r = self.grant("S7_模板预览", "1")
        self.assertEqual(0, r.returncode, r.stdout + r.stderr)
        self.assertIn("凭证已铸造", r.stdout)

    def test_s7_accepts_explicit_words_too(self):
        r = self.grant("S7_模板预览", "确认执行")
        self.assertEqual(0, r.returncode, r.stdout + r.stderr)

    def test_non_s7_rejects_bare_number(self):
        for state in ("S2_客群确认", "S5_保存参数", "S9_序列配置", "S10_加联系人"):
            with self.subTest(state=state):
                r = self.grant(state, "1")
                self.assertNotEqual(0, r.returncode, f"{state} 不应接受裸「1」: {r.stdout}")
                self.assertIn("确认", r.stdout + r.stderr)


if __name__ == "__main__":
    unittest.main()
