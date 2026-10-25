"""文档引用回归（2026-10-23 元数据与引用治理）。

执行 tools/check_doc_links.py 的同一套核验：
1. Markdown 相对链接坏链 = 0；
2. 反引号里的 .md 路径坏引用 = 0；
3. 工具/测试代码中的 .md 文件名（排除运行档案与测试夹具）都能在仓库找到同名文件；
4. 每个目录都有 INDEX.md，且 INDEX.md 覆盖直接子项。
"""
import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
_MOD_PATH = ROOT / "tools" / "check_doc_links.py"
_spec = importlib.util.spec_from_file_location("check_doc_links", _MOD_PATH)
checker = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(checker)


class DocLinksTest(unittest.TestCase):
    def test_markdown_links_resolve(self):
        checked, skipped, bad = checker.check_markdown_links(ROOT)
        self.assertGreater(checked, 0, "没有扫描到 Markdown 链接")
        self.assertEqual([], bad, "Markdown 坏链：" + repr(bad))

    def test_backtick_md_paths_resolve(self):
        checked, skipped, bad = checker.check_backtick_paths(ROOT)
        self.assertGreater(checked, 0, "没有扫描到反引号 .md 路径")
        self.assertEqual([], bad, "反引号坏引用：" + repr(bad))

    def test_code_md_refs_exist(self):
        checked, skipped, bad = checker.check_code_md_refs(ROOT)
        self.assertGreater(checked, 0, "没有扫描到代码内 .md 文件名")
        self.assertEqual([], bad, "代码内缺失同名文件：" + repr(bad))

    def test_duplicate_headings_get_suffix_anchor(self):
        import tempfile
        from pathlib import Path as _P
        with tempfile.TemporaryDirectory() as td:
            root = _P(td)
            (root / "fixture-doc.md").write_text(
                "## 重复标题\n\n## 重复标题\n\n"
                "[one](#重复标题)\n[two](#重复标题-1)\n[bad](#重复标题-2)\n",
                encoding="utf-8",
            )
            checked, skipped, bad = checker.check_markdown_links(root)
            self.assertEqual(1, len(bad), bad)
            self.assertIn("重复标题-2", bad[0][2])

    def test_anchor_links_checked(self):
        import tempfile
        from pathlib import Path as _P
        with tempfile.TemporaryDirectory() as td:
            root = _P(td)
            (root / "fixture-target.md").write_text("# 标题\n\n## 快速开始\n", encoding="utf-8")
            (root / "fixture-doc.md").write_text("## 快速开始\n\n[same](#快速开始)\n[bad](#不存在)\n[cross](fixture-target.md#快速开始)\n", encoding="utf-8")
            checked, skipped, bad = checker.check_markdown_links(root)
            joined = " ".join(str(b[2]) for b in bad)
            self.assertIn("不存在", joined, "坏锚点必须报出")
            self.assertNotIn("快速开始", joined, "好锚点不能误报")

    def test_reference_style_links_checked(self):
        import tempfile
        from pathlib import Path as _P
        with tempfile.TemporaryDirectory() as td:
            root = _P(td)
            (root / "fixture-a.md").write_text("# a\n", encoding="utf-8")
            (root / "fixture-doc.md").write_text("[ok][good]\n[bad][missing]\n\n[good]: fixture-a.md\n[missing]: fixture-missing.md\n", encoding="utf-8")
            checked, skipped, bad = checker.check_markdown_links(root)
            joined = " ".join(str(b[2]) for b in bad)
            self.assertIn("fixture-missing.md", joined, "参考式坏链必须报出")
            self.assertNotIn("fixture-a.md", joined, "好的参考式链接不能误报")

    def test_link_checker_is_case_sensitive(self):
        """macOS 的 exists() 不区分大小写，检查器必须按真实文件名精确比对。"""
        import tempfile
        from pathlib import Path as _P
        with tempfile.TemporaryDirectory() as td:
            root = _P(td)
            (root / "sub").mkdir()
            (root / "sub" / "fixture-a.md").write_text("# a\n", encoding="utf-8")
            (root / "fixture-doc.md").write_text("[up](sub/fixture-A.MD)\n[ok](sub/fixture-a.md)\n", encoding="utf-8")
            checked, skipped, bad = checker.check_markdown_links(root)
            self.assertEqual([("fixture-doc.md", 1, "sub/fixture-A.MD")], bad, "大小写写错的链接必须报坏链")
            self.assertTrue(checker._exact_exists(root / "sub" / "fixture-a.md"))
            self.assertFalse(checker._exact_exists(root / "sub" / "fixture-A.md"))

    def test_link_checker_decodes_urlencoded(self):
        """URL 编码的合法链接（%2E 等）要能解析；编码后指向不存在文件仍报坏链。"""
        import tempfile
        from pathlib import Path as _P
        with tempfile.TemporaryDirectory() as td:
            root = _P(td)
            (root / "sub").mkdir()
            (root / "sub" / "fixture-a.md").write_text("# a\n", encoding="utf-8")
            (root / "fixture-doc.md").write_text("[enc](sub/fixture-a%2Emd)\n[bad](sub/missing%2Emd)\n", encoding="utf-8")
            checked, skipped, bad = checker.check_markdown_links(root)
            self.assertEqual([("fixture-doc.md", 2, "sub/missing%2Emd")], bad, "编码后的坏链必须报出")

    def test_every_directory_has_index(self):
        dirs, missing, cov = checker.check_index_coverage(ROOT)
        self.assertGreater(len(dirs), 10, "目录枚举异常")
        self.assertEqual([], missing, "缺 INDEX.md：" + repr(missing))
        self.assertEqual([], cov, "INDEX 未覆盖直接子项：" + repr(cov))


if __name__ == "__main__":
    unittest.main()
