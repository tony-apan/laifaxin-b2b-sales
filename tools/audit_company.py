#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
来发信 · 客户精准度审计工具（可复用、可审计）

用途：对 refine/company-list 搜索结果的每一页，逐条判定客户是否匹配目标产品，
      输出「判定 + 命中关键词 + 理由」，并按页统计精准度，找到 70% 临界页。

用法：
  python3 audit_company.py --query "..." --pages 500,700,800,900,950,980,990,999,1000 \
      --token <TOKEN_IN_MEMORY> --org <ORG_IN_MEMORY> --mode strict --product "猫粮"
  python3 audit_company.py --domains "buyer.example,another.example" \
      --token <TOKEN_IN_MEMORY> --org <ORG_IN_MEMORY> --match-words "kayak,raft,充气"
  （TOKEN/ORG_IN_MEMORY 仅为主 AI 内存占位，不是让用户设置变量或执行命令）

★网络/HTTP 错误不再被吞（2026-10-23 修复）：401/403/422 与网络异常一律上抛并 exit 2，
  5xx 允许重试 ≤2；不再把错误响应当成「无数据」静默给 0% 结论。
★--domains 走 refine/company-list（keyword=该域名）——扩量不用相似列表接口
  （api-dictionary 口径），四区 filters 与普通审计一致。
★匹配率分母恒为该页实际返回条数（total）；旧 loose 把 REJECT 计入分子导致恒 100%，已修正。

判定标准：
  MATCH    = 客户业务是「会采购本产品的买家」
  REJECT   = 客户业务与「采购本产品」无关
  MARGINAL = 沾边但不确定（描述太模糊）

★产品词必须由调用方传入（2026-09-09 真机实测断点）：
  内置 STRONG_MATCH/STRONG_REJECT 是"宠物食品包装"这一品类的样例词表；
  换产品（如皮筏艇）时若不带产品词，内置词表完全不匹配 → 全页判 REJECT=0% 精准度。
  规则：`--match-words` 必须传本产品的中英词（品类/材质/形态/角色），
  未传且内置词表与 `--product` 不匹配时工具会**直接报错退出**，不再静默给 0%。

★判定口径以 `specs/threshold-method.md` 为准：正式 S4 收口要求 **AI 语义反思**（"这个买家会不会买"），
本工具只做**关键词趋势初筛**，临界页必须人工逐条读完整 10 条。

严格模式(mode=strict)  ：MATCH 才算精准（分母 = 该页实际返回条数）
中等模式(mode=moderate)：MATCH+MARGINAL 都算精准（默认）
宽松模式(mode=loose)   ：MATCH+MARGINAL 都算精准；旧实现把 REJECT 也计入分子（恒 100%）已废弃
"""

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
import json
import re
import subprocess
import sys
import time
from collections import Counter

# ============ 判定规则表（可维护，改这里即可） ============
# 强匹配词：客户业务明确是宠物食品/宠物用品的买家（零售/批发/分销/进口/电商）
STRONG_MATCH = [
    "cat food", "pet food", "feline", "pet nutrition", "animal feed",
    "pet supplies", "pet store", "pet shop", "pet retailer", "pet distributor",
    "pet wholesaler", "pet importer", "pet product", "pet brand",
    "pet care", "pet accessory", "pet ecommerce", "pet online",
    "宠物食品", "猫粮", "猫食品", "宠物用品", "宠物店", "宠物经销商", "宠物零售",
    "宠物批发", "宠物进口", "动物饲料", "宠物品牌", "宠物电商", "宠物专卖",
    "宠物连锁", "猫零食", "宠物零食", "pet groomer",  # 宠物美容常兼售粮
]

# 强排除词：明确与「采购猫粮」无关（即使属于宠物行业）
STRONG_REJECT = [
    # 宠物行业但非食品类
    "grooming equipment", "pet grooming equipment", "beauty tool", "apparel",
    "pet apparel", "pet fashion", "clothing", "pet clothing", "pet garment",
    "pet toy", "cat toy", "dog toy", "pet bed", "pet house", "pet furniture",
    "cat litter", "litter box", "pet cage", "pet bowl", "pet fountain",
    # 明确非宠物行业
    "restaurant", "food service", "grocery", "grocery wholesale", "catering",
    "home appliance", "electronics", "household goods", "general merchandise",
    "construction", "industrial", "agriculture machinery",
    # 其他
    "vet clinic terminal", "hospital", "school", "nonprofit",
    "餐饮", "杂货", "家电", "家居饰品", "通用商品", "建筑", "医院", "学校",
    "美容设备", "美容工具", "服饰", "服装", "玩具", "猫砂", "猫爬架", "猫窝",
    "宠物窝", "宠物家具", "宠物笼", "犬舍", "宠物美容", "美容服务",
    # ★ 媒体/杂志/评测/内容平台（不是采购方！用户明确）
    "magazine", "media", "news", "newsletter", "blog", "review", "journal",
    "media platform", "content publisher", "publication", "editorial",
    "杂志", "媒体", "新闻", "评测", "测评", "资讯", "内容平台", "内容发布",
    "出版商", "编辑部", "博客",
]

# 边缘词：沾边但不确定（宠物行业非食品为主 / 描述太泛）
MARGINAL_WORDS = [
    "pet", "cat", "dog", "animal", "veterinary", "vet", "kitten", "puppy",
    "宠物", "猫", "狗", "动物", "兽医", "兽药",
]


class AuditHTTPError(RuntimeError):
    """网络/HTTP 错误：必须向上报错并 exit 2，不得静默当成「无数据」。"""


CURL_STATUS_MARKER = "\n__HTTP_STATUS__:"


def _curl_json(cmd, what):
    from tag_write_guard import check_send
    check_send("refine/company-list", {})
    """执行 curl，返回 (payload, http_status)；网络失败/非 JSON/非对象 → AuditHTTPError。"""
    try:
        completed = subprocess.run(cmd, capture_output=True, text=True, timeout=60, encoding="utf-8", errors="replace")
    except (OSError, subprocess.SubprocessError) as exc:
        raise AuditHTTPError(f"{what} 网络请求失败：{exc}")
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "").strip()[:200]
        raise AuditHTTPError(f"{what} 网络请求失败（curl exit={completed.returncode}）：{detail}")
    raw = completed.stdout or ""
    status = None
    if CURL_STATUS_MARKER in raw:
        raw, _, status_text = raw.rpartition(CURL_STATUS_MARKER)
        try:
            status = int(status_text.strip())
        except ValueError:
            status = None
    try:
        payload = json.loads(raw.strip())
    except ValueError:
        raise AuditHTTPError(f"{what} 返回非JSON（HTTP {status if status is not None else '未知'}）：{raw.strip()[:200]}")
    if not isinstance(payload, dict):
        raise AuditHTTPError(f"{what} 返回结构异常（不是 JSON 对象）")
    return payload, status


def fetch(page, keyword, token, org, filters=None, page_size=10, retries=2):
    """只读搜客：POST refine/company-list。5xx 重试 ≤2；401/403/422/网络错误直接上抛。"""
    payload = {
        "keyword": keyword,
        "current": page,
        "pageSize": page_size,
        "filters": filters or [],
        "logic": "and",
    }
    cmd = [
        "curl", "-sSL", "-w", CURL_STATUS_MARKER + "%{http_code}", "-X", "POST",
        "https://web.laifaxin.com/api/refine/company-list",
        "-H", "Content-Type: application/json",
        "-H", f"accesstoken: {token}",
        "-H", f"uid: {org}",
        "-d", json.dumps(payload),
    ]
    last_error = None
    for attempt in range(retries + 1):
        try:
            result, status = _curl_json(cmd, f"第{page}页搜索")
        except AuditHTTPError as exc:
            last_error = exc
            if attempt < retries:
                time.sleep(0.5 * (attempt + 1))
                continue
            raise
        if status is not None and status >= 500:
            last_error = AuditHTTPError(f"第{page}页搜索 HTTP {status}（服务端错误）：{result.get('message') or ''}")
            if attempt < retries:
                time.sleep(0.5 * (attempt + 1))
                continue
            raise last_error
        if status is not None and status >= 400:
            raise AuditHTTPError(f"第{page}页搜索 HTTP {status}：{result.get('message') or 'HTTP 错误'}")
        if result.get("success") is False:
            raise AuditHTTPError(f"第{page}页搜索失败：{result.get('message') or '平台返回 success=false'}")
        data = result.get("data")
        if not isinstance(data, dict):
            raise AuditHTTPError(f"第{page}页搜索返回缺 data 对象：{str(result)[:200]}")
        return data
    raise last_error or AuditHTTPError(f"第{page}页搜索失败（未知原因）")


# 排除词中这些是"杂货/多品类"信号：命中即一票否决（即使命中匹配词），
# 因为描述里宠物用品只是其中一小类，客户不是专注猫粮/宠物食品的买家。
HARD_REJECT = [
    "home appliance", "electronics", "household goods", "general merchandise",
    "家居饰品", "家电", "杂货", "综合", "多品类",
    # ★ 服装/服饰/apparel/clothing/fashion 已移除——它们是行业正常商品（自行车店卖骑行服），不一票否决
]

# "服务于X"模式的宾语误判：描述写"服务于宠物店/宠物零售商"的是供应商，
# 不是买家。命中这些短语时应谨慎（由 serve_verb 检测）。
SERVE_TO = ["serve", "serving", "supply to", "supply for", "provide to",
            "服务于", "供应给", "提供给"]


def accuracy(stats, total, mode):
    """匹配率：分母恒为该页/该批实际返回条数（total）。

    旧 loose 用 (MATCH+MARGINAL+REJECT)/total —— 分子含全部桶，结构上恒 100%，已废弃；
    宽松口径不把 REJECT 算作匹配，分母按实际返回条数（尾页不足 10 条时照实算）。
    """
    total = int(total or 0)
    if total <= 0:
        return 0.0
    if mode == "strict":
        matched = stats["MATCH"]
    else:  # moderate / loose：MATCH+MARGINAL（宽松口径，不含 REJECT）
        matched = stats["MATCH"] + stats["MARGINAL"]
    return matched / total * 100


# 额外匹配词（--match-words 支持产品自定义，追加到 STRONG_MATCH）
EXTRA_MATCH = []


def classify(company):
    """返回 (判定, 命中的理由)"""
    zh = (company.get("summary_zh") or "").lower()
    en = (company.get("summary_en") or "").lower()
    name = (company.get("company_name") or "").lower()
    text = f"{zh} {en} {name}"

    match_pool = STRONG_MATCH + EXTRA_MATCH
    hit_match = [w for w in match_pool if w in text]
    hit_reject = [w for w in STRONG_REJECT if w in text]
    hit_hard = [w for w in HARD_REJECT if w in text]
    hit_marginal = [w for w in MARGINAL_WORDS if w in text]

    # 规则1：命中硬排除词（真杂货/家电/综合）且无产品匹配词 → 一票否决
    # （有产品词的客户即使含杂货词，也是行业零售商，不算杂货店）
    if hit_hard and not hit_match:
        return "REJECT", f"杂货/多品类排除词: {hit_hard[:3]}"
    # 规则2：命中强排除词且无强匹配词 → REJECT
    if hit_reject and not hit_match:
        return "REJECT", f"命中排除词: {hit_reject[:3]}"
    # 规则3：命中强匹配词 → 但需检查是否为"服务/供应给买家"的供应商（宾语误判）
    if hit_match:
        # 若是"服务于宠物店/供应给零售商"这类，且本身产品是猫薄荷/饲料原料等非成品猫粮，
        # 判 MARGINAL（由调用方结合上下文）；这里统一标 MARGINAL_SERVE 由人复核
        if any(s in text for s in SERVE_TO):
            return "MARGINAL", f"命中匹配词但疑似供应商模式(服务于X): {hit_match[:2]}"
        return "MATCH", f"命中匹配词: {hit_match[:3]}"
    # 规则4：只有边缘词 → MARGINAL
    if hit_marginal:
        return "MARGINAL", f"仅有边缘词: {hit_marginal[:3]}"
    # 规则5：什么都没有 → REJECT
    return "REJECT", "无任何相关描述"


def _print_semantic_rows(lst, unit="本页"):
    """语义模式只输出中文原文；缺中文的条目明确标记为不可判断，绝不拿英文冒充中文。"""
    usable = 0
    for i, c in enumerate(lst, 1):
        print(f"  {i:2d}. {c.get('company_name','')[:40]} | {c.get('country_code') or '-'}")
        zh = (c.get("summary_zh") or "").strip()
        if zh:
            print(f"      中文描述: {zh[:300]}")
            usable += 1
        else:
            print("      中文描述: （平台未返回中文，无法据此判断，请跳过或人工核）")
    print(f"  -> {unit}共{len(lst)}条，中文可用{usable}条，缺中文{len(lst)-usable}条；"
          f"只按中文可用条目逐条判断，不自动算精准度")
    print()


def _run(args, filters):
    # ---- 域名模式（★2026-10-23：改走 refine/company-list，keyword=域名；不用 similar-list）----
    if args.domains:
        for domain in [d.strip() for d in args.domains.split(",") if d.strip()]:
            lst = fetch(1, domain, args.token, args.org, filters).get("list", [])
            if not lst:
                print(f"===== 种子 {domain}: 无数据 =====")
                continue
            print(f"===== 种子 {domain}（keyword=域名，四区 filters）共{len(lst)}条 =====")
            _print_semantic_rows(lst, unit="本批")
        return

    for page in [int(p) for p in args.pages.split(",")]:
        data = fetch(page, args.query, args.token, args.org, filters)
        lst = data.get("list", [])
        if not lst:
            print(f"===== 第 {page} 页: 无数据 =====")
            continue
        print(f"===== 第 {page} 页 (共{len(lst)}条) =====")
        _print_semantic_rows(lst)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--query", default="", help="搜索关键词（--domains 模式下可省略）")
    ap.add_argument("--pages", default="", help="页码,逗号分隔,如 1,500,1000")
    ap.add_argument("--token", default="")
    ap.add_argument("--org", default="")
    ap.add_argument("--from-session", action="store_true", help="从本机会话读取凭据（免 argv 明文）")
    ap.add_argument("--mode", default="moderate", choices=["strict", "moderate", "loose"], help=argparse.SUPPRESS)
    ap.add_argument("--semantic", action="store_true",
                    help="语义模式：不跑关键词判定，逐条打印中文摘要，由 AI 直接判断是否潜在买家")
    ap.add_argument("--product", default="", help="产品名（仅用于展示）")
    ap.add_argument("--exclude", default="CN,TW,HK,MO", help="排除国家码,逗号分隔(★默认4区=RULES铁律0)")
    ap.add_argument("--domains", default="", help="域名模式: 逗号分隔的种子域名（作 refine/company-list 的 keyword）")
    ap.add_argument("--match-words", default="", help=argparse.SUPPRESS)
    args = ap.parse_args()
    if args.from_session:
        from session_store import load_ready
        _host, args.token, args.org = load_ready(__import__("pathlib").Path(__file__).resolve().parent.parent)
    if not args.token or not args.org:
        print("❌ 需要 --token/--org，或用 --from-session 读取本机会话")
        raise SystemExit(2)
    if args.domains and args.query:
        print("❌ --domains 与 --query 只能二选一（域名作关键词时不要同时给 --query）")
        raise SystemExit(2)
    if not args.domains and not args.pages:
        print("❌ 缺 --pages（页码，逗号分隔；或改用 --domains 域名模式）")
        raise SystemExit(2)

    exclude_set = {c.strip() for c in args.exclude.split(",") if c.strip()}
    filters = [{"property": "country_code", "operator": "exclude", "value": "", "values": list(exclude_set), "valueType": "select"}] if exclude_set else []

    print(f"# 产品: {args.product or '(未填)'} | 排除国家: {args.exclude}")
    print(f"# 搜索词: {(args.query or args.domains)[:80]}...")
    print("# 判定方式: 读中文描述直接判断，不用关键词、不算自动精准度\n")

    try:
        _run(args, filters)
    except AuditHTTPError as exc:
        print(f"❌ {exc}")
        print("   网络/HTTP 错误已终止本次审计：不产出匹配率结论，也不写任何文件。")
        print("   处置：401/403=钥匙或工作空间失效，需重新一键复制两行；422=参数问题；5xx/超时已重试仍失败则稍后再试。")
        raise SystemExit(2)


if __name__ == "__main__":
    main()
