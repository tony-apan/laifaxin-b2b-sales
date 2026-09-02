#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""S3 取公司域名/详情（只读）——统一走 AI 数据库搜索链路（refine/company-list → id → domain/base-info）。
★正确姿势（2026-09-03 用户拍板）：
  1) 客群 query_en 作关键词 → refine/company-list 第一页（每条含权威 id，但列表项无 domain 字段）
  2) 需要域名/详情：本工具 --id <那条的id> → POST domain/base-info {"domain":<id>} → 返回 domain+公司名+NAICS+中英摘要
  ⚠️勿拿公司名当搜索锚（同名异司 L-45）；不使用 domain/similar-list。
用法:
  python3 seed_resolve.py --token <T> --org <orgId> --id <搜索结果项的32hex id>     # 主路径：id→域名+详情
  python3 seed_resolve.py --token <T> --org <orgId> --keyword "<query_en>"          # 顺手搜第一页并逐条取域名
  python3 seed_resolve.py --token <T> --org <orgId> --company "<公司名>"            # 兜底：仅知公司名时精确反查
只读，不写任何数据。
"""
import json, subprocess, sys, argparse

ap = argparse.ArgumentParser()
ap.add_argument("--token", required=True)
ap.add_argument("--org", required=True)
ap.add_argument("--id", default="", help="搜索结果项的 32hex id（主路径：→ domain/base-info 取域名+详情）")
ap.add_argument("--keyword", default="", help="query_en 关键词：搜第一页并逐条取域名")
ap.add_argument("--company", default="", help="公司名（兜底：search/company-search 精确反查）")
args = ap.parse_args()

if not (args.id or args.keyword or args.company):
    print("❌ 需 --id <32hex id> 或 --keyword <query_en> 或 --company <公司名>"); sys.exit(2)

def api(path, p, t=60):
    r = subprocess.run(["curl", "-sSL", "-m", "55", "-X", "POST", f"https://web.laifaxin.com/api/{path}?uid={args.org}",
                        "-H", "Content-Type: application/json", "-H", f"accesstoken: {args.token}", "-d", json.dumps(p)],
                       capture_output=True, text=True, timeout=t)
    try: return json.loads(r.stdout)
    except: return {}

def show_baseinfo(bid):
    d = api("domain/base-info", {"domain": bid})
    data = d.get("data") if d.get("success") else None
    if not isinstance(data, dict) or not data.get("domain"):
        print(f"  ❌ id={bid} 未取到（接口间歇空可重试）"); return
    print(f"     ✅ 域名: {data.get('domain')} | {data.get('country_code')} | {data.get('operational_role')} | NAICS {data.get('naics_code')} {str(data.get('naics_label') or '')[:30]}")

if args.id:
    print("=== id → domain/base-info ===")
    d = api("domain/base-info", {"domain": args.id.strip()})
    data = d.get("data") if d.get("success") else None
    if not isinstance(data, dict) or not data.get("domain"):
        print("❌ 未取到（接口间歇空可重试）"); sys.exit(1)
    print(f"公司: {data.get('company_name')}")
    print(f"域名: {data.get('domain')}")
    print(f"国家: {data.get('country_code')} | 角色: {data.get('operational_role')} | {data.get('client_focus')} | 置信度: {data.get('confidence')}")
    print(f"NAICS: {data.get('naics_code')} {data.get('naics_label')}")
    print(f"摘要: {str(data.get('summary_zh') or '')[:80]}")
    sys.exit(0)

if args.keyword:
    print(f'=== AI数据库搜索 keyword="{args.keyword}" 第一页 + 逐条域名 ===')
    d = api("refine/company-list", {"keyword": args.keyword, "current": 1, "pageSize": 10, "filters": [], "logic": "and"})
    data = d.get("data") or {}
    lst = data.get("list") or []
    print(f"total: {data.get('total')} | 第一页 {len(lst)} 条\n")
    for i, c in enumerate(lst, 1):
        print(f"【{i}】{c.get('company_name')} | {c.get('country_code')} | {c.get('operational_role')} | emails:{c.get('emailsCount')} | 匹配:{round(float(c.get('_score') or 0),3)}")
        print(f"    摘要: {str(c.get('summary_zh') or '')[:48]}")
        show_baseinfo(c.get("id"))
    print(f'\n保存: save_first_n --keyword "{args.keyword}" --n <前N>（keyword=本关键词）')
    sys.exit(0)

# 兜底: 公司名精确反查
d = api("search/company-search", {"keyword": args.company, "current": 1, "pageSize": 5})
lst = (d.get("data") or {}).get("list") or []
print(f"「{args.company}」精确反查（{len(lst)} 条）——同名多司对照国家/行业选:")
for i, c in enumerate(lst, 1):
    print(f"  {i}. {(c.get('name') or '')[:32]:34} | domain: {(c.get('domain') or '—')[:30]} | {str(c.get('company_country') or '')[:12]} | {str(c.get('industry') or '')[:30]}")
