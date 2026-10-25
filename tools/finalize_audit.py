#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""S4 审计收口：审计证据+对抗审查均存在且通过后，推进 operation-record 到 S4。

★审计窗口机器校验（2026-10-23 P0 修复）：在写 finalized 产物（record → S4）之前，
除字面词 + 文件 hash 门禁外，再按 specs/threshold-probe-spec.md §4.4 四件套契约校验
audit-manifest.json 的 window（并读取 boundary 的逐页数据）：

  1. window 必须有逐页数据 page_rows（兼容 rows / pages 为 {page,matched,total} 列表的写法）；
  2. pages 必须是连续页（页码 +1 递增；从第 1 页起时取最长连续前缀，断页后的尾段不参与核验）；
  3. 每个连续 5 页窗口 matched 之和 / total 之和 ≥ 70%（total 按实际返回数，尾页不足 10 条时照实计算）；
  4. critical_page = 首个 <70% 窗口起点 + 3（即该窗口末页 = 前一达标窗口末页）；
     没有跌破窗口时，critical_page 取最后一个完整 5 页窗口末页（兼容页面末页 -1 写法）；
  5. 每页 page_rows 须含 page/matched/total 且 matched ≤ total，numerator/denominator 与逐页合计一致；
  6. 可选公司级语义表（company_rows / semantic_rows）行数须与 page_rows.total 对齐。

校验失败：打印中文原因并 exit 2（不写 record、不抛 traceback）。
兼容说明：window 与四件套其余字段（run_id/source_ref/query_scope/boundary）全缺的历史
manifest 按兼容模式放行并打印告警；一旦 manifest 声明了其中任一字段，缺 window 即 exit 2。
"""
import argparse
import datetime
import hashlib
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from evidence_validation import find_non_live_marker
from profile_utils import ensure_same_project_paths, profile_gate
from update_run_state import read_meta, record_matches_project, require_state, update_frontmatter

WINDOW_SIZE = 5
WINDOW_THRESHOLD = 70  # 百分比
CONTRACT_KEYS = ("run_id", "source_ref", "query_scope", "boundary")


def check_file(path, label, required):
    p = Path(path)
    if not p.is_file() or p.stat().st_size == 0:
        return f"{label}缺失/为空: {p}"
    text = p.read_text(encoding="utf-8", errors="replace")
    marker = find_non_live_marker(text)
    if marker: return f"{label}含非实时证据标记『{marker}』: {p}"
    if re.search(r"(?:不放行|未放行|拒绝放行|尚未通过|并未通过)", text): return f"{label}含否定结论: {p}"
    if "❌" in text or re.search(r"(?im)^\s*(?:FAIL(?:ED)?\b(?!\s*=\s*0)|P[01]\b(?!\s*[:=]\s*0\b))", text):
        return f"{label}含失败/P0/P1标记: {p}"
    if required and not all(word in text for word in required):
        return f"{label}缺必需内容{required}: {p}"
    return ""


def _is_int(value):
    return isinstance(value, int) and not isinstance(value, bool)


def _pick_rows(container, label):
    """识别 page_rows / rows 两种命名；pages 为逐页对象列表时也接受。"""
    if not isinstance(container, dict):
        return None, ""
    for key in ("page_rows", "rows"):
        value = container.get(key)
        if isinstance(value, list):
            return value, f"{label}.{key}"
    pages = container.get("pages")
    if isinstance(pages, list) and pages and all(isinstance(item, dict) for item in pages):
        return pages, f"{label}.pages"
    return None, ""


def _normalize_rows(raw_rows, label):
    errors, rows = [], []
    for index, raw in enumerate(raw_rows, 1):
        if not isinstance(raw, dict):
            errors.append(f"{label} 第{index}条不是对象（须为 {{page,matched,total}}）")
            continue
        missing = [key for key in ("page", "matched", "total") if key not in raw]
        if missing:
            errors.append(f"{label} 第{index}条缺字段 {'/'.join(missing)}（每页须含 page/matched/total）")
            continue
        page, matched, total = raw["page"], raw["matched"], raw["total"]
        if not (_is_int(page) and _is_int(matched) and _is_int(total)):
            errors.append(f"{label} 第{index}条 page/matched/total 须为整数")
            continue
        if page < 1:
            errors.append(f"{label} page={page} 须为 ≥1 的页码")
            continue
        if total <= 0:
            errors.append(f"{label} 第{page}页 total={total} 须为正整数（按实际返回数）")
            continue
        if matched < 0 or matched > total:
            errors.append(f"{label} 第{page}页 matched={matched} 不得为负且不得大于 total={total}")
            continue
        rows.append({"page": page, "matched": matched, "total": total})
    return rows, errors


def _contiguous_prefix(pages):
    prefix = [pages[0]]
    for previous, current in zip(pages, pages[1:]):
        if current != previous + 1:
            break
        prefix.append(current)
    return prefix


def _window_ratios(rows, size=WINDOW_SIZE):
    stats = []
    for start in range(len(rows) - size + 1):
        chunk = rows[start:start + size]
        matched = sum(row["matched"] for row in chunk)
        total = sum(row["total"] for row in chunk)
        ratio = matched * 100.0 / total if total else 0.0
        stats.append({"start": chunk[0]["page"], "end": chunk[-1]["page"],
                      "matched": matched, "total": total, "ratio": ratio})
    return stats


def _semantic_counts(semantic):
    """解析可选公司级语义表：列表（逐条带 page，或用 count 聚合）或 {页: 条数/行列表}。"""
    errors, counts = [], {}
    if isinstance(semantic, list):
        for index, item in enumerate(semantic, 1):
            if not isinstance(item, dict) or "page" not in item:
                errors.append(f"公司级语义表第{index}条缺 page（须逐条带页号）")
                continue
            page = item.get("page")
            count = item.get("count")
            if count is None:
                counts[page] = counts.get(page, 0) + 1
            elif _is_int(count):
                counts[page] = counts.get(page, 0) + count
            else:
                errors.append(f"公司级语义表第{page}页 count 须为整数")
    elif isinstance(semantic, dict):
        for page, value in semantic.items():
            if isinstance(value, list):
                counts[page] = len(value)
            elif _is_int(value):
                counts[page] = value
            else:
                errors.append(f"公司级语义表第{page}页条数无法识别（须为整数或行列表）")
    else:
        errors.append("公司级语义表字段须为列表或 {页:条数} 对象")
    return counts, errors


def validate_audit_window(manifest):
    """校验 manifest 的 window 四件套。返回 (errors, warnings)；errors 非空 → exit 2。"""
    errors, warnings = [], []
    window = manifest.get("window")
    if not isinstance(window, dict):
        if any(key in manifest for key in CONTRACT_KEYS):
            errors.append("缺 window：manifest 已声明四件套其他字段，必须给出 window"
                          "（pages/page_rows/numerator/denominator），否则无法核验连续5页窗口与临界页")
        else:
            warnings.append("audit manifest 未提供 window 四件套（window/run_id/source_ref/query_scope/boundary 均缺）："
                            "本次按历史兼容模式放行，窗口与临界页未做机器核验，不得声称已核验。")
        return errors, warnings

    raw_rows, rows_label = _pick_rows(window, "window")
    if raw_rows is None:
        errors.append("window 缺逐页数据：须提供 page_rows（或 rows）[{page,matched,total}]，"
                      "否则无法核验连续5页窗口")
        return errors, warnings
    rows, row_errors = _normalize_rows(raw_rows, rows_label)
    errors.extend(row_errors)
    if not rows:
        return errors, warnings
    row_pages = [row["page"] for row in rows]
    if len(set(row_pages)) != len(row_pages):
        errors.append(f"{rows_label} 页码重复：{row_pages}")
        return errors, warnings
    if row_pages != sorted(row_pages):
        errors.append(f"{rows_label} 页码须升序（当前 {row_pages}）")
        return errors, warnings

    declared_pages = window.get("pages")
    if isinstance(declared_pages, list) and declared_pages and all(_is_int(page) for page in declared_pages):
        pages = declared_pages
        if pages != row_pages:
            errors.append(f"window.pages 与 {rows_label} 页码不对齐：pages={pages}，rows={row_pages}")
    elif declared_pages is None or (isinstance(declared_pages, list) and all(isinstance(item, dict) for item in declared_pages)):
        pages = row_pages
    else:
        errors.append("window.pages 须为整数页码列表（或 {page,matched,total} 逐页对象列表）")
        pages = row_pages

    if len(pages) < WINDOW_SIZE:
        errors.append(f"window.pages 仅 {len(pages)} 页，连续 5 页滑动窗口至少要 5 页")
        return errors, warnings

    prefix = _contiguous_prefix(pages)
    if pages[0] == 1:
        if len(prefix) < len(pages):
            warnings.append(f"window.pages 从第1页起的最长连续前缀为 1–{prefix[-1]}；"
                            f"第{prefix[-1]}页后断页（{pages[len(prefix)]} 起），尾段不参与窗口核验")
        pages = prefix
        rows = rows[:len(prefix)]
        if len(pages) < WINDOW_SIZE:
            errors.append(f"第1页起最长连续前缀仅 {len(pages)} 页，不足 5 页无法核验窗口")
            return errors, warnings
    elif len(prefix) != len(pages):
        errors.append(f"window.pages 非连续：第{prefix[-1]}页后跳到第{pages[len(prefix)]}页（页码须 +1 递增）")
        return errors, warnings

    matched_sum = sum(row["matched"] for row in rows)
    total_sum = sum(row["total"] for row in rows)
    numerator = window.get("numerator", window.get("matched"))
    denominator = window.get("denominator", window.get("total"))
    if numerator is None or denominator is None:
        errors.append("window 缺 numerator/denominator（或 matched/total）：须写明窗口合计分子/分母")
    elif not (_is_int(numerator) and _is_int(denominator)):
        errors.append("window.numerator/denominator 须为整数")
    else:
        if numerator != matched_sum:
            errors.append(f"window.numerator={numerator} 与逐页 matched 合计 {matched_sum} 不一致")
        if denominator != total_sum:
            errors.append(f"window.denominator={denominator} 与逐页 total 合计 {total_sum} 不一致")
        if denominator <= 0 or numerator * 10 < denominator * 7:
            errors.append(f"窗口合计 {numerator}/{denominator} 低于 70% 达标线")

    for stat in _window_ratios(rows):
        if stat["ratio"] < WINDOW_THRESHOLD:
            errors.append(f"连续5页窗口 {stat['start']}–{stat['end']} 达标率 {stat['ratio']:.1f}% < "
                          f"{WINDOW_THRESHOLD}%（matched={stat['matched']}，total={stat['total']}）：审计窗口不达标")

    boundary = manifest.get("boundary")
    boundary = boundary if isinstance(boundary, dict) else {}
    critical = boundary.get("critical_page", window.get("critical_page"))
    if critical is None:
        errors.append("缺 critical_page（window.critical_page 或 boundary.critical_page）")
    elif not _is_int(critical):
        errors.append("critical_page 须为整数页码")
        critical = None

    boundary_rows = []
    raw_boundary_rows, boundary_label = _pick_rows(boundary, "boundary")
    if raw_boundary_rows is not None:
        boundary_rows, boundary_errors = _normalize_rows(raw_boundary_rows, boundary_label)
        errors.extend(boundary_errors)

    timeline = {row["page"]: dict(row) for row in rows}
    for row in boundary_rows:
        existing = timeline.get(row["page"])
        if existing and (existing["matched"], existing["total"]) != (row["matched"], row["total"]):
            errors.append(f"第{row['page']}页在 window 与 boundary 的 matched/total 不一致")
            continue
        timeline[row["page"]] = dict(row)

    if critical is not None:
        if critical not in [row["page"] for row in rows] and critical not in [row["page"] for row in boundary_rows]:
            errors.append(f"critical_page={critical} 不在 window/boundary 逐页数据中（窗口须覆盖临界页）")
        ordered = sorted(timeline)
        anchor = ordered.index(rows[0]["page"])
        start = anchor
        end = anchor
        while start - 1 >= 0 and ordered[start - 1] == ordered[start] - 1:
            start -= 1
        while end + 1 < len(ordered) and ordered[end + 1] == ordered[end] + 1:
            end += 1
        run_rows = [timeline[page] for page in ordered[start:end + 1]]
        first_drop = next((stat for stat in _window_ratios(run_rows) if stat["ratio"] < WINDOW_THRESHOLD), None)
        if first_drop is not None:
            expected = first_drop["start"] + 3
            if critical != expected:
                errors.append(
                    f"critical_page={critical} 与窗口证据不符：首个<70%窗口 "
                    f"{first_drop['start']}–{first_drop['end']}（{first_drop['matched']}/{first_drop['total']}"
                    f"={first_drop['ratio']:.1f}%）要求 critical_page={expected}（该窗口起点+3=前一达标窗口末页）")
        else:
            valid = {pages[-1]}
            if len(pages) >= WINDOW_SIZE + 1:
                valid.add(pages[-1] - 1)  # 兼容「pages 末页 -1」写法（6 页样本的两窗口末页均合法）
            if critical not in valid:
                errors.append(f"critical_page={critical} 与窗口证据不符：无<70%跌破窗口时须取"
                              f"最后一个完整5页窗口末页（{pages[-1]}）")

    semantic = manifest.get("company_rows", manifest.get("semantic_rows"))
    if semantic is None:
        semantic = window.get("company_rows", window.get("semantic_rows"))
    if semantic is not None:
        counts, semantic_errors = _semantic_counts(semantic)
        errors.extend(semantic_errors)
        if not semantic_errors:
            totals = {row["page"]: row["total"] for row in rows}
            for page, total in totals.items():
                actual = counts.get(page)
                if actual is None:
                    actual = counts.get(str(page))
                if actual is None:
                    errors.append(f"公司级语义表缺第{page}页行（page_rows.total={total}）")
                elif actual != total:
                    errors.append(f"公司级语义表第{page}页行数={actual} 与 page_rows.total={total} 不一致")
    return errors, warnings


def main():
    ap = argparse.ArgumentParser(description="S4审计证据收口（过审后才能保存）")
    ap.add_argument("--record", required=True)
    ap.add_argument("--profile", required=True)
    ap.add_argument("--project", required=True, help="<operator_key>/<product_key>")
    ap.add_argument("--manifest", required=True, help="audit-manifest.json，绑定project/profile/seed/time及audit/review文件hash")
    args = ap.parse_args()
    if not ensure_same_project_paths(args.record, args.profile) or not record_matches_project(args.record, args.project):
        print("❌ record/profile/project不属于同一项目")
        return 4
    status, issues, meta, sha = profile_gate(args.profile)
    if issues:
        for issue in issues: print("❌ profile: " + issue)
        return 4
    try:
        require_state(args.record, ("S3", "S4"))
    except ValueError as exc:
        print(f"❌ {exc}")
        return 4
    rec = read_meta(args.record)
    try:
        manifest = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"❌ audit manifest无效: {exc}"); return 2
    if manifest.get("evidence_mode") != "live":
        print("❌ audit manifest evidence_mode须为字面量live；模拟/占位证据禁止正式收口")
        return 2
    if manifest.get("project") != args.project or manifest.get("profile_sha256") != sha or manifest.get("seed") != rec.get("seed"):
        print("❌ audit manifest未绑定当前project/profile/seed"); return 4
    try:
        generated = datetime.datetime.fromisoformat(str(manifest.get("generated_at", "")))
        age = datetime.datetime.now() - generated
        if age.total_seconds() < -300 or age.total_seconds() > 72 * 3600: raise ValueError("超过72小时或来自未来")
    except Exception as exc:
        print(f"❌ audit manifest时间无效/过期: {exc}"); return 2
    # ★P0：写 finalized 产物前先做窗口机器校验（连续页 / 连续5页≥70% / 临界页公式 / page_rows 对齐）
    window_errors, window_warnings = validate_audit_window(manifest)
    for warning in window_warnings:
        print("⚠️ " + warning)
    if window_errors:
        for error in window_errors:
            print("❌ 审计窗口校验失败: " + error)
        return 2
    errors = []
    for key, label, words in (("audit", "审计证据", ("70%", "逐页")),  # 2026-10-23 三审H：现行口径=100页跳/连续5页窗口（validate_audit_window 已校验），旧「50页/三页平均/临界」不再作必需项
                              ("review", "对抗审查", ("放行", "P0=0", "P1=0"))):
        item = (manifest.get("evidence") or {}).get(key)
        if not isinstance(item, dict) or item.get("status") != "pass": errors.append(label + " manifest非pass"); continue
        p = Path(item.get("path", "")); p = p if p.is_absolute() else Path(args.record).parent / p
        if p.resolve().parent != Path(args.record).resolve().parent: errors.append(label + "不在项目目录"); continue
        if not p.is_file() or hashlib.sha256(p.read_bytes()).hexdigest() != item.get("sha256"): errors.append(label + "文件/hash不匹配"); continue
        err = check_file(p, label, words)
        if err: errors.append(err)
    if errors:
        for error in errors: print("❌ " + error)
        return 1
    update_frontmatter(args.record, {"status": "S4", "next_state": "S5",
                                      "profile_version": f'"{meta.get("profile_version", "")}"',
                                      "profile_sha256": f'"{sha}"'}, expected_states=("S3", "S4"))
    print(f"✅ S4审计已收口: {args.record} (next=S5)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
