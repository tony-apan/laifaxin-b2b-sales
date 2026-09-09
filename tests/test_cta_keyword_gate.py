#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""CTA 回复关键词闸门测试：引导对方回一个短词，且该短词必须加粗。
背景：真实产物曾整批零加粗、无短关键词，而旧工具逻辑（`if bolds and ...` + `if m:`）静默放行。

gen_templates.py 在模块级解析 argparse，不能直接 import；
这里用源码内联加载「提取器 + 四要素闸门」相关定义，等价于执行真实代码。
"""
import re
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SOURCE = (ROOT / "tools" / "gen_templates.py").read_text(encoding="utf-8")


def _extract(pattern, flags=re.M | re.S):
    match = re.search(pattern, SOURCE, flags)
    if not match:
        raise AssertionError(f"无法从 gen_templates.py 提取代码块: {pattern[:60]}")
    return match.group(0)


def _load_namespace():
    """内联加载：正则常量 + _cta_keyword + check_four_elements（含其依赖常量）。"""
    ns = {"re": re, "sys": sys}
    for name in ("_CTA_MARK_RE", "_GENERIC_CTA_RE", "_ADVANTAGE_RE",
                 "_CTA_KW_QUOTED_RE", "_CTA_KW_BARE_RE", "_CTA_KW_STOPWORDS", "_YESNO_CTA_RE"):
        exec(_extract(rf"^{name} = .*?(?=\n\n|\n# |\ndef )"), ns)
    for func in ("_cta_keyword", "check_four_elements"):
        exec(_extract(rf"^def {func}\(.*?(?=\ndef |\n# ----------)"), ns)
    return ns


NS = _load_namespace()
_cta_keyword = NS["_cta_keyword"]
check_four_elements = NS["check_four_elements"]


class CtaKeywordExtractionTest(unittest.TestCase):
    def kw(self, text):
        return _cta_keyword(re.sub(r"<[^>]+>", "", text))

    def test_quoted_keyword_forms(self):
        for text in ('Reply "CATALOG" and I will send our lineup.',
                     'Reply "<b>CATALOG</b>" and I will send our lineup.',
                     'Reply <b>"CATALOG"</b> and I will send our lineup.',
                     'Just reply "DATA" and I will send the sheet.',
                     '回复「目录」并告诉我，我发您资料。'):
            with self.subTest(text=text):
                self.assertTrue(self.kw(text), f"应提取到短关键词: {text}")

    def test_bare_keyword_forms(self):
        self.assertEqual("YES", self.kw("Just reply YES and I will send it now."))
        self.assertEqual("CATALOG", self.kw("Reply CATALOG and I will send it."))

    def test_open_ended_asks_yield_no_keyword(self):
        """开放式要求（要对方回一大串信息）不是短词钩子——必须识别为「无关键词」。"""
        for text in ("Reply with your target cup sizes or preferred lid styles, and I will send our catalog.",
                     "If you would like to evaluate, reply with your delivery address and I will prepare a sample.",
                     "Reply to this message and I will share a video tour.",
                     "Reply and let me know your preferred colorway, and I will draft a proposal.",
                     "If you cater to specialty cafes, reply here and I will send our sizing matrix.",
                     "Should I send the spec sheet — yes or no is enough."):
            with self.subTest(text=text):
                self.assertEqual("", self.kw(text))


class FourElementsGateTest(unittest.TestCase):
    """直接调用生成器的四要素校验，验证闸门真的会拦（而不是静默放行）。"""

    GOOD_DIRECTION = ("Are your <b>packaging</b> SKUs locked in? We build <b>seam</b> construction here.")

    def run_gate(self, variants, directions=None):
        """返回 exit code；通过（未抛 SystemExit）返回 None。"""
        directions = directions or [
            [f"R{i:02d}", f"方向{i}", f"{i} packaging subject", self.GOOD_DIRECTION] for i in range(1, 13)
        ]
        NS["DIRECTIONS"] = directions
        NS["VARIANTS"] = variants
        with mock.patch("builtins.print"):
            try:
                check_four_elements()
            except SystemExit as exc:
                return exc.code
        return None

    def test_zero_bold_variant_is_rejected(self):
        """核心回归：0 处加粗的变体必须 exit 2（旧逻辑 `if bolds and ...` 放行）。"""
        self.assertEqual(2, self.run_gate(["Reply with your target sizes, and I will send our catalog."] * 10))

    def test_unbolded_keyword_is_rejected(self):
        self.assertEqual(2, self.run_gate(['Worth a look? Reply "CATALOG" and I will send our <b>MOQ</b> sheet.'] * 10))

    def test_missing_keyword_open_ended_is_rejected(self):
        self.assertEqual(2, self.run_gate(['Reply with your <b>target sizes</b> and I will send our <b>MOQ</b> sheet.'] * 10))

    def test_compliant_variant_passes(self):
        good = 'Worth a look? Reply "<b>CATALOG</b>" and I will send our <b>MOQ</b> sheet — no commitment.'
        self.assertIsNone(self.run_gate([good] * 10))

    def test_yes_or_no_cta_is_allowed(self):
        """sequence-config 正例 `— yes or no is enough`：无短词但买家知道回什么，应放行。"""
        good = 'Should I send the <b>seam</b> spec sheet for your <b>rental</b> fleet — yes or no is enough.'
        self.assertIsNone(self.run_gate([good] * 10))


if __name__ == "__main__":
    unittest.main()
