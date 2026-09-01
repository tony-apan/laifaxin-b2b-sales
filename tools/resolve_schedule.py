#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""★时区计划时间解析器（★schedule_id 各账号不同,禁止硬编码——一律运行时 schedule-list 解析）
用法:
  python3 resolve_schedule.py --token <T> --org <orgId> --tz "America/New_York"   # 按 time_zone 精确匹配 → 输出 id
  python3 resolve_schedule.py --token <T> --org <orgId> --name 纽约               # 按名称包含匹配 → 输出 id
  python3 resolve_schedule.py --token <T> --org <orgId> --list                    # 列出全部计划时间模板
建序列前必须先跑本工具拿 schedule_id（node-playbook S9 / sequence-config 引用）。
"""
import json, subprocess, argparse, sys
ap = argparse.ArgumentParser()
ap.add_argument("--token", required=True); ap.add_argument("--org", required=True)
ap.add_argument("--tz", default="", help="time_zone 精确匹配, 如 America/New_York")
ap.add_argument("--name", default="", help="名称包含匹配, 如 纽约")
ap.add_argument("--list", action="store_true", help="列出全部模板")
args = ap.parse_args()

def api(path, p, t=60):
    cmd = ["curl","-sSL","-m","55","-X","POST",f"https://web.laifaxin.com/api/{path}?uid={args.org}",
           "-H","Content-Type: application/json","-H",f"accesstoken: {args.token}","-d",json.dumps(p)]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=t)
    try: return json.loads(r.stdout).get("data", {})
    except: return {}

d = api("settings/sequence/schedule-list", {"current":1, "pageSize":100})
lst = d if isinstance(d, list) else d.get("list", [])
if not lst:
    print("❌ schedule-list 失败/空（token失效或接口间歇空，重试）"); sys.exit(1)

if args.list:
    for s in lst:
        print(f"{s.get('id') or s.get('_id')} | {s.get('name')} | {s.get('time_zone')} | default:{s.get('isDefault')}")
    sys.exit(0)

if not args.tz and not args.name:
    print("❌ 须传 --tz 或 --name（或 --list）"); sys.exit(1)

hits = []
for s in lst:
    sid = s.get("id") or s.get("_id")
    if args.tz and s.get("time_zone") == args.tz:
        hits.append((sid, s))
    elif args.name and args.name in (s.get("name") or ""):
        hits.append((sid, s))

if not hits:
    print(f"❌ 未命中: tz={args.tz} name={args.name}——用 --list 看全部，或创建自定义 schedule"); sys.exit(1)
# 优先 isDefault，其次第一个
hits.sort(key=lambda x: (not x[1].get("isDefault"),))
sid, s = hits[0]
print(sid)
print(f"# {s.get('name')} | {s.get('time_zone')} | default:{s.get('isDefault')}" + (f" (另有{len(hits)-1}个同名/同时区候选)" if len(hits)>1 else ""), file=sys.stderr)
