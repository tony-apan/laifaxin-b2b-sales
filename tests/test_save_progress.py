# -*- coding: utf-8 -*-
"""S6 保存进度播报：一行中文、含已存/总数/剩余，且不编造。"""
import contextlib
import io
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import save_progress  # noqa: E402


class SaveProgressTest(unittest.TestCase):
    def test_basic_line(self):
        line = save_progress.format_progress(1200, 9560, points=1800, eta_s=600)
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

    def test_preserves_inconsistent_platform_counts(self):
        line = save_progress.format_progress(999, 100, points=None, elapsed_s=10)
        self.assertIn("999/100", line)
        self.assertIn("等待核实", line)

    def test_cli_eta_and_disabled_elapsed(self):
        for extra, success, expected in [(["--eta-seconds", "600"], True, "预计还要 10 分钟"),
                                          (["--elapsed", "600"], False, "已停用"),
                                          ([], True, "1/10"),
                                          (["--eta-seconds", "nan"], False, "有限"),
                                          (["--eta-seconds", "inf"], False, "有限"),
                                          (["--eta-seconds", "-1"], False, "非负")]:
            with self.subTest(extra=extra):
                out, err = io.StringIO(), io.StringIO()
                with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                    try:
                        code = save_progress.main(["--saved", "1", "--total", "10"] + extra)
                    except SystemExit as exc:
                        code = exc.code
                self.assertEqual(code == 0, success)
                self.assertIn(expected, out.getvalue() + err.getvalue())

    def test_bad_input_degrades(self):
        line = save_progress.format_progress("x", "y")
        self.assertIn("正在保存", line)


if __name__ == "__main__":
    unittest.main()
