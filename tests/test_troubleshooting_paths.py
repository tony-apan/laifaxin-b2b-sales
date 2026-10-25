import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]

class TroubleshootingPathTest(unittest.TestCase):
    """🆘 三个必答问题（2026-10-23 用户核验）：出错必须有固定查询路径。"""

    def test_readme_has_troubleshooting_entry(self):
        text = (ROOT / "README.md").read_text(encoding="utf-8")
        for kw in ("遇到问题先查这里", "wiki/faq.md", "specs/problems-and-fixes-2026-10-23.md",
                   "lessons/lessons-learned.md", "glossary/glossary.md",
                   "specs/environment-setup.md", "specs/migration-handoff.md", "开 Issue"):
            with self.subTest(kw=kw):
                self.assertIn(kw, text, f"README 排障入口缺少：{kw}")

    def test_skill_forces_self_check_before_asking_user(self):
        text = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("出错先自查", text)
        self.assertIn("wiki/faq.md", text)
        self.assertIn("problems-and-fixes-2026-10-23.md", text)
        self.assertIn("禁止让用户自己排查", text)

    def test_index_declares_fixed_troubleshooting_order(self):
        text = (ROOT / "INDEX.md").read_text(encoding="utf-8")
        self.assertIn("排障", text)
        self.assertIn("wiki/faq.md", text)
        self.assertIn("problems-and-fixes-2026-10-23.md", text)

    def test_troubleshooting_targets_exist(self):
        for rel in ("wiki/faq.md", "glossary/glossary.md", "lessons/lessons-learned.md",
                    "specs/problems-and-fixes-2026-10-23.md",
                    "specs/environment-setup.md", "specs/migration-handoff.md"):
            with self.subTest(path=rel):
                self.assertTrue((ROOT / rel).is_file(), f"排障路径指向不存在的文件：{rel}")

if __name__ == "__main__":
    unittest.main()
