"""文档命名与目录索引防回归（2026-10-23 文档重命名与索引重构）。

约束：
1. 全仓 .md 文件名必须是纯 ASCII（无空格、无中文）；排除 .git/.local，以及 runs 下除 _template 以外的用户运行档案；
2. 仓库内每个目录（排除 .git/.local 与缓存目录）必须存在 INDEX.md；
3. 每个 INDEX.md 必须提到该目录下所有直接子项（文件与子目录，排除 INDEX.md/隐藏项/缓存）；
4. 全仓不得再出现 24 个旧中文模板文件名（含 runs/_template 内那一个；排除用户运行档案与 .local）。
"""
import os
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# 目录级排除：.git 是版本库内部；.local 是本地数据；缓存目录不参与索引要求
EXCLUDE_DIRS = {".git", ".local"}
CACHE_DIRS = {"__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache"}

MD_NAME_RE = re.compile(r"^[A-Za-z0-9._-]+\.md$")

# 旧名拆成「阶段前缀 + 剩余部分」两段保存：断言仍按完整文件名匹配，
# 同时避免本测试文件自身成为“旧文件名引用”的残留命中。
OLD_NAME_PARTS = [
    ("Q1-Q5", "询盘精准跟进.md"),
    ("S0", "产品知识档案.md"),
    ("S0", "任务菜单.md"),
    ("S0", "安装完成汇报.md"),
    ("S0", "开场提问.md"),
    ("S0", "画像方案.md"),
    ("S0", "连接成功.md"),
    ("S0", "连接未通过.md"),
    ("S0", "适配说明.md"),
    ("S0a", "网站资料确认.md"),
    ("S0a", "运营方档案.md"),
    ("S10", "加联系人确认.md"),
    ("S11", "完成汇报.md"),
    ("S12", "激活确认.md"),
    ("S2", "客群确认.md"),
    ("S3", "种子确认.md"),
    ("S4", "审计进行中.md"),
    ("S5", "保存确认.md"),
    ("S6", "数量账.md"),
    ("S7", "模板确认.md"),
    ("S8", "模板构建中.md"),
    ("S9", "序列确认.md"),
    ("T", "token引导.md"),
    ("S01", "客群档模板.md"),
]

OLD_NAMES = [stage + "-" + rest for stage, rest in OLD_NAME_PARTS]

TEXT_EXTS = {".md", ".py", ".json", ".sh", ".yml", ".yaml", ".txt", ".tsv", ".ps1", ".html", ".css", ".js"}


def _excluded(path):
    parts = path.relative_to(ROOT).parts
    if ".git" in parts or ".local" in parts:
        return True
    if "runs" in parts:
        # runs/_template 是随仓库分发的模板，必须遵守命名规范；其余 runs/ 是用户运行档案，不强制。
        return "_template" not in parts
    return False


def _is_user_run_dir(parts):
    """runs/ 下除 _template 外的运营方项目目录是本地数据，不要求 INDEX（与 frontmatter/links 口径一致）。"""
    if "runs" not in parts:
        return False
    return "_template" not in parts and parts[-1] != "runs"


def _all_dirs():
    out = [ROOT]
    for dp, dns, fns in os.walk(ROOT):
        rel = os.path.relpath(dp, ROOT)
        parts = [] if rel == "." else rel.split(os.sep)
        if any(part in EXCLUDE_DIRS or part in CACHE_DIRS for part in parts) or _is_user_run_dir(parts):
            dns[:] = []
            continue
        dns[:] = [d for d in dns if d not in EXCLUDE_DIRS and d not in CACHE_DIRS and not d.startswith(".")]
        if rel != ".":
            out.append(Path(dp))
    return sorted(out)


def _md_files():
    for path in ROOT.rglob("*"):
        if path.is_file() and path.suffix.lower() == ".md" and not _excluded(path):
            yield path


def _text_files():
    for path in ROOT.rglob("*"):
        if not path.is_file() or _excluded(path):
            continue
        if path.name == ".gitignore" or path.suffix in TEXT_EXTS:
            yield path


class DocNamingTest(unittest.TestCase):
    def test_md_filenames_are_ascii(self):
        bad = []
        for path in _md_files():
            if not MD_NAME_RE.match(path.name):
                bad.append(str(path.relative_to(ROOT)))
        self.assertEqual([], sorted(bad), "存在非 ASCII/含空格的 .md 文件名：" + "; ".join(sorted(bad)))

    def test_every_directory_has_index(self):
        missing = []
        for d in _all_dirs():
            # macOS 大小写不敏感：必须按真实文件名精确匹配，防 index.md 冒充 INDEX.md
            if "INDEX.md" not in os.listdir(d):
                missing.append(str(d.relative_to(ROOT)) or ".")
        self.assertEqual([], missing, "缺少目录 INDEX.md：" + "; ".join(missing))

    def test_index_covers_every_direct_child(self):
        problems = {}
        for d in _all_dirs():
            index = d / "INDEX.md"
            if not index.is_file():
                continue
            text = index.read_text(encoding="utf-8")
            rows = [ln for ln in text.splitlines() if "|" in ln]
            missing = []
            if not any("---" in ln for ln in rows):
                missing.append("缺少表格表头/分隔行")
            for name in sorted(os.listdir(d)):
                if name == "INDEX.md" or name.startswith(".") or name in CACHE_DIRS:
                    continue
                # 必须作为表格首列条目出现，正文顺带提及不算登记
                if not any(len(ln.split("|")) > 1 and name in ln.split("|")[1] for ln in rows):
                    missing.append(name)
            if missing:
                key = str(d.relative_to(ROOT)) or "."
                problems[key] = missing
        self.assertEqual({}, problems, f"INDEX.md 漏登记直接子项：{problems}")

    def test_old_chinese_names_gone(self):
        hits = {}
        for path in _text_files():
            if path.name == "CHANGELOG.md":
                # CHANGELOG 是历史记录：允许保留「旧名→新名」迁移映射，不算仍在引用旧文件。
                continue
            try:
                text = path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            found = [name for name in OLD_NAMES if name in text]
            if found:
                hits[str(path.relative_to(ROOT))] = found
        self.assertEqual({}, hits, f"仍引用旧中文模板文件名：{hits}")


if __name__ == "__main__":
    unittest.main()
