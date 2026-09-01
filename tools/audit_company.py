#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
来发信 · 客户精准度审计工具（可复用、可审计）

用途：对 refine/company-list 搜索结果的每一页，逐条判定客户是否匹配目标产品，
      输出「判定 + 命中关键词 + 理由」，并按页统计精准度，找到 70% 临界页。

用法：
  python3 audit_company.py --query "..." --pages 500,700,800,900,950,980,990,999,1000 \
      --token "$TOKEN" --org <orgId> --mode strict --product "猫粮"

判定标准（写死在规则表里，不再主观漂移）：
  MATCH    = 客户业务是「会采购本产品的买家」（本产品：猫粮/宠物食品）
  REJECT   = 客户业务与「采购本产品」无关
  MARGINAL = 沾边但不确定（宠物行业但非食品 / 描述太模糊）

严格模式(mode=strict)：MATCH 才算精准
宽松模式(mode=loose) ：MATCH+MARGINAL 都算精准
"""
import argparse
import json
import re
import subprocess
import sys
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


def fetch(page, keyword, token, org, filters=None, page_size=10):
    payload = {
        "keyword": keyword,
        "current": page,
        "pageSize": page_size,
        "filters": filters or [],
        "logic": "and",
    }
    cmd = [
        "curl", "-sSL", "-X", "POST",
        f"https://web.laifaxin.com/api/refine/company-list?uid={org}",
        "-H", "Content-Type: application/json",
        "-H", f"accesstoken: {token}",
        "-d", json.dumps(payload),
    ]
    r = subprocess.run(cmd, capture_output=True, text=True)
    try:
        return json.loads(r.stdout).get("data", {})
    except Exception:
        return {}


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


def fetch_similar(domain, token, org):
    """调用 domain/similar-list 找相似"""
    payload = {"domain": domain}
    cmd = [
        "curl", "-sSL", "-X", "POST",
        f"https://web.laifaxin.com/api/domain/similar-list?uid={org}",
        "-H", "Content-Type: application/json",
        "-H", f"accesstoken: {token}",
        "-d", json.dumps(payload),
    ]
    r = subprocess.run(cmd, capture_output=True, text=True)
    try:
        return json.loads(r.stdout).get("data", {}).get("list", [])
    except Exception:
        return []


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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--query", required=True, help="搜索关键词")
    ap.add_argument("--pages", required=True, help="页码,逗号分隔,如 1,500,1000")
    ap.add_argument("--token", required=True)
    ap.add_argument("--org", required=True)
    ap.add_argument("--mode", default="moderate", choices=["strict", "moderate", "loose"],
                    help="匹配标准: strict=只算MATCH(采购方) / moderate=MATCH+MARGINAL(默认,含配件商/制造商) / loose=全算")
    ap.add_argument("--product", default="", help="产品名（仅用于展示）")
    ap.add_argument("--exclude", default="CN,TW,HK,MO", help="排除国家码,逗号分隔(★默认4区=RULES铁律0)")
    ap.add_argument("--domains", default="", help="域名找相似模式: 逗号分隔的种子域名")
    ap.add_argument("--match-words", default="", help="额外匹配词,逗号分隔(产品自定义)")
    args = ap.parse_args()

    # 设置额外匹配词（产品自定义）
    global EXTRA_MATCH
    EXTRA_MATCH = [w.strip().lower() for w in args.match_words.split(",") if w.strip()]

    exclude_set = {c.strip() for c in args.exclude.split(",") if c.strip()}
    filters = [{"property": "country_code", "operator": "exclude", "value": "", "values": list(exclude_set), "valueType": "select"}] if exclude_set else []

    print(f"# 产品: {args.product or '(未填)'} | 模式: {args.mode} | 排除国家: {args.exclude}")
    print(f"# 搜索词: {args.query[:80]}...")
    print(f"# 判定标准: MATCH=会采购本产品 | REJECT=无关 | MARGINAL=沾边\n")

    # ---- 域名找相似模式 ----
    if args.domains:
        for domain in [d.strip() for d in args.domains.split(",") if d.strip()]:
            lst = fetch_similar(domain, args.token, args.org)
            if not lst:
                print(f"===== 种子 {domain}: 无数据 =====")
                continue
            stats = Counter()
            print(f"===== 种子 {domain} -> 相似客户 (共{len(lst)}条) =====")
            for i, c in enumerate(lst, 1):
                verdict, reason = classify(c)
                stats[verdict] += 1
                print(f"  {i:2d}. [{verdict:8s}] {c.get('company_name','')[:38]:40s} "
                      f"{(c.get('country_code') or '-'):4s} {(c.get('client_focus') or '-'):4s} "
                      f"score={c.get('_score'):.2f} | {reason}")
            total = len(lst)
            if args.mode == "strict":
                acc = stats["MATCH"] / total * 100
            elif args.mode == "loose":
                acc = (stats["MATCH"] + stats["MARGINAL"] + stats["REJECT"]) / total * 100
            else:
                acc = (stats["MATCH"] + stats["MARGINAL"]) / total * 100
            print(f"  -> 本批: MATCH={stats['MATCH']} MARGINAL={stats['MARGINAL']} REJECT={stats['REJECT']}"
                  f" | 精准度({args.mode}) = {acc:.0f}%")
            print()
        return

    for page in [int(p) for p in args.pages.split(",")]:
        data = fetch(page, args.query, args.token, args.org, filters)
        lst = data.get("list", [])
        if not lst:
            print(f"===== 第 {page} 页: 无数据 =====")
            continue
        stats = Counter()
        print(f"===== 第 {page} 页 (共{len(lst)}条) =====")
        for i, c in enumerate(lst, 1):
            verdict, reason = classify(c)
            stats[verdict] += 1
            print(f"  {i:2d}. [{verdict:8s}] {c.get('company_name','')[:38]:40s} {(c.get('country_code') or '-'):4s} | {reason}")
        total = len(lst)
        if args.mode == "strict":
            acc = stats["MATCH"] / total * 100
        elif args.mode == "loose":
            acc = (stats["MATCH"] + stats["MARGINAL"] + stats["REJECT"]) / total * 100
        else:
            acc = (stats["MATCH"] + stats["MARGINAL"]) / total * 100
        print(f"  -> 本页: MATCH={stats['MATCH']} MARGINAL={stats['MARGINAL']} REJECT={stats['REJECT']}"
              f" | 精准度({args.mode}) = {acc:.0f}%")
        print()


if __name__ == "__main__":
    main()
