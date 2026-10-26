#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""数字确认端到端回归（2026-10-23 三审 K 余项，2026-10-26 修正适用范围）。

确认卡统一让用户「回 1」，因此放行范围必须与 output-templates 的确认卡一致：
  ① S7/S9/S10 允许裸「1」（S7 模板、S9 序列、S10 加人 三张卡都是「回 1」）
  ② 其他节点（S2/S5/S6/S8/S11/S12）--quote 1 → 拒绝，仍要明确确认词（防手滑）
  ③ 明确确认词在所有节点都允许
2026-10-26 真机卡点：S9 卡让用户回 1，但 approval.py 只放行 S7，合法确认被拒。
"""
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROJECT = "tony/demo"



try:
    from gate_env import gate_test_env
except ImportError:
    from tests.gate_env import gate_test_env

class S7NumericConfirmTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="s7num-"))
        self.repo = self.tmp / "repo"
        shutil.copytree(ROOT, self.repo, ignore=shutil.ignore_patterns(
            ".git", ".local", "runs", "__pycache__", ".pytest_cache"))
        self.env = __import__("os").environ.copy()
        self.env.update(gate_test_env())
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

    def test_s9_s10_accept_bare_number(self):
        for state in ("S9_序列配置", "S10_加联系人"):
            with self.subTest(state=state):
                r = self.grant(state, "1")
                self.assertEqual(0, r.returncode, r.stdout + r.stderr)

    def test_other_states_reject_bare_number(self):
        for state in ("S2_客群确认", "S5_保存参数", "S6_保存执行", "S12_激活"):
            with self.subTest(state=state):
                r = self.grant(state, "1")
                self.assertNotEqual(0, r.returncode, f"{state} 不应接受裸「1」: {r.stdout}")
                out = r.stdout + r.stderr
                self.assertTrue(any(k in out for k in ("确认", "禁止", "拒绝")), out)


if __name__ == "__main__":
    unittest.main()
