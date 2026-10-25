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
        self.assertIn("连续 5 页", text)

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


if __name__ == "__main__":
    unittest.main()
