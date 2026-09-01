#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""★序列终检（激活前硬闸门）：step-list断言 12步+每个template_ids均为24hex+在模板库name映射+wait合理
用法: python3 verify_sequence.py --token <T> --org <orgId> --seq <序列id>
"""
import json, subprocess, argparse, re, sys
ap=argparse.ArgumentParser(); ap.add_argument("--token",required=True); ap.add_argument("--org",required=True)
ap.add_argument("--seq",required=True)
args=ap.parse_args()
def api(path,p,t=50):
    cmd=["curl","-sSL","-X","POST",f"https://web.laifaxin.com/api/{path}?uid={args.org}","-H","Content-Type: application/json","-H",f"accesstoken: {args.token}","-d",json.dumps(p)]
    r=subprocess.run(cmd,capture_output=True,text=True,timeout=t)
    try: return json.loads(r.stdout).get("data",{})
    except: return {}
steps=api("sequences/step-list",{"seqId":args.seq,"current":1,"pageSize":20})
if not isinstance(steps,list) or not steps:
    print("❌ step-list 失败/空(可能500)"); sys.exit(1)
print(f"步骤数: {len(steps)}")
if len(steps)!=12:
    print(f"❌ 终检失败: 步骤数={len(steps)}≠12——序列步数错乱,不得激活"); sys.exit(1)
# 模板库 name→id（拉够页,覆盖超300模板场景）
tplset=set()
for pg in range(1,8):
    lst=api("mailbox/templates-list",{"current":pg,"pageSize":100,"filter":{},"sort":{}}).get("list",[])
    if not lst: break
    for t in lst:
        if isinstance(t,dict) and not t.get("folder") and t.get("_id"): tplset.add(t["_id"])
    if len(lst)<100: break
ok=True
for s in steps:
    tids=s.get("template_ids") or []
    bad=[t for t in tids if not re.fullmatch(r'[0-9a-f]{24}',str(t)) or t not in tplset]
    wt=s.get("wait_time"); step=s.get("step")
    exp = ("minute",30) if step==1 else ("day",5) if step==2 else ("day",15) if step==3 else ("day",30)
    wmode=s.get("wait_mode")
    if bad or (wmode,wt)!=exp:
        ok=False
        print(f"  ⚠️ step{step}: 坏id={bad} wait={wt}")
print(f"✅ 全部{len(steps)}步: template_ids均24hex+在模板库+wait(step1=30分/step2=5天/step3=15天/step4+=30天)正确" if ok else "❌ 终检失败——不得激活")
sys.exit(0 if ok else 1)
