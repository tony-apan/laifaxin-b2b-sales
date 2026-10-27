"""锁定「逐模块逻辑 + 流程图」索引的存在与关键口径，防止以后被删/被改回旧口径。"""

import pathlib
import unittest


REPO = pathlib.Path(__file__).resolve().parents[1]
MERMAID = "mermaid"
STEP_MAP = REPO / "specs" / "step-map.md"


class StepMapTest(unittest.TestCase):
    def test_step_map_exists_with_mermaid_and_modules(self):
        self.assertTrue(STEP_MAP.is_file(), "缺少 specs/step-map.md")
        text = STEP_MAP.read_text(encoding="utf-8")
        self.assertIn(MERMAID, text)
        for module in ["M0", "M1", "M2", "M3", "M4", "M5", "M6", "M7", "M8", "M9", "M10", "M11", "M12"]:
            self.assertIn("### " + module, text, "缺模块: " + module)

    def test_70pct_scope_is_explicit(self):
        text = STEP_MAP.read_text(encoding="utf-8")
        self.assertIn("70% 只用于", text)
        self.assertIn("客群推演（S2）没有 70% 指标", text)
        self.assertIn("100 页 1 跳", text)
        self.assertIn("连续 3 页", text)
        self.assertIn("每页≥50%", text, "3 页窗口必须带单页下限，防回退到 5 页")

    def test_agents_points_to_step_map_and_has_mermaid(self):
        text = (REPO / "AGENTS.md").read_text(encoding="utf-8")
        self.assertIn("specs/step-map.md", text)
        self.assertIn(MERMAID, text)

    def test_100_page_jump_unified_in_rules_and_index(self):
        rules = (REPO / "RULES.md").read_text(encoding="utf-8")
        index = (REPO / "INDEX.md").read_text(encoding="utf-8")
        self.assertIn("100页跳", rules)
        self.assertNotIn("50页跳", rules)
        self.assertNotIn("50页跳", index)

    def test_user_facing_templates_have_no_mermaid(self):
        for p in sorted((REPO / "output-templates").glob("*.md")):
            self.assertNotIn(MERMAID, p.read_text(encoding="utf-8"),
                             "用户可见模板禁止出现 Mermaid: " + p.name)

class EntryOrderDiagramTest(unittest.TestCase):
    """2026-10-27 用户裁决：流程图入口=先连平台（复用已验证会话/专用浏览器），连上才问两样。"""

    def test_agents_mermaid_connect_before_questions(self):
        text = (REPO / "AGENTS.md").read_text(encoding="utf-8")
        self.assertNotIn("只问两样：昵称+产品", text, "第0屏不得再以先问昵称+产品开头")
        self.assertIn("复用已验证会话", text, "连接优先复用已验证会话")

    def test_step_map_m0_connects_first(self):
        text = STEP_MAP.read_text(encoding="utf-8")
        self.assertNotIn("→ 只问昵称+产品", text, "M0 动作不得再是只问昵称+产品")
        self.assertIn("先连平台", text, "M0/M1 顺序应为先连平台")


if __name__ == "__main__":
    unittest.main()
