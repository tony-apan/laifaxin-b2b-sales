#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""安装首屏口径（2026-10-23 用户裁决）：刚装好直接问昵称+产品，不出菜单、不要数字。"""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def read(rel):
    return (ROOT / rel).read_text(encoding="utf-8")


def blocks(text):
    return re.findall(r"```[a-zA-Z]*\n(.*?)```", text, re.S)


class InstallFirstScreenTest(unittest.TestCase):
    def test_install_report_new_user_connects_first_not_menu(self):
        text = read("output-templates/S0-install-report.md")
        new_user = text.split("## 话术（新用户", 1)[1].split("## 话术（老用户", 1)[0]
        self.assertIn("连接", new_user, "新用户第一业务动作必须是连接平台（2026-10-27 改序）")
        self.assertNotIn("怎么称呼您", new_user, "连接成功前不得先问昵称")
        self.assertNotIn("卖什么产品", new_user, "连接成功前不得先问产品")
        self.assertNotIn("回复数字", new_user, "新用户话术不得要求回数字")
        self.assertNotIn("开始新的获客项目", new_user, "新用户话术不得列出任务菜单")

    def test_task_menu_is_history_only(self):
        text = read("output-templates/S0-task-menu.md")
        self.assertIn("有旧项目", text)
        self.assertNotIn("## 无旧项目时", text, "新用户不应再看到任务菜单")

    def test_readme_says_connect_then_two_things(self):
        text = read("README.md")
        self.assertIn("先连上你的来发信账号", text, "README 应写清装完先连账号（2026-10-27 改序）")
        self.assertIn("再问你两样", text, "README 应写清连接成功后再问昵称+产品")
        self.assertNotIn("6. 最后只问我：“安装完成。你现在想做什么？”", text, "旧口径已废弃")

    def test_rules_and_skill_share_new_rule(self):
        for name in ("RULES.md", "SKILL.md"):
            text = read(name)
            with self.subTest(file=name):
                self.assertIn("不展示菜单", text, f"{name} 应写清新用户不展示菜单")
                self.assertIn("昵称 + 产品", text, f"{name} 应写清只问昵称+产品")

    def test_onboard_check_no_menu_for_new_users(self):
        source = read("tools/onboard_check.py")
        self.assertRegex(source, r"本次未检测到旧项目.*?不展示菜单", "onboard_check 新用户分支不得输出菜单")
        self.assertIn("S0-opening-questions.md C1 只问两样", source)

    def test_opening_gate_contract(self):
        import sys
        sys.path.insert(0, str(ROOT / "tools"))
        import opening_gate
        decision = opening_gate.decide_opening([])
        self.assertEqual("new", decision["mode"])
        self.assertEqual(["昵称", "产品"], decision["ask"])
        self.assertEqual([], decision["options"])


class EntryOrderConnectFirstTest(unittest.TestCase):
    """入口顺序（2026-10-27 用户裁决）：先连平台，连接成功后才问昵称+产品。"""

    def test_install_report_new_user_leads_with_connect_not_two_questions(self):
        text = read("output-templates/S0-install-report.md")
        new_user = text.split("## 话术（新用户", 1)[1].split("## 话术（老用户", 1)[0]
        self.assertNotIn("怎么称呼您", new_user, "连接成功前不得先问昵称")
        self.assertNotIn("卖什么产品", new_user, "连接成功前不得先问产品")
        self.assertIn("连接", new_user, "新用户第一业务动作应是连接平台")

    def test_onboard_check_new_user_branch_says_connect_first(self):
        source = read("tools/onboard_check.py")
        self.assertRegex(source, r"连接成功前.{0,12}不问昵称",
                         "onboard 新用户分支应写明先连账号、连上才问两样")


class ActiveNavSopEntryOrderTest(unittest.TestCase):
    """R2（2026-10-27）：现役导航/SOP 不得宣传旧序「先昵称产品/档案之后才连接」，也不得把一键复制当默认。"""

    FILES = ("output-templates/README.md", "specs/operator-profile-sop.md", "specs/operations-sop.md",
             "specs/node-playbook.md", "methodology/decision-trees.md")
    OLD = ("安装完成·先问两样", "档案确认后·唯一需用户动手", "开局只问纯个人昵称", "不要催 token",
           "产品档案确认后，**先**按", "再收昵称+一句话产品", "禁止开局催 token 或列清单", "首次平台调用前再验证token")

    def test_no_old_order_phrases(self):
        for rel in self.FILES:
            text = read(rel)
            for bad in self.OLD:
                with self.subTest(file=rel, phrase=bad):
                    self.assertNotIn(bad, text, f"{rel} 仍写旧序：{bad}")

    def test_new_order_stated(self):
        for rel in self.FILES:
            text = read(rel)
            with self.subTest(file=rel):
                self.assertRegex(text, r"连接成功(前|后|之后).{0,30}(昵称|产品)|先连平台|先连接", f"{rel} 缺新序（先连平台→成功后问昵称产品）")

    def test_token_guide_index_not_one_click_default(self):
        text = read("output-templates/README.md")
        row = [l for l in text.splitlines() if "T-token-guide.md" in l][0]
        self.assertNotIn("浏览器一键复制的两行整段", row, "索引不得再把一键复制当默认")
        self.assertRegex(row, r"已验证会话|专用浏览器", "索引应写已验证会话/专用浏览器优先")
        self.assertIn("兜底", row, "人工复制仅环境失败兜底")


import io


def _skill_diagram():
    m = re.search(r"```mermaid\n(flowchart TD.*?)```", read("SKILL.md"), re.S)
    return m.group(1) if m else ""


def _diagram_edges(diagram):
    edges = []
    for m in re.finditer(r'([A-Za-z][A-Za-z0-9_]*)\s*(?:--\s*"([^"]*)"\s*-->|--)\s*>?\s*([A-Za-z][A-Za-z0-9_]*)', diagram):
        edges.append((m.group(1), m.group(3), m.group(2) or ""))
    return edges


def _readme_table_rows():
    out = []
    for i, line in enumerate(read("output-templates/README.md").splitlines()):
        if line.startswith("|") and ".md" in line and "](" in line:
            out.append((i, line))
    return out


class SkillDiagramTrueOrderTest(unittest.TestCase):
    """守卫收口（2026-10-27）：真箭头拓扑 + 真表行顺序 + 变异自检。"""

    def test_backbone_edges_T_N_S0(self):
        edges = _diagram_edges(_skill_diagram())
        self.assertIn(("T", "N", "通过"), edges)
        self.assertIn(("N", "S0", ""), edges)
        self.assertIn(("T", "TF", "失败"), edges)
        self.assertIn(("TF", "T", ""), edges)
        self.assertNotIn(("T", "N", "失败"), edges)
        self.assertNotIn(("S0A", "T", ""), edges)

    def test_T_node_no_after_profile_wording(self):
        d = _skill_diagram()
        tdef = re.search(r'T\["连接平台.*?"\]', d, re.S).group(0)
        self.assertNotIn("档案确认后", tdef)

    def test_S1_row_reuses_verified_session_no_reconnect(self):
        row = [l for l in read("SKILL.md").splitlines() if l.startswith("| S1 PATH_PENDING")][0]
        self.assertIn("此前连接已验证", row)
        self.assertIn("不再次连平台", row)
        self.assertIn("不重复问昵称", row)
        self.assertNotIn("档案确认后先按", row)
        self.assertNotIn("档案确认后立即", row)

    def test_template_readme_table_row_order(self):
        rows = _readme_table_rows()
        idx = {kw: min((i for i, l in rows if kw in l), default=10**9) for kw in
               ("T-token-guide.md", "S0-connect-success.md", "S0-opening-questions.md")}
        self.assertLess(idx["T-token-guide.md"], idx["S0-opening-questions.md"])
        self.assertLess(idx["S0-connect-success.md"], idx["S0-opening-questions.md"])

    def _run_self_on(self, skill_text, readme_text):
        real_read = globals()["read"]
        def fake_read(rel):
            if rel == "SKILL.md": return skill_text
            if rel == "output-templates/README.md": return readme_text
            return real_read(rel)
        globals()["read"] = fake_read
        try:
            suite = unittest.defaultTestLoader.loadTestsFromTestCase(type(self))
            suite._tests = [x for x in suite._tests if x._testMethodName in
                            ("test_backbone_edges_T_N_S0", "test_template_readme_table_row_order")]
            res = unittest.TextTestRunner(stream=io.StringIO(), verbosity=0).run(suite)
            return len(res.failures) + len(res.errors) > 0
        finally:
            globals()["read"] = real_read

    def test_mutation_self_check(self):
        skill = read("SKILL.md")
        readme = read("output-templates/README.md")
        cases = {
            "del_T_N": skill.replace('T -- "通过" --> N', ''),
            "reverse_T_N": skill.replace('T -- "通过" --> N', 'N -- "通过" --> T'),
            "fail_edge_to_N": skill.replace('T -- "失败" --> TF', 'T -- "失败" --> N'),
            "del_TF_back": skill.replace('    TF --> T', ''),
            "del_N_S0": skill.replace('N --> S0', 'N --> W'),
        }
        for name, txt in cases.items():
            with self.subTest(mut=name):
                self.assertTrue(self._run_self_on(txt, readme), f"变异 {name} 未触发守卫")
        lines = readme.splitlines()
        ti = next(i for i, l in enumerate(lines) if l.startswith("|") and "T-token-guide.md" in l)
        trow = lines.pop(ti)
        ci = next(i for i, l in enumerate(lines) if l.startswith("|") and "S0-opening-questions.md" in l)
        lines.insert(ci + 1, trow)
        fake = "\n".join(lines).replace("## 模板索引", "## 模板索引\n（先看 T-token-guide.md 与 S0-connect-success.md）", 1)
        with self.subTest(mut="readme_fake_prose_bad_table"):
            self.assertTrue(self._run_self_on(skill, fake), "README 正文伪提及不能替代真实表行顺序")


if __name__ == "__main__":
    unittest.main()