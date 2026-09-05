#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""★序列终检（激活前硬闸门）：断言序列存在且默认inactive + 12步 + 模板ID/时间正确。
用法: python3 verify_sequence.py --token <T> --org <orgId> --seq <序列id> [--allow-active]
"""
import json, subprocess, argparse, re, sys
ap=argparse.ArgumentParser(); ap.add_argument("--token",required=True); ap.add_argument("--org",required=True)
ap.add_argument("--seq",required=True); ap.add_argument("--allow-active",action="store_true",help="仅激活后复核时允许active；S11默认必须inactive")
args=ap.parse_args()
def api(path,p,t=50):
    cmd=["curl","-sSL","-X","POST",f"https://web.laifaxin.com/api/{path}?uid={args.org}","-H","Content-Type: application/json","-H",f"accesstoken: {args.token}","-d",json.dumps(p)]
    r=subprocess.run(cmd,capture_output=True,text=True,timeout=t)
    try: return json.loads(r.stdout).get("data",{})
    except: return {}
# 激活前状态硬闸：查询失败/未命中/active 均 fail-closed
found=None
for pg in range(1,6):
    data=api("sequences/sequence-list",{"current":pg,"pageSize":100,"filter":{},"sort":{}})
    lst=data if isinstance(data,list) else (data.get("list") if isinstance(data,dict) else None)
    if not isinstance(lst,list):
        print("❌ sequence-list 查询失败——无法确认inactive，不得激活"); sys.exit(1)
    for item in lst:
        if str(item.get("id") or item.get("_id") or "")==args.seq: found=item; break
    if found or len(lst)<100: break
if not found:
    print(f"❌ 序列不存在/不可见: {args.seq}"); sys.exit(1)
status=str(found.get("status") or "").lower()
if found.get("active") is True or str(found.get("active")) == "1": status="active"
if status!="inactive" and not (args.allow_active and status=="active"):
    print(f"❌ 序列status={status or '未知'}，S11终检默认必须inactive"); sys.exit(1)
print(f"✅ 序列 {args.seq} 状态={status}")
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
