
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""文档引用与目录索引核验：链接、反引号 .md 路径、代码内 .md 名、INDEX 覆盖。"""
import os
import random
import re
import sys
from pathlib import Path
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parent.parent
SKIP_DIRS = {".git", ".local", "__pycache__", ".pytest_cache", ".mypy_cache"}
HISTORY_SKIP = {"CHANGELOG.md"}
RUNTIME_PLACEHOLDERS = {"index.md", "operator-profile.md", "S7-report.md", "S9-report.md", "S11-report.md"}
CODE_RUNTIME = {"operator-profile.md", "segments-projection.md", "s4-audit.md", "s4-review.md", "verification-panel.md", "S7-report.md", "S9-report.md", "S11-report.md"}
CODE_FIXTURES = {"outside.md", "acme.md", "copied-product-profile.md", "copied-operator.md", "other-product.md"}
BT = chr(96)
Q = chr(34) + chr(39)

LINK_RE = re.compile(r'(?<!!)\[[^\]]*\]\(([^)\s]+)(?:\s+"[^"]*")?\)')
BT_RE = re.compile(BT + r"([^" + BT + r"\n]+\.md)" + BT)
CODE_RE = re.compile("[" + Q + r"]([^" + Q + r"\n]+\.md)[" + Q + r"]")
REF_USE_RE = re.compile(r"\[([^\]]+)\]\[([^\]]*)\]")
REF_DEF_RE = re.compile(r"^\s{0,3}\[([^\]]+)\]:\s*(\S+)")


def in_scope(rel):
    parts = rel.split("/")
    if any(p in SKIP_DIRS for p in parts):
        return False
    if parts[0] == "runs" and len(parts) > 1:
        return parts[1] == "_template" or rel == "runs/INDEX.md"
    return True


def iter_md_files(root=ROOT):
    out = []
    for dp, dns, fns in os.walk(root):
        rel_dir = os.path.relpath(dp, root)
        parts = [] if rel_dir == "." else rel_dir.split(os.sep)
        if any(p in SKIP_DIRS for p in parts):
            dns[:] = []
            continue
        dns[:] = [d for d in dns if d not in SKIP_DIRS]
        for fn in fns:
            if not fn.lower().endswith(".md"):
                continue
            rel = str((Path(dp) / fn).relative_to(root))
            if in_scope(rel):
                out.append(rel)
    return sorted(out)


def strip_fences(text):
    out = []
    fence = False
    for line in text.splitlines():
        s = line.lstrip()
        if s.startswith("~~~") or s.startswith(BT * 3):
            fence = not fence
            out.append("")
            continue
        out.append("" if fence else line)
    return out


def strip_inline_code(line):
    return re.sub(BT + r"+[^" + BT + r"]*" + BT + r"+", "", line)


def _template_fallback(rel_file, target):
    if rel_file.startswith("runs/_template/") and target.startswith("../../../"):
        return (ROOT / target[9:]).resolve()
    return None


def _exact_exists(p):
    """大小写敏感的存在性校验。

    macOS/Windows 的 Path.exists() 不区分大小写，sub/A.MD 会误判为存在；
    这里逐级比对父目录真实 listing，保证 Linux/CI 上不会漏掉大小写写错的链接。
    """
    try:
        p = Path(os.path.abspath(str(p)))
    except OSError:
        return False
    if not p.exists():
        return False
    cur = Path(p.anchor) if p.is_absolute() else Path(".")
    parts = p.parts[1:] if p.is_absolute() else p.parts
    for part in parts:
        try:
            if part not in os.listdir(cur):
                return False
        except OSError:
            return False
        cur = cur / part
    return True


def _slugify(heading):
    h = re.sub(r'[^\w\u4e00-\u9fff\- ]', '', heading.strip())
    return h.strip().lower().replace(' ', '-')


def _anchors(text):
    """收集可跳转锚点：标题 slug（GitHub 同名标题自动追加 -1/-2）+ HTML <a id/name>。"""
    out = set()
    dup_count = {}
    for line in text.splitlines():
        m = re.match(r'^#{1,6}\s+(.*)', line)
        if m:
            base = _slugify(m.group(1))
            slug = base
            if slug in out:
                k = dup_count.get(base, 0) + 1
                while (base + '-' + str(k)) in out:
                    k += 1
                dup_count[base] = k
                slug = base + '-' + str(k)
            out.add(slug)
        for am in re.finditer(r'<a\s+[^>]*?(?:id|name)=["\']([^"\']+)["\']', line, re.I):
            out.add(am.group(1).strip().lower())
    return out


def _anchor_ok(path, text, anchor):
    if not anchor:
        return True
    return anchor.strip().lower() in _anchors(text)


def check_markdown_links(root=ROOT):
    bad = []
    checked = skipped = 0
    for rel in iter_md_files(root):
        path = root / rel
        raw_text = path.read_text(encoding='utf-8-sig', errors='replace')
        lines = strip_fences(raw_text)
        defs = {}
        for line in lines:
            dm = REF_DEF_RE.match(line)
            if dm:
                defs[dm.group(1).strip().lower()] = dm.group(2).strip()
        for lineno, line in enumerate(lines, 1):
            scan_line = strip_inline_code(line)
            for m in LINK_RE.finditer(scan_line):
                target = m.group(1).strip()
                if target.startswith(('http://', 'https://', 'mailto:')):
                    skipped += 1
                    continue
                if '<' in target or '>' in target or target.startswith('.local/'):
                    skipped += 1
                    continue
                checked += 1
                anchor = target.split('#', 1)[1] if '#' in target else ''
                clean = target.split('#')[0].split('?')[0]
                if not clean:
                    if not _anchor_ok(path, raw_text, anchor):
                        bad.append((rel, lineno, target + ' (anchor)'))
                    continue
                if clean.startswith('/') or clean.startswith('~'):
                    bad.append((rel, lineno, target))
                    continue
                candidates = [path.parent / unquote(clean)]
                alt = _template_fallback(rel, clean)
                if alt is not None:
                    candidates.append(alt)
                hit = next((c for c in candidates if _exact_exists(c)), None)
                if hit is None:
                    bad.append((rel, lineno, target))
                    continue
                if anchor:
                    try:
                        ttxt = hit.read_text(encoding='utf-8', errors='ignore')
                    except OSError:
                        ttxt = ''
                    if not _anchor_ok(hit, ttxt, anchor):
                        bad.append((rel, lineno, target + ' (anchor)'))
            for m in REF_USE_RE.finditer(scan_line):
                label = (m.group(2) or m.group(1)).strip().lower()
                target = defs.get(label)
                if target is None:
                    skipped += 1
                    continue
                if target.startswith(('http://', 'https://', 'mailto:')):
                    skipped += 1
                    continue
                if '<' in target or '>' in target or target.startswith('.local/'):
                    skipped += 1
                    continue
                checked += 1
                anchor = target.split('#', 1)[1] if '#' in target else ''
                clean = target.split('#')[0].split('?')[0]
                candidates = [] if not clean else [path.parent / unquote(clean)]
                if clean:
                    alt = _template_fallback(rel, clean)
                    if alt is not None:
                        candidates.append(alt)
                if not clean:
                    hit = path
                else:
                    hit = next((c for c in candidates if _exact_exists(c)), None)
                if hit is None:
                    bad.append((rel, lineno, m.group(0) + ' -> ' + target))
                    continue
                if anchor:
                    try:
                        ttxt = hit.read_text(encoding='utf-8', errors='ignore')
                    except OSError:
                        ttxt = ''
                    if not _anchor_ok(hit, ttxt, anchor):
                        bad.append((rel, lineno, m.group(0) + ' -> ' + target + ' (anchor)'))
    return checked, skipped, bad
def check_backtick_paths(root=ROOT):
    bad = []
    checked = skipped = 0
    all_names = set()
    for dp, dns, fns in os.walk(root):
        rel_dir = os.path.relpath(dp, root)
        parts = [] if rel_dir == "." else rel_dir.split(os.sep)
        if any(p in SKIP_DIRS for p in parts):
            dns[:] = []
            continue
        dns[:] = [d for d in dns if d not in SKIP_DIRS]
        all_names.update(fns)
    for rel in iter_md_files(root):
        if rel in HISTORY_SKIP:
            continue
        path = root / rel
        lines = strip_fences(path.read_text(encoding="utf-8-sig", errors="replace"))
        for lineno, line in enumerate(lines, 1):
            for m in BT_RE.finditer(line):
                raw = m.group(1).strip()
                if any(ch in raw for ch in "<>*{}") or raw.startswith(("http://", "https://", ".local/")):
                    skipped += 1
                    continue
                if "/" not in raw and raw in RUNTIME_PLACEHOLDERS:
                    skipped += 1
                    continue
                if re.search(r"(XX|YY|\.\.\.)", raw):
                    skipped += 1
                    continue
                checked += 1
                if "/" in raw:
                    candidates = [root / unquote(raw), path.parent / unquote(raw)]
                    alt = _template_fallback(rel, raw)
                    if alt is not None:
                        candidates.append(alt)
                    if any(_exact_exists(c) for c in candidates):
                        continue
                    bad.append((rel, lineno, raw, "path"))
                else:
                    if raw in all_names:
                        continue
                    bad.append((rel, lineno, raw, "basename"))
    return checked, skipped, bad


def check_code_md_refs(root=ROOT):
    bad = []
    checked = skipped = 0
    names = set()
    for dp, dns, fns in os.walk(root):
        rel_dir = os.path.relpath(dp, root)
        parts = [] if rel_dir == "." else rel_dir.split(os.sep)
        if any(p in SKIP_DIRS for p in parts):
            dns[:] = []
            continue
        dns[:] = [d for d in dns if d not in SKIP_DIRS]
        names.update(fns)
    targets = []
    for sub, pats in (("tools", (".py", ".sh")), ("tests", (".py",))):
        d = root / sub
        if not d.is_dir():
            continue
        for p in sorted(d.iterdir()):
            if p.is_file() and p.suffix in pats:
                targets.append((p.relative_to(root).as_posix(), p))
    for rel, p in targets:
        if rel == "tools/check_doc_links.py":
            continue
        text = p.read_text(encoding="utf-8", errors="replace")
        for lineno, line in enumerate(text.splitlines(), 1):
            for m in CODE_RE.finditer(line):
                raw = m.group(1)
                if any(ch in raw for ch in "<>*{}") or " " in raw or "/" in raw:
                    continue
                if raw.lower().startswith(("tmp", "temp", "example", "demo", "fixture")):
                    continue
                if any(ord(ch) > 127 for ch in raw):
                    continue  # 旧中文名负向断言
                if raw in CODE_RUNTIME or raw in CODE_FIXTURES:
                    skipped += 1
                    continue
                if raw == "xxx.md":
                    skipped += 1
                    continue
                checked += 1
                if raw not in names:
                    bad.append((rel, lineno, raw))
    return checked, skipped, bad


def _is_user_run_dir(parts):
    if "runs" not in parts:
        return False
    return "_template" not in parts and parts[-1] != "runs"


def iter_dirs(root=ROOT):
    out = ["."]
    for dp, dns, fns in os.walk(root):
        rel_dir = os.path.relpath(dp, root)
        parts = [] if rel_dir == "." else rel_dir.split(os.sep)
        if any(p in SKIP_DIRS for p in parts) or _is_user_run_dir(parts):
            dns[:] = []
            continue
        dns[:] = sorted(d for d in dns if d not in SKIP_DIRS and not d.startswith("."))
        if rel_dir != ".":
            out.append(rel_dir)
    return sorted(out)


def check_index_coverage(root=ROOT):
    missing_index = []
    coverage = []
    dirs = iter_dirs(root)
    for rel_dir in dirs:
        d = root if rel_dir == "." else root / rel_dir
        idx = d / "INDEX.md"
        if "INDEX.md" not in os.listdir(d):
            missing_index.append(rel_dir)
            continue
        text = idx.read_text(encoding="utf-8", errors="replace")
        rows = [ln for ln in text.splitlines() if "|" in ln]
        if not any(set(ln.replace(" ", "")) >= set("|---") and "---" in ln for ln in rows):
            coverage.append((rel_dir, "缺少表格表头/分隔行"))
        for name in sorted(os.listdir(d)):
            if name == "INDEX.md" or name.startswith(".") or name == "__pycache__":
                continue
            # 用户运行档案（runs/<运营方>/）是本地数据，不要求登记进 INDEX（与 .gitignore runs/*/ 一致）
            if _is_user_run_dir(([] if rel_dir == "." else rel_dir.split(os.sep)) + [name]):
                continue
            # 必须作为表格首列条目出现，正文顺带提及不算登记
            if not any(len(ln.split("|")) > 1 and name in ln.split("|")[1] for ln in rows):
                coverage.append((rel_dir, name))
    return dirs, missing_index, coverage


def report(root=ROOT):
    lines = []
    lines.append("Markdown 文件（scope）：" + str(len(iter_md_files(root))))
    checked, skipped, bad = check_markdown_links(root)
    lines.append("Markdown 相对链接：检查 " + str(checked) + "，跳过 " + str(skipped) + "，坏链 " + str(len(bad)))
    for b in bad:
        lines.append("  BAD_LINK " + b[0] + ":" + str(b[1]) + " -> " + b[2])
    checked, skipped, bad2 = check_backtick_paths(root)
    lines.append("反引号 .md 路径：检查 " + str(checked) + "，跳过 " + str(skipped) + "，坏引用 " + str(len(bad2)))
    for b in bad2:
        lines.append("  BAD_BT " + b[0] + ":" + str(b[1]) + " -> " + b[2] + " (" + b[3] + ")")
    checked, skipped, bad3 = check_code_md_refs(root)
    lines.append("代码内 .md 文件名：检查 " + str(checked) + "，跳过 " + str(skipped) + "，缺失同名 " + str(len(bad3)))
    for b in bad3:
        lines.append("  BAD_CODE " + b[0] + ":" + str(b[1]) + " -> " + b[2])
    dirs, missing_index, cov = check_index_coverage(root)
    lines.append("目录总数：" + str(len(dirs)) + "，有 INDEX：" + str(len(dirs) - len(missing_index)) + "，缺 INDEX：" + str(len(missing_index)))
    for d in missing_index:
        lines.append("  MISSING_INDEX " + d)
    lines.append("INDEX 未覆盖直接子项：" + str(len(cov)))
    for d, n in cov:
        lines.append("  COVERAGE " + d + " -> " + n)
    total_bad = len(bad) + len(bad2) + len(bad3) + len(missing_index) + len(cov)
    lines.append("TOTAL_BAD " + str(total_bad))
    return "\n".join(lines), total_bad


def _index_rows(root=ROOT):
    rows = []
    for rel in iter_md_files(root):
        path = Path(root) / rel if not Path(rel).is_absolute() else Path(rel)
        if path.name != 'INDEX.md':
            continue
        text = path.read_text(encoding='utf-8', errors='replace')
        header = None
        in_table = False
        for ln in text.splitlines():
            line = ln.strip()
            if not line.startswith('|'):
                in_table = False
                header = None
                continue
            cells = [c.strip() for c in line.strip('|').split('|')]
            if set(''.join(cells).replace(' ', '')) <= set(':-') and '-' in ''.join(cells):
                in_table = True
                continue
            if not in_table:
                header = cells
                continue
            rows.append((str(rel), header or [], cells))
    return rows


def sample_index(n=20, seed=20261023):
    rows = _index_rows(ROOT)
    if not rows:
        return '没有可抽检的 INDEX 行'
    rnd = random.Random(seed)
    picked = rnd.sample(rows, min(n, len(rows)))
    lines = ['INDEX 描述抽检（随机 ' + str(len(picked)) + ' / 共 ' + str(len(rows)) + ' 行，seed=' + str(seed) + '）']
    for rel, header, cells in picked:
        lines.append(rel + ' :: ' + ' | '.join(cells))
    return '\n'.join(lines)


def main():
    import argparse
    parser = argparse.ArgumentParser(description='Markdown 引用/锚点/INDEX 覆盖率核验')
    parser.add_argument('--sample-index', type=int, default=0, help='随机抽检 N 行 INDEX 描述（人工核对真实性）')
    parser.add_argument('--seed', type=int, default=20261023)
    args = parser.parse_args()
    if args.sample_index:
        print(sample_index(args.sample_index, args.seed))
        return 0
    text, total = report(ROOT)
    print(text)
    return 1 if total else 0


if __name__ == '__main__':
    sys.exit(main())
