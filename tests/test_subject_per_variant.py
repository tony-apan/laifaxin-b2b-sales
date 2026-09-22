#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""标题逐变体差异化测试（2026-09-18 用户实测后立）。

事故：用户在平台模板列表看到同一轮 4 个变体的**标题完全一样**
（R01 的 V02/V03/V06 主题都是 `Headwear OEM for your collections`）——
正文虽然不同，但标题是收件人最先看到的内容，标题相同 = 看不出差异，
等于白做了"同轮不重复"的正文差异化。

根因：旧 plan 格式把标题放在**轮级**（`directions` 第 3 位是单个字符串），
所有变体共用；且 `check_template_diff.py` **只比 html 不比标题**，标题全同也判"差异达标"（假阴性）。

本测试锁三件事：
  ①plan 加载阶段就拒绝"多变异体却只给一个标题"
  ②拒绝同轮标题重复 / 跨轮标题重复
  ③差异断言必须单独查标题（不能只看正文相似度）
"""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"


class SubjectPerVariantTest(unittest.TestCase):
    """真跑 gen_templates.py 的 plan 校验（不需要平台，校验在联网之前）。"""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="subj-"))

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def write_plan(self, directions, variants):
        p = self.tmp / "plan.json"
        p.write_text(json.dumps({"profile_sha256": "0" * 64, "directions": directions,
                                 "variants": variants, "claims": []}), encoding="utf-8")
        return p

    def run_plan_gate(self, directions, variants):
        """跑到 plan 校验为止（无 token 会在更后面才报，plan 错误在其之前 exit 2）。"""
        plan = self.write_plan(directions, variants)
        r = subprocess.run(
            [sys.executable, str(TOOLS / "gen_templates.py"), "--plan", str(plan),
             "--token", "x", "--org", "1", "--product", "demo", "--name", "Tony",
             "--prefix", "英-demo-", "--project", "tony/demo",
             "--profile", "runs/tony/demo/product-profile.md"],
            capture_output=True, text=True, cwd=ROOT, timeout=90)
        return r

    def test_rejects_single_subject_for_multiple_variants(self):
        """★核心：4 个变体只给 1 个标题 → 必须拒绝（这正是事故形态）。"""
        d = [["R01", "破冰", "Headwear OEM for your collections", "angle"]]
        r = self.run_plan_gate(d, ["v1", "v2", "v3", "v4"])
        self.assertEqual(2, r.returncode, r.stdout + r.stderr)
        self.assertIn("标题", r.stdout + r.stderr, "报错须说清是标题问题")
        self.assertRegex(r.stdout + r.stderr, r"标题列表|各变体",
                         "报错须告诉怎么改（给标题列表）")

    def test_rejects_duplicate_subjects_within_round(self):
        d = [["R01", "破冰", ["Same subject", "Same subject", "B", "C"], "angle"]]
        r = self.run_plan_gate(d, ["v1", "v2", "v3", "v4"])
        self.assertEqual(2, r.returncode, r.stdout + r.stderr)
        self.assertIn("主题重复", r.stdout + r.stderr)

    def test_rejects_duplicate_subjects_across_rounds(self):
        subj = ["A", "B", "C", "D"]
        d = [["R01", "破冰", subj, "angle1"], ["R02", "信任", subj, "angle2"]]
        r = self.run_plan_gate(d, ["v1", "v2", "v3", "v4"])
        self.assertEqual(2, r.returncode, r.stdout + r.stderr)
        self.assertRegex(r.stdout + r.stderr, r"跨轮标题重复|标题重复")

    def test_rejects_subject_count_mismatch(self):
        d = [["R01", "破冰", ["A", "B"], "angle"]]
        r = self.run_plan_gate(d, ["v1", "v2", "v3", "v4"])
        self.assertEqual(2, r.returncode, r.stdout + r.stderr)
        self.assertIn("不一致", r.stdout + r.stderr)

    def test_accepts_distinct_subjects(self):
        """合法新格式必须放行（否则就是修成死锁）。"""
        d = [["R01", "破冰", ["A1", "A2", "A3", "A4"], "angle1"],
             ["R02", "信任", ["B1", "B2", "B3", "B4"], "angle2"]]
        r = self.run_plan_gate(d, ["v1", "v2", "v3", "v4"])
        self.assertNotEqual(2, r.returncode,
                            f"合法 plan 不应被拒：{r.stdout}{r.stderr}")

    def test_diff_tool_checks_subject_duplicates(self):
        """差异断言必须单独查标题（旧版只比 html → 标题全同也判达标）。"""
        src = (TOOLS / "check_template_diff.py").read_text(encoding="utf-8")
        self.assertIn("subject", src.lower(), "差异工具未读标题")
        self.assertRegex(src, r"标题重复|sub_dupes",
                         "差异工具未单独查标题重复（只比正文=假阴性）")

    def test_specs_document_the_rule(self):
        text = (ROOT / "specs" / "sequence-config.md").read_text(encoding="utf-8")
        self.assertIn("标题必须逐变体不同", text, "规格未写明该规则")
        self.assertRegex(text, r"标题列表", "规格未给出新格式写法")
