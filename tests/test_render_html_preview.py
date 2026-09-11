#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""HTML 预览渲染测试：加粗标记不泄漏、CTA 段独立标注、变量替换正确。"""
import json
import re
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import render_html_preview as preview  # noqa: E402


class RecipientViewTest(unittest.TestCase):
    def test_bold_becomes_strong_without_marker_leak(self):
        lines = preview.recipient_view('Worth a look? Reply "<b>CATALOG</b>" and I will send <b>MOQ</b> sheet.')
        rendered = "".join(preview.to_paragraph_html(l) for l in lines)
        self.assertIn("<strong>CATALOG</strong>", rendered)
        self.assertIn("<strong>MOQ</strong>", rendered)
        self.assertNotIn("\x01", rendered)
        self.assertNotIn("\x02", rendered)

    def test_contact_variable_replaced(self):
        lines = preview.recipient_view('<p>Hi <code class="lfxFieldVeriable">{联系人:名称}</code>,</p>', name="Iris")
        self.assertEqual(["Hi Iris,"], lines)

    def test_html_escaped_in_output(self):
        rendered = preview.to_paragraph_html('a <script>alert(1)</script> b')
        self.assertNotIn("<script>", rendered)
        self.assertIn("&lt;script&gt;", rendered)


class PreviewFileTest(unittest.TestCase):
    def test_renders_all_rounds_and_marks_cta_paragraph(self):
        plan = {"directions": [["R01", "破冰", "Subject A", "Are your <b>SKUs</b> locked in?"],
                               ["R02", "信任", "Subject B", "Do you need <b>seams</b> tested?"]],
                "variants": ['Worth a look? Reply "<b>CATALOG</b>" and I will send our <b>MOQ</b> sheet.']}
        with tempfile.TemporaryDirectory() as tmp:
            plan_path = Path(tmp) / "plan.json"
            plan_path.write_text(json.dumps(plan, ensure_ascii=False), encoding="utf-8")
            out = Path(tmp) / "preview.html"
            rc = preview.main(["--plan", str(plan_path), "--out", str(out), "--name", "Tony"])
            self.assertEqual(0, rc)
            html_text = out.read_text(encoding="utf-8")
        self.assertEqual(2, html_text.count('<div class="card">'))
        self.assertEqual(2, html_text.count('class="cta"'), "每张卡的最后一个段落必须标为 CTA 段")
        self.assertIn("<strong>CATALOG</strong>", html_text)
        self.assertNotIn("\x01", html_text)

    def test_selection_limits_rounds_and_variants(self):
        plan = {"directions": [[f"R{i:02d}", f"方向{i}", f"S{i}", f"Angle {i}"] for i in range(1, 13)],
                "variants": [f"Variant {i} — reply \"<b>KW{i}</b>\" for details." for i in range(1, 11)]}  # 每轮变体数仅影响渲染，不涉及 10/4 契约
        with tempfile.TemporaryDirectory() as tmp:
            plan_path = Path(tmp) / "plan.json"
            plan_path.write_text(json.dumps(plan, ensure_ascii=False), encoding="utf-8")
            out = Path(tmp) / "preview.html"
            preview.main(["--plan", str(plan_path), "--out", str(out), "--rounds", "1-3", "--variants", "1,2"])
            html_text = out.read_text(encoding="utf-8")
        self.assertEqual(6, html_text.count('<div class="card">'), "3 轮 × 2 变体 = 6 张卡")
        self.assertIn("R01-V01", html_text)
        self.assertIn("R03-V02", html_text)
        self.assertNotIn("R04-V01", html_text)

    def test_missing_directions_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan_path = Path(tmp) / "plan.json"
            plan_path.write_text(json.dumps({"variants": ["x"]}), encoding="utf-8")
            self.assertEqual(2, preview.main(["--plan", str(plan_path), "--out", str(Path(tmp) / "o.html")]))


if __name__ == "__main__":
    unittest.main()
