#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""★清空基础产品档案（product-list 全量 + product-delete id逐个）——用户界面"产品档案"= product-* 不是 inference-product-*
⚠️防呆（对齐 delete_all_contacts/tags/templates）: 默认 --dry-run 仅预览; 必须 --execute + --confirm "DELETE-ALL" 才真删。
"""
import json, subprocess, time, argparse

CONFIRM_PHRASE = "DELETE-ALL"
ap = argparse.ArgumentParser()
ap.add_argument("--token", required=True)
ap.add_argument("--org", required=True)
ap.add_argument("--dry-run", action="store_true", default=True, help="仅预览待删产品(★默认启用; 加 --execute 才真删)")
ap.add_argument("--execute", action="store_true", help="⚠️ 真正执行删除——必须同时提供 --org(已必填) 与 --confirm \"DELETE-ALL\"")
ap.add_argument("--confirm", default="", help=f"确认短语,必须等于 \"{CONFIRM_PHRASE}\"")
args = ap.parse_args()

# ★P0-3 修正: store_true+default=True 会让 dry_run 恒 True → 删除分支死代码。改以 --execute 为执行闸。
if args.execute and args.confirm != CONFIRM_PHRASE:
    print(f"❌ --confirm 须等于 \"{CONFIRM_PHRASE}\"(防误删)——你给的是 {args.confirm!r}"); raise SystemExit(1)
executing = args.execute and args.confirm == CONFIRM_PHRASE

def api(path, p, t=40):
    cmd = ["curl", "-sSL", "-X", "POST", f"https://web.laifaxin.com/api/{path}?uid={args.org}",
           "-H", "Content-Type: application/json", "-H", f"accesstoken: {args.token}", "-d", json.dumps(p)]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=t)
    try: return json.loads(r.stdout)
    except: return {}

allp = []
for page in range(1, 8):
    d = api("profile/product-list", {"current": page, "pageSize": 10, "filter": {}, "sort": {"create_time": -1}, "keyword": ""}).get("data", {})
    lst = d.get("list", []) if isinstance(d, dict) else []
    if not lst: break
    allp += lst
    if len(lst) < 10: break

print(f"产品档案: {len(allp)}")
if not allp:
    print("(无产品档案可删)"); raise SystemExit(0)
if args.dry_run and not executing:
    print("[dry-run] 待删(不删除):")
    for p in allp: print("  ", p.get("_id"), (p.get("product_name") or "")[:20])
    print(f'[dry-run] 未加 --execute,不删除。确认后请: --execute --confirm "{CONFIRM_PHRASE}"')
else:
    for p in allp:
        r = api("profile/product-delete", {"id": p.get("_id")})
        print("  删", (p.get("product_name") or "")[:16], r.get("success"))
        time.sleep(0.3)
    time.sleep(1)
    d = api("profile/product-list", {"current": 1, "pageSize": 10, "filter": {}, "sort": {"create_time": -1}, "keyword": ""}).get("data", {})
    print("剩余:", d.get("total") if isinstance(d, dict) else "?")
