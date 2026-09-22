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

    def test_rejects_variable_or_html_in_subject(self):
        """★标题纯文案（规格既有规则，工具此前从未校验）：含 {变量} 或 HTML → 拒绝。"""
        for bad in ["Has {联系人:名称}", "Has <b>bold</b>", "Var lfxFieldVeriable x"]:
            d = [["R01", "破冰", [bad, "B", "C", "D"], "angle"]]
            r = self.run_plan_gate(d, ["v1", "v2", "v3", "v4"])
            with self.subTest(bad=bad):
                self.assertEqual(2, r.returncode, f"标题含变量/HTML 未拦: {bad}")
                self.assertIn("纯文案", r.stdout + r.stderr)

    def test_rejects_skin_deep_angle_titles(self):
        """★2026-09-18 用户拍板『标题要多角度』：不只是字面不同，角度也要不同。

        三类"假差异"必须拦：
        ①编号堆砌（Subject 1/2/3/4）②同框架换一个词（Caps OEM→Hats OEM）③同句换数字
        真多角度（产品线/打样/交期产能/趋势各写一面）必须放行。
        """
        cases = [
            ("编号堆砌", [["R01","破冰",["Subject 1","Subject 2","Subject 3","Subject 4"],"a"]], True),
            ("同框架换皮", [["R01","破冰",["Caps OEM for your brand","Hats OEM for your brand",
                                        "Beanies OEM for your brand","Scarves OEM for your brand"],"a"]], True),
            ("同句换数字", [["R01","破冰",["Caps from 1 factory","Caps from 2 factory",
                                        "Caps from 3 factory","Caps from 4 factory"],"a"]], True),
            ("真多角度", [["R01","破冰",["Headwear OEM for your collections",
                                      "Free sampling on your next caps order",
                                      "15-day lead time, 3000 pcs MOQ",
                                      "Recycled fabrics trending in EU headwear"],"a"]], False),
        ]
        for name, dirs, should_reject in cases:
            r = self.run_plan_gate(dirs, ["v1", "v2", "v3", "v4"])
            rc, out = r.returncode, r.stdout + r.stderr
            with self.subTest(case=name):
                if should_reject:
                    self.assertEqual(2, rc, f"「{name}」未被拦（假差异放行）")
                    self.assertRegex(out, r"多角度|角度雷同|堆砌", "报错须解释要真多角度")
                else:
                    self.assertNotEqual(2, rc, f"「{name}」被误拦: {out[:200]}")

    def test_tool_docs_describe_new_format(self):
        """★对抗复查补：工具自身的 docstring/--help 必须写新格式——
        AI 照 help 写 plan，写旧格式会被校验拒掉=白跑一趟。"""
        src = (TOOLS / "gen_templates.py").read_text(encoding="utf-8")
        self.assertNotIn('"主题纯文案"', src,
                         "工具文档仍写旧格式（单字符串标题）——会误导 AI 生成被拒的 plan")
        self.assertIn("逐变体主题", src, "工具文档未写明新格式（逐变体标题列表）")

    def test_specs_document_the_rule(self):
        text = (ROOT / "specs" / "sequence-config.md").read_text(encoding="utf-8")
        self.assertIn("标题必须逐变体不同", text, "规格未写明该规则")
        self.assertRegex(text, r"标题列表", "规格未给出新格式写法")
