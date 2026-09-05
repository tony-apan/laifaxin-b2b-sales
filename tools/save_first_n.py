#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
通用：保存"前 N 条"（★正确API，实测 selectKeys空+selectTotal=前N）
★审批硬闸门: --profile + 稳定 --project 必填；审批参数JSON必须绑定 project/profile{sha,status,version}/keyword/n/company_tag/contact_tag/max/exclude/verify_status。
用法:
  python3 save_first_n.py --token $TOKEN --org <orgId> --keyword <seed-domain> --n 8000 \
    --company-tag <tagId> --contact-tag <tagId> --max 3 --profile runs/<operator_key>/<product_key>/product-profile.md \
    --record runs/<operator_key>/<product_key>/operation-record.md --approval ap-xxxx --project <operator_key>/<product_key>
"""
import argparse, hashlib, json, subprocess, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from approval import require_approval, stable_params_hash
from profile_utils import ensure_same_project_paths, profile_gate
from project_lock import acquire_project_lock
from update_run_state import require_state, update_frontmatter

def api(org, token, path, payload, timeout=120):
    cmd = ["curl","-sSL","-X","POST",f"https://web.laifaxin.com{path}?uid={org}",
           "-H","Content-Type: application/json","-H",f"accesstoken: {token}",
           "-d", json.dumps(payload)]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    try: return json.loads(r.stdout)
    except Exception: return {"success": False, "message": r.stdout[:200]}

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--token", required=True); ap.add_argument("--org", required=True)
    ap.add_argument("--keyword", required=True, help="搜索词/种子网址")
    ap.add_argument("--n", type=int, required=True, help="保存前N条")
    ap.add_argument("--company-tag", required=True); ap.add_argument("--contact-tag", required=True)
    ap.add_argument("--max", type=int, default=3, help="每公司邮箱数(★默认3,阶梯3→6→9:存不到数据才升级,以3为阶梯)")
    ap.add_argument("--exclude", default="CN,TW,HK,MO", help="排除国家/地区(默认4区)")
    ap.add_argument("--profile", required=True, help="当前产品档案路径；项目键/hash/status进入审批绑定")
    ap.add_argument("--record", required=True, help="项目operation-record；保存任务创建成功后推进S5,next=S6")
    ap.add_argument("--approval", default="", help="★绑定本次全部保存参数的S5凭证")
    ap.add_argument("--project", required=True, help="稳定项目键=<operator_key>/<product_key>")
    args = ap.parse_args()
    try: require_state(args.record, ("S4", "S5")); acquire_project_lock(args.record, "save_first_n")
    except (ValueError, RuntimeError) as exc: print(f"❌ {exc}"); raise SystemExit(4)
    profile_path = Path(args.profile)
    if not profile_path.is_absolute(): profile_path = Path(__file__).resolve().parent.parent / profile_path
    if not ensure_same_project_paths(args.record, profile_path):
        print("❌ --record 与 --profile 不在同一项目目录"); raise SystemExit(4)
    pstatus, pissues, pmeta, psha = profile_gate(profile_path)
    expected_project = f"{pmeta.get('operator_key','').strip()}/{pmeta.get('product_key','').strip()}"
    if not pissues and args.project != expected_project: pissues.append("--project与产品档案项目键不一致")
    if pissues:
        for issue in pissues: print(f"❌ 产品档案闸门: {issue}")
        raise SystemExit(4)
    exclude = sorted({x.strip() for x in args.exclude.split(",") if x.strip()})
    binding = {"project": args.project, "org_sha256": hashlib.sha256(str(args.org).encode()).hexdigest(), "profile": {"sha256": psha, "status": pstatus, "version": pmeta.get("profile_version", "")},
               "keyword": args.keyword, "n": args.n, "company_tag": args.company_tag, "contact_tag": args.contact_tag,
               "max": args.max, "exclude": exclude, "verify_status": ["valid", "unkown"]}
    require_approval(args.approval, args.project, ("S5",), what="保存前N", expected_hash=stable_params_hash(binding))
    # ★ 正确 exclude schema（实测 2026-08-29）：必须带 value:"" + valueType:"select"！
    # 排除生效（amc: 含4区 6→1，仅剩种子公司自身；total不变=截断+补位）
    exclude = sorted({x.strip() for x in args.exclude.split(",") if x.strip()})
    filters = [{"property":"country_code","operator":"exclude","value":"","values":exclude,"valueType":"select"}] if exclude else []
    payload = {
        "companyTags":[args.company_tag], "companyOption":"nothing", "companySave":True,
        "contactTags":[args.contact_tag], "contactOption":"nothing",
        "contactVerifyStatus":["valid","unkown"],
        "contactPositions":[], "contactExcludes":[], "contactMaxCount":args.max,
        "contactSave":True,
        "selectKeys":[],                # ★ 空 = 前N！
        "selectSort":{}, "selectTotal":args.n, "selectOption":"front",
        "filters":filters, "filter":{},
        "keyword":args.keyword, "logic":"and",
    }
    r = api(args.org, args.token, "/api/refine/company-save", payload, timeout=180)
    if not r.get("success"):
        print("❌ 保存任务创建失败: " + str(r.get("message") or r)[:160])
        raise SystemExit(1)
    task_id = (r.get("data") or {}).get("id", "") if isinstance(r.get("data"), dict) else ""
    print("保存前{}条 task:{}".format(args.n, task_id))
    if args.record:
        update_frontmatter(args.record, {"status": "S5", "next_state": "S6", "save_task_id": f'"{task_id}"',
                                               "company_tag_id": f'"{args.company_tag}"', "contact_tag_id": f'"{args.contact_tag}"'}, expected_states=("S4", "S5"))
        print(f"✅ 运行状态已推进: {args.record} → S5 (next=S6；任务finished后再推进S6)")
    print("★ 验证: 用 backend-task-status(type=cluesSave, id=<上面task id>) 查 contactSaveCount>0=提邮箱、companySaveCount=公司数")
    print("   ⚠️ 勿用 company-save-list(看不到 contactSaveCount,会误判邮箱0)——见 api-reference")
    print("📊 数量账(用户问'怎么才存这么点'时照此解释,模板 output-templates/S6-数量账.md):")
    print(f"   · 每公司上限 {args.max} 个邮箱(防止过度触达) · 平台验真过滤(有效+未知都存) · 跨批去重 · 邮箱异步分批提取")
    print(f"   · 正常水平约 1.4~2.1 邮箱/家;低于 1.0 建议检查锚点纯度(L-46)")

if __name__ == "__main__":
    main()
