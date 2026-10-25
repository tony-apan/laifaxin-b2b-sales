"""文档 frontmatter 回归（2026-10-23 元数据补齐）。

范围：全仓 .md，排除 .git/.local 与用户 runs（含 runs/_template，保留 runs/INDEX.md）。
断言：
1. 每个文件首部有 YAML frontmatter（三横线包裹，无 BOM）；
2. doc_id/title/description/type/status/updated 六字段齐全且非空；
3. description 非空、长度 >= 10，且不是「本文档介绍……」空话；
4. doc_id 全局唯一且为小写短横线 slug；
5. type 在 8 类枚举内；updated 为 YYYY-MM-DD；
6. MD-METADATA.md 存在，含 7 个字段名与 type 枚举。
"""
import datetime
import os
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKIP_DIRS = {".git", ".local", "__pycache__", ".pytest_cache", ".mypy_cache"}
REQUIRED = ("doc_id", "title", "description", "type", "status", "updated")
TYPES = {"rule", "entry", "spec", "template", "guide", "index", "record", "readme"}
SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
BOILERPLATE = ("本文档介绍", "本文件介绍", "主要用于介绍")
# 机器种子保留自身状态占位，不要求 active（见 MD-METADATA 第 2 节例外）
STATUS_EXCEPTIONS = {"runs/_template/product-profile.md", "runs/_template/operation-record.md"}


def _in_scope(rel):
    parts = rel.split("/")
    if any(p in SKIP_DIRS for p in parts):
        return False
    if parts[0] == "runs" and len(parts) > 1:
        return parts[1] == "_template" or rel == "runs/INDEX.md"
    return True


def _md_files():
    out = []
    for dp, dns, fns in os.walk(ROOT):
        rel_dir = os.path.relpath(dp, ROOT)
        parts = [] if rel_dir == "." else rel_dir.split(os.sep)
        if any(p in SKIP_DIRS for p in parts):
            dns[:] = []
            continue
        dns[:] = [d for d in dns if d not in SKIP_DIRS]
        for fn in fns:
            if fn.lower().endswith(".md"):
                rel = str((Path(dp) / fn).relative_to(ROOT)).replace(os.sep, "/")
                if _in_scope(rel):
                    out.append(rel)
    return sorted(out)


def _parse_frontmatter(text):
    if text.startswith("\ufeff"):
        text = text[1:]
    lines = text.splitlines()
    # 严格：首行必须是顶格 ---（不接受缩进）；闭合行同样顶格
    if not lines or lines[0] != "---":
        return None
    for i in range(1, len(lines)):
        if lines[i] == "---":
            fields = {}
            dups = []
            for line in lines[1:i]:
                m = re.match(r"^([A-Za-z_][\w-]*):\s?(.*)$", line)
                if m:
                    key = m.group(1)
                    if key in fields:
                        dups.append(key)
                    fields[key] = m.group(2).strip()
            if dups:
                fields["__dups__"] = ",".join(sorted(set(dups)))
            return fields
    return None


def _value(raw):
    raw = raw.strip()
    if len(raw) >= 2 and raw[0] == raw[-1] and raw[0] in "\"'":
        return raw[1:-1]
    return raw


class DocFrontmatterTest(unittest.TestCase):
    def test_every_md_has_frontmatter(self):
        missing = []
        for rel in _md_files():
            data = (ROOT / rel).read_bytes()
            if data.startswith(b"\xef\xbb\xbf"):
                missing.append(rel + " (BOM)")
                continue
            if _parse_frontmatter(data.decode("utf-8", errors="replace")) is None:
                missing.append(rel)
        self.assertEqual([], missing, "缺少 frontmatter 或带 BOM：" + "; ".join(missing))

    def test_required_fields_and_description(self):
        problems = {}
        for rel in _md_files():
            fields = _parse_frontmatter((ROOT / rel).read_text(encoding="utf-8", errors="replace")) or {}
            bad = []
            for key in REQUIRED:
                if not _value(fields.get(key, "")):
                    bad.append("缺 " + key)
            desc = _value(fields.get("description", ""))
            if desc and len(desc) < 10:
                bad.append("description 太短")
            if desc and len(desc) > 80:
                bad.append("description 超长(>80)")
            if desc.startswith(BOILERPLATE):
                bad.append("description 空话")
            typ = _value(fields.get("type", ""))
            if typ and typ not in TYPES:
                bad.append("type 不在枚举: " + typ)
            if fields.get("__dups__"):
                bad.append("重复 YAML 键: " + fields["__dups__"])
            status = _value(fields.get("status", ""))
            if status and status != "active" and rel not in STATUS_EXCEPTIONS:
                bad.append("status 非 active: " + status)
            updated = _value(fields.get("updated", ""))
            if updated:
                if not DATE_RE.match(updated):
                    bad.append("updated 非日期: " + updated)
                else:
                    try:
                        parsed = datetime.date.fromisoformat(updated)
                    except ValueError:
                        bad.append("updated 非真实日期: " + updated)
                    else:
                        if parsed > datetime.date.today():
                            bad.append("updated 是未来日期: " + updated)
            if bad:
                problems[rel] = bad
        self.assertEqual({}, problems, f"frontmatter 字段问题：{problems}")

    def test_doc_id_unique_and_slug(self):
        ids = {}
        problems = {}
        for rel in _md_files():
            fields = _parse_frontmatter((ROOT / rel).read_text(encoding="utf-8", errors="replace")) or {}
            doc_id = _value(fields.get("doc_id", ""))
            if not doc_id:
                continue
            if not SLUG_RE.match(doc_id):
                problems[rel] = "非 slug: " + doc_id
            if doc_id in ids:
                problems[rel] = "重复 doc_id " + doc_id + "（另见 " + ids[doc_id] + "）"
            ids[doc_id] = rel
        self.assertEqual({}, problems, f"doc_id 问题：{problems}")

    def test_descriptions_are_unique(self):
        """两条文档 description 完全相同，说明多半是复制粘贴，要求重写。"""
        seen = {}
        dups = []
        for rel in _md_files():
            fields = _parse_frontmatter((ROOT / rel).read_text(encoding="utf-8", errors="replace")) or {}
            desc = _value(fields.get("description", ""))
            if not desc:
                continue
            if desc in seen:
                dups.append((rel, seen[desc]))
            else:
                seen[desc] = rel
        self.assertEqual([], dups, "description 重复：" + repr(dups))

    def test_related_paths_exist(self):
        """related 里的显式 .md 路径必须存在；禁止绝对路径与 URL。"""
        bad = []
        for rel in _md_files():
            fields = _parse_frontmatter((ROOT / rel).read_text(encoding="utf-8", errors="replace")) or {}
            raw = fields.get("related", "").strip()
            if not raw.startswith("[") or not raw.endswith("]"):
                continue
            for item in raw[1:-1].split(","):
                item = _value(item.strip())
                if not item:
                    continue
                if item.startswith(("http://", "https://")) or item.startswith("/"):
                    bad.append((rel, item))
                    continue
                if item.endswith(".md") and not (ROOT / item).is_file() and not (ROOT / rel).parent.joinpath(item).is_file():
                    bad.append((rel, item))
        self.assertEqual([], bad, "related 路径不存在或非法：" + repr(bad))

    def test_title_and_h1_share_topic(self):
        """title 与正文 H1 至少共享 4 个连续有效字符，防标题与正文跑偏。"""
        def norm(s):
            return re.sub(r"[^\w\u4e00-\u9fff]", "", s).lower()
        def lcs(a, b):
            best = 0
            for i in range(len(a)):
                for j in range(len(b)):
                    k = 0
                    while i + k < len(a) and j + k < len(b) and a[i + k] == b[j + k]:
                        k += 1
                    best = max(best, k)
            return best
        bad = []
        for rel in _md_files():
            text = (ROOT / rel).read_text(encoding="utf-8", errors="replace")
            fields = _parse_frontmatter(text) or {}
            title = _value(fields.get("title", ""))
            m = re.search(r"^#\s+(.*)$", text, re.M)
            if not title or not m:
                continue
            score = lcs(norm(title), norm(m.group(1)))
            if score < 4:
                bad.append((rel, score, title, m.group(1)))
        self.assertEqual([], bad, "title 与 H1 主题不一致：" + repr(bad))

    def test_md_metadata_spec_is_complete(self):
        path = ROOT / "MD-METADATA.md"
        self.assertTrue(path.is_file(), "缺少 MD-METADATA.md")
        text = path.read_text(encoding="utf-8")
        for field in REQUIRED + ("related",):
            self.assertIn(field, text, "MD-METADATA 缺字段说明: " + field)
        for typ in TYPES:
            self.assertIn(typ, text, "MD-METADATA 缺 type 枚举: " + typ)


if __name__ == "__main__":
    unittest.main()
