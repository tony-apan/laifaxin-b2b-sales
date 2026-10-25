#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""垃圾邮件触发词与看数据话术回归（2026-10-23 用户要求）。"""
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class SpamTriggerDoctrineTest(unittest.TestCase):
    def test_sequence_config_has_spam_list_once(self):
        doc = (ROOT / "specs/sequence-config.md").read_text(encoding="utf-8")
        head = "★垃圾邮件触发词清单"
        self.assertEqual(1, doc.count(head), "清单重复插入或缺失")
        for word in ("free sample", "act now", "click here", "limited time", "!!!", "B 类 慎用"):
            self.assertIn(word, doc)

    def test_generator_wires_hard_ban(self):
        src = (ROOT / "tools/gen_templates.py").read_text(encoding="utf-8")
        self.assertEqual(1, src.count("SPAM_HARD_BAN = ["), "常量重复或缺失")
        self.assertIn("标题含垃圾邮件触发词", src)
        self.assertIn("垃圾邮件触发词「", src)
        self.assertIn("_norm_spam_text", src)

    def test_s7_tells_ai_to_avoid_spam_words(self):
        s7 = (ROOT / "output-templates/S7-template-confirm.md").read_text(encoding="utf-8")
        self.assertIn("避开垃圾词", s7)

    def test_s12_answers_delivery_questions(self):
        s12 = (ROOT / "output-templates/S12-activation-confirm.md").read_text(encoding="utf-8")
        for needle in ("用户看数据时最常问的 5 句", "对方说没收到", "不是垃圾邮件",
                       "20% 以内属正常波动", "30%", "发信环境由平台统一负责", "回 **1**/「好的」不会开", "打开率", "退回去的还能再发吗", "截图发我", "对方的回信会在平台邮箱里收到", "顺延到下一个可发送时点", "回读「没开」只说明现在已关", "数据会陆续更新", "20%–30% 之间", "想排下一波跟我说一声", "还没发的不会再发"):
            self.assertIn(needle, s12)


    def test_s12_activation_failure_states(self):
        s12 = (ROOT / "output-templates/S12-activation-confirm.md").read_text(encoding="utf-8")
        for needle in ("回读「没开」只说明现在已关", "另查发送记录", "暂不能确认"):
            self.assertIn(needle, s12)

    def test_s12_delivery_bands_unified(self):
        s12 = (ROOT / "output-templates/S12-activation-confirm.md").read_text(encoding="utf-8")
        self.assertIn("20%–30% 先查内容、暂不停发", s12)
        self.assertIn("超过 30% 才停发并检查内容", s12)
        self.assertGreaterEqual(s12.count("20%–30%"), 2)

    def test_30min_has_send_window_condition(self):
        s7 = (ROOT / "output-templates/S7-template-confirm.md").read_text(encoding="utf-8")
        s9 = (ROOT / "output-templates/S9-sequence-confirm.md").read_text(encoding="utf-8")
        self.assertIn("在允许发送窗口内", s7)
        self.assertIn("在允许发送窗口内", s9)

    def test_stoploss_uniform_in_entry_docs(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        faq = (ROOT / "wiki/faq.md").read_text(encoding="utf-8")
        for text in (readme, faq):
            self.assertNotIn("连续两轮不达标", text)
            self.assertIn("1–2 个", text)
            self.assertIn("连续两轮都是 0 个", text)


if __name__ == "__main__":
    unittest.main()
