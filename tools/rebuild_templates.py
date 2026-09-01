#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""⚠️⚠️ 原型(半自动)——皮筏艇2026-08-30实操用此脚本失败两次后改为手工分步(见 L-43 / 模板差异实测·模板id校验)。已知坑:
  - 模板名称唯一: 旧模板未删时同名 template-add 失败("模板名称已存在")
  - 被序列引用模板不可删("模板使用中,请在序列中删除"); 序列"至少保留一个步骤"; 步骤"邮件模板不能为空"
  - step-save/step-create 不校验 template_ids(垃圾字符串也 success)→step-list 500
  ✅ 实操成功的顺序(2026-08-30): ①收集旧模板id+步骤wait配置 → ②step-delete 删到剩1步(记录最后1步id) → ③gen_templates 用新后缀(如-RT2)避免重名 → ④删全部旧模板 → ⑤step-save 最后1步指向新id → ⑥step-create 其余步骤 → ⑦删残留旧模板 → ⑧verify_sequence+check_template_diff
用法:
  python3 rebuild_templates.py --token <T> --org <orgId> --product 皮筏艇 --prefix "英-皮筏艇-" --suffix -RT --seq <seqId> --name <昵称> --approval <ap-id> --project 皮筏艇
前置: 序列必须 inactive(不激活); 本脚本只重建模板与步骤, 不 contact-add 不激活。
"""
import json, subprocess, time, sys, argparse, re
from pathlib import Path

KB = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KB / "tools"))
from approval import require_approval

ap = argparse.ArgumentParser()
ap.add_argument("--token", required=True); ap.add_argument("--org", required=True)
ap.add_argument("--product", required=True); ap.add_argument("--prefix", required=True)
ap.add_argument("--suffix", default="-RT"); ap.add_argument("--seq", required=True)
ap.add_argument("--name", required=True, help="签名昵称(=客户邮件落款,必填)"); ap.add_argument("--dry-run", action="store_true")
ap.add_argument("--approval", default="", help="★审批凭证id(审批闸门(工具级)): S7/S8 模板节点")
ap.add_argument("--project", default="", help="产品名(审批project匹配)")
ap.add_argument("--out", default="", help="name→id 映射落盘路径(默认 db/tmap-<产品>.json; 建议 runs/<运营方>/<产品>/tmap.json)")
args = ap.parse_args()

def api(path, p, t=60):
    cmd = ["curl","-sSL","-X","POST",f"https://web.laifaxin.com/api/{path}?uid={args.org}",
           "-H","Content-Type: application/json","-H",f"accesstoken: {args.token}","-d",json.dumps(p)]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=t)
    try: return json.loads(r.stdout)
    except: return {"success": False}

def collect_old():
    ids = []
    for pg in range(1, 30):
        d = api("mailbox/templates-list", {"current":pg,"pageSize":20,"filter":{},"sort":{}})
        lst = d.get("data", {}).get("list", [])
        if not lst: break
        for t in lst:
            if t.get("folder"): continue
            if (t.get("name") or "").startswith(args.prefix):
                ids.append((t.get("name"), t.get("_id")))
    return ids

old = collect_old()
print(f"[0/4] 旧模板(prefix={args.prefix}): {len(old)}")
if args.dry_run:
    for n, i in old[:3]: print(f"   (dry) {n} {i}")
    print("dry-run 结束(不建/不改/不删)"); sys.exit(0)

require_approval(args.approval, args.project, ("S7", "S8"), what="重建模板+序列步骤")

# 1) 生成新模板(差异达标) + 落盘 name→id（★先建新, 旧模板仍被序列引用不能删）
outf = args.out or str(KB / "db" / f"tmap-{args.product}.json")
subprocess.run([sys.executable, str(KB/"tools"/"gen_templates.py"), "--token", args.token, "--org", args.org,
                "--product", args.product, "--prefix", args.prefix, f"--suffix={args.suffix}",
                "--name", args.name, "--out", outf, "--approval", args.approval, "--project", args.project],
               check=True)
mapping = json.load(open(outf))
all_ids = list(mapping.values())
assert len(all_ids) == 120, f"期望120新模板, 实得 {len(all_ids)}"
groups = [all_ids[i*10:(i+1)*10] for i in range(12)]
print(f"[1/4] 生成新模板 {len(all_ids)} 个 (差异达标, 待 check_template_diff 实测)")

# 2) 序列12步 step-save 指向新模板（★先改引用, 旧模板才可删）
d = api("sequences/step-list", {"seqId": args.seq, "current":1, "pageSize":20})
lst = d.get("data", {})
lst = lst if isinstance(lst, list) else lst.get("list", [])
lst = sorted(lst, key=lambda s: s.get("step", 0))
assert len(lst) == 12, f"期望12步, 实得 {len(lst)}"
print(f"[2/4] 序列 {len(lst)} 步 → 逐个 step-save 指向新模板")
for s in lst:
    step = s.get("step")
    payload = {"seqId": args.seq, "id": s.get("_id"), "step": step,
               "template_ids": groups[step-1],
               "wait_mode": s.get("wait_mode"), "wait_time": s.get("wait_time"),
               "senders": s.get("senders", [])}
    r = api("sequences/step-save", payload)
    print(f"   step{step}: {'✅' if r.get('success') else '❌ '+str(r)[:80]}")

# 3) 删旧模板（现在已不被引用）
fails = []
for n, i in old:
    r = api("mailbox/template-delete", {"id": i})
    if not r.get("success"): fails.append(n)
print(f"[3/4] 删除旧模板: {len(old)-len(fails)}/{len(old)} 成功" + (f"; 失败 {fails[:5]}" if fails else ""))

print("\n✅ 完成。请校验:")
print(f"   python3 tools/check_template_diff.py --token <T> --org {args.org} --prefix '{args.prefix}' --limit 120")
print(f"   python3 tools/verify_sequence.py --token <T> --org {args.org} --seq {args.seq}")
