#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""★产品档案管理 CLI（本地写操作, 不调用平台）——产品档案与签名硬闸门的建档/确认入口。
用法:
  python3 tools/product_profile.py init --profile runs/<operator_key>/<product_key>/product-profile.md \
      --operator-key <operator_key> --product-key <product_key> [--declined]
  python3 tools/product_profile.py validate --profile <path> [--require-confirmed]
  python3 tools/product_profile.py confirm --profile <path> --by <纯昵称> --quote <用户确认原话>
  python3 tools/product_profile.py status --profile <path>
口径:
  - 签名=纯个人昵称(--by 须过 validate_nickname); 公司名/官网/邮箱/认证/产能/MOQ/交期/价格带
    =用户自己的商业资产, 可写入档案供建档/背调, 绝不进邮件签名。
  - confirm 严格解析确认原话(静态红队P1): 含否定/犹豫词(不好/不可以/不行/不要确认/not ok/
    尚未确认/再等等...)→ 拒绝; 单字/短英文确认词(好/行/嗯/ok/y)只在整句短精确时通过。
  - 客户/潜在联系人第三方联系方式禁止写入档案(校验会拦); 实际邮箱/电话号码也不得进
    product-profile——运营方自己的联系邮箱只放运营方档案 contact_email 字段。
退出码: 0=成功; 1=运行错误(IO等); 2=输入/校验失败(昵称非法·缺确认词·档案结构错·文件缺失);
        3=init 目标已存在(不覆盖)。"""
import argparse
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from profile_utils import (
    content_sha256, detect_third_party_contact, parse_frontmatter, profile_field_facts,
    profile_sha256, read_profile, split_markdown, validate_nickname, validate_product_profile,
)

KB = Path(__file__).resolve().parent.parent
TEMPLATE = KB / "runs" / "_template" / "product-profile.md"
OPERATION_TEMPLATE = KB / "runs" / "_template" / "operation-record.md"

# ---------- 用户确认原话·严格解析(静态红队P1) ----------
# 否定/犹豫词: 出现即拒绝(先于确认词判断), 中英都拦
_CONFIRM_NEGATION_ZH = (
    "不好", "不可以", "不行", "不要", "不用", "先不", "暂不", "别确认", "别发", "否", "拒绝", "不同意",
    "尚未", "还没", "还没有", "未确认", "未拍板", "再等等", "等等", "等一下", "稍等",
    "再看看", "再考虑", "考虑一下", "下次再说", "再说", "否决", "拒绝", "有问题",
)
_CONFIRM_NEGATION_EN = re.compile(
    r"\b(?:no|nope|not|never|wait|later|pending|unconfirmed|undecided|don'?t|cant|can'?t|problem)\b",
    re.IGNORECASE)
# 整句短精确词: 仅当去掉首尾标点后整句等于这些词才通过(不做子串匹配)
_CONFIRM_EXACT = {
    "好", "行", "嗯", "哦了", "确认", "确认了", "确定", "确定了", "好的",
    "可以", "没问题", "同意", "通过", "准了", "ok", "okay", "okk", "yes", "y", "ye",
}
# 多字明确确认词: 允许包含匹配(中文) / 词边界匹配(英文)
_CONFIRM_CONTAIN_ZH = ("确认", "确定", "好的", "可以", "没问题", "同意", "通过", "准了")
_CONFIRM_CONTAIN_EN = re.compile(r"\b(?:ok|okay|yes|confirm(?:ed|s)?|approved?|agree[de]?)\b", re.IGNORECASE)
_QUOTE_STRIP_CHARS = " \t。．.!！?？,，~～;；:：-—“”\"'`"


def check_confirm_quote(quote):
    """严格解析用户确认原话, 返回 (ok: bool, reason: str)。
    规则(静态红队P1):
      1) 含否定/犹豫词(不好/不可以/不行/不要确认/not ok/尚未确认/再等等/no/wait...)→ 一律拒绝;
      2) 只接受明确确认词——多字确认词做包含/词边界匹配; 单字或短英文词(好/行/嗯/ok/y)
         只在『整句短精确词』(去首尾标点后整句相等)时通过, 不做单字子串匹配。"""
    q = re.sub(r"\s+", " ", str(quote or "").strip())
    if re.search(r"(?:不|未|别|不要|尚未|还没)[^。，,；;。！？!?]{0,12}(?:确认|确定|同意|通过|可以)", q):
        return False, "原话含否定确认语义"
    compact = q.strip(_QUOTE_STRIP_CHARS)
    if not compact:
        return False, "确认为空"
    if re.search(r"[?？]", q) or re.search(r"(?:吗|呢|么|是不是|对不对|可以吗|确认吗)\s*$", compact):
        return False, "原话是疑问句，不构成明确确认"
    for w in _CONFIRM_NEGATION_ZH:
        if w in compact:
            return False, f"含否定/犹豫词『{w}』——用户尚未明确确认, 禁止置 confirmed"
    m = _CONFIRM_NEGATION_EN.search(compact)
    if m:
        return False, f"含否定/犹豫词『{m.group(0)}』——用户尚未明确确认, 禁止置 confirmed"
    low = compact.lower()
    if low in _CONFIRM_EXACT:
        return True, ""
    for w in _CONFIRM_CONTAIN_ZH:
        if w in compact:
            return True, ""
    if _CONFIRM_CONTAIN_EN.search(low):
        return True, ""
    return False, "未含明确确认词(确认/确定/好的/可以/没问题/ok/okay/yes...)"


def _now():
    return time.strftime("%Y-%m-%dT%H:%M:%S")


def _fail(code, msg):
    print(msg)
    raise SystemExit(code)


def _ensure_operation_record(target, operator_key, product_key, status, profile_version="", profile_sha="", invalidate_downstream=False):
    """产品档案同目录自动建立/更新标准 operation-record 状态；已有后续节点不倒退。"""
    op = Path(target).parent / "operation-record.md"
    if not op.exists():
        if not OPERATION_TEMPLATE.is_file():
            _fail(1, f"❌ 缺运行记录模板: {OPERATION_TEMPLATE}")
        text = OPERATION_TEMPLATE.read_text(encoding="utf-8")
        for token, value in (("${OPERATOR_KEY}", operator_key), ("${PRODUCT_KEY}", product_key)):
            text = text.replace(token, value)
        text = text.replace("status: S0", f"status: {status}")
        text = text.replace("next_state: S0a_PRODUCT_PROFILE", "next_state: S2" if status == "S1" else "next_state: S0a_PRODUCT_PROFILE")
        text = text.replace('profile_version: ""', f'profile_version: "{profile_version}"')
        text = text.replace('profile_sha256: ""', f'profile_sha256: "{profile_sha}"')
        op.write_text(text, encoding="utf-8")
        return
    text = op.read_text(encoding="utf-8")
    current = parse_frontmatter(op).get("status", "")
    if invalidate_downstream and current not in ("S0", "S0a_PRODUCT_PROFILE", "S1", ""):
        text = re.sub(r"(?m)^status:.*$", "status: ERROR_BLOCKED", text, count=1)
        text = re.sub(r"(?m)^next_state:.*$", "next_state: S2", text, count=1)
    elif current in ("S0", "S0a_PRODUCT_PROFILE", ""):
        text = re.sub(r"(?m)^status:.*$", f"status: {status}", text, count=1)
        text = re.sub(r"(?m)^next_state:.*$", "next_state: S2" if status == "S1" else "next_state: S0a_PRODUCT_PROFILE", text, count=1)
    if profile_version:
        text = re.sub(r'(?m)^profile_version:.*$', f'profile_version: "{profile_version}"', text, count=1)
    if profile_sha:
        text = re.sub(r'(?m)^profile_sha256:.*$', f'profile_sha256: "{profile_sha}"', text, count=1)
    op.write_text(text, encoding="utf-8")


def cmd_init(args):
    """从 runs/_template/product-profile.md 渲染 frontmatter 并落盘; 已存在不覆盖(exit 3)。"""
    target = Path(args.profile)
    if target.exists():
        _fail(3, f"❌ 档案已存在, 不覆盖(如需重建请人工处理): {target} (exit 3)")
    if not TEMPLATE.is_file():
        _fail(1, f"❌ 模板缺失: {TEMPLATE}")
    if not args.operator_key.strip() or not args.product_key.strip():
        _fail(2, "❌ --operator-key/--product-key 不能为空 (exit 2)")
    status = "declined" if args.declined else "draft"
    text = TEMPLATE.read_text(encoding="utf-8")
    for token, val in (("${OPERATOR_KEY}", args.operator_key.strip()),
                       ("${PRODUCT_KEY}", args.product_key.strip()),
                       ("${CREATED_AT}", _now()), ("${UPDATED_AT}", _now()),
                       ("${STATUS}", status),
                       ("${SOURCES_STATUS}", "declined" if args.declined else "requested")):
        text = text.replace(token, val)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")
    _ensure_operation_record(target, args.operator_key.strip(), args.product_key.strip(),
                             "S1" if args.declined else "S0a_PRODUCT_PROFILE", profile_version="1")
    issues = validate_product_profile(target, require_confirmed=False)
    print(f"✅ 已建档: {target} (status={status})")
    if issues:
        for i in issues:
            print(f"   ⚠️ {i}")
        _fail(2, "❌ 渲染结果未过结构校验(模板与校验器不一致, 须修复) (exit 2)")
    print(f"   下一步: AI 填 8 字段 → 用户拍板 → confirm --profile ... --by <纯昵称> --quote <原话>")
    return 0


def _safe_frontmatter_value(value, max_len=500):
    """把用户原话安全收进单行 frontmatter，防换行注入新键；保留审计语义但限制长度。"""
    return " ".join(str(value).replace("\r", " ").replace("\n", " ").split())[:max_len]


def _append_change_record(body, when, action, summary):
    """在正文的 append-only 变更表末尾追加一行；不改写历史行。"""
    line = f"| {when} | {action} | {summary} |"
    if not body.endswith("\n"):
        body += "\n"
    return body + line + "\n"


def _rewrite_frontmatter(path, updates, body_override=None):
    """只改 frontmatter 字段、正文逐字保留。updates: {key: 新值}。"""
    text = Path(path).read_text(encoding="utf-8")
    fm_lines, body = split_markdown(text)
    if not fm_lines:
        _fail(2, f"❌ 无机读 frontmatter, 无法更新: {path} (exit 2)")
    seen, new_lines = set(), []
    for line in fm_lines:
        s = line.strip()
        if s and not s.startswith("#") and ":" in s:
            key = s.partition(":")[0].strip()
            if key in updates:
                new_lines.append(f"{key}: {updates[key]}")
                seen.add(key)
                continue
        new_lines.append(line)
    for key, val in updates.items():  # 原文件缺的字段补到块尾
        if key not in seen:
            new_lines.append(f"{key}: {val}")
    out_body = body if body_override is None else body_override
    out = "---\n" + "\n".join(new_lines) + "\n---\n" + out_body
    Path(path).write_text(out, encoding="utf-8")


def cmd_confirm(args):
    """把 draft/declined 档案置为 confirmed: 记 confirmed_by(纯昵称)/confirmed_at/quote,
    content_sha256 对正文稳定计算; 正文逐字保留。"""
    p = Path(args.profile)
    if not p.is_file():
        _fail(2, f"❌ 档案不存在: {p} (先 init) (exit 2)")
    ok, why = validate_nickname(args.by)
    if not ok:
        _fail(2, f"❌ --by 不是纯昵称({args.by}): {why}——签名只能是纯个人昵称 (exit 2)")
    quote = (args.quote or "").strip()
    if not quote:
        _fail(2, "❌ --quote 不能为空(须为用户确认原话, 含确认词如 确认/好的/可以/ok) (exit 2)")
    ok, why = check_confirm_quote(quote)
    if not ok:
        _fail(2, f"❌ --quote 不是明确确认({why}): {quote[:60]} (exit 2)")
    tp = detect_third_party_contact(quote, label="--quote")
    if tp:
        for t in tp:
            print(f"   ❌ {t}")
        _fail(2, "❌ --quote 含第三方联系方式(邮箱/电话/清单)——确认原话会写入档案审计字段, 联系方式只放运营方档案 contact_email (exit 2)")
    meta, body = read_profile(p)
    issues = validate_product_profile(p, require_confirmed=False)
    # 豁免两类"confirm 本身会重算/重写"的失配, 其余结构/来源值域/第三方信息问题仍阻断:
    #  1) 已确认档案允许"正文已更新→重新确认"(旧 content_sha256 失配);
    #  2) draft 填完 8 字段后 frontmatter 的 sources_* 尚未同步——confirm 会按字段实际重算并写回。
    issues = [i for i in issues
              if not (meta.get("status") == "confirmed" and "content_sha256 与正文不匹配" in i)
              and "与字段实际不一致" not in i]
    if issues:
        for i in issues:
            print(f"   ❌ {i}")
        _fail(2, f"❌ 档案结构未过校验, 先修复再 confirm (exit 2)")
    now = _now()
    try:
        old_version = int(meta.get("profile_version", "1"))
    except ValueError:
        _fail(2, f"❌ profile_version 非整数: {meta.get('profile_version')!r} (exit 2)")
    was_confirmed = meta.get("status") == "confirmed"
    new_version = old_version + 1 if was_confirmed else old_version
    safe_quote = _safe_frontmatter_value(quote)
    summary = _safe_frontmatter_value(args.summary or "用户确认当前8字段与来源", max_len=160).replace("|", "/")
    body_with_log = _append_change_record(body, now, f"confirm v{new_version}", summary)
    _rewrite_frontmatter(p, {"profile_version": str(new_version), "status": "confirmed", "updated_at": now,
                             "confirmed_at": now, "confirmed_by": args.by.strip(),
                             "confirm_quote": safe_quote, "content_sha256": ""}, body_override=body_with_log)
    facts = profile_field_facts(p)
    provided = [n for n, f in sorted(facts.items())
                if f.get("content") not in ("", "（待补）", "待补")
                and f.get("source", "").lower() not in ("", "none", "推断")]
    inferred = [n for n, f in sorted(facts.items())
                if f.get("content") not in ("", "（待补）", "待补")
                and f.get("source", "").lower() == "推断"]
    # 与 validate_product_profile 的 sources 一致性口径对齐(静态红队P1)
    if len(provided) == 8:
        sources_status = "provided"
    elif provided or inferred:
        sources_status = "partial"
    else:
        sources_status = "declined" if meta.get("sources_status") == "declined" else "requested"
    sources_present = "yes" if len(provided) == 8 else ("partial" if provided or inferred else "no")
    _rewrite_frontmatter(p, {"sources_status": sources_status, "sources_present": sources_present})
    body_hash = content_sha256(p)
    _rewrite_frontmatter(p, {"content_sha256": body_hash})
    # 复核: 正文 hash 与新版本/变更记录一起锁定，且新状态过校验
    meta, _ = read_profile(p)
    if meta.get("content_sha256") != body_hash or content_sha256(p) != body_hash:
        _fail(1, f"❌ confirm 写入异常(正文哈希失配), 请检查文件 (exit 1)")
    issues = validate_product_profile(p, require_confirmed=True)
    if issues:
        for i in issues:
            print(f"   ❌ {i}")
        _fail(2, "❌ confirm 后仍未过 confirmed 校验 (exit 2)")
    final_sha = profile_sha256(p)
    _ensure_operation_record(p, meta.get("operator_key", ""), meta.get("product_key", ""),
                             "S1", profile_version=str(new_version), profile_sha=final_sha,
                             invalidate_downstream=True)
    print(f"✅ 已确认: {p} (status=confirmed, version={new_version}, confirmed_by={args.by.strip()}, content_sha256={body_hash[:12]}...)")
    return 0


def cmd_decline(args):
    p = Path(args.profile)
    if not p.is_file(): _fail(2, f"❌ 档案不存在: {p}")
    quote = " ".join(str(args.quote or "").split())
    if not any(w in quote for w in ("跳过", "不提供", "拒绝提供", "暂不提供")):
        _fail(2, "❌ decline须提供用户明确跳过/不提供资料的原话")
    meta, body = read_profile(p)
    now = _now(); version = int(meta.get("profile_version", "1")) + (1 if meta.get("status") == "confirmed" else 0)
    body = re.sub(r"(?m)^- 内容：.*$", "- 内容：（待补）", body)
    body = re.sub(r"(?m)^- source:.*$", "- source: none", body)
    body = re.sub(r"(?m)^- confidence:.*$", "- confidence: low", body)
    body = _append_change_record(body, now, f"decline v{version}", _safe_frontmatter_value(args.summary or quote,160).replace("|","/"))
    _rewrite_frontmatter(p, {"profile_version": str(version), "status": "declined", "updated_at": now,
                             "confirmed_at": "", "confirmed_by": "", "confirm_quote": _safe_frontmatter_value(quote),
                             "content_sha256": "", "sources_status": "declined", "sources_present": "no"}, body_override=body)
    _ensure_operation_record(p, meta.get("operator_key", ""), meta.get("product_key", ""), "S1",
                             profile_version=str(version), profile_sha=profile_sha256(p), invalidate_downstream=True)
    print(f"✅ 已记录用户跳过/撤回产品资料: {p} (status=declined, version={version}); 下游产物已失效需重审")
    return 0


def cmd_validate(args):
    p = Path(args.profile)
    issues = validate_product_profile(p, require_confirmed=args.require_confirmed)
    if issues:
        for i in issues:
            print(f"❌ {i}")
        print(f"档案校验未通过: {p} (exit 2)")
        raise SystemExit(2)
    meta = parse_frontmatter(p)
    print(f"✅ 档案校验通过: {p} (status={meta.get('status')}, sha256={profile_sha256(p)[:12]}...)")
    return 0


def cmd_status(args):
    p = Path(args.profile)
    if not p.is_file():
        _fail(2, f"❌ 档案不存在: {p} (exit 2)")
    meta, _ = read_profile(p)
    print(f"profile: {p}")
    print(f"status: {meta.get('status', '(缺)')}")
    print(f"sources_status: {meta.get('sources_status', '(缺)')} | sources_present: {meta.get('sources_present', '(缺)')}")
    print(f"operator_key: {meta.get('operator_key', '(缺)')} | product_key: {meta.get('product_key', '(缺)')}")
    print(f"created_at: {meta.get('created_at', '(缺)')} | updated_at: {meta.get('updated_at', '(缺)')}")
    print(f"confirmed_at: {meta.get('confirmed_at', '') or '(未确认)'} | confirmed_by: {meta.get('confirmed_by', '') or '(未确认)'}")
    print(f"profile_sha256: {profile_sha256(p)}")
    print(f"content_sha256: {content_sha256(p)}")
    return 0


def main():
    ap = argparse.ArgumentParser(description="产品档案管理 CLI(本地写操作, 不调用平台)——见文件头 docstring")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sp = sub.add_parser("init", help="从 runs/_template/product-profile.md 建档(不覆盖已有, exit 3)")
    sp.add_argument("--profile", required=True, help="档案路径: runs/<operator_key>/<product_key>/product-profile.md")
    sp.add_argument("--operator-key", required=True, help="运营方标识(= runs/<运营方>/ 目录名)")
    sp.add_argument("--product-key", required=True, help="产品标识(= runs/<运营方>/<产品>/ 目录名)")
    sp.add_argument("--declined", action="store_true", help="用户明确拒绝提供资料→仍建档但 status=declined(可用无具体事实的通用计划)")
    sp.set_defaults(fn=cmd_init)
    sp = sub.add_parser("decline", help="用户明确跳过/撤回产品资料→status=declined；清空当前事实并使下游失效")
    sp.add_argument("--profile", required=True)
    sp.add_argument("--quote", required=True, help="须含跳过/不提供/拒绝提供/暂不提供")
    sp.add_argument("--summary", default="")
    sp.set_defaults(fn=cmd_decline)
    sp = sub.add_parser("validate", help="结构校验(退出码 0 通过 / 2 未通过)")
    sp.add_argument("--profile", required=True)
    sp.add_argument("--require-confirmed", action="store_true", help="额外要求 status=confirmed")
    sp.set_defaults(fn=cmd_validate)
    sp = sub.add_parser("confirm", help="用户拍板→status=confirmed；已确认档案正文更新后再次 confirm 会递增 profile_version 并追加变更记录")
    sp.add_argument("--profile", required=True)
    sp.add_argument("--by", required=True, help="确认人=纯个人昵称(过 validate_nickname, 如 Tony/Iris)")
    sp.add_argument("--quote", required=True, help="用户确认原话(须含确认词: 确认/好的/可以/ok/yes...；会清理换行后写入审计字段)")
    sp.add_argument("--summary", default="", help="本次档案变更摘要(追加到变更记录；如 新增ISO证书和MOQ来源)")
    sp.set_defaults(fn=cmd_confirm)
    sp = sub.add_parser("status", help="打印档案状态/哈希")
    sp.add_argument("--profile", required=True)
    sp.set_defaults(fn=cmd_status)
    args = ap.parse_args()
    raise SystemExit(args.fn(args) or 0)


if __name__ == "__main__":
    main()
