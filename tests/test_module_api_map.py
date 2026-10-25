"""锁定逐模块 API 核验表与「文档=代码」口径，防止回退到旧说法。"""

import pathlib
import unittest


REPO = pathlib.Path(__file__).resolve().parents[1]
MAP = REPO / "specs" / "module-api-map.md"


class ModuleApiMapTest(unittest.TestCase):
    def test_map_exists_with_all_modules(self):
        self.assertTrue(MAP.is_file(), "缺少 specs/module-api-map.md")
        text = MAP.read_text(encoding="utf-8")
        for mod in ["M0", "M1", "M2", "M3", "M4", "M5", "M6", "M7", "M8", "M9", "M10", "M11", "M12"]:
            self.assertIn("| " + mod, text, "缺模块: " + mod)
        self.assertIn("门禁的真实分层", text)
        self.assertIn("差异清单", text)

    def test_ticket_layering_is_truthful(self):
        text = MAP.read_text(encoding="utf-8")
        self.assertIn("approval.py", text)
        self.assertIn("authorize_write", text)
        self.assertIn("contact_add_authorized.py", text)
        self.assertIn("仅 S10", text)

    def test_skill_no_stale_claims(self):
        skill = (REPO / "SKILL.md").read_text(encoding="utf-8")
        self.assertNotIn("v3.5", skill)
        self.assertIn("contact_add_authorized.py", skill)
        self.assertNotIn("模板/序列/激活必须持 `auth_guard` 票据", skill)

    def test_docs10_matches_code_layering(self):
        text = (REPO / "docs" / "10-execution-guardrails.md").read_text(encoding="utf-8")
        self.assertIn("按实际分层", text)
        self.assertIn("approval", text)

    def test_api_dictionary_no_placeholder(self):
        text = (REPO / "specs" / "api-dictionary.md").read_text(encoding="utf-8")
        self.assertNotIn("## 5. 待补", text)
        self.assertIn("sequences/contact-add", text)

    def test_tools_readme_lists_current_channel_and_version_check(self):
        text = (REPO / "tools" / "README.md").read_text(encoding="utf-8")
        self.assertIn("contact_add_authorized.py", text)
        self.assertIn("version_check.py", text)

    def test_no_stale_foid0_and_price_band(self):
        import re
        for rel in ["specs/api-dictionary.md", "specs/sequence-config.md", "specs/module-api-map.md"]:
            text = (REPO / rel).read_text(encoding="utf-8")
            self.assertNotIn("foid:\"0\"", text, rel + " 仍有 foid:\"0\"（应为自动分组id）")
        skill = (REPO / "SKILL.md").read_text(encoding="utf-8")
        self.assertNotIn("价格带可用于", skill)
        self.assertIn("价格/折扣", skill)

    def test_map_records_differences_d9_to_d20(self):
        text = MAP.read_text(encoding="utf-8")
        for n in range(1, 21):
            self.assertIn("| D" + str(n) + " |", text, "缺差异记录 D" + str(n))

    def test_map_endpoints_exist_in_tool_code(self):
        src = "".join(p.read_text(encoding="utf-8") for p in (REPO / "tools").glob("*.py"))
        for ep in ["refine/company-list", "refine/company-save", "sequences/contact-add",
                   "sequences/sequence-active", "mailbox/template-add", "domain/base-info"]:
            self.assertIn(ep, src, "代码里找不到端点: " + ep)


if __name__ == "__main__":
    unittest.main()
