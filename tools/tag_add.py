#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""★S5 前置·建标签（一条龙缺口#3，冷启动审查发现）：创建公司/联系人标签，返回 id(名称) 记录格式
铁律7: 标签=客户群体中文名,升级格式「语言-行业-角色」（如 英语-水上运动-经销商/英语-漂流景区-运营商），不写我方产品；记录一律 id(名称) 成对。
用法:
  python3 tag_add.py --token <T> --org <orgId> --name "英语-水上运动-经销商" --type company --profile runs/<operator_key>/<product_key>/product-profile.md --approval <绑定凭证> --project <operator_key>/<product_key>
  python3 tag_add.py --token <T> --org <orgId> --list   # 列现有标签(只读,免审批)
"""
import hashlib, json, subprocess, sys, argparse
from pathlib import Path

KB = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KB / "tools"))

ap = argparse.ArgumentParser()
ap.add_argument("--token", required=True, help="accesstoken 整串(web.laifaxin.com&<orgId>&<hash>)")
ap.add_argument("--org", required=True, help="orgId(=token 第2段)")
ap.add_argument("--name", default="", help="标签名(★客户群体中文名,如 水上运动行业客户——勿写产品名)")
ap.add_argument("--type", default="", choices=["company", "contacts"], help="company=公司标签 / contacts=联系人标签")
ap.add_argument("--profile", default="", help="创建标签时必填当前产品档案；--list只读免填")
ap.add_argument("--approval", default="", help="★绑定profile+name+type的S2/S5凭证")
ap.add_argument("--project", default="", help="稳定项目键=<operator_key>/<product_key>")
ap.add_argument("--list", action="store_true", help="只列现有标签(免审批)")
args = ap.parse_args()

def api(path, p, t=40):
    cmd = ["curl","-sSL","-m","35","-X","POST",f"https://web.laifaxin.com/api/{path}?uid={args.org}",
           "-H","Content-Type: application/json","-H",f"accesstoken: {args.token}","-d",json.dumps(p)]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=t)
    try: return json.loads(r.stdout)
    except: return {}

if args.list:
    for typ in ("company", "contacts"):
        d = api("contacts/tags-list", {"type": typ})
        lst = d.get("data", {})
        lst = lst if isinstance(lst, list) else lst.get("list", [])
        print(f"[{typ}] " + (", ".join(f"{t.get('id') or t.get('_id')}({t.get('name')})" for t in lst) or "(空)"))
    sys.exit(0)

if not (args.name and args.type):
    print("❌ 需要 --name <客户群体中文名> --type company|contacts（或 --list 查看）"); sys.exit(2)

# 铁律7 提醒（不硬拦，但醒目提示）
import re as _re
if _re.search(r'[a-zA-Z]', args.name):
    print("⚠️ RULES 铁律7/8: 标签名应为客户群体【中文】名（如 水上运动行业客户），勿用英文/产品名——继续执行但建议复核")

from approval import require_approval, stable_params_hash
from profile_utils import profile_gate
if not args.profile or not args.project:
    print("❌ 创建标签须带 --profile <product-profile.md> --project <operator_key>/<product_key>"); sys.exit(2)
pp = Path(args.profile); pp = pp if pp.is_absolute() else KB / pp
ps, issues, pm, ph = profile_gate(pp)
expected = f"{pm.get('operator_key','').strip()}/{pm.get('product_key','').strip()}"
if not issues and args.project != expected: issues.append("--project与产品档案项目键不一致")
if issues:
    for issue in issues: print(f"❌ 产品档案闸门: {issue}")
    sys.exit(4)
binding = {"project": args.project, "org_sha256": hashlib.sha256(str(args.org).encode()).hexdigest(), "profile": {"sha256": ph, "status": ps, "version": pm.get("profile_version", "")},
           "tag": {"name": args.name, "type": args.type}}
require_approval(args.approval, args.project, ("S2", "S5"), what="建标签", expected_hash=stable_params_hash(binding))

# 查重（同名已存在则直接返回现有 id，不重复建）
d = api("contacts/tags-list", {"type": args.type})
lst = d.get("data", {})
lst = lst if isinstance(lst, list) else lst.get("list", [])
for t in lst:
    if t.get("name") == args.name:
        tid = t.get("id") or t.get("_id")
        print(f"ℹ️ 标签「{args.name}」已存在: {tid}({args.name}) —— 直接复用，勿重复创建")
        print(f"   记录格式: {tid}({args.name})")
        sys.exit(0)

r = api("contacts/tags-add", {"name": args.name, "type": args.type})
if r.get("success"):
    tid = (r.get("data", {}) or {}).get("id") or (r.get("data") if isinstance(r.get("data"), str) else "")
    print(f"✅ 标签已建: {tid}({args.name})  [type={args.type}]")
    print(f"   记录格式: {tid}({args.name}) —— 写入 runs/<运营方>/<产品>/operation-record.md 与 runs.tsv")
    print(f"   save_first_n 用: --company-tag/--contact-tag {tid}")
else:
    print(f"❌ 创建失败: {r.get('message') or str(r)[:100]}"); sys.exit(1)
