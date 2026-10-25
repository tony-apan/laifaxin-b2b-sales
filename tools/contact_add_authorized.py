#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""★S10 加联系人入序列（一条龙缺口#2）：时序守卫(保存finished+标签>0) → contact-add(views:[]铁律) → 核对 add 数
★S10 授权写通道（现役正路）：经 save_guard.authorize_write(action="sequence", payload, ticket) 校验票据后写平台；
  票据由 auth_guard.py authorize --action sequence 生成，payload 哈希逐字绑定，缺失/不符=拒绝。
用法:
  python3 contact_add.py --token <T> --org <orgId> --seq <seqId> --tags <联系人标签id,可逗号多个> \
      --task <保存任务id>(★必填:时序铁律) --approval <ap-id> --project <项目键> \
      --record runs/<operator_key>/<product_key>/operation-record.md \
      --auth-ticket .local/auth/ticket-<nonce>.json [--dry-run]
  ★--auth-ticket 在非 dry-run 时必填：票据由 auth_guard.py authorize --action sequence 生成,
    缺失/坏票/哈希不符一律拒绝(exit 2)且不调用任何平台写接口。
铁律: views 恒为 []（传 "all" 会把全库 139万 联系人加进来!）; 时序不满足=拒绝执行
★静态红队P0修复:
  - 序列查询失败/翻页中断/未命中 → fail-closed 拒绝(不再"尽力而为不阻断"); 标签列表查询失败 → fail-closed 拒绝
  - 序列回读 status 必须 inactive(active 序列加联系人=立即真发; 状态缺失/未知同样拒绝)
  - 审批凭证须绑定本次实际参数(哈希由本工具重算, 不信CLI传入): 绑定schema与 flow S10 / approval.py grant 一致:
      {"project":"<operator_key>/<product_key>","seq":"<序列id>","tags":["<标签id>",...](去重排序),"task":"<保存任务id>"}
★S10 加人前只读预检(本工具内, 不写平台): 打印本客群标签下人数/预计加人量/去重说明/序列未激活;
  人数为 0 或标签缺失 → 中文报错 exit 2, 禁止 contact-add(不写平台)。
"""

def _utf8_stdout():
    """Windows 控制台/管道默认 GBK：输出 emoji 会抛 UnicodeEncodeError；显式改 UTF-8。"""
    import sys as _sys
    for _s in (_sys.stdout, _sys.stderr):
        try:
            _s.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
_utf8_stdout()
import hashlib, json, subprocess, sys, time, argparse
from pathlib import Path

KB = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KB / "tools"))
from approval import require_approval, stable_params_hash
from project_lock import acquire_project_lock
from update_run_state import record_matches_project, require_state, update_frontmatter
from workspace_guard import preflight
import save_guard

ap = argparse.ArgumentParser()
ap.add_argument("--token", required=True, help="accesstoken 完整串（token中段是用户UID）")
ap.add_argument("--org", required=True, help="当前工作空间ID=localStorage独立orgId键（企业必填；禁止拿token第2段代替）")
ap.add_argument("--seq", required=True, help="序列id")
ap.add_argument("--tags", required=True, help="联系人标签id(逗号分隔)")
ap.add_argument("--task", required=True, help="保存任务id(refine/company-save 返回)——★必填:时序铁律,无任务id=无法确认finished,拒绝执行")
ap.add_argument("--record", default="", help="项目operation-record；成功且add对账后推进S10,next=S11")
ap.add_argument("--approval", default="", help="★S10 审批凭证id(.local/approvals.tsv)")
ap.add_argument("--project", required=True, help="稳定项目键=<operator_key>/<product_key>")
ap.add_argument("--timeout", type=int, default=900, help="等保存任务最大秒数")
ap.add_argument("--dry-run", action="store_true", help="只打印 payload/时序检查,不写")
ap.add_argument("--auth-ticket", default="", help="★S10 写票据文件路径 .local/auth/ticket-<nonce>.json")
ap.add_argument("--allow-count-mismatch", action="store_true", help="★仅人工排查用：跳过「保存任务 contactSaveCount = 标签人数」硬对账（默认 fail-closed；使用须在记录里写明原因）")
args = ap.parse_args()
# ★P0-A 票据门(静态红队): 非 dry-run 一律必须有写票据——缺失时在**任何联网之前**拒绝,
#   绝不"先查一圈平台再发现没票"; 坏票/哈希不符在写入前由 save_guard 校验并拒绝。
if not args.dry_run and not str(args.auth_ticket or "").strip():
    print("❌ 正式 contact-add 必须带 --auth-ticket <写票据文件路径>(.local/auth/ticket-<nonce>.json)——"
          "缺票据=未授权, 拒绝执行, 未向平台发出任何请求")
    print("   票据由 python3 tools/auth_guard.py authorize --action sequence --payload-file <本次payload.json> 签发；"
          "payload 哈希须与本次 seq/tags 逐字一致")
    sys.exit(2)
if not args.dry_run and not args.record:
    print("❌ 正式 contact-add 必须带 --record <operation-record.md>，否则换机状态无法推进"); sys.exit(2)
if not args.dry_run:
    if not record_matches_project(args.record, args.project):
        print("❌ --record 的 operator_key/product_key 与 --project 不一致"); sys.exit(4)
    try: require_state(args.record, ("S9", "S10"))
    except ValueError as exc: print(f"❌ {exc}"); sys.exit(4)
    try: acquire_project_lock(args.record, "contact_add")
    except RuntimeError as exc: print(f"❌ {exc}"); sys.exit(4)

tags = sorted({t.strip() for t in args.tags.split(",") if t.strip()})  # 去重排序: 与审批绑定schema一致(稳定哈希)
if not tags:
    print("❌ S10 加人前预检未通过：没给联系人标签（缺标签）——不写平台、不加人")
    print("   --tags 须是本客群的联系人标签id（逗号分隔可多个）；请先在 S5 建好/确认标签")
    sys.exit(2)
# ★审批硬闸门+参数绑定: 本工具按本次实际参数(seq/tags/task/project)重算哈希, 凭证memo须逐字一致
binding = {"project": args.project, "org_sha256": hashlib.sha256(str(args.org).encode()).hexdigest(), "seq": args.seq, "tags": tags, "task": args.task}
require_approval(args.approval, args.project, ("S10",), what="加联系人入序列",
                 expected_hash=stable_params_hash(binding))
# ★工作空间落点校验(写之前): 防"给了企业 orgId 却落进个人空间"
preflight(args.token, args.org, dry_run=args.dry_run, what="加联系人入序列")
gots = {}

def api(path, p, t=40):
# LFX_GATE_WRITE
    try:
        from startup_gate import enforce_cli_startup as _lfx_gate
        _lfx_gate()
    except ImportError:
        pass
    except Exception as _lfx_gate_exc:
        __import__("sys").stderr.write("还差一步：请先告诉我怎么称呼您、主要卖什么产品，登记后我马上继续（不是你的账号问题）。\n")
        raise SystemExit(2)
    cmd = ["curl","-sSL","-m","35","-X","POST",f"https://web.laifaxin.com/api/{path}",
           "-H","Content-Type: application/json","-H",f"accesstoken: {args.token}",
           "-H", f"uid: {args.org}","-d",json.dumps(p)]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=t)
    try: return json.loads(r.stdout)
    except:
        print("  ⚠️ 接口无返回——可能是网络不通（这不是配置问题），稍等重试；反复出现看 平台接口间歇空(已知)。")
        return {}

# —— 语言前缀识别表(铁律9 三方配对用; 多字优先, 单字形带"-"防误命中正常词) ——
LANG_MARKERS = [
    (lang, m)
    for lang, ms in {
        "en": ("英语", "英文", "english", "英-"),
        "es": ("西语", "西班牙语", "西班牙文", "spanish", "西-"),
        "pt": ("葡萄牙语", "葡语", "portuguese", "葡-"),
        "de": ("德语", "德文", "german", "德-"),
        "fr": ("法语", "法文", "french", "法-"),
        "ru": ("俄语", "俄文", "russian", "俄-"),
        "ja": ("日语", "日文", "japanese", "日-"),
        "ko": ("韩语", "韩文", "korean", "韩-"),
        "it": ("意大利语", "意语", "italian", "意-"),
        "ar": ("阿拉伯语", "arabic"),
        "tr": ("土耳其语", "turkish"),
        "zh": ("中文", "汉语", "chinese", "中-"),
    }.items()
    for m in ms
]
def detect_lang(text):
    """尽力而为: 从名称中识别语言前缀(如 英语-…/西语-…), 识别不出返回 None(legacy 无前缀→不阻断)。"""
    t = (text or "").lower()
    for lang, marker in sorted(LANG_MARKERS, key=lambda x: -len(x[1])):
        if marker.lower() in t:
            return lang
    return None

def find_seq():
    """翻页查 --seq 对应序列(sequences/sequence-list,与 build_sequence 同口径)。
    返回 (seq_item|None, authoritative|None): authoritative=None=接口取不到(平台接口间歇空,已知问题), True=列表权威可判定, False=翻页中断列表不全不作权威。"""
    page = 1
    while page <= 5:
        d = api("sequences/sequence-list", {"current": page, "pageSize": 100, "filter": {}, "sort": {}})
        data = d.get("data")
        lst = data if isinstance(data, list) else (data.get("list") if isinstance(data, dict) else None)
        if not isinstance(lst, list):
            return None, (None if page == 1 else False)
        for it in lst:
            if isinstance(it, dict) and str(it.get("id") or it.get("_id") or "") == args.seq:
                return it, True   # 命中即权威,不需翻完
        if len(lst) < 100:
            break
        page += 1
    return None, True

def seqitem_active(item):
    """status 缺失时按 active 字段推断(True/1=active)——与 activate_sequence.py 回读口径一致。"""
    act = item.get("active")
    return act is True or str(act) == "1"

# 0a) 本地只读守卫①: --seq 序列存在性 + ★status必须inactive + ★查询失败fail-closed(红队P0: 不再"不阻断")
seq_item, seq_authoritative = None, None
for _attempt in range(3):  # 平台接口间歇空(已知): 接口偶发空,重试3次再放弃
    seq_item, seq_authoritative = find_seq()
    if seq_authoritative is not None:
        break
if seq_authoritative is None:
    print("❌ 序列查询失败(sequences/sequence-list 多次无返回,平台接口间歇空——已知问题)——fail-closed, 禁止 contact-add")
    sys.exit(1)
if seq_authoritative is False:
    print("❌ 序列列表翻页中断,序列存在性无法权威判定——fail-closed, 禁止 contact-add")
    sys.exit(1)
if seq_item is None:
    print(f"❌ 序列不存在/不可见: --seq {args.seq}(sequences/sequence-list 未命中)——禁止 contact-add")
    sys.exit(1)
seq_status = str(seq_item.get("status") or "").strip().lower()
if seqitem_active(seq_item):
    seq_status = "active"
if seq_status != "inactive":
    print(f"❌ 序列 status={seq_item.get('status')!r}≠inactive——活动/未知状态序列加联系人=立即真发, 禁止 contact-add(红队P0)")
    sys.exit(1)
print(f"✅ 序列存在: {seq_item.get('name')} (status=inactive)")

# 0b) 本地只读守卫②: 语言三方配对(铁律9)——--tags 标签名 vs 序列名语言; ★tags-list查询失败=fail-closed(红队P0); 标签识别不出语言仍不阻断(legacy)
tag_names = {}
d = api("contacts/tags-list", {"type": "contacts"})
data = d.get("data")
tl = data if isinstance(data, list) else (data.get("list") if isinstance(data, dict) else [])
if not isinstance(tl, list):
    print("❌ 标签列表查询失败(contacts/tags-list 无返回,平台接口间歇空——已知问题)——fail-closed, 无法核验标签/语言配对, 禁止 contact-add")
    sys.exit(1)
for t in tl:
    if isinstance(t, dict) and (t.get("id") or t.get("_id")):
        tag_names[str(t.get("id") or t.get("_id"))] = t.get("name") or ""
if not tag_names:
    print("❌ S10 加人前预检未通过：平台联系人标签列表为空（缺标签）——不写平台、不加人")
    sys.exit(2)
seq_lang = detect_lang(seq_item.get("name") or "")
unresolved = [tg for tg in tags if tg not in tag_names]
if unresolved:
    print("❌ S10 加人前预检未通过：本客群标签在平台联系人标签列表里找不到（缺标签）——不写平台、不加人")
    print(f"   找不到的标签id: {', '.join(unresolved)}")
    print("   请先在 S5 建好/确认联系人标签（标签=语言-行业-角色），拿到真实标签id 后重跑预检")
    sys.exit(2)
bad = []
for tg in tags:
    nm = tag_names.get(tg)
    tl_ = detect_lang(nm) if nm else None
    if tl_ and seq_lang and tl_ != seq_lang:
        bad.append((tg, nm, tl_))
if bad:
    det = ", ".join(f"{tg}({nm})={l}" for tg, nm, l in bad)
    print(f"❌ 语言三方配对失败(铁律9): 序列「{seq_item.get('name')}」语言={seq_lang}, 标签 {det} 语言不同——西语客群禁收英语信,禁止 contact-add")
    sys.exit(1)
pairs = ", ".join(f"{tg}({tag_names.get(tg,'?')}→{detect_lang(tag_names.get(tg)) or '未识别'})" for tg in tags)
print(f"✅ 语言配对(铁律9): 序列「{seq_item.get('name')}」语言={seq_lang or '未识别(legacy 无前缀,按序列实际市场判定)'} | 标签 {pairs}")

# 1) 时序守卫①: 保存任务 finished
save_status = {}
if args.task:
    start = time.time(); status = ""
    while time.time() - start < args.timeout:
        d = api("operation/backend-task-status", {"type":"cluesSave","id":args.task}).get("data",{})
        status = d.get("status","")
        if status == "finished":
            save_status = d
            print(f"✅ 保存任务 finished: contactSaveCount={d.get('contactSaveCount')}"); break
        print(f"⏳ 等保存任务... status:{status} fin:{d.get('finished')}/{d.get('total')}", flush=True)
        time.sleep(10)
    else:
        print(f"❌ 超时({args.timeout}s)仍 {status}——禁止 contact-add"); sys.exit(1)

# 2) ★S10 加人前只读预检（名额/去重/序列状态；本段不写平台）：
#    白话明细 = 本客群标签下人数 + 预计加人量 + 去重说明 + 序列未激活。
#    人数为 0 或标签缺失 → 中文报错 exit 2，禁止 contact-add（不是"尽力而为"）。
print("📋 S10 加人前只读预检（未写平台）：")
precheck_counts = {}
for tg in tags:
    got = None
    for i in range(6):
        d = api("contacts/contacts/show", {"current":1,"pageSize":10,"filters":[{"property":"tags","operator":"include","value":tg,"values":[tg],"valueType":"select"}],"sort":{}})
        data = d.get("data")
        try:
            n = int(data.get("total")) if isinstance(data, dict) else int(data)
        except (TypeError, ValueError, AttributeError):
            n = None  # 形状异常(接口偶发 平台接口间歇空(已知))——重试,不裸崩(terra 2-④)
        if isinstance(n, int) and n >= 0:
            got = n; break  # 0 是平台权威答案(=没人可加)，不再空等；形状异常才重试
        time.sleep(8)
    if not got:
        print("❌ S10 加人前预检未通过：本客群标签下人数为 0（或接口多次无返回，无法确认）")
        print(f"   标签: {tg}（{tag_names.get(tg) or '名称未解析'}）")
        print("   不写平台、不加人。若保存任务刚结束，等 5-10 分钟让平台计数落定后重跑预检；仍为 0 则回 S5 核对标签。")
        sys.exit(2)
    precheck_counts[tg] = got
estimated_add = sum(precheck_counts.values())

# ★人数硬对账（三审 K/L 缺口，2026-10-23）：保存任务 contactSaveCount 必须等于本客群标签人数；
#   不等 = 标签可能混批/任务未落定/取错标签 → 不得写平台。默认 fail-closed，仅 --allow-count-mismatch 人工放行。
_saved = save_status.get("contactSaveCount")
if _saved is None:
    print("❌ S10 人数对账无法完成：保存任务 finished 但没返回 contactSaveCount")
    print("   不写平台、不加人。等 5-10 分钟平台计数落定后重跑；仍缺失请查保存任务详情（不要猜数字）。")
    sys.exit(2)
try:
    _saved = int(_saved)
except (TypeError, ValueError):
    print(f"❌ S10 人数对账失败：contactSaveCount={_saved!r} 不是整数——不写平台")
    sys.exit(2)
if _saved != estimated_add:
    print(f"❌ S10 人数对账不通过：保存任务 contactSaveCount={_saved} ≠ 本客群标签人数={estimated_add}")
    print("   常见原因：标签混了别的批次 / 保存任务没完全落定 / 取错标签。不写平台、不加人。")
    print("   处理：回 S5 核对保存任务与标签；等计数落定后重跑。确属人工排查后要强推，才加 --allow-count-mismatch 并在记录里写明原因。")
    if not args.allow_count_mismatch:
        sys.exit(2)
    print("⚠️ 已按 --allow-count-mismatch 跳过人数硬对账——责任与原因须写入 operation-record")
else:
    print(f"✅ S10 人数对账通过: 保存任务 contactSaveCount={_saved} = 本客群标签人数={estimated_add}")
tag_detail = "、".join(f"{tg}（{tag_names.get(tg) or '未命名'}）={n} 人" for tg, n in precheck_counts.items())
print(f"   本客群标签: {tag_detail}")
print(f"   本客群标签下人数: {estimated_add} 人")
print(f"   预计加人量: {estimated_add} 人（只加本客群标签内的联系人，不混其他客群）")
print("   去重说明: 平台按联系人去重——已在库里/重复的联系人不会重复加入，实际 add 可能少于预计量；"
      "以平台返回 add 为准，加完按「保存新增=标签人数=add」对账。")
print(f"   序列: {seq_item.get('name')}（status=inactive，未激活，加人不会发信）")
gots = dict(precheck_counts)  # 写后对账复用同一份预检人数（不再重复查一遍）

# 危险写入前再次回读，堵住等待保存/查标签期间序列被激活的竞态
seq_now, auth_now = find_seq()
now_status = str((seq_now or {}).get("status") or "").strip().lower()
if seq_now and seqitem_active(seq_now): now_status = "active"
if auth_now is not True or not seq_now or now_status != "inactive":
    print(f"❌ contact-add写入前复核失败/序列已变化(status={now_status or '未知'})——fail-closed")
    sys.exit(1)
payload = {"seqId": args.seq, "tags": tags, "views": []}  # ★views:[] 铁律
if args.dry_run:
    print(f"[dry-run] 将执行 sequences/contact-add payload={json.dumps(payload, ensure_ascii=False)}（views 恒为空数组）"); sys.exit(0)

# 3) contact-add
# ★P0-A 票据门(静态红队): authorize_write 的返回值必须检查——save_guard 无票/坏票只返回
#   {"ok": False, "code": ...}, **不会抛异常**; 旧代码丢弃返回值后照常写平台 = 票据门形同虚设。
#   任何非 ok 一律中文报错 + exit 2, 绝不继续写(拒绝路径 http_calls==0, 本函数不发网络)。
authz = save_guard.authorize_write(action="sequence", payload=payload, ticket=args.auth_ticket)
if not isinstance(authz, dict) or not authz.get("ok"):
    authz = authz if isinstance(authz, dict) else {}
    print(f"❌ S10 写票据校验未通过({authz.get('code') or 'E_AUTH_DENIED'}): {authz.get('reason') or '拒绝原因未知'}")
    print("   未向平台写入任何数据——contact-add 已中止。请用 approvals 认可的票据重新授权：")
    print("   python3 tools/auth_guard.py authorize --action sequence --payload-file <本次payload.json> "
          "(payload={\"seqId\":...,\"tags\":[...],\"views\":[]})")
    sys.exit(2)
print(f"✅ S10 写票据校验通过: action=sequence | payload_hash={str(authz.get('payload_hash') or '')[:12]}... | http_calls=0")
r = api("sequences/contact-add", payload, t=120)
data = r.get("data", {}) if isinstance(r.get("data"), dict) else {}
add = data.get("add")
if r.get("success"):
    print(f"✅ contact-add 成功: add={add} (标签人数合计={sum(gots.values())})")
    if add is None:
        print("❌ 返回无 add 数——无法对账，进入 ERROR_BLOCKED；用 sequence-details 核对")
        if args.record: update_frontmatter(args.record, {"status": "ERROR_BLOCKED", "next_state": "S10"}, expected_states=("S9", "S10"))
        sys.exit(1)
    if sum(gots.values()) and add > sum(gots.values()):
        print(f"❌ add={add} 明显超过标签人数合计 {sum(gots.values())}——异常，进入ERROR_BLOCKED")
        if args.record: update_frontmatter(args.record, {"status": "ERROR_BLOCKED", "next_state": "S10"}, expected_states=("S9", "S10"))
        sys.exit(1)
    if not args.record:
        print("❌ 正式 contact-add 缺 --record，无法推进换机状态真源"); sys.exit(2)
    update_frontmatter(args.record, {"status": "S10", "next_state": "S11", "contact_add_count": str(add)}, expected_states=("S9", "S10"))
    print(f"✅ 运行状态已推进: {args.record} → S10 (next=S11)")
else:
    print(f"❌ contact-add 失败: {str(r)[:150]}"); sys.exit(1)
