#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
通用：保存"前 N 条"（★正确API，实测 selectKeys空+selectTotal=前N）
★审批硬闸门(审批闸门(工具级)): 必须先经 S5 确认节点, 传 --approval <id> --project <产品> 才执行
用法:
  python3 save_first_n.py --token $TOKEN --org <orgId> \
    --keyword <seed-domain> --n 8000 \
    --company-tag <tagId> --contact-tag <tagId> --max 3 \
    --approval ap-xxxx --project 皮筏艇
"""
import argparse, json, subprocess, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from approval import require_approval

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
    ap.add_argument("--approval", default="", help="★审批凭证id(审批闸门·工具级): .local/approvals.tsv 或编排器输出")
    ap.add_argument("--project", default="", help="产品名(审批project匹配)")
    args = ap.parse_args()
    require_approval(args.approval, args.project, ("S5",), what="保存前N")
    # ★ 正确 exclude schema（实测 2026-08-29）：必须带 value:"" + valueType:"select"！
    # 排除生效（amc: 含4区 6→1，仅剩种子公司自身；total不变=截断+补位）
    exclude = [x.strip() for x in args.exclude.split(",") if x.strip()]
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
    print("保存前{}条 task:".format(args.n), r.get("data",{}).get("id","") if r.get("success") else r.get("message",""))
    print("★ 验证: 用 backend-task-status(type=cluesSave, id=<上面task id>) 查 contactSaveCount>0=提邮箱、companySaveCount=公司数")
    print("   ⚠️ 勿用 company-save-list(看不到 contactSaveCount,会误判邮箱0)——见 api-reference")
    print("📊 数量账(用户问'怎么才存这么点'时照此解释,模板 output-templates/S6-数量账.md):")
    print(f"   · 每公司上限 {args.max} 个邮箱(防止过度触达) · 平台验真过滤(有效+未知都存) · 跨批去重 · 邮箱异步分批提取")
    print(f"   · 正常水平约 1.4~2.1 邮箱/家;低于 1.0 建议检查锚点纯度(L-46)")

if __name__ == "__main__":
    main()
