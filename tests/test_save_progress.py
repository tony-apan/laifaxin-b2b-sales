# -*- coding: utf-8 -*-
"""S6 保存进度播报：一行中文、含已存/总数/剩余，且不编造。"""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import save_progress  # noqa: E402


class SaveProgressTest(unittest.TestCase):
    def test_basic_line(self):
        line = save_progress.format_progress(1200, 9560, points=1800, elapsed_s=600)
        self.assertIn("1200/9560", line)
        self.assertIn("已用 1800 点", line)
        self.assertIn("预计还要", line)
        self.assertIn("您不用操作", line)
        for bad in ("S6", "task", "hash", "点数余额"):
            self.assertNotIn(bad, line)

    def test_no_numbers_no_fabrication(self):
        line = save_progress.format_progress(0, 0)
        self.assertIn("正在保存", line)
        self.assertNotIn("%", line)

    def test_never_exceeds_total(self):
        line = save_progress.format_progress(999, 100, points=None, elapsed_s=10)
        self.assertIn("100/100", line)

    def test_bad_input_degrades(self):
        line = save_progress.format_progress("x", "y")
        self.assertIn("正在保存", line)


if __name__ == "__main__":
    unittest.main()
