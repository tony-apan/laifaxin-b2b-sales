#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""第 5–7 屏真人视角模拟暴露的边界话术回归（2026-10-23）。"""
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(rel):
    return (ROOT / rel).read_text(encoding="utf-8")


class LateStageEdgeCaseTest(unittest.TestCase):
    def test_s8_retry_does_not_duplicate_templates(self):
        s8 = read("output-templates/S8-template-building.md")
        self.assertIn("不会重复建", s8)
        self.assertIn("复用", s8)

    def test_s9_gives_real_small_trial_path(self):
        s9 = read("output-templates/S9-sequence-confirm.md")
        self.assertIn("先小范围试", s9)
        self.assertIn("停发只停后续", s9)

    def test_s10_says_no_partial_add(self):
        s10 = read("output-templates/S10-contacts-confirm.md")
        self.assertIn("只能整批加入", s10)

    def test_early_activation_is_not_executed(self):
        flow = read("specs/beginner-flow.md")
        self.assertIn("还没到发信那一步", flow)
        self.assertIn("不提前激活", flow)

    def test_s11_digit_reply_does_not_activate(self):
        s11 = read("output-templates/S11-completion-report.md")
        self.assertIn("也不会开开关", s11)
        self.assertIn("不等于激活", s11)


if __name__ == "__main__":
    unittest.main()
