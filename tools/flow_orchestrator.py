#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""⚠️ 流程编排器【原型/向导,非一键】——只做节点确认向导+approvals记账；保存/模板/序列/contact-add 须由人工/对应工具执行，本脚本不自动执行。例外：S2 的租户本地推演写(inference-product-add+inference-segment-generate)用于展示候选客群,客群选择仍须用户确认。
用法:
  python3 flow_orchestrator.py --token <TOKEN> --org <orgId> --nickname <纯昵称> \
      --product "金属粉末" --product-info "金属粉末/3D打印/增材/分销" \
      --profile runs/<operator_key>/<product_key>/product-profile.md \
      [--seed <精准客户网址可选>] [--skip-preview] [--dry-run]
规则:
  - 签名昵称=纯个人昵称(如 Tony/Iris);启动即校验,含公司/职位/产品/邮箱/数字/from → 退出2
  - 产品档案硬闸门(任何平台写操作前): 档案须存在且 status=confirmed/declined;draft/缺失 → 打印 S0a 索取/确认指引并退出4
    confirmed→档案正文作为 product_info 底座(显式 --product-info 只追加不覆盖);declined→可继续但只能用无具体事实口径
  - 高影响节点(客群/种子/保存/contact-add/激活) 永远等用户确认（stdin 输入）
  - --skip-preview: 仅跳过模板草稿展示（对应"不要看模板"），不豁免其他
  - 每个确认写入 .local/approvals.tsv(含 profile hash/version/project 等实际参数, memo=stable_params_hash)
  - ★凭证三态(静态红队P0修复): 只有用户确认且本节点实际参数齐全 → confirm/confirmed(可授权);
    用户给修改意见 → modify/modified(不可授权); 参数不全(拿不到实际N/plan/tmap/seq/task等) → decision_pending/pending(不可授权),
    对应工具执行前须由专门审批命令 `python3 tools/approval.py grant --params-file <实际参数.json>` 铸造绑定凭证——绝不伪绑定
  - 写节点绑定参数(与对应工具端schema逐字段一致):
      S5: {project, profile{sha256,status,version}, n, seed, exclude}
      S7: {project, profile{sha256,status,version}, plan{sha256}}           (rebuild_templates 另绑定 seq/suffix, 用 grant 铸造)
      S9: {project, profile{sha256,status,version}, tmap{sha256}, rules{...}}
      S10(=contact_add.py): {project, seq, tags(sorted), task}
      S12(=activate_sequence.py): {project, seq, profile{sha256,status,version}, compliance{sha256}}
  - 首次运行创建 .local/operators/<operator_key>.md(公司级资料;不含token;旧单文件兼容读取)
  - 测试不激活；异常→ERROR_BLOCKED 退出非0
"""
import json, subprocess, time, sys, argparse, hashlib, os
import re as _re
from pathlib import Path

KB = Path(__file__).resolve().parent.parent
APPROVALS = KB / ".local" / "approvals.tsv"
sys.path.insert(0, str(KB / "tools"))
from approval import confirm_quote_ok, record as record_approval, stable_params_hash
from profile_utils import profile_gate, read_profile, validate_nickname
from update_run_state import require_state, update_frontmatter

ap = argparse.ArgumentParser()
ap.add_argument("--token", required=True, help="accesstoken 整串(格式 web.laifaxin.com&<orgId>&<hash>)——用户按教程获取: https://www.laifa.xin/share/ai/laifaxin-ai-account-connection")
ap.add_argument("--org", required=True, help="orgId(=token 第2段;必填,禁止默认租户)")
ap.add_argument("--nickname", required=True, help="昵称=客户邮件落款·纯个人昵称(如 Tony/Iris;启动即校验:含公司/职位/产品/邮箱/数字/from→退出2)")
ap.add_argument("--product", required=True, help="产品名(必填)")
ap.add_argument("--product-info", default="", help="产品一句话(可选;档案 confirmed 时追加在档案正文之后,不覆盖档案)。★禁止填编造的 MOQ/认证/产能数字——用户没给的数字一律不写")
ap.add_argument("--profile", required=True, help="产品档案路径(硬闸门): runs/<operator_key>/<product_key>/product-profile.md; status须confirmed/declined;draft/缺失→S0a指引+退出4")
ap.add_argument("--seed", default="", help="精准客户网址(可选,有→快速路径A)")
ap.add_argument("--exclude", default="CN,TW,HK,MO")
ap.add_argument("--skip-preview", action="store_true", help="跳过模板草稿展示(用户说不要看)")
ap.add_argument("--dry-run", action="store_true", help="只读盘点/展示，不写(签名/档案硬闸门不豁免)")
# ★写节点实际参数载体(向导拿不到完整参数时不签发可执行凭证, 由这些参数或专门审批命令 grant 补齐绑定)
ap.add_argument("--save-n", type=int, default=0, help="S5 实际保存条数N(与回复中 前N=xx 等效; 缺→S5只记decision_pending)")
ap.add_argument("--plan", default="", help="S7 模板计划JSON路径(实际plan; 缺→S7只记decision_pending)")
ap.add_argument("--tmap", default="", help="S9 模板name→id映射JSON路径(gen_templates --out 产物; 缺→S9只记decision_pending)")
ap.add_argument("--seq", default="", help="S9/S10/S12 序列id(实际序列; 缺→S10/S12只记decision_pending)")
ap.add_argument("--contact-tags", default="", help="S10 联系人标签id(逗号分隔,与contact_add --tags一致; 缺→S10只记decision_pending)")
ap.add_argument("--task", default="", help="S10 保存任务id(与contact_add --task一致; 缺→S10只记decision_pending)")
ap.add_argument("--compliance-file", default="", help="S12 合规核验JSON(market/list_source/sender_identity/unsubscribe/suppression均pass; 与activate_sequence一致)")
args = ap.parse_args()

# ---------- 签名昵称硬闸门(启动即校验,退出2) ----------
_nick_ok, _nick_why = validate_nickname(args.nickname)
if not _nick_ok:
    print(f"●S0 签名闸门: ❌ 昵称非法 {args.nickname!r} —— {_nick_why}")
    print("   签名=纯个人昵称(如 Tony/Iris);公司名/官网/邮箱/职位/产品绝不进签名——可写入产品档案(product-profile)供建档/背调。请向用户要一个纯昵称后重跑。(exit 2)")
    sys.exit(2)

# ---------- 产品档案硬闸门(在任何平台写操作之前;draft/缺失→S0a 指引+退出4) ----------
PROFILE_PATH = Path(args.profile)
if not PROFILE_PATH.is_absolute():
    PROFILE_PATH = KB / PROFILE_PATH
PROFILE_STATUS, PROFILE_ISSUES, PROFILE_META, PROFILE_SHA = profile_gate(PROFILE_PATH)
if PROFILE_ISSUES:
    print(f"●S0a 产品档案闸门: ❌ {PROFILE_PATH}")
    for _i in PROFILE_ISSUES:
        print(f"   - {_i}")
    print("  S0a·产品资料主动索取/确认指引(修好后重跑本向导):")
    print("   1) AI 主动向用户要一次产品资料(给模板可跳过,不逼问): 公司名/官网/产品目录/卖点/认证/产能/MOQ/交期/价格带——")
    print("      这些是用户自己的商业资产,只写本地档案供建档/背调,绝不进邮件签名(签名=纯昵称);客户/潜在联系人第三方联系方式不得写入档案。")
    print("   2) 用户给了 → AI 按 runs/_template/product-profile.md 填8字段(每项 source=用户/URL/推断 + confidence) →")
    print("      python3 tools/product_profile.py confirm --profile <档案> --by <纯昵称> --quote <用户确认原话>")
    print("   3) 用户明确不给 → python3 tools/product_profile.py init --profile <档案> --operator-key <运营方> --product-key <产品> --declined")
    print("      (declined 仍可继续流程,但模板只能用无具体事实的通用口径)")
    print("   4) 首次建档 → python3 tools/product_profile.py init --profile <档案> --operator-key <运营方> --product-key <产品> (status=draft,待确认)")
    sys.exit(4)

_explicit_info = args.product_info  # 用户显式给的一句话(可为空)
if PROFILE_STATUS == "confirmed":
    _body = read_profile(PROFILE_PATH)[1].strip()
    if _body:
        args.product_info = _body + (f"\n\n[用户一句话补充] {_explicit_info}" if _explicit_info else "")
    elif _explicit_info:
        args.product_info = _explicit_info
elif PROFILE_STATUS == "declined":
    print("●S0a 产品档案闸门: ⚠️ status=declined——可继续,但后续开发信只能用无具体事实的通用口径")
    print("   (禁具体数字/认证/交期/MOQ/产能/价格/稀缺话术;用户后续给了资料可编辑档案8字段后再 confirm——init 不覆盖已有档案)")
    args.product_info = _explicit_info or args.product  # 一句话产品兜底;禁止为凑字段编造 MOQ/认证

PROJECT_KEY = f"{PROFILE_META.get('operator_key', '').strip()}/{PROFILE_META.get('product_key', '').strip()}"
if args.product != PROFILE_META.get("product_key", "").strip():
    print(f"●S0a 产品档案闸门: ❌ --product={args.product!r} 与 profile.product_key={PROFILE_META.get('product_key')!r} 不一致——拒绝跨产品复用档案。(exit 4)")
    sys.exit(4)
STATE = {"project": PROJECT_KEY, "params": {"product": args.product, "info": args.product_info, "seed": args.seed, "exclude": args.exclude,
        "profile": {"path": str(PROFILE_PATH), "sha256": PROFILE_SHA, "status": PROFILE_STATUS,
                    "version": PROFILE_META.get("profile_version", "")}}}

def ensure_operator_profile():
    """确保当前 operator_key 的公司级档案存在并与纯昵称一致；兼容读取旧单文件，不含 token。"""
    okey = PROFILE_META.get("operator_key", "").strip()
    op = KB / ".local" / "operators" / f"{okey}.md"
    legacy = KB / ".local" / "operator-profile.md"
    candidate = op
    if not op.exists() and legacy.exists():
        old = {}
        for line in legacy.read_text(encoding="utf-8", errors="replace").splitlines():
            if ":" in line and not line.lstrip().startswith("#"):
                k, v = line.split(":", 1); old[k.strip()] = v.strip()
        if old.get("operator_key") == okey and old.get("nickname") == args.nickname:
            candidate = legacy
            print("  ℹ️ 兼容读取旧版 .local/operator-profile.md；建议用 operator_profile.py 迁移到多运营方路径")
    if candidate.exists():
        current = {}
        for line in candidate.read_text(encoding="utf-8", errors="replace").splitlines():
            if ":" in line and not line.lstrip().startswith("#"):
                k, v = line.split(":", 1); current[k.strip()] = v.strip()
        if current.get("operator_key") != okey or current.get("nickname") != args.nickname:
            print(f"●S0 运营方档案闸门: ❌ {candidate.relative_to(KB)} 与当前 profile 不一致(operator_key/nickname)——拒绝跨运营方续跑。(exit 4)")
            sys.exit(4)
        return
    op.parent.mkdir(parents=True, exist_ok=True)
    op.write_text("# 运营方档案（本地，不入 Git；不含 token）\n"
                  f"operator_key: {okey}\nnickname: {args.nickname}\n"
                  "company_name:\nwebsite:\ncontact_email:\ntarget_markets:\ndefault_languages:\n",
                  encoding="utf-8")
    print(f"  ✅ 已初始化 {op.relative_to(KB)} (nickname={args.nickname}; 公司资料待按 operator-profile-sop 渐进补充)")

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

def sha_file(path):
    """文件整体 sha256(十六进制64位); 不存在/读不了返回空串(plan/tmap/compliance 绑定用, 与对应工具同口径)。"""
    try:
        return hashlib.sha256(Path(path).read_bytes()).hexdigest()
    except Exception:
        return ""

def node_params(extra=None):
    """写节点绑定参数基底(与各工具端schema一致, 不含路径类易变字段): project + profile{sha256,status,version}。"""
    p = {"project": STATE["project"],
         "profile": {"sha256": STATE["params"]["profile"]["sha256"],
                     "status": STATE["params"]["profile"]["status"],
                     "version": STATE["params"]["profile"]["version"]}}
    if extra:
        p.update(extra)
    return p

def record(state, decision, quote, params):
    """★凭证三态记账: confirm→confirmed(可授权) / modify→modified(不可授权) / 其他(decision_pending等)→pending(不可授权)。"""
    h = stable_params_hash(params)
    if args.dry_run:
        print("  (dry-run 不写凭证) {}: {}".format(state, quote[:30]))
        return ""
    status = "confirmed" if decision == "confirm" else ("modified" if decision == "modify" else "pending")
    aid = record_approval(STATE["project"], state, decision, quote, h, status)
    if status == "confirmed":
        print(f"  ✅ 凭证写入 {state}: {quote[:30]} (approval_id={aid}) [status=confirmed, 参数哈希已绑定 {h}]")
        print(f"     → 写操作工具须带: --approval {aid} --project {STATE['project']} (审批硬闸门·工具级)")
    elif status == "modified":
        print(f"  ✍ 修改意见已记账 {state} [status=modified——不可授权写操作]")
    else:
        print(f"  ⏸ decision_pending 已记账 {state} [status=pending——不可授权, 须专门审批命令补齐绑定后铸造]")
    return aid

CONFIRM_WORDS = ("确认","是","好","好的","可以","行","嗯","嗯嗯","行吧","好了","ok","okay","y","yes")

def classify(ans):
    """答案三分类: 'confirm' / 'reject' / 'modify'。犹豫词/否定+确认一律不给 confirm(凭证安全优先)。"""
    low = ans.lower()
    # ★F1-F3(R5 fuzz): 犹豫词/否定+确认 一律不给确认凭证——凭证安全优先于判定聪明
    if _re.search(r"[?？]", ans) or _re.search(r"\b(?:no|not|never|don'?t|do not|cannot|can't|wait|later|cancel|stop)\b", low):
        return "reject"
    standalone_neg = _re.search(r'(?:^|[，,。；;！？!?\s])(?:否|拒绝|不同意)(?:$|[，,。；;！？!?\s])', ans)
    neg_conf = _re.search(r'(不|别|甭|莫|莫要|勿|先不|暂不|不用|不要|无须|无需|没法|无法|难以|没|还没)[^。，,；;。！？!?]{0,12}确认|确认[^。，,；;。！？!?]{0,12}(不|别|否|没)', ans)
    hesitate = _re.search(r'(别急|等等|稍等|先看|考虑|想想|再看看|回头|迟点|再说|研究|商量|暂缓|犹豫|可能|大概|应该|也许)', ans)
    if standalone_neg or neg_conf:
        return "reject"
    if hesitate:
        return "modify"
    if confirm_quote_ok(ans):
        return "confirm"
    if (ans in ("不","否","别","甭","莫","不要","不行","n","no") or ans.startswith(("否","不要","不行","甭","莫"))
            or _re.match(r'^(no|nope|nah)\b', low)):
        return "reject"
    return "modify"

def ask(state, prompt, terminate_on_no=True):
    """打印+等输入, 返回 (kind, ans)。kind=confirm/reject/modify; reject 时默认终止(exit 2), terminate_on_no=False 则返回。"""
    if args.dry_run:
        print(f"【确认·{state}】{prompt} (dry-run 自动通过)"); return "confirm", "(dry-run)"
    while True:
        try:
            ans=input(f"\n❓【确认节点 {state}】{prompt}\n   回复「确认」继续 /「否」终止 / 或直接说要改什么: ").strip()
        except EOFError:
            print("  ❌ 需要交互终端运行本向导（stdin 已关闭）"); sys.exit(2)
        if not ans:
            print("  没听懂——请回复「确认」「否」或你的修改意见"); continue
        kind = classify(ans)
        if kind == "reject" and terminate_on_no:
            print("  已终止(用户否决)"); sys.exit(2)
        return kind, ans

def _record_modify_once(state, ans, params):
    seen_modify = getattr(_record_modify_once, "_seen", set())
    if (state, ans) not in seen_modify:
        seen_modify.add((state, ans)); record(state, "modify", ans, params)
        _record_modify_once._seen = seen_modify  # 同话重复意见不重复记账
    print("  ✍ 已记录你的修改意见——由 AI 据此调整参数后重新发起本节点确认(本向导不自动回退;同话重复意见不重复记账)")

def confirm(state, prompt, params):
    """高影响节点:打印+等确认。返回用户原话(确认时,truthy)或 False(修改)。
    B4-1: 统一词族解析; 听不懂→重问(不再默默记为修改); 修改→诚实提示(不假称回退)。"""
    kind, ans = ask(state, prompt)
    if kind == "confirm":
        record(state,"confirm",ans,params); return ans
    _record_modify_once(state, ans, params)
    return False

GRANT_CMD = 'python3 tools/approval.py grant --project {project} --state {state} --quote "<用户确认原话>" --params-file <实际参数.json>'

def confirm_bound(state, prompt, params, missing, schema_hint):
    """★写节点确认(参数绑定): 实际参数齐全且用户确认 → confirm/confirmed(哈希绑定实际参数);
    缺任一实际参数 → 只记 decision_pending/pending, 不签发可执行凭证(绝不伪绑定), 打印专门审批命令指引。
    missing: 缺失参数名列表(空=齐全); schema_hint: 补齐铸造时的参数JSON结构说明。"""
    kind, ans = ask(state, prompt)
    if kind == "modify":
        _record_modify_once(state, ans, params); return False
    if missing:
        record(state, "decision_pending", ans, params)
        print(f"  ⚠️ 本节点缺实际绑定参数: {missing}——只记 decision_pending, 不签发可执行凭证(绝不伪绑定)")
        print(f"     对应工具执行前, 按实际参数用专门审批命令铸造绑定凭证:")
        print("     " + GRANT_CMD.format(project=STATE["project"], state=state))
        print(f"     参数JSON结构: {schema_hint}")
        return ans
    record(state, "confirm", ans, params)
    return ans

# ---------- S0 INPUT GATE ----------
print(f"●S0 INPUT_GATE: 昵称={args.nickname} | 产品={args.product} | 产品信息={'用户提供' if _explicit_info else '档案/一句话(未提供详述)'}")
print(f"  产品档案: status={PROFILE_STATUS} | sha256={PROFILE_SHA[:12]}... | {PROFILE_PATH}")
if not (args.nickname and args.product): print("  ❌ 缺昵称/产品，终止"); sys.exit(1)
if not args.product_info: args.product_info = args.product  # 一句话产品兜底;禁止为凑字段编造 MOQ/认证
if args.dry_run:
    print("  (dry-run 不创建/修改运营方档案；仅核对已有profile，不写本地状态)")
else:
    ensure_operator_profile()
check_login_first()
record("S0","gate_ok",f"nickname={args.nickname},product={args.product},profile={PROFILE_STATUS}",STATE["params"])

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
    try: require_state(PROFILE_PATH.parent / "operation-record.md", ("S1", "S2"))
    except ValueError as exc: print(f"❌ {exc}"); sys.exit(4)
    print(f"   产品档案: status={PROFILE_STATUS} | sha256={PROFILE_SHA[:12]}... (已过 S0a 硬闸门)")
    # ★B-3: 写操作(建产品档案+推演客群)必须在用户确认后才执行——先确认, 后写
    # 绑定实际参数: project+profile{sha256,status,version}+product/info(向导均已持有)
    if confirm("S2_客群", "将创建产品档案并推演客群（写操作，租户本地），推演结果出来后我再给您选。继续？",
               node_params({"product": args.product, "info": args.product_info})):
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
            gen = api("profile/inference-segment-generate",{"product_id":pid})
            if not gen.get("success"):
                print("  ❌ 客群generate未成功——中止，不读取历史客群、不推进S2")
                sys.exit(1)
            segs=[]
            for _i in range(6):
                segs=api("profile/inference-segment-list",{"product_id":pid}).get("data",[]) or []
                if segs: break
                time.sleep(10)
            print("   ★推演客群(默认4+; 按 v2 客户线人工剔除跨产品污染簇, 见 threshold-method):")
            for s in segs: print(f"    - {s.get('segment_name')} | {s.get('value_path')}")
            if not segs:
                print("   ⚠️ 推演返回空(平台慢/未落库)——等 1-2 分钟重跑本向导, 或改跑 tools/segments_infer.py")
            else:
                update_frontmatter(PROFILE_PATH.parent / "operation-record.md", {"status": "S2", "next_state": "S3",
                                   "updated": time.strftime("%Y-%m-%d"), "profile_version": f'"{PROFILE_META.get("profile_version", "")}"',
                                   "profile_sha256": f'"{PROFILE_SHA}"'}, expected_states=("S1", "S2"))
                print("   ✅ 运行状态已推进: S2 (next=S3)")

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
    r3 = confirm("S3_种子", "确认用这个锚点继续？(回复编号/新网址/确认)", node_params({"seed": args.seed}))
    if r3 is False:
        m3 = _re.search(r'[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', input("  请把新种子网址完整发一次: ").strip())
        if m3:
            args.seed = m3.group(0); STATE["params"]["seed"] = args.seed; pathA = True
            print("  ✅ 种子已更新为: " + args.seed)
            if not args.dry_run: show_seed_candidates(args.seed)
        else:
            print("  没认出网址——请单独发一次完整网址(如 example.com)，或回复「确认」用原种子继续")
        continue
    if r3 and args.seed and not args.dry_run:
        try: require_state(PROFILE_PATH.parent / "operation-record.md", ("S1", "S2", "S3"))
        except ValueError as exc: print(f"❌ {exc}"); sys.exit(4)
        update_frontmatter(PROFILE_PATH.parent / "operation-record.md", {"status": "S3", "next_state": "S4", "updated": time.strftime("%Y-%m-%d"), "seed": f'"{args.seed}"'}, expected_states=("S1", "S2", "S3"))
        print("  ✅ 种子已确认，运行状态推进: S3 (next=S4)")
    break

# ---------- S4 AUDIT (只读, 可自由) ----------
print("●S4 AUDIT_RUNNING: 只读搜客+AI语义审计(50页跳→三页平均→逐页→跌破往前)——见工具 audit_company.py")
if args.dry_run: print("  (dry-run 跳过审计)")
else:
    kw = args.seed
    if kw:
        print(f"  种子={kw}: ★按 v2 三条客户线(直采/OEM/拓品, threshold-method.md)逐条 AI 判定+判定表留痕; 50页跳→三页平均→逐页→跌破往前; 边界案例做敏感性检查; 未完成不能保存")

# ---------- S5 SAVE_PENDING (B4-5: 解析并回显 N; ★绑定实际N/seed/exclude) ----------
print("●S5 SAVE_PENDING: 展示 临界N/标签/排除/max/点数 → 确认后保存")
S5_SCHEMA = '{"project":"...","org_sha256":"...","profile":{...},"keyword":"...","n":N,"company_tag":"...","contact_tag":"...","max":3,"exclude":["CN","HK","MO","TW"],"verify_status":["valid","unkown"]}'
kind5, ans5 = ask("S5_保存参数", "保存前N条+排除4区+max3? (可写「确认保存 前N=2000」指定数量)")
if kind5 == "modify":
    _record_modify_once("S5_保存参数", ans5, node_params({"seed": args.seed, "exclude": args.exclude}))
    print("  ⚠️ 参数调整后须重新发起本节点确认; 未确认前不得保存")
else:
    n5 = args.save_n
    if not n5:
        m5 = _re.search(r'[Nn]=(\d+)', str(ans5)) or _re.search(r'前(\d+)', str(ans5))
        if m5:
            n5 = int(m5.group(1))
    if n5:
        pending_params = node_params({"n": n5, "seed": args.seed, "exclude": args.exclude})
        record("S5_保存参数", "decision_pending", ans5, pending_params)
        print(f"  ⚠️ 已确认保存意向与N={n5}，但向导没有实际 company/contact 标签ID、max与邮箱状态——只记pending，不签发执行凭证")
        print("     标签确定后按 save_first_n.py docstring 的完整参数JSON用 approval.py grant 铸造")
    else:
        record("S5_保存参数", "decision_pending", ans5, node_params({"seed": args.seed, "exclude": args.exclude}))
        print("  ⚠️ 实际N未知(--save-n 未给且原话未指定)——只记 decision_pending, 不签发可执行凭证(绝不伪绑定)")
        print("     保存前按实际N铸造: " + GRANT_CMD.format(project=STATE["project"], state="S5_保存参数"))
        print(f"     参数JSON结构: {S5_SCHEMA}")

# ---------- S6 SAVE_RUNNING ----------
print("●S6 SAVE_RUNNING: 用 save_first_n.py 保存(等finished)→ 见工具")
if not args.dry_run:
    print("  (实际调用 save_first_n.py; N/tags 由确认节点输入; ★须带 S5 的 --approval id)")

# ---------- S7 TEMPLATE_PENDING（向导不掌握全部写入范围参数，永远只记pending；执行前grant） ----------
print("●S7 TEMPLATE_PENDING: 展示3-8个跨轮模板+理由(草稿)")
S7_SCHEMA = '{"project":"...","org_sha256":"...","profile":{...},"plan":{"sha256":"..."},"name":"<纯昵称>","prefix":"...","suffix":"...","foid":"auto|id","out":"<tmap路径>"}'
kind7, ans7 = ask("S7_模板预览", "展示草稿后是否按当前方向生成?（这里只记录意向，实际全参数齐后另行绑定审批）")
if kind7 == "modify":
    _record_modify_once("S7_模板预览", ans7, node_params({}))
else:
    record("S7_模板预览", "decision_pending", ans7, node_params({}))
    print("  ⚠️ 仅记录pending；执行gen_templates前按实际org/prefix/suffix/name/foid/out/profile/plan用approval.py grant")
    print(f"     参数JSON结构: {S7_SCHEMA}")

# ---------- S8 TEMPLATE_BUILD ----------
print("●S8 TEMPLATE_BUILD: 生成120差异化模板(用 gen_templates.py; ★须带 S7 的 --approval id; 生成后跑 check_template_diff 断言差异)")

# ---------- S9 SEQUENCE_PENDING（执行参数含序列名/发送昵称/org，向导不全，永远pending） ----------
print("●S9 SEQUENCE_PENDING: 展示12步/时区/上限/notSentTags；实际全参数齐后另行绑定审批")
S9_SCHEMA = '{"project":"...","org_sha256":"...","name":"<序列名>","from_name":"<纯昵称>","profile":{...},"tmap":{"sha256":"..."},"rules":{...}}'
kind9, ans9 = ask("S9_序列配置", "以上序列配置方向确认?（这里只记录意向，不签执行凭证）")
if kind9 == "modify":
    _record_modify_once("S9_序列配置", ans9, node_params({}))
else:
    record("S9_序列配置", "decision_pending", ans9, node_params({}))
    print("  ⚠️ 仅记录pending；build_sequence执行前按全部实际参数用approval.py grant")
    print(f"     参数JSON结构: {S9_SCHEMA}")

# ---------- S10 CONTACT_PENDING (★绑定实际seq/tags/task, schema与contact_add.py逐字段一致) ----------
print("●S10 CONTACT_PENDING: 保存finished+标签>0+序列inactive+对账 → 确认后 contact-add(views:[])")
S10_SCHEMA = '{"project":"...","org_sha256":"...","seq":"...","tags":[...],"task":"..."}'
tags10 = sorted({t.strip() for t in (args.contact_tags or "").split(",") if t.strip()})
s10_params = {"project": STATE["project"], "org_sha256": hashlib.sha256(str(args.org).encode()).hexdigest(), "seq": args.seq, "tags": tags10, "task": args.task}
s10_missing = [n for n, v in (("seq", args.seq), ("tags(--contact-tags)", tags10), ("task", args.task)) if not v]
confirm_bound("S10_加联系人", "确认加入联系人? 输入'确认加入' (只读对账后)", s10_params, s10_missing, S10_SCHEMA)

# ---------- S11 READY_INACTIVE ----------
print("\n●S11 READY_INACTIVE: ⚠️本脚本仅向导,写操作须另行执行(见各步骤提示)")
print(f"  产品={args.product} | 昵称={args.nickname} | 路径={'A快速' if pathA else 'B标准'} | 排除4区={args.exclude}")
print("  ⚠️ 未激活——仅用户明确'确认激活'才 S12")
record("S11","decision_pending","向导展示完成；实际工具/终检未证明完成",STATE["params"])
print("  ⚠️ 本向导走到末尾不等于 S11 完成；只有各工具推进 operation-record 且终检全过后才可标 S11")

# ---------- S12 ACTIVATE_PENDING (★向导不激活; 只在 seq+合规核验文件齐全时铸造绑定凭证, 否则 decision_pending) ----------
print("●S12 ACTIVATE_PENDING: 激活由 tools/activate_sequence.py 执行(须 --profile --compliance-file --approval); 本向导只可预铸绑定凭证")
S12_SCHEMA = '{"project":"<operator_key>/<product_key>","seq":"<序列id>","profile":{"sha256":"<64hex>","status":"confirmed|declined","version":"<v>"},"compliance":{"sha256":"<合规核验JSON文件sha256>"}}  (与activate_sequence.py绑定schema一致)'
comp_sha = sha_file(args.compliance_file)
s12_params = {"project": STATE["project"], "org_sha256": hashlib.sha256(str(args.org).encode()).hexdigest(), "seq": args.seq,
              "profile": {"sha256": PROFILE_SHA, "status": PROFILE_STATUS, "version": PROFILE_META.get("profile_version", "")},
              **({"compliance": {"sha256": comp_sha}} if comp_sha else {})}
s12_missing = [n for n, v in (("seq", args.seq), ("compliance-file(合规核验JSON: market/list_source/sender_identity/unsubscribe/suppression均pass)", comp_sha)) if not v]
if s12_missing:
    record("S12_激活", "decision_pending", "向导阶段不激活(缺绑定参数)", s12_params)
    print(f"  ⚠️ 缺实际绑定参数: {s12_missing}——只记 decision_pending, 不签发可执行凭证(激活工具已禁自签发)")
    print("  补齐 --seq 与 --compliance-file 后，在当前交互式终端重跑 flow 到 S12，由用户现场确认；S12禁止 approval.py grant 自签")
    print(f"  参数JSON结构: {S12_SCHEMA}")
    print("  然后: python3 tools/activate_sequence.py --token <T> --org <orgId> --seq <id> --project <项目键> --profile <档案> --compliance-file <合规JSON> --confirm \"<用户确认激活原话>\" --approval <凭证id>")
else:
    if not sys.stdin.isatty():
        record("S12_激活", "decision_pending", "S12需要当前交互式终端用户确认", s12_params)
        print("  ❌ S12凭证只能在当前交互式终端由用户现场确认；stdin管道/自动输入不可签发")
    else:
        kind12, ans12 = ask("S12_激活", f"确认激活序列 {args.seq}?(本向导只铸造凭证, 不执行激活; 否=暂不激活)", terminate_on_no=False)
        if kind12 == "confirm":
            record("S12_激活", "confirm", ans12, s12_params)
            print(f"  🔑 S12绑定凭证已铸造；激活工具的 --confirm 必须与该原话逐字一致")
        elif kind12 == "modify":
            _record_modify_once("S12_激活", ans12, s12_params)
            print("  ⚠️ 激活意向有修改——未铸造凭证, 未激活")
        else:
            record("S12_激活", "decision_pending", "用户暂不激活", s12_params)
            print("  ✅ 未激活(用户未确认)")

print("\n✅ 输出: 见本地运行记录（.local/ 与 runs/<运营方>/<产品>/ 档案，不入 Git）+ 本流程(不激活)\n请在对话里向用户发完整流程待确认。")
