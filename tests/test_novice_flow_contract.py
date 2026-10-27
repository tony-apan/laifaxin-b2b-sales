#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""新手流程契约测试（specs/novice-flow-contract.md v1.0）。

锁死：第 0 屏单一真源、第 1 屏诚实报价与连平台、所有阶段卡三行进度、
回复点唯一、旧口径（只回数字/2 次/3 类/A-B-C 方向）不得回潮。
"""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TEMPLATES = ROOT / "output-templates"

STAGE_CARDS = (
    "S0-product-profile.md", "S2-segment-confirm.md", "S4-audit-running.md",
    "S5-save-confirm.md",
    "S6-count-report.md", "S7-template-confirm.md", "S8-template-building.md", "S9-sequence-confirm.md",
    "S10-contacts-confirm.md", "S11-completion-report.md", "S12-activation-confirm.md",
)


def _blocks(name):
    text = (TEMPLATES / name).read_text(encoding="utf-8")
    return re.findall(r"```[a-zA-Z]*\n(.*?)```", text, re.S)


class InstallScreenSingleSourceTest(unittest.TestCase):
    def test_first_screen_is_byte_identical(self):
        flow = (ROOT / "specs" / "beginner-flow.md").read_text(encoding="utf-8")
        m = re.search(r"### 第 0 屏.*?```[a-z]*\n(.*?)```", flow, re.S)
        self.assertIsNotNone(m, "beginner-flow 缺第 0 屏代码块")
        install = (TEMPLATES / "S0-install-report.md").read_text(encoding="utf-8")
        blocks = re.findall(r"```[a-zA-Z]*\n(.*?)```", install, re.S)
        self.assertTrue(blocks, "安装汇报卡没有话术块")
        self.assertEqual(blocks[0].strip(), m.group(1).strip(),
                         "第 0 屏必须与 S0-install-report.md 逐字一致（单一真源）")

    def test_first_screen_no_menu_or_number(self):
        block = _blocks("S0-install-report.md")[0]
        for banned in ("任务菜单", "只回一个数字", "开始新的获客项目", "6 步"):
            self.assertNotIn(banned, block, f"第 0 屏不该出现「{banned}」")
        # 2026-10-27 改序：第 0 屏只连接，连接成功前不得问昵称/产品（留给 C1）
        for banned in ("怎么称呼您", "卖什么产品", "一条消息回两样"):
            self.assertNotIn(banned, block, f"第 0 屏连接成功前不得先问「{banned}」")
        for must in ("装好了", "连接", "确认激活", "有人回复不会自动停",
                     "不用装任何东西", "平台额度", "不搜索", "不扣点"):
            self.assertIn(must, block, f"第 0 屏缺少「{must}」")


class InstallScreenShortAndBranchTest(unittest.TestCase):
    """2026-10-27 二次裁决：第 0 屏压到 ≤6 行，并按本机状态分 A/B/C/D 四支。"""

    def setUp(self):
        self.block = _blocks("S0-install-report.md")[0]

    def test_screen_is_short_and_uses_list_markers(self):
        lines = [l for l in self.block.strip().splitlines() if l.strip()]
        self.assertLessEqual(len(lines), 8,
                             "第 0 屏超过 8 行（新用户会懵）：%d 行" % len(lines))
        # Markdown 会把「单个换行」渲染成空格：连续正文行在真实界面里会糊成一段。
        # 所以要点必须用 • 起行（渲染器一定逐行显示），数量 ≥4。
        bullets = [l for l in lines if l.startswith("• ")]
        self.assertGreaterEqual(
            len(bullets), 4,
            "第 0 屏要点必须用 • 起行（否则 Markdown 软换行会糊成一段）：%r" % bullets)
        for line in lines:
            self.assertLessEqual(len(line), 46, "第 0 屏单行过长（%d 字）：%s" % (len(line), line))

    def test_screen_offers_exactly_two_options(self):
        self.assertIn("回 1", self.block, "第 0 屏必须给回 1")
        self.assertIn("回 2", self.block, "第 0 屏必须给回 2（手动办法兜底）")
        self.assertNotIn("回 3", self.block, "一屏最多两个选项")

    def test_branch_table_covers_four_branches(self):
        card = (TEMPLATES / "S0-install-report.md").read_text(encoding="utf-8")
        rows = [l for l in card.splitlines() if l.startswith("| **")]
        self.assertEqual(4, len(rows), "分支对照表应正好 4 行（A/B/C/D）：%r" % rows)
        for tag, row in zip(("**A ", "**B ", "**C ", "**D "), rows):
            self.assertIn(tag, row, "分支对照表第 %s 行标签不对" % tag)
            self.assertIn("回 1", row, "分支 %s 没给回 1" % tag)

    def test_flow_chart_covers_four_branches(self):
        flow = (ROOT / "specs" / "beginner-flow.md").read_text(encoding="utf-8")
        self.assertIn("第 0 屏分流图", flow, "beginner-flow 缺分流图")
        self.assertIn("flowchart TD", flow, "分流图不是 mermaid flowchart")
        for node in ("分支A", "分支B", "分支C", "分支D"):
            self.assertIn(node, flow, "流程图缺 %s" % node)

    def test_detection_commands_documented(self):
        flow = (ROOT / "specs" / "beginner-flow.md").read_text(encoding="utf-8")
        for cmd in ("onboard_check.py", "check_login.py", "browser_login.py --probe-only"):
            self.assertIn(cmd, flow, "检测项缺 %s" % cmd)


class Step1HonestQuoteTest(unittest.TestCase):
    def setUp(self):
        flow = (ROOT / "specs" / "beginner-flow.md").read_text(encoding="utf-8")
        m = re.search(r"### 第 1 屏.*?```[a-z]*\n(.*?)```", flow, re.S)
        self.assertIsNotNone(m, "beginner-flow 缺第 1 屏代码块")
        self.block = m.group(1)

    def test_connection_is_announced_before_step_one(self):
        # 2026-10-27 改序：连接在第 0 屏已完成，第 1 屏只确认「账号已连好」，不再重复约连接
        self.assertIn("账号刚才已经连好", self.block)
        self.assertIn("2 分钟", self.block)
        self.assertNotIn("连您的来发信账号", self.block, "连接已前移，第 1 屏不得再约连接")

    def test_honest_reply_count(self):
        self.assertIn("还要回 8 次", self.block)
        self.assertIn("顺利的话", self.block)
        self.assertNotIn("最多 9 次不动", self.block)
        for banned in ("只回一个数字", "全程你只需要回数字", "3 类"):
            self.assertNotIn(banned, self.block, f"第 1 屏不得再承诺「{banned}」")

    def test_s11_does_not_ask_activation_twice(self):
        block = _blocks("S11-completion-report.md")[0]
        self.assertIn("该回什么：先不用回", block, "S11 不应二次索要激活原话；激活只在 S12 收一次")
        self.assertIn("确认激活", block, "S11 仍要说清最后一步靠「确认激活」")

    def test_ends_with_do_not_reply_yet(self):
        lines = [l for l in self.block.strip().splitlines() if l.strip()]
        self.assertTrue(lines[-1].startswith("该回什么："), "第 1 屏末行必须是「该回什么：…」")


class StageCardsHaveProgressHeaderTest(unittest.TestCase):
    def test_every_stage_card_starts_with_three_lines(self):
        for name in STAGE_CARDS:
            with self.subTest(card=name):
                block = _blocks(name)[0]
                first = [l for l in block.splitlines() if l.strip()][:4]
                head = "\n".join(first)
                self.assertIn("进度：", head, f"{name} 缺「进度：」")
                self.assertIn("现在：", head, f"{name} 缺「现在：」")
                self.assertTrue("等你回：" in head or "该回什么：" in head,
                                f"{name} 缺「等你回/该回什么」")

    def test_stage_card_ends_with_what_to_reply(self):
        for name in STAGE_CARDS:
            with self.subTest(card=name):
                block = _blocks(name)[0]
                self.assertIn("该回什么：", block, f"{name} 必须写「该回什么：…」")


class ReplyContractTest(unittest.TestCase):
    def test_s5_requires_save_count(self):
        block = _blocks("S5-save-confirm.md")[0]
        self.assertIn("确认保存", block)
        self.assertIn("确认保存 前", block, "S5 必须要求「确认保存 前 N 家」原话")
        self.assertIn("家", block)
        self.assertIn("**2**", block, "S5 必须保留「回 2 改数量」选项")

    def test_s9_single_reply_method(self):
        text = (TEMPLATES / "S9-sequence-confirm.md").read_text(encoding="utf-8")
        self.assertNotIn("确认建序列", text, "S9 不得再出现第二种回法")
        self.assertIn("回 **1**", text)

    def test_s2_no_direction_letters(self):
        block = _blocks("S2-segment-confirm.md")[0]
        self.assertNotIn("方向字母", block)
        self.assertNotIn("获客方向 <", block)

    def test_old_burden_phrases_gone(self):
        corpus = ""
        files = list((ROOT / "specs").glob("*.md")) + list(TEMPLATES.glob("*.md"))
        files += [ROOT / "README.md", ROOT / "SKILL.md", ROOT / "RULES.md"]
        for p in files:
            corpus += p.read_text(encoding="utf-8")
        for banned in ("真正拿主意只有", "全程你只需要回数字", "3 类买家候选"):
            self.assertNotIn(banned, corpus, f"旧口径回潮：{banned}")

    def test_contract_references_existing_cards(self):
        contract = (ROOT / "specs" / "novice-flow-contract.md").read_text(encoding="utf-8")
        for card in ("S0-fit-plan", "S3-seed-confirm", "S5-save-confirm", "S7-template-confirm",
                     "S9-sequence-confirm", "S10-contacts-confirm", "S12-activation-confirm"):
            self.assertIn(card, contract)
            self.assertTrue((TEMPLATES / f"{card}.md").is_file(), f"契约引用了不存在的卡：{card}")


if __name__ == "__main__":
    unittest.main()