#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""★S3 种子域名解析（只读）：候选公司名 → 反查真实域名 → 供 refine/company-list 搜相似。
★为什么需要：refine/company-list 返回的公司【无 domain 字段】——拿公司名直接搜相似会命中同名异司（L-45 卡点1）。
流程: 候选公司名 → search/company-search(精确找单家,拿 domain) → 同名多司列出让你选 → 输出 <域名> 作种子。
用法:
  python3 seed_resolve.py --token <T> --org <orgId> --company "<候选公司名>"
  python3 seed_resolve.py --token <T> --org <orgId> --domain <已知域名>   # 域名反查单家(校验存在)
只读: 不写任何数据。search/company-search 精确匹配 total:1。
"""
import json, subprocess, sys, argparse

ap = argparse.ArgumentParser()
ap.add_argument("--token", required=True, help="accesstoken 整串")
ap.add_argument("--org", required=True, help="orgId(=token 第2段)")
ap.add_argument("--company", default="", help="候选公司名(从 refine/company-list 候选来)")
ap.add_argument("--domain", default="", help="已知域名(反查校验,可省略)")
args = ap.parse_args()

if not args.company and not args.domain:
    print("❌ 需 --company <公司名> 或 --domain <域名>"); sys.exit(2)

def api(path, p, t=60):
    r = subprocess.run(["curl", "-sSL", "-m", "55", "-X", "POST", f"https://web.laifaxin.com/api/{path}?uid={args.org}",
                        "-H", "Content-Type: application/json", "-H", f"accesstoken: {args.token}", "-d", json.dumps(p)],
                       capture_output=True, text=True, timeout=t)
    try: return json.loads(r.stdout)
    except: return {}

kw = args.domain if args.domain else args.company
d = api("search/company-search", {"keyword": kw, "current": 1, "pageSize": 5})
lst = (d.get("data") or {}).get("list") or []
if not lst:
    print(f"❌ 未找到「{kw}」——接口间歇空可重试，或公司名/域名不精确"); sys.exit(1)

if args.domain:
    # 域名反查: 应命中单家
    for c in lst[:1]:
        print(f"✅ 域名 {kw} → {c.get('name')} | {c.get('company_country')} | {(c.get('industry') or '')[:40]}")
        print(f"  种子用: {kw}")
    sys.exit(0)

# 公司名反查: 列出候选, 找真实 domain
print(f"「{kw}」反查结果 ({len(lst)} 条):")
print(f"{'#':<3}{'公司名':<34}{'域名':<30}{'国家':<6}{'行业'}")
for i, c in enumerate(lst, 1):
    dm = c.get("domain") or ""
    print(f"{i:<3}{(c.get('name') or '')[:32]:<34}{dm[:28]:<30}{(c.get('company_country') or '')[:5]:<6}{(c.get('industry') or '')[:30]}")
print("\n★种子 = 上面命中的【域名】（非公司名）——拿域名去搜相似才精准（L-45）。")
print("  若同名多司：对照国家/行业挑你认得的买家那家，用它的域名。")
