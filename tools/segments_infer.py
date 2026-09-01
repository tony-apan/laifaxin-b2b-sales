#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""★推理N轮→拉全量客群→生成/更新 segments/ 档+索引（S2 产出的机读落地）
用法:
  python3 segments_infer.py --token <T> --org <orgId> --product 皮筏艇 --rounds 4 [--dry-run]
前提: 该产品已有推理档案(inference-product)；产出后必须: ①空白代理对抗审查 ②AI 五维评分+客群确认 ③重生成 segments.md 与本地数据表（db/segments.tsv，不入库）
"""
import json, subprocess, sys, argparse, time
from pathlib import Path
KB = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KB / "tools"))
from approval import require_approval

ap = argparse.ArgumentParser()
ap.add_argument("--token", required=True); ap.add_argument("--org", required=True)
ap.add_argument("--product", required=True, help="产品名(⚠️两套档案命名可能不同L-37:匹配name/zh/en三字段;不确定时--dry-run看,或直接--pid)")
ap.add_argument("--pid", default="", help="推理档案id直传(免匹配,最稳)")
ap.add_argument("--rounds", type=int, default=4)
ap.add_argument("--approval", default="", help="S2 审批凭证")
ap.add_argument("--project", default="")
ap.add_argument("--dry-run", action="store_true")
args = ap.parse_args()

def api(path, p, t=90):
    r = subprocess.run(["curl","-sSL","-m","80","-X","POST",f"https://web.laifaxin.com/api/{path}?uid={args.org}",
                        "-H","Content-Type: application/json","-H",f"accesstoken: {args.token}","-d",json.dumps(p)],
                       capture_output=True, text=True, timeout=t)
    try:
        d = json.loads(r.stdout)
        if d.get("success") is False:
            print(f"❌ 服务端拒绝: {d.get('message')}"); sys.exit(1)
        return d
    except: return {}

# 找该产品的推理档案 id（--pid 直传优先）
pid = args.pid or None
if not pid:
    prods = api("profile/inference-product-list", {}).get("data", [])
    prods = prods if isinstance(prods, list) else prods.get("list", [])
    for x in prods:
        hay = " ".join(str(x.get(k) or "") for k in ("product_name","product_zh","product_en","name"))
        if args.product in hay:
            pid = x.get("product_id") or x.get("_id") or x.get("id"); break
    if not pid:
        print("❌ 未匹配到推理档案（两套档案命名可能不同 L-37）——可先看清单:")
        for x in prods or []:
            print(f"   - {x.get('product_name')} | zh:{x.get('product_zh')} | id:{x.get('_id')}")
        print("   用 --pid <id> 直传即可"); sys.exit(1)
if not pid:
    print(f"❌ 未找到「{args.product}」推理档案——先在界面/S2 建推理产品档案"); sys.exit(1)
print(f"✅ 推理档案: {pid}")

if args.dry_run:
    print(f"[dry-run] 将 generate×{args.rounds} → segment-list → 产出骨架（不写线上）"); sys.exit(0)

require_approval(args.approval, args.project, ("S2",), what="推理客群")

for i in range(args.rounds):
    r = api("profile/inference-segment-generate", {"product_id": pid}, t=180)
    print(f"  第{i+1}轮 generate: {'✅' if r.get('success') else r.get('message')}")
    time.sleep(1)

segs = api("profile/inference-segment-list", {"product_id": pid}).get("data", [])
segs = segs if isinstance(segs, list) else segs.get("list", [])
print(f"\n✅ 共 {len(segs)} 客群：")
for s in segs:
    print(f"  - {s.get('segment_name')} | query_en: {str(s.get('query_en'))[:60]} | total:{s.get('query_total')}")
print(f"\n下一步: ①空白代理审查此产出 ②AI 按 segments/README.md 字段字典逐档评分建档 ③重生成索引")
