#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""邮件格式口径回归：HTML 是载体、CTA 靠加粗、emoji 受限、字数有上限；旧教程已纠偏。"""
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class EmailFormatDoctrineTest(unittest.TestCase):
    def test_s7_explains_format_in_plain_words(self):
        s7 = (ROOT / "output-templates/S7-template-confirm.md").read_text(encoding="utf-8")
        for needle in ("邮件格式白话口径", "不放产品大图", "Reply " + chr(34) + "CATALOG" + chr(34), "emoji 0–1", "≤120 词", "垃圾箱"):
            self.assertIn(needle, s7)

    def test_docs07_points_to_current_spec(self):
        doc = (ROOT / "docs/07-ai-cold-email.md").read_text(encoding="utf-8")
        head = doc.split("##")[0]
        self.assertIn("格式口径以", head)
        self.assertIn("sequence-config", head)
        self.assertIn("已作废", head)
        self.assertIn("12 轮×4=48", doc)

    def test_docs07_old_highlight_removed(self):
        doc = (ROOT / "docs/07-ai-cold-email.md").read_text(encoding="utf-8")
        self.assertNotIn("background-color:yellow", doc)
        self.assertNotIn("强制 HTML 结构", doc)


if __name__ == "__main__":
    unittest.main()
