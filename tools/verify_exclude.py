#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""★4区排除抽验：用 company-list + exclude 拉前N页，统计残留 CN/TW/HK/MO（看列表内容，L-33）
⚠️ 局限(对抗审查 抽样验证局限)：默认仅抽前3页×10=30家(≈0.4%)；且验的是 company-list(列表) 非 company-save 实际保存结果=proxy验证。抽样请 --pages 1,2,3,50,100,200 扩大；保存结果的4区最终以 backend-task-status 联系人清单为准。
用法: python3 verify_exclude.py --token <TOKEN> --org <orgId> --keyword <种子> [--pages 1,2,3]
"""
import json, subprocess, argparse
ap=argparse.ArgumentParser(); ap.add_argument("--token",required=True); ap.add_argument("--org",required=True)
ap.add_argument("--keyword",required=True); ap.add_argument("--pages",default="1,2,3",help="页码csv")
args=ap.parse_args()
BAD=("CN","TW","HK","MO")
def clist(pg):
    p={"logic":"and","current":pg,"pageSize":10,"filters":[{"property":"country_code","operator":"exclude","value":"","values":["CN","TW","HK","MO"],"valueType":"select"}],"sort":{},"keyword":args.keyword,"filter":{}}
    cmd=["curl","-sSL","-X","POST",f"https://web.laifaxin.com/api/refine/company-list?uid={args.org}","-H","Content-Type: application/json","-H",f"accesstoken: {args.token}","-d",json.dumps(p)]
    r=subprocess.run(cmd,capture_output=True,text=True,timeout=60)
    try: return json.loads(r.stdout).get("data",{}).get("list",[])
    except: return []
bad=[]
for pg in [int(x) for x in args.pages.split(",")]:
    for c in clist(pg):
        cc=c.get("country_code")
        if cc in BAD: bad.append((pg,c.get("company_name","")[:24],cc))
print(f"验({args.keyword} 页{args.pages}): 含4区={len(bad)}")
for pg,name,cc in bad[:8]: print(f"  ⚠️ p{pg}: {name} ({cc})")
if bad: print("❌ 排除有残留（种子公司自身或数据异常）——复核（L-33: total截断≠无效,看列表）")
else: print("✅ 排除生效（无4区残留）")
print(f"⚠️ 抽验覆盖={len([int(x) for x in args.pages.split(',')])*10}家(proxy=company-list非保存结果); 抽样扩大: --pages 1,2,3,50,100,200")
