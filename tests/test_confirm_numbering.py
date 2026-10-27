"""确认点一律回数字（2026-10-23 用户要求：只回数字就能继续）。

用户反馈：写模板等确认点让用户回「确认生成」太麻烦，要求统一成 1/2/3；
发信激活必须回「确认激活」四个字（防手滑，系统硬性要求）。
"""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

CONFIRM_TEMPLATES = (
    "S2-segment-confirm.md",
    "S5-save-confirm.md",
    "S7-template-confirm.md",
    "S9-sequence-confirm.md",
    "S10-contacts-confirm.md",
)

ACTIVATION_TEMPLATES = ("S11-completion-report.md", "S12-activation-confirm.md")


def _user_block(name: str) -> str:
    text = (ROOT / "output-templates" / name).read_text(encoding="utf-8")
    m = re.search(r"```[a-z]*\n(.*?)```", text, re.S)
    return m.group(1) if m else ""


class ConfirmNumberingTest(unittest.TestCase):
    def test_confirm_templates_ask_for_number(self):
        for name in CONFIRM_TEMPLATES:
            with self.subTest(template=name):
                block = _user_block(name)
                self.assertTrue(block, f"{name} 没有用户话术块")
                self.assertRegex(
                    block,
                    r"回\s*\*\*1\*\*|回\s*1[^0-9]|回复编号|回复数字|确认保存|回一个编号",
                    f"{name} 的话术块要让用户回数字（如「回 1」）",
                )

    def test_s5_requires_count_after_confirm_phrase(self):
        block = _user_block("S5-save-confirm.md")
        self.assertIn("确认保存 前", block, "S5 必须写清「确认保存 前 <N> 家」")
        self.assertIn("2", block, "S5 必须保留「回 2」改数量选项")

    def test_activation_templates_require_exact_phrase(self):
        for name in ACTIVATION_TEMPLATES:
            with self.subTest(template=name):
                block = _user_block(name)
                self.assertIn("确认激活", block, f"{name} 必须要求用户回「确认激活」")

    def test_beginner_flow_counts_replies(self):
        text = (ROOT / "specs" / "beginner-flow.md").read_text(encoding="utf-8")
        self.assertIn("你要回几次", text, "beginner-flow 要写清用户一共回几次")
        self.assertIn("保存客户必须单独", (ROOT / "specs" / "novice-flow-contract.md").read_text(encoding="utf-8"))
        self.assertIn("建序列和加人已经并进", text)
        self.assertIn("确认激活", text)
        rules = (ROOT / "RULES.md").read_text(encoding="utf-8")
        self.assertIn("S9审批与S10审批+票据分别", rules)
        self.assertIn("10 次", text, "beginner-flow 要如实写清约 10 次回话")


if __name__ == "__main__":
    unittest.main()


class ConfirmQuoteRealWorldTest(unittest.TestCase):
    """2026-10-23 三审第7关 S0：确认口令过滤不得误杀真实产品名/正常说法。"""

    @classmethod
    def setUpClass(cls):
        import importlib.util
        spec = importlib.util.spec_from_file_location("_lfx_approval", ROOT / "tools" / "approval.py")
        cls.mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.mod)

    def test_product_name_with_bu_is_accepted(self):
        self.assertTrue(self.mod.confirm_quote_ok("确认激活 不锈钢-S04"))
        self.assertTrue(self.mod.confirm_quote_ok("确认激活 不锈钢-咖啡器具-12轮4封"))

    def test_considered_and_confirm_is_accepted(self):
        self.assertTrue(self.mod.confirm_quote_ok("我考虑清楚了，确认激活"))

    def test_real_negations_still_rejected(self):
        for bad in ("先不激活", "再考虑一下", "取消激活", "别激活", "还没确认", "确认激活吗？", "要不要激活"):
            with self.subTest(quote=bad):
                self.assertFalse(self.mod.confirm_quote_ok(bad), f"否定/疑问必须拒绝: {bad}")
