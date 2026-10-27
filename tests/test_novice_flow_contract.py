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


class DemoResidualTest(unittest.TestCase):
    def test_demo_connection_before_profile_and_no_first_screen_bans(self):
        demo = (ROOT / "docs" / "14-novice-walkthrough-demo.md").read_text(encoding="utf-8")
        chart = demo.split("## 一、整条路", 1)[1].split("```", 2)[1]
        self.assertIn("先选连接方式", chart)
        self.assertIn("实际校验登录与工作空间", chart)
        self.assertIn("通过", chart)
        self.assertNotIn("只问昵称+产品", chart)
        section = demo.split("### 环节 0", 1)[1].split("### 紧接着", 1)[0]
        screen = re.search(r"```text\n(.*?)```", section, re.S).group(1)
        for banned in ("确认激活", "不会自动停", "额度", "怎么称呼", "主要卖什么"):
            self.assertNotIn(banned, screen)
        for required in ("回 1", "回 2", "登录", "两行"):
            self.assertIn(required, screen)
        table = demo.split("| 序 | 什么时候", 1)[1].split("---", 2)[-1]
        self.assertLess(table.index("第 0 屏连接"), table.index("连接校验通过后"))

    def test_demo_save_card_covers_three_ways_and_rejections(self):
        demo = (ROOT / "docs" / "14-novice-walkthrough-demo.md").read_text(encoding="utf-8")
        section = demo.split("### 环节 3", 1)[1].split("### 环节 4", 1)[0]
        for phrase in ("确认", "确认保存 前 2600 家", "2600", "空答", "精确等于", "N=1", "删除必须带家数", "任何纯数字无效"):
            self.assertIn(phrase, section)
        self.assertNotIn("只回「1」我不动手", section)


class AgentEntrySummaryTest(unittest.TestCase):
    def test_entry_node_preserves_graph_and_branch_choices(self):
        agents = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
        graph = re.search(r"```mermaid\n(.*?)```", agents, re.S).group(1)
        node = re.search(r'A\(\[安装完成\]\) --> B\["(.*?)"\]', graph).group(1)
        self.assertIn("B --> V{", graph)
        for phrase in ("找海外买家", "写开发信", "排跟进", "回 1", "回 2", "复用", "换账号", "自动连接", "两行"):
            self.assertIn(phrase, node)
        for banned in ("激活", "回复不会自动停", "额度", "不菜单", "不数字"):
            self.assertNotIn(banned, node)
        self.assertIn("有人回复不自动停", graph.split("B --> V", 1)[1])
        self.assertRegex(graph, r'V -- "通过" --> Q\["[^"\n]*昵称[^"\n]*产品[^"\n]*已提供[^"\n]*"\] --> R\["[^"\n]*登记开工必读[^"\n]*"\] --> G\{')
        self.assertRegex(graph, r'V -- "未通过" --> VF\{"[^"\n]*原因[^"\n]*"\}')
        self.assertRegex(graph, r'VF -- "契约允许重试且尚有次数" --> VR\["[^"\n]*"\] --> V')
        self.assertRegex(graph, r'VF -- "不可自动处理/需确认/未知/次数用尽" --> VS\(\["[^"\n]*停止[^"\n]*唯一下一步[^"\n]*"\]\)')
        self.assertNotRegex(graph, r'(?m)^\s*VS\s*--')
        self.assertNotRegex(graph, r'V -- "未通过"[^\n]*--> Q')
        self.assertRegex(graph, r'G -- "否" --> GX\["[^"\n]*"\] --> Q')
        self.assertRegex(graph, r'G -- "是" --> C\[')
        self.assertNotRegex(graph, r'G -- "否"[^\n]*--> B')

    def test_step_three_waits_for_choice_and_checks_session(self):
        agents = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
        step = re.search(r"(?m)^3\. (.*)$", agents).group(1)
        for phrase in ("只读探测", "S0-install-report.md", "回 1", "回 2", "用户选择", "实际校验", "连接成功前不问昵称和产品"):
            self.assertIn(phrase, step)
        self.assertLess(step.index("回 1"), step.index("用户选择"))
        self.assertLess(step.index("用户选择"), step.index("实际校验"))


    def test_other_entries_describe_branch_choice(self):
        skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        entry = next(line for line in skill.splitlines() if line.startswith("- **新用户第一业务动作"))
        for phrase in ("只读探测", "回 1", "回 2", "用户选择", "实际校验", "连接成功后"):
            self.assertIn(phrase, entry)
        self.assertNotIn("人工复制仅环境故障兜底", entry)
        self.assertLess(entry.index("回 1"), entry.index("用户选择"))
        start = (ROOT / "START-HERE.md").read_text(encoding="utf-8")
        choice = next(line for line in start.splitlines() if line.startswith("0. "))
        for phrase in ("回 1", "回 2", "检测分支", "继续", "换账号", "不扣点"):
            self.assertIn(phrase, choice)
        for banned in ("电脑开不了浏览器", "账户钥匙"):
            self.assertNotIn(banned, choice)


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
        for must in ("装好了", "我能帮您", "来发信", "回 1", "回 2"):
            self.assertIn(must, block, f"第 0 屏缺少「{must}」")
        # 2026-10-27 最新裁决：这三句不进第 0 屏；对用户也不说这些词
        for moved in ("确认激活", "有人回复不会自动停", "平台额度",
                      "您不用装任何东西", "环境", "参数", "手动"):
            self.assertNotIn(moved, block, f"第 0 屏不得再出现「{moved}」")
        card = (TEMPLATES / "S0-install-report.md").read_text(encoding="utf-8")
        for must in ("试着打开窗口", "两行登录信息", "⭐推荐"):
            self.assertIn(must, card, f"填完的分支表缺少「{must}」")


class InstallScreenShortAndBranchTest(unittest.TestCase):
    """2026-10-27 终裁：第 0 屏按本机状态分 A/B/C/D；真列表、最多 6 处加粗，上限 9 行。"""

    def setUp(self):
        self.block = _blocks("S0-install-report.md")[0]

    def test_screen_is_short_and_uses_list_markers(self):
        lines = [l for l in self.block.strip().splitlines() if l.strip()]
        self.assertLessEqual(len(lines), 9,
                             "第 0 屏超过 9 行（新用户会懵）：%d 行" % len(lines))
        bullets = [l for l in lines if l.startswith("- ")]
        self.assertGreaterEqual(
            len(bullets), 4,
            "第 0 屏要点必须用 - 真列表起行：%r" % bullets)
        self.assertFalse(any(l.startswith("• ") for l in lines),
                         "第 0 屏不得再用圆点 •")

    def _branch_rows(self):
        card = (TEMPLATES / "S0-install-report.md").read_text(encoding="utf-8")
        return [l for l in card.splitlines() if l.startswith("| **")]

    def _rendered(self, detect, reply1, reply2):
        """星标写在动作前；没有星标时冒号前不留空格。"""
        def opt(label, cell):
            star = ""
            action = cell.strip()
            if action.startswith("⭐推荐"):
                star = " ⭐推荐"
                action = action[len("⭐推荐"):].lstrip("：: ").strip()
            return "- **%s**%s：%s" % (label, star, action)

        lines = []
        for raw in self.block.splitlines():
            if raw.startswith("我查过了："):
                lines.append("我查过了：" + detect)
            elif raw.startswith("- **回 1**"):
                lines.append(opt("回 1", reply1))
            elif raw.startswith("- **回 2**"):
                lines.append(opt("回 2", reply2))
            else:
                lines.append(raw)
        return "\n".join(lines)

    def test_rendered_branches_fit_and_have_no_placeholders(self):
        """长度按填完四个分支后的用户屏计算，不能只量带尖括号的骨架。"""
        self.assertIn("<检测一句>", self.block)
        self.assertIn("<星或空>", self.block)
        self.assertIn("<动作1>", self.block)
        self.assertIn("<动作2>", self.block)
        rows = self._branch_rows()
        self.assertEqual(4, len(rows), "分支对照表应正好 4 行")
        for row in rows:
            cells = [c.strip() for c in row.strip("|").split("|")]
            detect, reply1, reply2 = cells[2], cells[3], cells[4]
            for cell in (detect, reply1, reply2):
                self.assertNotIn("<", cell, "模拟输出不得留尖括号：%s" % cell)
                self.assertNotIn(">", cell, "模拟输出不得留尖括号：%s" % cell)
            for action in (reply1, reply2):
                self.assertNotIn("回 1", action, "表里只放星标和动作：%s" % action)
                self.assertNotIn("回 2", action, "表里只放星标和动作：%s" % action)
            rendered = self._rendered(detect, reply1, reply2)
            self.assertNotIn("<", rendered, "渲染稿不得留尖括号：\n%s" % rendered)
            self.assertNotIn(">", rendered, "渲染稿不得留尖括号：\n%s" % rendered)
            self.assertEqual(1, rendered.count("**回 1**"), "回 1 被填重了：\n%s" % rendered)
            self.assertEqual(1, rendered.count("**回 2**"), "回 2 被填重了：\n%s" % rendered)
            self.assertEqual(1, rendered.count("⭐推荐"), "每套只推荐一行：\n%s" % rendered)
            for banned in ("您不用装任何东西", "确认激活", "有人回复不会自动停",
                           "平台额度", "环境", "参数", "手动"):
                self.assertNotIn(banned, rendered, "填完稿不得出现「%s」" % banned)
            lines = [l for l in rendered.strip().splitlines() if l.strip()]
            self.assertLessEqual(len(lines), 9, "渲染后超过 9 行：%s" % cells[0])
            for line in lines:
                self.assertLessEqual(
                    len(line), 46,
                    "渲染后单行过长（%d 字，%s）：%s" % (len(line), cells[0], line))

    def test_screen_offers_exactly_two_options(self):
        self.assertIn("回 1", self.block, "第 0 屏必须给回 1")
        self.assertIn("回 2", self.block, "第 0 屏必须给回 2")
        self.assertNotIn("回 3", self.block, "一屏最多两个选项")

    def test_bold_covers_six_focus_words(self):
        """加粗最多 6 处，且必须覆盖这 6 个重点。"""
        bolds = re.findall(r"\*\*([^*]+)\*\*", self.block)
        self.assertLessEqual(len(bolds), 6, "加粗超过 6 处：%r" % bolds)
        for word in ("装好了", "我能帮您", "回 1", "回 2"):
            self.assertIn(word, bolds, "必须加粗「%s」：%r" % (word, bolds))
        self.assertEqual(["装好了", "我能帮您", "回 1", "回 2"], bolds,
                         "加粗只许这四处：%r" % bolds)

    def test_reply_options_are_their_own_list_lines(self):
        lines = [l for l in self.block.strip().splitlines() if l.strip()]
        one = [l for l in lines if l.startswith("- **回 1**")]
        two = [l for l in lines if l.startswith("- **回 2**")]
        self.assertEqual(1, len(one), "「回 1」必须单独成一行真列表：%r" % lines)
        self.assertEqual(1, len(two), "「回 2」必须单独成一行真列表：%r" % lines)
        cue = [l for l in lines if "您选一个回复我" in l]
        self.assertEqual(1, len(cue), "「您选一个回复我」必须单独成行")
        self.assertLess(lines.index(cue[0]), lines.index(one[0]))
        self.assertLess(lines.index(one[0]), lines.index(two[0]))
        detect = [l for l in lines if l.startswith("我查过了")]
        self.assertEqual(1, len(detect), "检测句必须单独成行")
        self.assertNotIn("确认激活", self.block)
        self.assertNotIn("有人回复不会自动停", self.block)

    def test_branch_table_covers_four_branches(self):
        rows = self._branch_rows()
        self.assertEqual(4, len(rows), "分支对照表应正好 4 行（A/B/C/D）：%r" % rows)
        for tag, row in zip(("**A ", "**B ", "**C ", "**D "), rows):
            self.assertIn(tag, row, "分支对照表第 %s 行标签不对" % tag)
            cells = [c.strip() for c in row.strip("|").split("|")]
            self.assertGreaterEqual(len(cells), 5, "分支行要有检测句、回 1、回 2：%s" % row)
            for cell in cells[2:5]:
                self.assertNotIn("回 1", cell, "表里只放星标和动作：%s" % cell)
                self.assertNotIn("回 2", cell, "表里只放星标和动作：%s" % cell)
            stars = (cells[3].startswith("⭐推荐"), cells[4].startswith("⭐推荐"))
            self.assertEqual(1, sum(stars), "每支正好一颗星：%s" % row)
            if "**D " in row:
                self.assertTrue(stars[0], "D 支推荐必须仍是回 1：%s" % row)
                self.assertIn("再试着打开窗口", cells[3])
            if "**C " in row:
                self.assertTrue(stars[1], "C 支推荐在回 2：%s" % row)
                self.assertIn("不能自动连接", cells[2])
                self.assertIn("检查能否修好", cells[3])
                self.assertNotIn("直接连上", cells[3])

    def test_browser_presence_is_not_verified_capability(self):
        card = (TEMPLATES / "S0-install-report.md").read_text(encoding="utf-8")
        rows = {row.split("| ")[1].split(" ")[0]: [c.strip() for c in row.strip("|").split("|")]
                for row in self._branch_rows()}
        unknown = rows["**B"]
        unsupported = rows["**C"]
        # probe 返回 browsers 非空、can_auto=false、can_launch=false 时未试启动。
        probe = {"browsers": [{"name": "chrome"}], "can_auto": False, "can_launch": False}
        self.assertTrue(probe["browsers"])
        self.assertFalse(probe["can_auto"] or probe["can_launch"])
        self.assertIn("未全部验证", unknown[1])
        self.assertIn("还没试过", unknown[2])
        self.assertNotIn("不能自动连接", unknown[2])
        self.assertNotIn("可以", unknown[2])
        self.assertIn("已确认", unsupported[1])
        self.assertIn("不能自动连接", unsupported[2])
        self.assertIn("回 1 前不得为验证启动或安装", card)
        self.assertIn("用户说「登录好了」仅是通知", card)

    def test_flow_chart_covers_four_branches(self):
        flow = (ROOT / "specs" / "beginner-flow.md").read_text(encoding="utf-8")
        self.assertIn("第 0 屏分流图", flow, "beginner-flow 缺分流图")
        self.assertIn("flowchart TD", flow, "分流图不是 mermaid flowchart")
        for node in ("分支A", "分支B", "分支C", "分支D"):
            self.assertIn(node, flow, "流程图缺 %s" % node)
        chart = flow[flow.index("#### 第 0 屏分流图"):flow.index("#### 检测项")]
        self.assertIn("B2 -- 回 1 后打开窗口 --> W", chart)
        self.assertIn("B2 -- 回 2 贴两行 --> V", chart)
        self.assertIn("W --> V", chart)
        self.assertIn("V -- 通过 --> E", chart)
        self.assertNotIn("B2 --> E", chart)
        self.assertNotIn("W --> E", chart)
        for banned in ("手动", "环境", "参数"):
            self.assertNotIn(banned, chart, "分流图对用户的选项不得说「%s」" % banned)

    def test_detection_commands_documented(self):
        flow = (ROOT / "specs" / "beginner-flow.md").read_text(encoding="utf-8")
        for cmd in ("onboard_check.py", "check_login.py", "browser_login.py --probe-only"):
            self.assertIn(cmd, flow, "检测项缺 %s" % cmd)
        screen = re.search(r"### 第 0 屏.*?```[a-z]*\n(.*?)```", flow, re.S).group(1)
        for cmd in ("onboard_check.py", "check_login.py", "browser_login.py"):
            self.assertNotIn(cmd, screen, "命令不得进第 0 屏用户代码块")

    def test_install_failure_is_not_screen_zero(self):
        card = (TEMPLATES / "S0-install-report.md").read_text(encoding="utf-8")
        self.assertIn("## 话术（安装没通过", card)
        fail = card.split("## 话术（安装没通过", 1)[1].split("## ", 1)[0]
        blocks = re.findall(r"```[a-zA-Z]*\n(.*?)```", fail, re.S)
        self.assertTrue(blocks, "安装没通过缺用户话术块")
        block = blocks[0]
        for must in ("有个东西没装好", "不是您的问题", "确认能否安全处理"):
            self.assertIn(must, block, "安装没通过缺少「%s」" % must)
        self.assertNotIn("组件", block, "安装没通过不得对用户说「组件」")
        for banned in ("装好了", "回 1", "回 2", "环境", "参数", "手动"):
            self.assertNotIn(banned, block, "安装没通过不得出现「%s」" % banned)
        self.assertIn("非交互", fail)
        self.assertIn("复查失败", fail)
        self.assertIn("唯一下一步", fail)

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
        self.assertIn("确认激活", self.block, "确认激活必须留在第 1 屏")
        self.assertIn("有人回复不会自动停", self.block, "有人回复不会自动停必须留在第 1 屏")
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