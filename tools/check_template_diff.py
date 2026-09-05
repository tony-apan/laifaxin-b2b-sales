#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""★模板差异断言：拉模板(按前缀) → 逐模板 template-info 取真实 html → 两两 Jaccard 相似度，断言差异≥30%(相似度≤70%)
⚠️ templates-list 的 list 项不含 html(只有 subject)——必须再调 template-info(id) 取正文，否则空 html 恒"达标"(假阴性,模板差异实测（工具级）)
用法: python3 check_template_diff.py --token <TOKEN> --org <orgId> --prefix "英-皮筏艇-" [--limit 120]
"""
import json, subprocess, argparse, re, sys
ap=argparse.ArgumentParser(); ap.add_argument("--token",required=True); ap.add_argument("--org",required=True)
ap.add_argument("--prefix",required=True); ap.add_argument("--limit",type=int,default=120)
args=ap.parse_args()
def api(path,p,t=60):
    cmd=["curl","-sSL","-X","POST",f"https://web.laifaxin.com/api/{path}?uid={args.org}","-H","Content-Type: application/json","-H",f"accesstoken: {args.token}","-d",json.dumps(p)]
    r=subprocess.run(cmd,capture_output=True,text=True,timeout=t)
    try:
        d=json.loads(r.stdout)
        if d.get("success") is False: raise ValueError(d.get("message") or "服务端拒绝")
        if "data" not in d: raise ValueError("返回缺data")
        return d["data"] or {}
    except Exception as exc:
        print(f"❌ 接口失败，无法验证模板差异: {path} -> {exc}")
        sys.exit(1)

# 1) 收集模板名+id（跳过 folder）
tpls=[]
for pg in range(1,30):
    lst=api("mailbox/templates-list",{"current":pg,"pageSize":20,"filter":{},"sort":{}}).get("list",[])
    if not lst: break
    for t in lst:
        if t.get("folder"): continue
        nm=t.get("name") or ""
        if nm.startswith(args.prefix): tpls.append({"name":nm,"id":t.get("_id")})
    if len(tpls)>=args.limit: break
print(f"模板数: {len(tpls)} (前缀 {args.prefix})")
if len(tpls) != args.limit:
    print(f"❌ 模板数量={len(tpls)}，期望={args.limit}；缺模板时不得做差异达标结论"); sys.exit(1)

# 2) 逐模板取真实 html（★模板正文在 template-info，不在 templates-list）
missing=[]
for t in tpls:
    info=api("mailbox/template-info",{"id":t["id"]},t=40)
    t["subject"]=info.get("subject","")
    t["html"]=info.get("html","")
    if not t["html"]: missing.append(t["name"])
if missing:
    print(f"❌ {len(missing)} 个模板 html 为空: {missing[:5]}——空正文不能参与差异结论")
    sys.exit(1)

def words(s):
    s=re.sub(r"<[^>]+>"," ",s).lower()
    return set(x for x in re.findall(r"[^\W_]+",s,flags=re.UNICODE) if x)
def jac(a,b):
    if not a or not b: return 0.0
    return len(a&b)/len(a|b)

for t in tpls:
    if not words(t["html"]):
        print(f"❌ 模板无法分词，不能计算差异: {t['name']}")
        sys.exit(1)

bad=[]; maxsim=0; worst=None
for i in range(len(tpls)):
    for j in range(i+1,len(tpls)):
        a,b=tpls[i],tpls[j]
        sim=jac(words(a["html"]),words(b["html"]))
        if sim>maxsim: maxsim=sim; worst=(a["name"],b["name"])
        if sim>0.70: bad.append((round(sim,2),a["name"],b["name"]))
print(f"最大相似度: {maxsim:.2f} ({worst[0] if worst else '-'} vs {worst[1] if worst else '-'})")
if bad:
    print(f"❌ 相似度>0.70 的 {len(bad)} 对（差异<30%违例），示例:")
    for s,a,b in bad[:8]: print(f"  {s} | {a} vs {b}")
    print("提示: 固定 boilerplate + 同轮共享 angle 是 模板差异实测（工具级）——body 须按轮/变体差异化")
    sys.exit(1)
else:
    print("✅ 两两相似度均≤0.70（差异≥30%达标）")
    sys.exit(0)
