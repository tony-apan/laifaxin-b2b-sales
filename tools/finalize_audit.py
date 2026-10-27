#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""S4 审计收口：审计证据+对抗审查均存在且通过后，推进 operation-record 到 S4。

★审计窗口机器校验（2026-10-27 审计边界与公司级证据修复）：在写 finalized 产物
（record → S4）之前，除字面词 + 文件 hash 门禁外，再按 specs/threshold-probe-spec.md
§4.4 四件套契约校验 audit-manifest.json 的 window / boundary / 公司级语义表：

  1. window 必须有逐页数据 page_rows（兼容 rows / pages 为 {page,matched,total} 列表的写法）；
     窗口长度 = WINDOW_SIZE（现行 3 页）；空页、不足 3 页、页码不连续均失败；
  2. 三页合计 matched/total ≥ 70% 且每页 ≥ 50%（total 按实际返回数，尾页不足 10 条照实计）；
  3. critical_page：有跌破时 = 首个 <70% 窗口起点 + WINDOW_SIZE - 2（前一实测达标窗口末页），
     且首个窗口即跌破（无前一实测达标窗口）时不得定界；无跌破时只认最后一个完整实测
     窗口末页，不得无依据前移（旧「末页-1 兼容」已删除）；
  4. 每页 page_rows 须含 page/matched/total 且 matched ≤ total，numerator/denominator 与逐页合计一致；
  5. 公司级语义表（manifest.company_rows / semantic_rows）为正式 live 收口必需：
     必须是逐行真实对象 [{page, company_id, company_name, summary_zh, matched, reason}, ...]
     （等价字段名见 SEMANTIC_FIELD_ALIASES），拒绝 {page,count} 聚合空壳与 {页:条数} 计数映射；
     已判定行（matched=true/false）必须有非空公司 id/名称/中文描述/理由；
     缺中文或身份行只能 matched=null（未知），不得计为匹配；
     每页 total 行数与 matched=true 行数必须与 page_rows 重算相等；
     重复 company_id、页外行一律拒绝。该校验只证明字段自洽，不宣称证明 AI 理解或真实性。

校验失败：打印中文原因并 exit 2（不写 record、不抛 traceback）。
兼容边界（2026-10-27 收紧）：正式 live 收口必须带完整 window 四件套与逐行公司级语义表，
历史无四件套 manifest 一律拒绝（不再兼容放行）；只读离线历史诊断请另行使用，不得借道本 CLI
推进 live。""",


def _utf8_stdout():
    """Windows 控制台/管道默认 GBK：输出 emoji 会抛 UnicodeEncodeError；显式改 UTF-8。"""
    import sys as _sys
    for _s in (_sys.stdout, _sys.stderr):
        try:
            _s.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
_utf8_stdout()
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

# v3（2026-10-27 用户裁决）：窗口从连续 5 页改 3 页，省约 40% 消耗；
# 同时加“每页不低于 50%”下限，防 3 页窗口被单页崩盘拉低后误判。
WINDOW_SIZE = 3
WINDOW_THRESHOLD = 70  # 百分比
WINDOW_PAGE_FLOOR = 50  # 单页达标率下限（百分比）
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


SEMANTIC_FIELD_ALIASES = {
    "page": ("page",),
    "company_id": ("company_id", "companyId", "id"),
    "company_name": ("company_name", "companyName", "name"),
    "summary_zh": ("summary_zh", "summaryZh", "summary", "description_zh"),
    "matched": ("matched", "is_buyer", "will_buy"),
    "reason": ("reason", "reason_zh", "note"),
}


def _semantic_field(row, field):
    for key in SEMANTIC_FIELD_ALIASES[field]:
        if key in row:
            return row[key]
    return None


def _semantic_rows(semantic):
    """校验公司级语义表为逐行真实对象，拒绝 {page,count} 空壳与计数映射。

    返回 (rows, errors)：rows = [{page, company_id, company_name, summary_zh,
    matched, reason}]（matched: True/False/None）。
    """
    errors = []
    if not isinstance(semantic, list):
        return None, ["公司级语义表须为逐行对象列表（每页每公司一行）"]
    rows, seen_ids = [], {}
    pages = set()
    for index, item in enumerate(semantic, 1):
        label = f"公司级语义表第{index}行"
        if not isinstance(item, dict):
            errors.append(f"{label}不是对象（须为逐行对象，非计数）")
            continue
        page = _semantic_field(item, "page")
        if not _is_int(page) or page < 1:
            errors.append(f"{label}缺 page 或页码无效（须为 ≥1 整数）")
            continue
        pages.add(page)
        cid = str(_semantic_field(item, "company_id") or "").strip()
        cname = str(_semantic_field(item, "company_name") or "").strip()
        summary = str(_semantic_field(item, "summary_zh") or "").strip()
        matched = _semantic_field(item, "matched")
        reason = str(_semantic_field(item, "reason") or "").strip()
        if "count" in item and "matched" not in item:
            errors.append(f"{label}是 {{page,count}} 聚合空壳：语义表必须逐公司一行，"
                          "不得用计数冒充逐行证据")
            continue
        if matched is not None and not isinstance(matched, bool):
            errors.append(f"{label} matched 只能为 true/false/null（未知）")
            continue
        if matched is not None and not (cid and cname and summary and reason):
            errors.append(f"{label}已判定（matched={str(matched).lower()}）但公司 id/名称/"
                          "中文描述/理由有空缺：缺中文或身份行只能 matched=null（未知），"
                          "不得强判")
            continue
        if matched is None and not reason:
            errors.append(f"{label} matched=null（未知）必须给 reason 说明（如缺中文描述）")
            continue
        if matched is not None and summary and not re.search(r"[\u4e00-\u9fff]", summary):
            errors.append(f"{label} summary_zh 非中文：正负判定（matched={str(matched).lower()}）"
                          "都必须以平台返回的中文公司描述为依据，英文描述不得作为判定行依据")
            continue
        if cid and cid in seen_ids:
            errors.append(f"{label} company_id={cid} 与第{seen_ids[cid]}行重复（重复 id 拒绝）")
            continue
        if cid:
            seen_ids[cid] = index
        rows.append({"page": page, "company_id": cid, "company_name": cname,
                     "summary_zh": summary, "matched": matched, "reason": reason})
    if not errors and not rows:
        errors.append("公司级语义表为空：每页每公司须一行（行数 = Σ page_rows.total）")
    return rows, errors


SOURCE_LINEAGE_FIELDS = ("platform_product_id", "generation_id", "segment_id", "keyword")


def validate_source_lineage(manifest):
    """审计必须能追溯到平台真实批次/客群；缺一即拒绝收口。

    根因：2026-10-26 真机 S4 只留下页码与公司名单，没有 generation/segment，
    保存端 E_SOURCE_STALE 拒绝。审计收口就挡住，避免“审完才发现不能保存”。
    """
    source = manifest.get("source") if isinstance(manifest, dict) else None
    source = source if isinstance(source, dict) else {}
    missing = [key for key in SOURCE_LINEAGE_FIELDS
               if not str(source.get(key) or "").strip()]
    if missing:
        return ["audit manifest 缺来源字段: " + ", ".join(missing)]
    return []


def validate_audit_window(manifest):
    """校验 manifest 的 window 四件套。返回 (errors, warnings)；errors 非空 → exit 2。"""
    errors, warnings = [], []
    window = manifest.get("window")
    if not isinstance(window, dict):
        errors.append("缺 window：正式 live 收口必须给出 window 四件套"
                      "（pages/page_rows/numerator/denominator），否则无法核验连续3页窗口与临界页；"
                      "历史无四件套 manifest 不再兼容放行（2026-10-27 收紧）")
        return errors, warnings

    raw_rows, rows_label = _pick_rows(window, "window")
    if raw_rows is None:
        errors.append("window 缺逐页数据：须提供 page_rows（或 rows）[{page,matched,total}]，"
                      "否则无法核验连续{WINDOW_SIZE}页窗口")
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
        errors.append(f"window.pages 仅 {len(pages)} 页，连续 {WINDOW_SIZE} 页滑动窗口至少要 {WINDOW_SIZE} 页"
                      f"（空页/不足{WINDOW_SIZE}页不得定界）")
        return errors, warnings

    prefix = _contiguous_prefix(pages)
    if pages[0] == 1:
        if len(prefix) < len(pages):
            warnings.append(f"window.pages 从第1页起的最长连续前缀为 1–{prefix[-1]}；"
                            f"第{prefix[-1]}页后断页（{pages[len(prefix)]} 起），尾段不参与窗口核验")
        pages = prefix
        rows = rows[:len(prefix)]
        if len(pages) < WINDOW_SIZE:
            errors.append(f"第1页起最长连续前缀仅 {len(pages)} 页，不足 {WINDOW_SIZE} 页无法核验窗口")
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

    for row in rows:
        page_ratio = row["matched"] * 100.0 / row["total"] if row["total"] else 0.0
        if page_ratio < WINDOW_PAGE_FLOOR:
            errors.append(f"第{row['page']}页达标率 {page_ratio:.1f}% < {WINDOW_PAGE_FLOOR}%"
                          f"（{WINDOW_SIZE} 页窗口的单页下限）：单页崩盘不能靠窗口平均掩盖")
    for stat in _window_ratios(rows):
        if stat["ratio"] < WINDOW_THRESHOLD:
            errors.append(f"连续{WINDOW_SIZE}页窗口 {stat['start']}–{stat['end']} 达标率 {stat['ratio']:.1f}% < "
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
        window_stats = _window_ratios(run_rows)
        first_drop = next((stat for stat in window_stats if stat["ratio"] < WINDOW_THRESHOLD), None)
        if first_drop is not None:
            drop_index = window_stats.index(first_drop)
            if drop_index == 0:
                errors.append(f"首个连续{WINDOW_SIZE}页窗口 {first_drop['start']}–{first_drop['end']} 即 <70%"
                              f"（{first_drop['matched']}/{first_drop['total']}={first_drop['ratio']:.1f}%）："
                              "无前一实测达标窗口，不能定界（critical_page 无依据）")
            else:
                expected = first_drop["start"] + WINDOW_SIZE - 2
                if critical != expected:
                    errors.append(
                        f"critical_page={critical} 与窗口证据不符：首个<70%窗口 "
                        f"{first_drop['start']}–{first_drop['end']}（{first_drop['matched']}/{first_drop['total']}"
                        f"={first_drop['ratio']:.1f}%）要求 critical_page={expected}"
                        f"（该窗口起点+{WINDOW_SIZE - 2}=前一实测达标窗口末页）")
        else:
            if critical != pages[-1]:
                errors.append(f"critical_page={critical} 与窗口证据不符：无<70%跌破窗口时只认"
                              f"最后一个完整实测窗口末页（{pages[-1]}），不得无依据前移")

    semantic = manifest.get("company_rows", manifest.get("semantic_rows"))
    if semantic is None:
        semantic = window.get("company_rows", window.get("semantic_rows"))
    if semantic is None:
        errors.append("缺公司级语义表：正式 live 收口必须提供逐行公司级语义表"
                      "（company_rows=[{page,company_id,company_name,summary_zh,matched,reason}]），"
                      "不得只交窗口计数")
        return errors, warnings
    semantic_rows, semantic_errors = _semantic_rows(semantic)
    errors.extend(semantic_errors)
    if semantic_errors:
        return errors, warnings
    totals = {row["page"]: row["total"] for row in rows}
    matched_declared = {row["page"]: row["matched"] for row in rows}
    page_rows_actual = {}
    matched_actual = {}
    offpage = []
    for row in semantic_rows:
        page = row["page"]
        if page not in totals:
            offpage.append(row)
            continue
        page_rows_actual[page] = page_rows_actual.get(page, 0) + 1
        if row["matched"] is True:
            matched_actual[page] = matched_actual.get(page, 0) + 1
    if offpage:
        first = offpage[0]
        errors.append(f"公司级语义表存在页外行（如 page={first['page']}，不在 window 页码内）：页外行拒绝")
    for page, total in totals.items():
        actual = page_rows_actual.get(page, 0)
        if actual != total:
            errors.append(f"公司级语义表第{page}页行数={actual} 与 page_rows.total={total} 不一致")
        matched_exp = matched_declared[page]
        matched_got = matched_actual.get(page, 0)
        if matched_got != matched_exp:
            errors.append(f"公司级语义表第{page}页 matched=true 行数={matched_got} "
                          f"与 page_rows.matched={matched_exp} 不一致")
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
    lineage_errors = validate_source_lineage(manifest)
    if lineage_errors:
        for error in lineage_errors:
            print("❌ " + error)
        print("   先做平台客群推演并登记真实批次/客群，再出审计清单；否则保存端会拒绝。")
        return 2
    if manifest.get("project") != args.project or manifest.get("profile_sha256") != sha or manifest.get("seed") != rec.get("seed"):
        print("❌ audit manifest未绑定当前project/profile/seed"); return 4
    try:
        generated_text = str(manifest.get("generated_at", "")).strip()
        if generated_text.endswith("Z"):
            generated_text = generated_text[:-1] + "+00:00"
        generated = datetime.datetime.fromisoformat(generated_text)
        now = datetime.datetime.now(generated.tzinfo) if generated.tzinfo else datetime.datetime.now()
        age = now - generated
        if age.total_seconds() < -300 or age.total_seconds() > 72 * 3600: raise ValueError("超过72小时或来自未来")
    except Exception as exc:
        print(f"❌ audit manifest时间无效/过期: {exc}"); return 2
    # ★P0：写 finalized 产物前先做窗口机器校验（连续页 / 连续{WINDOW_SIZE}页≥70% / 临界页公式 / page_rows 对齐）
    window_errors, window_warnings = validate_audit_window(manifest)
    for warning in window_warnings:
        print("⚠️ " + warning)
    if window_errors:
        for error in window_errors:
            print("❌ 审计窗口校验失败: " + error)
        return 2
    errors = []
    # 2026-10-23 三审H（历史注记：当时口径为 5 页窗口；2026-10-27 v3 起现行口径=3 页窗口，见 WINDOW_SIZE）
    for key, label, words in (("audit", "审计证据", ("70%", "逐页")),
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
