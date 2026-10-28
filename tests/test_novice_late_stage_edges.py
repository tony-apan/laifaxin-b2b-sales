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
        self.assertIn("这一次只能整批加", s9)
        self.assertIn("想少加可直接说数量", s9)
        self.assertIn("重新选定完整批次", s9)

    def test_s10_says_no_partial_add(self):
        s10 = read("output-templates/S10-contacts-confirm.md")
        self.assertIn("只能整批加入", s10)

    def test_early_activation_is_not_executed(self):
        flow = read("specs/beginner-flow.md")
        self.assertIn("还没到发信那一步", flow)
        self.assertIn("不提前激活", flow)

    def test_s11_digit_reply_does_not_activate(self):
        s11 = read("output-templates/S11-completion-report.md")
        self.assertIn("也不会打开发信", s11)
        self.assertIn("完成不等于开始发", s11)

    def test_s0_profile_recommended_reply_passes_check_confirm_quote(self):
        # B2: S0 产品资料屏推荐回复词需包含确认词且能通过 check_confirm_quote。
        import sys
        sys.path.insert(0, str(ROOT / "tools"))
        from product_profile import check_confirm_quote

        s0 = read("output-templates/S0-product-profile.md")
        parts = s0.split("```text")
        self.assertGreater(len(parts), 1, "S0 必须含有 text 代码块")
        target_block = parts[1].split("```")[0]

        self.assertIn("回 1", target_block)
        self.assertIn("回 2", target_block)
        self.assertTrue(check_confirm_quote("1")[0])
        self.assertTrue(check_confirm_quote("没问题")[0])
        for quote in ("2", "12", "不确认", "确认吗？"):
            self.assertFalse(check_confirm_quote(quote)[0])

    def test_product_profile_user_block_has_no_website_asking(self):
        # B3 负向测试：保证档案屏用户块不含目标客户网址询问（延后至 S3 明确询问）。
        s0 = read("output-templates/S0-product-profile.md")
        parts = s0.split("```text")
        self.assertGreater(len(parts), 1, "S0 必须含有 text 代码块")
        target_block = parts[1].split("```")[0]

        for phrase in ("目标客户的网址", "买家官网", "有没有目标客户网址", "发我网址", "官网", "网址"):
            self.assertNotIn(phrase, target_block, f"档案屏用户块不得含有网址询问: {phrase}")


if __name__ == "__main__":
    unittest.main()
