#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""email-style 样式文件机器闸门回归（2026-10-23 三审H）。

锁死：旧开发信只能学结构与语气；价格/联系方式/认证/承诺等事实性内容
不得写进该样式文件，否则 gen_templates 在生成前 exit 2。
"""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

from email_style_gate import EMAIL_STYLE_NAME, check_email_style_file, check_email_style_text  # noqa: E402

GOOD = """# 邮件风格
- 称呼方式：Hi 名字
- 开场：一句关于使用场景的问题
- 段落结构：三段，先说问题再给方案
- CTA 写法：结尾问一句是否愿意进一步了解
- 签名形式：昵称一行
"""


class EmailStyleGateTest(unittest.TestCase):
    def test_good_style_passes(self):
        self.assertEqual([], check_email_style_text(GOOD))

    def test_missing_section_rejected(self):
        bad = GOOD.replace("- CTA 写法：结尾问一句是否愿意进一步了解\n", "")
        errs = check_email_style_text(bad)
        self.assertTrue(any("CTA" in e for e in errs), errs)

    def test_price_rejected(self):
        errs = check_email_style_text(GOOD + "\n价格：FOB USD 12.5/件")
        self.assertTrue(any("价格" in e for e in errs), errs)

    def test_email_rejected(self):
        errs = check_email_style_text(GOOD + "\n联系：sales@example.com")
        self.assertTrue(any("邮箱" in e for e in errs), errs)

    def test_phone_rejected(self):
        errs = check_email_style_text(GOOD + "\n电话：+86 138 0000 0000")
        self.assertTrue(any("电话" in e for e in errs), errs)

    def test_certification_rejected(self):
        errs = check_email_style_text(GOOD + "\n认证：ISO 9001")
        self.assertTrue(any("认证" in e for e in errs), errs)

    def test_file_missing_is_skipped(self):
        self.assertEqual([], check_email_style_file(Path("/nonexistent") / "product-profile.md"))

    def test_file_with_bad_content_rejected(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "product-profile.md"
            p.write_text("x", encoding="utf-8")
            (Path(d) / EMAIL_STYLE_NAME).write_text(GOOD + "\n价格：USD 9.9", encoding="utf-8")
            errs = check_email_style_file(p)
            self.assertTrue(errs)


if __name__ == "__main__":
    unittest.main()
