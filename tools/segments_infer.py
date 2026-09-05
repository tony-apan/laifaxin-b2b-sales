#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""★推理N轮→拉全量客群→生成/更新 segments/ 档+索引（S2 产出的机读落地）
用法:
  python3 segments_infer.py --token <T> --org <orgId> --product <产品> --rounds 4 --profile runs/<operator_key>/<product_key>/product-profile.md --record runs/<operator_key>/<product_key>/operation-record.md --project <operator_key>/<product_key> --approval <绑定凭证> [--dry-run]
前提: 该产品已有推理档案(inference-product)；产出后必须: ①空白代理对抗审查 ②AI 五维评分+客群确认 ③重生成 segments.md 与本地数据表（db/segments.tsv，不入库）
"""
import hashlib, json, subprocess, sys, argparse, time
from pathlib import Path
KB = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KB / "tools"))
from approval import require_approval, stable_params_hash
from profile_utils import ensure_same_project_paths, profile_gate
from update_run_state import require_state, update_frontmatter

ap = argparse.ArgumentParser()
ap.add_argument("--token", required=True); ap.add_argument("--org", required=True)
ap.add_argument("--product", required=True, help="产品名(⚠️两套档案命名可能不同L-37:匹配name/zh/en三字段;不确定时--dry-run看,或直接--pid)")
ap.add_argument("--pid", default="", help="推理档案id直传(免匹配,最稳)")
ap.add_argument("--rounds", type=int, default=4)
ap.add_argument("--profile", required=True, help="当前产品档案；状态/hash/项目键进入S2审批绑定")
ap.add_argument("--record", default="", help="项目operation-record；客群生成非空后推进S2,next=S3")
ap.add_argument("--approval", default="", help="S2 绑定profile+pid+rounds的审批凭证")
ap.add_argument("--project", required=True, help="稳定项目键=<operator_key>/<product_key>")
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
    except SystemExit:
        raise
    except (json.JSONDecodeError, TypeError):
        print(f"❌ 接口返回无法解析: {path}")
        sys.exit(1)

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
if not args.record:
    print("❌ 正式客群生成必须带 --record <operation-record.md>，否则换机状态无法推进"); sys.exit(2)
try: require_state(args.record, ("S1", "S2"))
except ValueError as exc: print(f"❌ {exc}"); sys.exit(4)

profile_path = Path(args.profile); profile_path = profile_path if profile_path.is_absolute() else KB / profile_path
if not ensure_same_project_paths(args.record, profile_path):
    print("❌ --record 与 --profile 不在同一项目目录"); sys.exit(4)
ps, issues, pm, ph = profile_gate(profile_path)
expected_project = f"{pm.get('operator_key','').strip()}/{pm.get('product_key','').strip()}"
if not issues and args.project != expected_project: issues.append("--project与产品档案项目键不一致")
if issues:
    for issue in issues: print(f"❌ 产品档案闸门: {issue}")
    sys.exit(4)
binding = {"project": args.project, "org_sha256": hashlib.sha256(str(args.org).encode()).hexdigest(), "profile": {"sha256": ph, "status": ps, "version": pm.get("profile_version", "")},
           "pid": str(pid), "rounds": args.rounds}
require_approval(args.approval, args.project, ("S2",), what="推理客群", expected_hash=stable_params_hash(binding))

for i in range(args.rounds):
    r = api("profile/inference-segment-generate", {"product_id": pid}, t=180)
    if not r.get("success"):
        print(f"❌ 第{i+1}轮 generate 未成功——中止，不读取旧客群、不推进状态")
        sys.exit(1)
    print(f"  第{i+1}轮 generate: ✅")
    time.sleep(1)

segs = api("profile/inference-segment-list", {"product_id": pid}).get("data", [])
segs = segs if isinstance(segs, list) else segs.get("list", [])
print(f"\n✅ 共 {len(segs)} 客群：")
for s in segs:
    print(f"  - {s.get('segment_name')} | query_en: {str(s.get('query_en'))[:60]} | total:{s.get('query_total')}")
if not segs:
    print("❌ 客群结果为空，不推进状态；稍后重试或检查档案")
    sys.exit(1)
if not args.record:
    print("❌ 正式客群生成缺 --record，无法推进换机状态真源"); sys.exit(2)
update_frontmatter(args.record, {"status": "S2", "next_state": "S3", "updated": time.strftime("%Y-%m-%d"),
                                     "profile_version": f'"{pm.get("profile_version", "")}"', "profile_sha256": f'"{ph}"'}, expected_states=("S1", "S2"))
print(f"✅ 运行状态已推进: {args.record} → S2 (next=S3)")
print(f"\n下一步: ①空白代理审查此产出 ②AI 按 segments/README.md 字段字典逐档评分建档 ③重生成索引")
