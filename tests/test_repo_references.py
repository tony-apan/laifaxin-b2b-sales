"""仓库自洽性：文档引用的工具/模板必须真实存在（2026-10-23 新手实测暴露）。

新手实测发现：文档把 save_company_cli.py / auth_guard.py / step_gate.py /
contact_add_authorized.py 当成"现役工具"反复引用，但仓库里根本没有这些文件；
S0-opening-questions.md / S0-fit-notes.md 同样缺失。AI 照着文档跑会直接断。
本测试把"文档承诺 = 仓库事实"钉死。
"""
import py_compile
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TOOLS = ROOT / "tools"
TEMPLATES = ROOT / "output-templates"

TOOL_REF = re.compile(r"tools/([A-Za-z0-9_\-]+\.(?:py|sh|ps1))")
TPL_REF = re.compile(r"output-templates/([^\s`\")\]]+\.md)")


def _md_files():
    for p in ROOT.rglob("*.md"):
        if ".git" in p.parts:
            continue
        if p.name == "CHANGELOG.md":
            continue  # 历史记录允许提到已删除/未实现的文件
        yield p


class ReferencedFilesExistTest(unittest.TestCase):
    def test_referenced_tools_exist(self):
        have = {p.name for p in TOOLS.iterdir() if p.is_file()}
        missing = {}
        for p in _md_files():
            for name in TOOL_REF.findall(p.read_text(encoding="utf-8", errors="ignore")):
                if name not in have:
                    missing.setdefault(name, []).append(str(p.relative_to(ROOT)))
        self.assertEqual({}, missing, f"文档引用了不存在的工具：{missing}")

    def test_referenced_templates_exist(self):
        have = {p.name for p in TEMPLATES.glob("*.md")}
        missing = {}
        for p in _md_files():
            for name in TPL_REF.findall(p.read_text(encoding="utf-8", errors="ignore")):
                if "<" in name or "*" in name:
                    continue  # 形如 S<节点>-*.md 是用户数据文件模式，不是仓库模板
                if name not in have:
                    missing.setdefault(name, []).append(str(p.relative_to(ROOT)))
        self.assertEqual({}, missing, f"文档引用了不存在的模板：{missing}")

    def test_all_tools_compile(self):
        bad = []
        tmp = ROOT / ".pyc_check_tmp"
        for p in sorted(TOOLS.glob("*.py")):
            try:
                py_compile.compile(str(p), doraise=True, cfile=str(tmp))
            except py_compile.PyCompileError as exc:
                bad.append(f"{p.name}: {str(exc.msg)[:120]}")
        tmp.unlink(missing_ok=True)
        self.assertEqual([], bad, "工具脚本语法错误：" + "; ".join(bad))


class FirstScreenPlainLanguageTest(unittest.TestCase):
    """首屏 = 装好后第一段话（第 0 屏）：只问昵称+产品，不许要数字、不许出菜单。"""

    BANNED = ("客群", "划边界", "序列", "点数", "硬门", "审批凭证")

    def _blocks(self):
        text = (ROOT / "specs" / "beginner-flow.md").read_text(encoding="utf-8")
        m = re.search(r"## 一、开场两屏.*?(\Z|## 二、)", text, re.S)
        self.assertIsNotNone(m, "beginner-flow 缺少「开场两屏」小节")
        blocks = re.findall(r"```[a-z]*\n(.*?)```", m.group(0), re.S)
        self.assertEqual(2, len(blocks), "开场两屏应各有 1 个代码块（第 0 屏 / 第 1 屏）")
        return blocks

    def test_install_screen_asks_two_things_only(self):
        block = self._blocks()[0]
        for word in self.BANNED:
            self.assertNotIn(word, block, f"首屏出现黑话「{word}」")
        # 2026-10-27 改序：第 0 屏只连接，昵称/产品在连接成功后由 C1 询问
        for must in ("装好了", "连接", "确认激活"):
            self.assertIn(must, block, f"第 0 屏缺少「{must}」")
        for banned in ("怎么称呼您", "卖什么产品"):
            self.assertNotIn(banned, block, f"连接成功前第 0 屏不得先问「{banned}」")
        for banned in ("只回一个数字", "6 步", "开始新的获客项目"):
            self.assertNotIn(banned, block, f"第 0 屏不该出现「{banned}」（那是第 1 屏/旧菜单的内容）")
        lines = [l for l in block.splitlines() if l.strip()]
        self.assertLessEqual(len(lines), 10, f"第 0 屏太长（{len(lines)} 行），新手看不完")

    def test_step1_screen_has_six_steps_and_number(self):
        block = self._blocks()[1]
        for must in ("找买家", "筛名单", "建跟进计划", "现在", "该回什么", "还要回 8 次"):
            self.assertIn(must, block, f"第 1 屏缺少「{must}」")


class SaveAuthorizationWordingTest(unittest.TestCase):
    """保存要花额度：卡上必须先写清数字，用户回 1 才算授权。"""

    def test_save_card_shows_numbers_and_number_reply(self):
        text = (ROOT / "output-templates" / "S5-save-confirm.md").read_text(encoding="utf-8")
        self.assertIn("确认保存", text)
        self.assertTrue("额度" in text or "点数" in text, "保存卡必须写清会花多少额度/点数")

    def test_beginner_flow_explains_save_exception(self):
        text = (ROOT / "specs" / "beginner-flow.md").read_text(encoding="utf-8")
        self.assertIn("确认保存", text)
        self.assertIn("确认激活", text)


if __name__ == "__main__":
    unittest.main()
