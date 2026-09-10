#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""注册/开通事实口径测试（2026-09-09 对抗审查）。

背景：对抗审查核对官网发现两处 P0——
  ① 仓库写"赠点约 2.3 万"，官网实际是「购买后到账 20,000 点（永久）+ 每月 3,000 点」，
     从未出现"2.3 万"这个数；
  ② 全仓库**没有"如何注册账号"的引导**——README 第 3 行就说"需要配合来发信平台使用"，
     但用户没账号时会卡在连接那一步。

本测试锁定：注册引导必须在位；过时数字不得复现；权益口径必须带"以平台实时为准"免责。
"""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# 会面向用户讲开通/费用的文件
USER_DOCS = (
    "README.md", "SKILL.md", "wiki/faq.md",
    "docs/09-mass-outreach-to-precision-follow-up.md",
    "output-templates/T-token引导.md",
)


def read(name):
    return (ROOT / name).read_text(encoding="utf-8")


class RegistrationGuidanceTest(unittest.TestCase):
    """注册引导必须在位（对抗审查 P0：全仓缺注册引导）。"""

    def test_readme_tells_user_how_to_register(self):
        text = read("README.md")
        self.assertIn("免费注册", text, "README 必须告诉用户怎么注册")
        self.assertIn("laifa.xin", text, "README 必须给出注册入口")
        self.assertRegex(text, r"还没有.{0,4}账号|没有账号", "README 应显式覆盖'还没账号'场景")

    def test_connect_card_covers_no_account(self):
        text = read("output-templates/T-token引导.md")
        self.assertIn("免费注册", text, "连接卡必须覆盖'没有账号'")
        self.assertIn("不代办注册", text, "AI 不得代办注册")

    def test_skill_routes_no_account_question(self):
        text = read("SKILL.md")
        self.assertIn("没有账号", text, "SKILL 触发词应含'没有账号'")
        self.assertIn("不代办注册", text, "SKILL 应写明 AI 不代办注册")

    def test_registration_is_free_no_prepay(self):
        for name in ("README.md", "output-templates/T-token引导.md"):
            with self.subTest(file=name):
                text = read(name)
                self.assertRegex(text, r"注册免费|不用先付费|无需先付费",
                                 f"{name} 应说明注册免费、无需先付费")


class StaleNumberTest(unittest.TestCase):
    """过时数字不得复现（对抗审查 P0：赠点 2.3 万与官网不符）。"""

    def test_no_stale_gift_points_number(self):
        for name in USER_DOCS:
            with self.subTest(file=name):
                text = read(name)
                self.assertNotRegex(text, r"2\.3\s*[万w]",
                                    f"{name} 仍出现过时的'2.3 万'赠点口径")

    def test_price_claims_carry_disclaimer(self):
        """任何价格/赠点声明必须带'以平台实时为准'类免责。"""
        for name in ("README.md", "wiki/faq.md", "docs/09-mass-outreach-to-precision-follow-up.md"):
            with self.subTest(file=name):
                text = read(name)
                if re.search(r"399|999|赠点|套餐", text):
                    self.assertRegex(text, r"实时为准|以平台.*为准|客服.*确认|随时可能调整|不替平台承诺",
                                     f"{name} 价格/赠点声明缺免责口径")

    def test_official_price_facts_match_website(self):
        """若写具体价格，须与官网一致（年费原价 999、券后 399）。"""
        text = read("README.md")
        if "999" in text:
            self.assertIn("399", text, "写原价 999 时应同时给出券后 399 的对照")
        # 不得把月费/加油包等写成主推套餐（当前主推是年费）
        self.assertNotRegex(text, r"主推.{0,6}月费", "README 不应把月费写成主推")


class PointsRuleConsistencyTest(unittest.TestCase):
    """点数消耗口径须与官网一致（有效 2 点/未知 1 点）。"""

    def test_save_points_rule(self):
        text = read("wiki/faq.md")
        self.assertRegex(text, r"有效.{0,4}2\s*点", "FAQ 应写有效邮箱 2 点/个")
        self.assertRegex(text, r"未知.{0,4}1\s*点", "FAQ 应写未知邮箱 1 点/个")

    def test_registration_grant_not_overstated(self):
        """注册赠送点数不得夸大到 9100（官网明确 9,100 是'等值总权益'，不是全部立即到账）。"""
        for name in USER_DOCS:
            with self.subTest(file=name):
                text = read(name)
                if "9,100" in text or "9100" in text:
                    self.assertRegex(text, r"等值|不是全部|分批|逐步",
                                     f"{name} 写 9100 时必须说明是'等值总权益'而非一次性到账")


class TaskMenuFormatTest(unittest.TestCase):
    """任务菜单格式（2026-09-10 用户拍板）：逐行 + emoji 突出 + 标 ⭐推荐。"""

    def setUp(self):
        self.path = ROOT / "output-templates" / "S0-任务菜单.md"

    def test_menu_template_exists(self):
        self.assertTrue(self.path.is_file(), "缺任务菜单展示模板")

    def test_menu_items_are_line_separated_with_emoji(self):
        text = self.path.read_text(encoding="utf-8")
        blocks = re.findall(r"```[a-zA-Z]*\n(.*?)```", text, re.S)
        self.assertTrue(blocks, "菜单模板缺代码块")
        # ★两个代码块（有旧项目 / 无旧项目）都要逐行+emoji
        for bi, block in enumerate(blocks, 1):
            self._check_block(block, bi)

    def _check_block(self, block, bi):
        # ★项数铁律(2026-09-10)：只列 4 项，上限 5（防选择困难）
        lines = [l for l in block.splitlines() if re.match(r"\s*[1-9]\.\s", l)]
        self.assertEqual(4, len(lines), f"菜单应为 4 行独立项（用户反馈6项太多），实际 {len(lines)} 行")
        self.assertLessEqual(len(lines), 5, f"菜单项数超过上限 5: {len(lines)}")
        # ★禁止一行塞多项：任一菜单行里不得再出现 "数字. " 的第二项
        for line in lines:
            with self.subTest(compressed=line.strip()[:40]):
                inline = re.findall(r"[1-6]\.\s*★?[\w\u4e00-\u9fff]", line)
                self.assertLessEqual(len(inline), 1,
                                     f"菜单行疑似压了多项（应逐行独立）: {line.strip()[:60]}")
        emoji_re = re.compile("[\U0001F300-\U0001FAFF\u2600-\u27BF]")
        for line in lines:
            with self.subTest(line=line.strip()[:30]):
                self.assertRegex(line, emoji_re, f"菜单项缺 emoji 突出: {line.strip()[:40]}")

    def test_menu_is_state_aware_and_hides_irrelevant(self):
        """★按状态裁剪：两个菜单（有/无旧项目）各自给 4 项；不得含「更新/换机」。"""
        blocks = re.findall(r"```[a-zA-Z]*\n(.*?)```", self.path.read_text(encoding="utf-8"), re.S)
        self.assertEqual(2, len(blocks), "应分别给出「有旧项目」「无旧项目」两个菜单")
        with_proj, without_proj = blocks
        # 有旧项目 → 必须出现"继续"；无旧项目 → 不得出现"继续"（列"（无）"是噪音）
        self.assertIn("继续", with_proj, "有旧项目菜单应含「继续项目」")
        self.assertNotIn("继续", without_proj, "无旧项目菜单不应出现「继续项目」")
        # 两份都不得把"更新/换机"当菜单项（刚装完无关；用户主动说才走路由）
        for name, block in (("有旧项目", with_proj), ("无旧项目", without_proj)):
            with self.subTest(menu=name):
                self.assertNotIn("更新系统", block, f"{name}菜单不应含「更新系统」")

    def test_menu_marks_recommendation(self):
        text = self.path.read_text(encoding="utf-8")
        self.assertIn("⭐推荐", text, "菜单必须标注推荐项")
        self.assertIn("无旧项目", text, "应区分有无旧项目的推荐")
        self.assertIn("有旧项目", text)

    def test_menu_forbids_inline_compression(self):
        text = self.path.read_text(encoding="utf-8")
        self.assertRegex(text, r"禁止.*①②③|违例", "模板应写明禁止压成①②③一行")

    def test_onboard_check_requires_emoji_and_recommendation(self):
        source = (ROOT / "tools" / "onboard_check.py").read_text(encoding="utf-8")
        self.assertIn("emoji 突出", source, "onboard_check 输出应要求 emoji 突出")
        self.assertIn("⭐推荐", source, "onboard_check 输出应含推荐标记")
        self.assertIn("禁止压成", source, "onboard_check 应禁止压成一行")
        self.assertIn("只列 4 项", source, "onboard_check 应写明项数上限")

    def test_rules_carry_menu_format_rule(self):
        text = (ROOT / "RULES.md").read_text(encoding="utf-8")
        self.assertRegex(text, r"菜单.*逐行|逐行.*emoji", "RULES 应含菜单格式纪律")
        self.assertIn("①②③", text, "RULES 应点名禁止的写法")

    def test_menu_template_distinguishes_chat_vs_email_emoji(self):
        """聊天鼓励 emoji，邮件禁 emoji——模板必须说明两者不混用。"""
        text = self.path.read_text(encoding="utf-8")
        self.assertIn("sequence-config", text)
        self.assertRegex(text, r"聊天.*emoji|emoji.*聊天", "应区分聊天与邮件的 emoji 规则")


if __name__ == "__main__":
    unittest.main()


class BeginnerFriendlyReportTest(unittest.TestCase):
    """小白适配（2026-09-10 对抗审查）：安装后先白话汇报，禁抛内部术语。"""

    def setUp(self):
        self.path = ROOT / "output-templates" / "S0-安装完成汇报.md"
        self.text = self.path.read_text(encoding="utf-8") if self.path.is_file() else ""

    def test_report_template_exists(self):
        self.assertTrue(self.path.is_file(), "缺安装完成汇报模板（小白看不懂 onboard 原始输出）")

    def test_report_has_plain_language_and_no_jargon_in_user_block(self):
        blocks = re.findall(r"```[a-zA-Z]*\n(.*?)```", self.text, re.S)
        self.assertTrue(blocks, "汇报模板缺用户话术块")
        # 用户话术块内禁止内部术语
        banned = ("S0", "S10", "S12", ".py", ".local/", "runs/", "status=", "contact_add")
        for bi, block in enumerate(blocks, 1):
            for term in banned:
                with self.subTest(block=bi, term=term):
                    self.assertNotIn(term, block, f"汇报话术块出现内部术语「{term}」")

    def test_report_covers_four_things(self):
        text = self.text
        for need in ("装好了", "能帮", "确认", "项目"):
            with self.subTest(need=need):
                self.assertIn(need, text, f"汇报模板应覆盖: {need}")

    def test_report_has_status_plain_mapping(self):
        """必须有 S0-S12 → 白话 对照表（防 AI 对用户抛 S10）。"""
        for code in ("S1", "S4", "S10", "S12", "ERROR_BLOCKED"):
            with self.subTest(code=code):
                self.assertIn(code, self.text, f"白话对照表缺 {code}")

    def test_report_emphasizes_nothing_sends_without_confirm(self):
        self.assertIn("不会发", self.text.replace("一封都不会发", "不会发"),
                      "汇报必须强调'不确认就不发信'")


class PlainStepMappingTest(unittest.TestCase):
    """onboard_check 必须内置状态码→白话映射。"""

    def setUp(self):
        self.source = (ROOT / "tools" / "onboard_check.py").read_text(encoding="utf-8")

    def test_plain_hint_exists_and_covers_key_nodes(self):
        import importlib.util, tempfile, shutil, subprocess, sys
        # 直接跑函数：白话映射必须真能翻译关键节点（防"表被清空但仍匹配键名"的假通过）
        script = (
            "import sys; sys.path.insert(0, 'tools')\n"
            "import onboard_check as oc\n"
            "for s in ('S1','S4','S10','S12','ERROR_BLOCKED'):\n"
            "    print(s, '=>', oc.plain_step_for(s))\n"
        )
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "repo"
            shutil.copytree(ROOT, repo, ignore=shutil.ignore_patterns(".git", "__pycache__", ".local", "runs"))
            out = subprocess.run([sys.executable, "-c", script], cwd=str(repo),
                                 capture_output=True, text=True, timeout=120)
        self.assertEqual(0, out.returncode, out.stderr[-400:])
        lines = dict(l.split(" => ", 1) for l in out.stdout.strip().splitlines() if " => " in l)
        # ★语义断言：白话必须真的描述那个阶段（防 fallback 兜底通过）
        expect = {
            "S1": "客户", "S4": "名单", "S10": "跟进计划",
            "S12": "发送", "ERROR_BLOCKED": "卡",
        }
        for node, keyword in expect.items():
            with self.subTest(node=node):
                self.assertIn(node, lines)
                self.assertNotEqual(node, lines[node].strip(), f"{node} 未翻译成白话")
                self.assertIn(keyword, lines[node],
                              f"{node} 的白话应含「{keyword}」，实际: {lines[node]}")

    def test_output_tells_ai_to_use_plain_form(self):
        self.assertIn("对用户说", self.source, "输出应提示 AI 用白话汇报")
        self.assertIn("勿抛状态码", self.source, "输出应明确禁止抛状态码")

    def test_jargon_stays_out_of_user_facing_text(self):
        """README 的安装指令不得再让 AI 汇报'安装目录和当前版本'这种技术项。"""
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn("S0-安装完成汇报", readme, "README 安装指令应指向白话汇报模板")
        self.assertNotIn("安装目录和当前版本", readme, "README 不应让 AI 汇报技术目录/版本")


class ReadmeMenuConsistencyTest(unittest.TestCase):
    """README 里的菜单说明必须与 S0-任务菜单.md 的 4 项一致（防两处不同步）。"""

    def test_readme_does_not_list_six_items(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        # 不得再出现旧的 6 项编号列表
        self.assertNotRegex(readme, r"1\. 开始一个新的获客项目；\s*2\. 判断产品是否适合批量冷邮件",
                            "README 仍含旧 6 项菜单（应与模板同步为 4 项）")

    def test_readme_mentions_four_options(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertRegex(readme, r"4 个选项|四项|4 项", "README 应说明是 4 个选项")


if __name__ == "__main__":
    unittest.main()


class ReleaseBookkeepingTest(unittest.TestCase):
    """发版记账一致性（2026-09-10 发现：CHANGELOG 漏了 v0.5.9~v0.5.19 共 11 个版本、
    knowledge 仓 SKILL 版本停在 0.5.17）。发版=三件事同步：SKILL 版本 / CHANGELOG 条目 / 两仓一致。"""

    def _skill_version(self):
        text = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        m = re.search(r"^version:\s*([0-9.]+)\s*$", text, re.M)
        self.assertIsNotNone(m, "SKILL.md frontmatter 缺 version")
        return m.group(1)

    def test_changelog_has_entry_for_current_version(self):
        ver = self._skill_version()
        changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
        # 注意 [ 必须转义（否则被当字符类）
        self.assertIn(f"## [v{ver}]", changelog,
                      f"CHANGELOG 缺当前版本 v{ver} 的条目——发版必须记 CHANGELOG")

    def test_no_version_gaps_in_recent_series(self):
        """v0.5.x 系列不得有缺口（补发/漏记都会在序列里留洞）。"""
        changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
        vers = sorted({int(m) for m in re.findall(r"^## \[v0\.5\.(\d+)\]", changelog, re.M)})
        self.assertTrue(vers, "CHANGELOG 缺 v0.5.x 条目")
        gaps = [v for v in range(min(vers), max(vers) + 1) if v not in vers]
        self.assertEqual([], gaps, f"CHANGELOG 的 v0.5.x 有缺口: {gaps}（漏记版本）")

    def test_no_duplicate_version_entries(self):
        changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
        vers = re.findall(r"^## \[(v[0-9.]+)\]", changelog, re.M)
        dupes = sorted({v for v in vers if vers.count(v) > 1})
        self.assertEqual([], dupes, f"CHANGELOG 有重复版本条目: {dupes}")

    def test_knowledge_repo_version_matches(self):
        """两仓 SKILL 版本必须一致（本次实测知识仓曾停在 0.5.17）。"""
        knowledge = ROOT.parent / "laifaxin-knowledge"
        if not knowledge.is_dir():
            self.skipTest("知识仓不在同级目录")
        kp = knowledge / "SKILL.md"
        if not kp.is_file():
            self.skipTest("知识仓无 SKILL.md")
        km = re.search(r"^version:\s*([0-9.]+)\s*$", kp.read_text(encoding="utf-8"), re.M)
        self.assertIsNotNone(km)
        self.assertEqual(self._skill_version(), km.group(1),
                         "两仓 SKILL 版本不一致——发版时漏同步其中一个仓库")
