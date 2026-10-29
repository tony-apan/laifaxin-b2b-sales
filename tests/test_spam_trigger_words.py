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
                       "平台安全拦截", "硬退信", "30%", "发信环境由平台统一负责", "只回 1、只回「好的」或只回「激活」都不开", "打开率", "退回去的还能再发吗", "截图发我", "回信在平台邮箱里", "顺延到下一个可发时点", "不等于过去一封没发", "数据指标严格区分", "20%–30%", "想排下一波跟我说一声", "还没发的不再发"):
            self.assertIn(needle, s12)


    def test_s12_activation_failure_states(self):
        s12 = (ROOT / "output-templates/S12-activation-confirm.md").read_text(encoding="utf-8")
        for needle in ("只说明此刻是关的", "不等于过去一封没发", "另查发送记录", "暂不能确认"):
            self.assertIn(needle, s12)

    def test_s12_delivery_bands_unified(self):
        s12 = (ROOT / "output-templates/S12-activation-confirm.md").read_text(encoding="utf-8")
        self.assertIn("20%–30% 先查内容、暂不停发", s12)
        self.assertIn("超过 30% 才停发并检查内容", s12)
        # 根据主控裁决，历史运营数值保留在 S12 说明内，当前建议行91已移除固定百分比触发动作
        self.assertGreaterEqual(s12.count("20%–30%"), 1)

    def test_30min_has_send_window_condition(self):
        s7 = (ROOT / "output-templates/S7-template-confirm.md").read_text(encoding="utf-8")
        s9 = (ROOT / "output-templates/S9-sequence-confirm.md").read_text(encoding="utf-8")
        self.assertIn("在允许发送窗口内", s7)
        self.assertIn("在允许发送窗口内", s9)

    def test_stoploss_uniform_in_entry_docs(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        faq = (ROOT / "wiki/faq.md").read_text(encoding="utf-8")
        self.assertNotIn("连续两轮不达标", readme)
        self.assertIn("1–2 个", readme)
        self.assertIn("连续两轮都是 0 个", readme)
        # 根据主控最终裁决，wiki/faq.md 已移除固定 48h 询盘数自动扩量止损硬门
        self.assertNotIn("连续两轮都是 0 个 → 才建议停止该项目止损", faq)
        self.assertNotIn("发出后 48 小时数有效询盘", faq)


if __name__ == "__main__":
    unittest.main()
