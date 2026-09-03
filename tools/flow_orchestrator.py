#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""⚠️ 流程编排器【原型/向导,非一键】——只做节点确认向导+approvals记账；保存/模板/序列/contact-add 须由人工/对应工具执行，本脚本不自动执行。例外：S2 的租户本地推演写(inference-product-add+inference-segment-generate)用于展示候选客群,客群选择仍须用户确认。
用法:
  python3 flow_orchestrator.py --token <TOKEN> --org <orgId> --nickname <昵称> \
      --product "金属粉末" --product-info "金属粉末/3D打印/增材/分销" \
      [--seed <精准客户网址可选>] [--skip-preview] [--dry-run]
规则:
  - 高影响节点(客群/种子/保存/contact-add/激活) 永远等用户确认（stdin 输入）
  - --skip-preview: 仅跳过模板草稿展示（对应"不要看模板"），不豁免其他
  - 每个确认写入 .local/approvals.tsv
  - 测试不激活；异常→ERROR_BLOCKED 退出非0
"""
import json, subprocess, time, sys, argparse, hashlib, os
import re as _re
from pathlib import Path

KB = Path(__file__).resolve().parent.parent
APPROVALS = KB / ".local" / "approvals.tsv"
sys.path.insert(0, str(KB / "tools"))
from approval import record as record_approval

ap = argparse.ArgumentParser()
ap.add_argument("--token", required=True, help="accesstoken 整串(格式 web.laifaxin.com&<orgId>&<hash>)——用户按教程获取: https://www.laifa.xin/share/ai/laifaxin-ai-account-connection")
ap.add_argument("--org", required=True, help="orgId(=token 第2段;必填,禁止默认租户)")
ap.add_argument("--nickname", required=True, help="昵称=客户邮件落款(建议英文,如 Tina from ABC Corp)")
ap.add_argument("--product", required=True, help="产品名(必填)")
ap.add_argument("--product-info", default="", help="产品一句话(可选;未提供则用 --product)。★禁止填编造的 MOQ/认证/产能数字——用户没给的数字一律不写")
ap.add_argument("--seed", default="", help="精准客户网址(可选,有→快速路径A)")
ap.add_argument("--exclude", default="CN,TW,HK,MO")
ap.add_argument("--skip-preview", action="store_true", help="跳过模板草稿展示(用户说不要看)")
ap.add_argument("--dry-run", action="store_true", help="只读盘点/展示，不写")
args = ap.parse_args()
STATE = {"project": f"{args.product}", "params": {"product": args.product, "info": args.product_info, "seed": args.seed, "exclude": args.exclude}}

def api(path, p, t=60):
    cmd=["curl","-sSL","-X","POST",f"https://web.laifaxin.com/api/{path}?uid={args.org}","-H","Content-Type: application/json","-H",f"accesstoken: {args.token}","-d",json.dumps(p)]
    r=subprocess.run(cmd,capture_output=True,text=True,timeout=t)
    try: return json.loads(r.stdout)
    except: return {}

LOGIN_GUIDE_URL = "https://www.laifa.xin/share/ai/laifaxin-ai-account-connection"

def check_login_first():
    """AI-2: S0 第一步=登录检查——复用 tools/check_login.py 的硬化三分类(exit 0/1/2/3), 不内联复写(terra 4-③)。"""
    if args.dry_run:
        print("●S0 第一步·登录检查: (dry-run 跳过线上校验)"); return
    try:
        r = subprocess.run([sys.executable, str(KB/"tools"/"check_login.py"), "--token", args.token, "--org", args.org],
                           capture_output=True, text=True, timeout=60)
    except subprocess.TimeoutExpired:
        print("●S0 第一步·登录检查: ❌ 超时——稍等重试（这不是 token 问题）。"); sys.exit(1)
    print("●S0 第一步·登录检查:")
    print("\n".join("  " + l for l in (r.stdout or "").strip().splitlines()))
    if r.returncode == 1:
        print("   流程终止（token 失效——按上面教程重取后重跑本向导, 已确认 approvals 不作废）。")
    elif r.returncode == 2:
        print("   流程终止（token 复制不完整——按上面方法二一键复制后重跑）。")
    elif r.returncode != 0:
        print("   流程终止（网络/接口问题,不是 token 问题——稍等重试）。")
    if r.returncode != 0:
        sys.exit(1)

def record(state, decision, quote, params):
    h=hashlib.sha256(json.dumps(params,sort_keys=True).encode()).hexdigest()[:12]
    if args.dry_run:
        print("  (dry-run 不写凭证) {}: {}".format(state, quote[:30]))
        return ""
    aid=record_approval(STATE["project"], state, decision, quote, h, "confirmed")
    print(f"  ✅ 凭证写入 {state}: {quote[:30]} (approval_id={aid})")
    print(f"     → 写操作工具须带: --approval {aid} --project {STATE['project']} (审批硬闸门·工具级)")
    return aid

CONFIRM_WORDS = ("确认","是","好","好的","可以","行","嗯","嗯嗯","行吧","好了","ok","okay","y","yes")

def confirm(state, prompt, params):
    """高影响节点:打印+等确认。返回用户原话(确认时,truthy)或 False(修改)。
    B4-1: 统一词族解析; 听不懂→重问(不再默默记为修改); 修改→诚实提示(不假称回退)。"""
    if args.dry_run:
        print(f"【确认·{state}】{prompt} (dry-run 自动通过)"); return "(dry-run)"
    seen_modify = getattr(confirm, "_seen", set())
    while True:
        try:
            ans=input(f"\n❓【确认节点 {state}】{prompt}\n   回复「确认」继续 /「否」终止 / 或直接说要改什么: ").strip()
        except EOFError:
            print("  ❌ 需要交互终端运行本向导（stdin 已关闭）"); sys.exit(2)
        if not ans:
            print("  没听懂——请回复「确认」「否」或你的修改意见"); continue
        low = ans.lower()
        # ★F1-F3(R5 fuzz): 犹豫词/否定+确认 一律不给确认凭证——凭证安全优先于判定聪明
        neg_conf = _re.search(r'(不|别|甭|莫|莫要|勿|先不|暂不|不用|不要|无须|无需|没法|无法|难以|没|还没)[^。，,；;。！？!?]{0,12}确认|确认[^。，,；;。！？!?]{0,12}(不|别|否|没)', ans)
        hesitate = _re.search(r'(别急|等等|稍等|先看|考虑|想想|再看看|回头|迟点|再说|研究|商量|暂缓|犹豫|可能|大概|应该|也许)', ans)
        has_confirm = ((("确认" in ans) and not neg_conf and not hesitate) or (low in CONFIRM_WORDS)
                       or any(w in low.split() for w in ("ok","okay","y","yes","confirm")))
        if has_confirm:
            record(state,"confirm",ans,params); return ans
        if (ans in ("不","否","别","甭","莫","不要","不行","n","no") or ans.startswith(("否","不要","不行","甭","莫"))
                or _re.match(r'^(no|nope|nah)\b', low)):
            print("  已终止(用户否决)"); sys.exit(2)
        if (state, ans) not in seen_modify:
            seen_modify.add((state, ans)); record(state,"modify",ans,params)
            confirm._seen = seen_modify  # ★P1-1: 赋值必须在 return 前(原放 return 后=死代码)
        print("  ✍ 已记录你的修改意见——由 AI 据此调整参数后重新发起本节点确认(本向导不自动回退;同话重复意见不重复记账)")
        return False

# ---------- S0 INPUT GATE ----------
print(f"●S0 INPUT_GATE: 昵称={args.nickname} | 产品={args.product} | 产品信息={'用户提供' if args.product_info != args.product else '仅一句话(未提供详述) '}")
if not (args.nickname and args.product): print("  ❌ 缺昵称/产品，终止"); sys.exit(1)
if not args.product_info: args.product_info = args.product  # 一句话产品兜底;禁止为凑字段编造 MOQ/认证
check_login_first()
record("S0","gate_ok",f"nickname={args.nickname},product={args.product}",STATE["params"])

# ---------- 只读盘点自证干净(离线部分) ----------
if not args.dry_run:
    print("●自证盘点(只读): 序列/模板/产品档案(两套)/标签/视图/联系人")
    for name,path,p in [("产品档案(product)","profile/product-list",{"current":1,"pageSize":10,"filter":{},"sort":{"create_time":-1},"keyword":""}),
                        ("产品档案(inference)","profile/inference-product-list",{}),
                        ("序列","sequences/sequence-count",{})]:
        d=api(path,p,t=40)
        tot=d.get("data")
        if isinstance(tot,dict): tot=tot.get("total",tot)
        if tot is None or tot == {}:
            tot = "未取到(接口偶发空 平台接口间歇空(已知),可重试)"
        print("   {}: {}".format(name, tot if not isinstance(tot,dict) else "未取到"))

# ---------- S1 PATH ----------
pathA = bool(args.seed)
print(f"●S1 PATH_PENDING: {'快速路径A(有精准网址)' if pathA else '标准路径B(无网址→先推演)'}")
if not args.dry_run and not pathA:
    print("  (标准路径: 需要你确认→推演客群, 或提供精准网址)")

# ---------- S2 SEGMENT(标准路径) ----------
if not pathA:
    print("●S2 SEGMENT_PENDING: 推演客群(默认4个, 可扩展)")
    # ★B-3: 写操作(建产品档案+推演客群)必须在用户确认后才执行——先确认, 后写
    if confirm("S2_客群", "将创建产品档案并推演客群（写操作，租户本地），推演结果出来后我再给您选。继续？", STATE["params"]):
        if not args.dry_run:
            # ★ISS-48: 建【推理档案】须用 inference-product-add(字段 zh/en/desc_zh/exclusions)——旧用基础档案 product-add 会导致 inference-segment-generate 返回 500
            pa=api("profile/inference-product-add",{"product_name":args.product,"product_zh":args.product,"product_en":args.product,"product_desc_zh":args.product_info,"product_exclusions":""})
            pid=pa.get("data",{}).get("product_id") or pa.get("data",{}).get("_id") or pa.get("data",{}).get("id") or (pa.get("data") if isinstance(pa.get("data"),str) else "")
            pa_ok = "成功" if pa.get("success") else "未成功(token/网络? 检查S0登录检查输出)"
            print("   推理档案add: {} {}".format(pa_ok, str(pid)[:16] if pid else ""))
            if not pid:
                print("  ❌ 推理档案创建失败（多半 token 失效/网络——看上方登录检查输出）——流程终止,勿确认空客群")
                sys.exit(1)
            # 推演（★接口慢: generate 后须轮询 list 直到非空, 最长~60s; 立即 list 常为空）
            api("profile/inference-segment-generate",{"product_id":pid})
            segs=[]
            for _i in range(6):
                segs=api("profile/inference-segment-list",{"product_id":pid}).get("data",[]) or []
                if segs: break
                time.sleep(10)
            print("   ★推演客群(默认4+; 按 v2 客户线人工剔除跨产品污染簇, 见 threshold-method):")
            for s in segs: print(f"    - {s.get('segment_name')} | {s.get('value_path')}")
            if not segs: print("   ⚠️ 推演返回空(平台慢/未落库)——等 1-2 分钟重跑本向导, 或改跑 tools/segments_infer.py")

# ---------- S3 SEED(快速路径也需确认; B4-4: 换种子真正生效) ----------
def show_seed_candidates(kw):
    d=api("refine/company-list",{"keyword":kw,"current":1,"pageSize":8,"filters":[],"logic":"and"}).get("data",{})
    lst=d.get("list",[]) if isinstance(d,dict) else []
    if not lst:
        print("    (该网址暂未搜到候选——可能接口偶发空 平台接口间歇空(已知) 或网址不精准)")
    for c in lst[:5]:
        print("    - {:28s} {} {}".format((c.get('company_name') or '')[:26], c.get('country_code'), c.get('emailsCount')))
print("●S3 SEED_PENDING: 候选种子(精准客户) + 采购可能/邮箱")
if not args.dry_run:
    if args.seed:
        print("  当前种子: " + str(args.seed))
        show_seed_candidates(args.seed)
    else:
        print("  暂无候选种子——把一个精准客户网址直接打在回复里，或回复「确认」由 AI 走关键词路径")
        print("  （标准路径：向用户要 query_en 客群画像描述做文本搜种子发现；从结果页挑真实渠道商做种子——文本搜结果本身不直接保存）")
        print("  ★种子须用【域名】：候选公司名无 domain 字段，先用 tools/seed_resolve.py --company \"<公司名>\" 反查真实域名（L-45）")
while True:
    r3 = confirm("S3_种子", "确认用这个锚点继续？(回复编号/新网址/确认)", STATE["params"])
    if r3 is False:
        m3 = _re.search(r'[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', input("  请把新种子网址完整发一次: ").strip())
        if m3:
            args.seed = m3.group(0); STATE["params"]["seed"] = args.seed; pathA = True
            print("  ✅ 种子已更新为: " + args.seed)
            if not args.dry_run: show_seed_candidates(args.seed)
        else:
            print("  没认出网址——请单独发一次完整网址(如 example.com)，或回复「确认」用原种子继续")
        continue
    break

# ---------- S4 AUDIT (只读, 可自由) ----------
print("●S4 AUDIT_RUNNING: 只读搜客+AI语义审计(50页跳→三页平均→逐页→跌破往前)——见工具 audit_company.py")
if args.dry_run: print("  (dry-run 跳过审计)")
else:
    kw = args.seed
    if kw:
        print(f"  种子={kw}: ★按 v2 三条客户线(直采/OEM/拓品, threshold-method.md)逐条 AI 判定+判定表留痕; 50页跳→三页平均→逐页→跌破往前; 边界案例做敏感性检查; 未完成不能保存")

# ---------- S5 SAVE_PENDING (B4-5: 解析并回显 N) ----------
print("●S5 SAVE_PENDING: 展示 临界N/标签/排除/max/点数 → 确认后保存")
r5 = confirm("S5_保存参数", "保存前N条+排除4区+max3? (可写「确认保存 前N=2000」指定数量)", STATE["params"])
if r5:
    m5 = _re.search(r'[Nn]=(\d+)', str(r5)) or _re.search(r'前(\d+)', str(r5))
    if m5:
        print("  ✅ 已记录 N={}——保存命令将用 --n {}".format(m5.group(1), m5.group(1)))
    else:
        print("  (未指定 N——AI 将按审计临界折算并在保存命令里回显)")

# ---------- S6 SAVE_RUNNING ----------
print("●S6 SAVE_RUNNING: 用 save_first_n.py 保存(等finished)→ 见工具")
if not args.dry_run:
    print("  (实际调用 save_first_n.py; N/tags 由确认节点输入; ★须带 S5 的 --approval id)")

# ---------- S7 TEMPLATE_PENDING ----------
print("●S7 TEMPLATE_PENDING: 展示3-5个跨轮模板+理由(草稿)")
if args.skip_preview:
    print("  (用户要求跳过模板预览→直接按推荐生成)")
elif confirm("S7_模板预览","展示草稿后确认生成120个?", STATE["params"]):
    pass

# ---------- S8 TEMPLATE_BUILD ----------
print("●S8 TEMPLATE_BUILD: 生成120差异化模板(用 gen_templates.py; ★须带 S7 的 --approval id; 生成后跑 check_template_diff 断言差异)")

# ---------- S9 SEQUENCE_PENDING ----------
print("●S9 SEQUENCE_PENDING: 12步(step1=30分/step2=5天/step3=15天/step4-12=30天)+纽约时区+30000/5+禁发标签(询盘/不发) → 确认后建")
if confirm("S9_序列配置","以上序列配置确认? 输入'确认序列' ", STATE["params"]):
    pass

# ---------- S10 CONTACT_PENDING ----------
print("●S10 CONTACT_PENDING: 保存finished+标签>0+序列inactive+对账 → 确认后 contact-add(views:[])")
if confirm("S10_加联系人","确认加入联系人? 输入'确认加入' (只读对账后)", STATE["params"]):
    pass

# ---------- S11 READY_INACTIVE ----------
print("\n●S11 READY_INACTIVE: ⚠️本脚本仅向导,写操作须另行执行(见各步骤提示)")
print(f"  产品={args.product} | 昵称={args.nickname} | 路径={'A快速' if pathA else 'B标准'} | 排除4区={args.exclude}")
print("  ⚠️ 未激活——仅用户明确'确认激活'才 S12")
record("S11","ready_inactive","流程完成待确认",STATE["params"])
print("\n✅ 输出: 见本地运行记录（.local/ 与 runs/<运营方>/<产品>/ 档案，不入 Git）+ 本流程(不激活)\n请在对话里向用户发完整流程待确认。")
