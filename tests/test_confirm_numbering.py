"""确认点一律回数字（2026-10-23 用户要求：只回数字就能继续）。

用户反馈：写模板等确认点让用户回「确认生成」太麻烦，要求统一成 1/2/3；
发信激活必须回「确认激活」四个字（防手滑，系统硬性要求）。
"""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

CONFIRM_TEMPLATES = (
    "S2-客群确认.md",
    "S5-保存确认.md",
    "S7-模板确认.md",
    "S9-序列确认.md",
    "S10-加联系人确认.md",
)

ACTIVATION_TEMPLATES = ("S11-完成汇报.md", "S12-激活确认.md")


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
                    r"回\s*\*\*1\*\*|回\s*1[^0-9]|回复编号|回复数字",
                    f"{name} 的话术块要让用户回数字（如「回 1」）",
                )

    def test_activation_templates_require_exact_phrase(self):
        for name in ACTIVATION_TEMPLATES:
            with self.subTest(template=name):
                block = _user_block(name)
                self.assertIn("确认激活", block, f"{name} 必须要求用户回「确认激活」")

    def test_beginner_flow_counts_replies(self):
        text = (ROOT / "specs" / "beginner-flow.md").read_text(encoding="utf-8")
        self.assertIn("你要回几次", text, "beginner-flow 要写清用户一共回几次")
        self.assertIn("回 **1**", text, "beginner-flow 要写明每步回 1 继续")
        self.assertIn("2 次", text, "beginner-flow 要写明真正需要拿主意的只有 2 次")


if __name__ == "__main__":
    unittest.main()
