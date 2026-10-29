#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""一页公司全明细只读报告：collect 抓单页列表+逐家真实详情，render 结合 AI 判断渲染一页 Markdown。

链路（全程只读，不写平台任何数据）：
  1) collect：POST refine/company-list 单页（pageSize=10、四区排除 filters、logic=and、
     关键词原样透传不偷换）；列表项无 domain 字段 → 用每条原始 id 逐个 POST
     domain/base-info 取真实域名与详情。禁止拿公司名猜域名；一页最多 10 个详情请求，
     单条失败记 detail_status=failed / 无安全域名记 no_domain，不弃整页、不造客户。
  ★R2 加固：一切 HTTP 3xx 重定向就地拒绝（绝不携带 accesstoken/uid 跟随任何转发，
     列表重定向→exit 2 不产文件，详情重定向→仅该行 failed）；--page 非整数/0/负数与
     --exclude 缺四区(CN/TW/HK/MO) 在任何请求与凭据读取之前 exit 2；列表单页返回 >10
     条视为平台结构异常，exit 2 不截断不产文件；详情返回 id/company_id/_id 与请求 id
     矛盾记 id_mismatch（URL=未知，绝不嫁接别家 domain/中文/规模）；name/country/size/
     summary 字段类型非法一律记「未知」，不 str() 成 repr；来源 JSON 落真实 request
     （keyword/current/pageSize/filters/logic）与 canonical scope_sha256（无凭据），
     render 重验参数与 scope_sha256；platform_total 真实非负 int 才落数值，否则
     "unknown"，与本页实际条数分开。
  2) AI 判断：读 collect 输出的脱敏 JSON（完整中文描述、无凭据），逐行给出
     matched/reason/suggestion，整体绑定 source_sha256，另存判定 JSON。
  3) render：先校验判定与来源逐行绑定（错哈希/漏判/外来 id/重复/空白或全英文理由/
     夹带 score 字段/来源无中文却代判 一律拒绝），再渲染：公司/国家/可点击官网/
     规模或未知/是否潜在买家/逐家中文理由与建议。工具不做关键词评分、不代替 AI 理解。

凭据通道（与既有工具同口径，不新增）：--credentials-stdin（stdin 两行，由
credential_input.parse_credentials 严格解析）或 --from-session（session_store 本机会话）。
API 地址由 api_base_url 固定为生产域名；测试替身经 --api-context 注入，且仅接受
http loopback+端口（api_base_url.install_from_context 校验，远端一律拒绝）。
HTTP 全部走进程内 urllib（urlopen），凭据只进请求头，不进输出、不落盘。

用法：
  python3 tools/company_page_report.py collect --keyword "<买家类型 query_en 长句>" \
      --page 3 --credentials-stdin --out runs/company-page-p3.json   # stdin 贴两行凭据
  python3 tools/company_page_report.py collect --keyword "..." --page 3 \
      --from-session --out runs/company-page-p3.json
  # ↓ AI 补判断：逐行读 summary_zh，写 judge.json（见下方字段）
  python3 tools/company_page_report.py render --source runs/company-page-p3.json \
      --judgments judge.json --page-kind 候选页 --out report-p3.md

判定 JSON：{"source_sha256": "<来源文件里的值>", "judgments": [
  {"company_id": "<来源行 id>", "matched": true|false|null, "reason": "<中文理由>",
   "suggestion": "<中文建议>", "recommended": false}]}
  规则：来源 schema 为 company-page-source/2；matched=true/false 必须给非空中文
  reason 与 suggestion；来源行缺中文描述时
  只能 matched=null（留空理由）；recommended 仅允许标在 matched=true 且 AI 显式选中
  的一家；多余字段（含 _score 类）一律拒绝。
"""
def _utf8_stdout():
    import sys as _sys
    for _s in (_sys.stdout, _sys.stderr):
        try:
            _s.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
_utf8_stdout()
import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
import urllib.request
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))

import api_base_url
from credential_input import Invalid as CredentialInvalid, parse_credentials

PAGE_SIZE = 10
EXCLUDE_DEFAULT = "CN,TW,HK,MO"
SCHEMA = "company-page-source/2"
SOURCE_KIND = "refine/company-list+domain/base-info"
_ALLOWED_JUDGE_KEYS = {"company_id", "matched", "reason", "suggestion", "recommended"}
_CJK = re.compile(r"[\u4e00-\u9fff]")
_DOMAIN = re.compile(r"^[a-z0-9]([a-z0-9-]*[a-z0-9])?(\.[a-z0-9]([a-z0-9-]*[a-z0-9])?)+$")


class CollectError(RuntimeError):
    """collect 阶段致命错误（列表失败/行结构非法）：exit 2，不产出文件。"""


def _canonical(obj):
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _sha256_text(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _safe_site(domain):
    """域名 → (domain, https url)。非 hostname 形态（注入/换行/伪协议）一律判不安全。"""
    if not isinstance(domain, str):
        return "", ""
    d = domain.strip().lower()
    if not d or not _DOMAIN.match(d) or len(d) > 253:
        return "", ""
    return d, "https://" + d


def _gate():
    try:
        from startup_gate import enforce_cli_startup
        enforce_cli_startup()
    except ImportError:
        pass
    except Exception:
        sys.stderr.write("还差一步：请先告诉我怎么称呼您、主要卖什么产品，登记后我马上继续（不是你的账号问题）。\n")
        raise SystemExit(2)


def _load_credentials(args):
    if args.credentials_stdin:
        blob = sys.stdin.read()
        try:
            return parse_credentials(blob)
        except CredentialInvalid as exc:
            sys.stderr.write("❌ 凭据格式不对：%s\n" % exc)
            raise SystemExit(2)
    if args.from_session:
        try:
            from session_store import load_ready
            _host, token, org = load_ready(ROOT)
            return token, org
        except Exception as exc:
            sys.stderr.write("❌ 读取本机会话失败：%s\n" % exc)
            raise SystemExit(2)
    sys.stderr.write("❌ 凭据只能 --credentials-stdin（stdin 两行）或 --from-session（本机会话）。\n")
    raise SystemExit(2)


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """一切 3xx 就地报错：绝不携带 accesstoken/uid 跟随转发（含同基址跳转）。"""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise HTTPError(newurl, code, "禁止重定向（%s）" % code, headers, fp)


_OPENER = urllib.request.build_opener(_NoRedirect)


def _http_json(path, token, org, payload, timeout=30):
    from tag_write_guard import check_send
    check_send(path, payload)
    req = Request(api_base_url.api_url(path), data=json.dumps(payload).encode("utf-8"),
                  headers={"Content-Type": "application/json", "accesstoken": token, "uid": org},
                  method="POST")
    with _OPENER.open(req, timeout=timeout) as resp:
        raw = resp.read()
    doc = json.loads(raw.decode("utf-8", errors="replace"))
    if not isinstance(doc, dict):
        raise ValueError("返回不是 JSON 对象")
    return doc


MANDATORY_EXCLUDE = frozenset(("CN", "TW", "HK", "MO"))


def _parse_page(raw):
    """--page 严格正整数校验：非数字/0/负/小数在任何 HTTP 与凭据读取之前 exit 2。"""
    text = str(raw or "").strip()
    if not text.isdigit() or int(text) < 1:
        sys.stderr.write("❌ --page 必须是 ≥1 的整数（收到：%r）\n" % text)
        raise SystemExit(2)
    return int(text)


def _exclude_values(exclude):
    """解析 --exclude：必排除四区只能增补不能缺/清空，违者在任何请求前 exit 2。"""
    values = []
    for part in str(exclude or "").split(","):
        v = part.strip().upper()
        if v and v not in values:
            values.append(v)
    missing = sorted(MANDATORY_EXCLUDE - set(values))
    if missing:
        sys.stderr.write("❌ --exclude 缺必排除四区（CN/TW/HK/MO）：%s；只准在四区基础上增补，不得清空或漏排\n"
                         % ",".join(missing))
        raise SystemExit(2)
    return values


def _exclude_filters(values):
    return [{"property": "country_code", "operator": "exclude", "value": "",
             "values": list(values), "valueType": "select"}]


def _text_field(value, fallback="未知"):
    """文本字段类型安全：只有非空 str 可用；dict/list/bool/数字一律未知，不 str() 成 repr。"""
    return value.strip() if isinstance(value, str) and value.strip() else fallback


def _size_field(value):
    if isinstance(value, bool):
        return "未知"
    if isinstance(value, int) and value >= 0:
        return str(value)
    if isinstance(value, float) and value >= 0 and value.is_integer():
        return str(int(value))
    if isinstance(value, str) and value.strip().isdigit():
        return value.strip()
    return "未知"


def _fetch_page(token, org, request):
    doc = _http_json("refine/company-list", token, org, request)
    if doc.get("success") is False:
        raise CollectError("列表接口返回失败：%s" % (doc.get("message") or "success=false"))
    data = doc.get("data")
    lst = data.get("list") if isinstance(data, dict) else None
    if not isinstance(lst, list):
        raise CollectError("列表接口返回缺 data.list")
    total = data.get("total") if isinstance(data, dict) else None
    if isinstance(total, bool) or not isinstance(total, int) or total < 0:
        total = "unknown"
    if len(lst) > PAGE_SIZE:
        raise CollectError("列表接口单页返回 %d 条（>10）属平台结构异常：完整页不得静默截断，本次拒绝产出" % len(lst))
    return lst, total


def _row_basics(item, index):
    if not isinstance(item, dict):
        raise CollectError("第 %d 条不是对象" % index)
    cid = item.get("id")
    if not isinstance(cid, str) or not cid.strip():
        raise CollectError("第 %d 条缺 id，无法取真实详情（禁止拿公司名猜域名）" % index)
    return cid.strip()


def _detail_row(item, cid):
    zh = item.get("summary_zh")
    return {
        "company_id": cid,
        "company_name": _text_field(item.get("company_name")),
        "country_code": _text_field(item.get("country_code")),
        "summary_zh": zh if isinstance(zh, str) else "",
        "size": _size_field(item.get("employee_count")),
        "domain": "", "url": "", "detail_status": "failed", "detail_sha256": "",
    }


def _apply_detail(row, doc):
    data = doc.get("data") if isinstance(doc, dict) else None
    if not isinstance(data, dict) or doc.get("success") is False:
        return row  # 保持 failed
    aliases = [data.get(k) for k in ("id", "company_id", "_id")]
    # 所有实际存在且非空的别名逐一核类型与原 cid：任何一个矛盾 → 别家公司，URL 未知，
    # 绝不嫁接 domain/中文/规模（只看第一个别名会漏 id 对、company_id/_id 错的错绑）。
    for rid in aliases:
        if rid is None or rid == "":
            continue
        if not isinstance(rid, str) or rid != row["company_id"]:
            row["detail_status"] = "id_mismatch"
            return row
    row["detail_sha256"] = _sha256_text(_canonical(data))
    domain, url = _safe_site(data.get("domain"))
    zh = data.get("summary_zh")
    if isinstance(zh, str) and zh.strip() and not row["summary_zh"].strip():
        row["summary_zh"] = zh  # 列表缺中文时用详情中文补，仍无则保持空
    if row["size"] == "未知":
        row["size"] = _size_field(data.get("employee_count"))
    if not domain:
        row["detail_status"] = "no_domain"
        return row
    row["domain"], row["url"], row["detail_status"] = domain, url, "ok"
    return row


def cmd_collect(args):
    _gate()
    page = _parse_page(args.page)
    excludes = _exclude_values(args.exclude)
    if args.api_context:
        try:
            api_base_url.install_from_context(args.api_context)
        except Exception as exc:
            sys.stderr.write("❌ 测试替身地址非法（仅允许 http loopback+端口）：%s\n" % exc)
            raise SystemExit(2)
    token, org = _load_credentials(args)
    request = {"keyword": args.keyword, "current": page, "pageSize": PAGE_SIZE,
               "filters": _exclude_filters(excludes), "logic": "and"}
    try:
        lst, platform_total = _fetch_page(token, org, request)
    except (HTTPError, URLError, OSError, ValueError) as exc:
        sys.stderr.write("❌ 列表请求失败（本次不产出任何文件）：%s\n" % exc)
        raise SystemExit(2)
    except CollectError as exc:
        sys.stderr.write("❌ %s\n" % exc)
        raise SystemExit(2)
    seen, rows = set(), []
    try:
        for i, item in enumerate(lst[:PAGE_SIZE], 1):
            cid = _row_basics(item, i)
            if cid in seen:
                raise CollectError("第 %d 条 id 重复（%s…）：平台数据异常，拒绝产出" % (i, cid[:8]))
            seen.add(cid)
            rows.append(_detail_row(item, cid))
    except CollectError as exc:
        sys.stderr.write("❌ %s\n" % exc)
        raise SystemExit(2)
    for row in rows:
        try:
            doc = _http_json("domain/base-info", token, org, {"domain": row["company_id"]})
        except (HTTPError, URLError, OSError, ValueError):
            continue  # 单条失败保持 failed，不弃整页
        _apply_detail(row, doc)
    ok = sum(1 for r in rows if r["detail_status"] == "ok")
    doc_out = {
        "schema": SCHEMA, "source_kind": SOURCE_KIND, "page": page, "keyword": args.keyword,
        "row_count": len(rows), "requested_page_size": PAGE_SIZE,
        "request": request,
        "platform_total": platform_total,
        "provenance": {"list_api": "refine/company-list", "detail_api": "domain/base-info",
                       "detail_ok": ok, "detail_failed": len(rows) - ok,
                       "live_note": "本哈希只绑定本文件内容，不证明平台实时状态"},
        "rows": rows,
    }
    doc_out["scope_sha256"] = _sha256_text(_canonical(request))
    doc_out["source_sha256"] = _sha256_text(_canonical(doc_out))
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(doc_out, ensure_ascii=False, indent=1), encoding="utf-8")
    failed = len(rows) - ok
    print("✅ 已取第 %d 页：平台实际返回 %d 条（不造客户），逐家详情成功 %d、失败 %d（失败行网址=未知）。" % (
        page, len(rows), ok, failed))
    print("   来源链：refine/company-list 单页 → 逐条原始 id → domain/base-info 真实域名。")
    print("   下一步（AI）：逐行读 %s 的 summary_zh 判断是否潜在买家，写判定 JSON（绑定 source_sha256 与逐行 company_id），再跑 render。" % out)
    print("   已写入：%s" % out)


def _die(msg):
    sys.stderr.write("❌ %s\n" % msg)
    raise SystemExit(2)


def _load_json(path, what):
    try:
        doc = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        _die("%s 读取失败：%s" % (what, exc))
    if not isinstance(doc, dict):
        _die("%s 必须是 JSON 对象" % what)
    return doc


def _check_hash(doc):
    stored = doc.get("source_sha256")
    core = {k: doc.get(k) for k in ("schema", "source_kind", "page", "keyword", "row_count",
                                    "requested_page_size", "request", "scope_sha256",
                                    "platform_total", "provenance", "rows")}
    if not isinstance(stored, str) or stored != _sha256_text(_canonical(core)):
        _die("source_sha256 不符：来源文件被改动或非本工具产出，拒绝渲染")


def _check_scope(doc):
    """重验真实查询范围：scope_sha256 重算 + request 参数逐项对口径，防自报字段被单点篡改。"""
    req = doc.get("request")
    if not isinstance(req, dict):
        _die("来源缺 request 查询范围（真实 scope），拒绝渲染")
    if doc.get("scope_sha256") != _sha256_text(_canonical(req)):
        _die("scope_sha256 不符：查询范围被篡改或非本工具产出，拒绝渲染")
    page = doc.get("page")
    if not isinstance(page, int) or isinstance(page, bool) or page < 1:
        _die("来源 page 非法，拒绝渲染")
    if req.get("current") != page or req.get("pageSize") != PAGE_SIZE or req.get("logic") != "and":
        _die("request 查询参数与工具固定口径（pageSize=10/logic=and/页码一致）不符，拒绝渲染")
    if req.get("keyword") != doc.get("keyword"):
        _die("request.keyword 与来源 keyword 不一致，拒绝渲染")
    filters = req.get("filters")
    if not isinstance(filters, list) or len(filters) != 1 or not isinstance(filters[0], dict):
        _die("request.filters 结构异常，拒绝渲染")
    f = filters[0]
    values = f.get("values")
    if (f.get("property") != "country_code" or f.get("operator") != "exclude"
            or not isinstance(values, list) or not MANDATORY_EXCLUDE <= set(values)):
        _die("request.filters 缺必排除四区（CN/TW/HK/MO），拒绝渲染")


def _check_judgments(jud, doc):
    if jud.get("source_sha256") != doc.get("source_sha256"):
        _die("source_sha256 不符：判定文件与来源不匹配（必须绑定同一来源）")
    rows = doc["rows"]
    by_id = {r["company_id"]: r for r in rows}
    items = jud.get("judgments")
    if not isinstance(items, list):
        _die("判定文件缺 judgments 数组")
    ids, seen = [], set()
    for j in items:
        if not isinstance(j, dict):
            _die("judgment 必须是对象")
        cid = j.get("company_id")
        if not isinstance(cid, str) or not cid:
            _die("judgment 缺 company_id")
        extra = sorted(set(j) - _ALLOWED_JUDGE_KEYS)
        if extra:
            _die("judgment 含非法字段 %s：只允许 company_id/matched/reason/suggestion/recommended（禁止夹带 score 类评分）" % extra)
        if cid in seen:
            _die("判定重复：company_id=%s… 出现多次" % cid[:8])
        seen.add(cid)
        ids.append((cid, j))
    foreign = [c for c, _ in ids if c not in by_id]
    if foreign:
        _die("外来 company_id：判定含来源不存在的 id（%s…），拒绝整份" % foreign[0][:8])
    if len(ids) != len(rows):
        _die("漏判：来源共 %d 行，判定只有 %d 行；必须覆盖全部源行才输出完整报告" % (len(rows), len(ids)))
    for cid, j in ids:
        row, matched = by_id[cid], j.get("matched")
        if matched not in (True, False, None):
            _die("matched 只能是 true/false/null（company_id=%s…）" % cid[:8])
        reason, sugg = j.get("reason", ""), j.get("suggestion", "")
        if not isinstance(reason, str) or not isinstance(sugg, str):
            _die("reason/suggestion 必须是字符串（company_id=%s…）" % cid[:8])
        if matched is None:
            if reason.strip() or sugg.strip():
                _die("matched=null 时不得填理由或建议（company_id=%s…）" % cid[:8])
            if row["summary_zh"].strip():
                _die("来源有中文描述却 matched=null：请 AI 先读中文描述再判断（company_id=%s…）" % cid[:8])
            continue
        if not row["summary_zh"].strip():
            _die("来源无中文描述，只能 matched=null（不得代判，company_id=%s…）" % cid[:8])
        for name, text in (("reason", reason), ("suggestion", sugg)):
            if not text.strip():
                _die("matched=%s 必须给出非空 %s（company_id=%s…）" % (
                    "true" if matched else "false", name, cid[:8]))
            if not _CJK.search(text):
                _die("%s 必须含中文，不能全英文（company_id=%s…）" % (name, cid[:8]))
    recs = [(cid, j) for cid, j in ids if j.get("recommended")]
    for cid, j in recs:
        if j.get("matched") is not True:
            _die("recommended 只能标在 matched=true 且 AI 显式选中的行（company_id=%s…）" % cid[:8])
    if len(recs) > 1:
        _die("最多一个 recommended：本页收到 %d 个，请 AI 只选一家" % len(recs))
    return dict(ids), (recs[0] if recs else None)


def _esc(text):
    return str(text or "").replace("|", "\\|").replace("\r", " ").replace("\n", " ").strip()


def _md(row, j):
    d, u = _safe_site(row.get("domain"))
    if not u:
        u = row.get("url") or ""
    link = "[%s](%s)" % (d, u) if u else "未知"
    return link


def cmd_render(args):
    doc = _load_json(args.source, "来源文件")
    if doc.get("schema") != SCHEMA:
        _die("来源 schema 不符：只接受 %s（先用 collect 产出）" % SCHEMA)
    _check_hash(doc)
    _check_scope(doc)
    jud = _load_json(args.judgments, "判定文件")
    by_id, rec = _check_judgments(jud, doc)
    rows = doc["rows"]
    page, n = doc["page"], len(rows)
    lines = ["# 客户名单速览 · 第 %d 页（%s）" % (page, args.page_kind), ""]
    total = doc.get("platform_total")
    total_note = "平台总数 %s" % total if isinstance(total, int) else "平台总数未知"
    lines.append("本页共 %d 家（平台本页实际返回 %d 条，不足 10 家按实际计，不造客户；%s，与本页实际条数分开计）。" % (
        n, n, total_note))
    lines.append("")
    lines.append("| # | 公司 | 国家 | 官网 | 规模 | 是否潜在买家 | 最推荐 |")
    lines.append("|---|---|---|---|---|---|---|")
    for i, r in enumerate(rows, 1):
        j = by_id[r["company_id"]]
        matched = j.get("matched")
        verdict = "是" if matched is True else ("否" if matched is False else "待定")
        star = "⭐" if rec and r["company_id"] == rec[0] else ""
        lines.append("| %d | %s | %s | %s | %s | %s | %s |" % (
            i, _esc(r["company_name"]), _esc(r["country_code"]), _md(r, j),
            _esc(r["size"]) if r["size"] != "未知" else "未知", verdict, star))
    lines.append("")
    if rec:
        rr = next(r for r in rows if r["company_id"] == rec[0])
        lines.append("**最推荐：第 %d 家 %s** —— %s" % (
            rows.index(rr) + 1, _esc(rr["company_name"]), _esc(rec[1].get("reason"))))
    else:
        lines.append("本页没有可靠推荐（AI 未显式选中 matched=true 的一家，不强选）。")
    lines.append("")
    lines.append("## 逐家分析与建议")
    pending = sum(1 for r in rows if by_id[r["company_id"]].get("matched") is None)
    if pending:
        lines.append("")
        lines.append("> 提示：本页有 %d 家待 AI 判断（无中文描述或未判定），表中「待定」不代表否决。" % pending)
    for i, r in enumerate(rows, 1):
        j = by_id[r["company_id"]]
        matched = j.get("matched")
        lines.append("")
        lines.append("**%d. %s**（%s）" % (i, _esc(r["company_name"]), _esc(r["country_code"])))
        lines.append("- 官网：%s" % (_md(r, j) if _md(r, j) != "未知" else "未知（详情未取到）"))
        if matched is None:
            lines.append("- 判定：待 AI 判断")
            lines.append("- 理由：待 AI 判断（无中文描述，无法据此判断）")
            lines.append("- 建议：未知（先补判断）")
        else:
            lines.append("- 判定：%s潜在买家" % ("是" if matched else "不是"))
            lines.append("- 理由：%s" % _esc(j.get("reason")))
            lines.append("- 建议：%s" % _esc(j.get("suggestion")))
    lines.append("")
    lines.append("> 数据来源：平台客户列表第 %d 页（实际返回 %d 条）；官网为平台逐家详情返回的真实域名，缺网址按未知单列。" % (page, n))
    md = "\n".join(lines) + "\n"
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(md, encoding="utf-8")
    print(md)
    print("已写入：%s" % out)


def main():
    ap = argparse.ArgumentParser(description="一页公司全明细只读报告（collect→AI判断→render）")
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("collect", help="抓单页列表+逐家真实详情，产出脱敏来源 JSON")
    c.add_argument("--keyword", required=True, help="买家类型 query_en 长句（原样透传，不偷换）")
    c.add_argument("--page", default="1")
    c.add_argument("--out", required=True)
    c.add_argument("--exclude", default=EXCLUDE_DEFAULT, help="排除国家码（默认四区）")
    c.add_argument("--credentials-stdin", action="store_true", help="凭据走 stdin 两行")
    c.add_argument("--from-session", action="store_true", help="凭据读本机会话")
    c.add_argument("--api-context", default="", help="测试替身 context（仅 http loopback）")
    c.set_defaults(func=cmd_collect)
    r = sub.add_parser("render", help="校验 AI 判定并渲染一页 Markdown")
    r.add_argument("--source", required=True, help="collect 产出的来源 JSON")
    r.add_argument("--judgments", required=True, help="AI 判定 JSON（绑定 source_sha256）")
    r.add_argument("--page-kind", default="候选页", choices=["候选页", "临界页"])
    r.add_argument("--out", required=True)
    r.set_defaults(func=cmd_render)
    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
