#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""★S12 激活序列（★用户明确"确认激活"才执行）+ 回读验证防假成功
用法:
  python3 activate_sequence.py --token <T> --org <orgId> --seq <seqId> --project <operator_key>/<product_key> \
      --profile runs/<operator_key>/<product_key>/product-profile.md \
      --compliance-file <合规核验JSON> --record runs/<operator_key>/<product_key>/operation-record.md \
      --confirm "<用户确认激活原话>" --approval <ap-id>
  python3 activate_sequence.py --token <T> --org <orgId> --seq <seqId> --status    # 只读查当前状态
  python3 activate_sequence.py --token <T> --org <orgId> --seq <seqId> --deactivate [--confirm "<用户原话>"]  # 回滚(降风险)
铁律(静态红队P0修复):
  - ★禁止自签发审批: S12凭证只能由 flow_orchestrator 当前TTY交互节点生成；approval.py grant 明确拒绝S12。
    绑定参数schema(本工具按本次实际参数重算并逐字比对, 不信CLI传入的哈希; 须逐字段一致):
      {"project":"<operator_key>/<product_key>","seq":"<序列id>",
       "profile":{"sha256":"<档案文件sha256>","status":"confirmed|declined","version":"<profile_version>"},
       "compliance":{"sha256":"<合规核验JSON文件sha256>"}}
  - 仅用户明确正向命令（"确认激活"/"激活序列<名称>"）才激活，禁止自行激活（RULES 铁律）; 否定句/犹豫词一律拒绝
  - --profile 必填(激活路径): 档案须过结构校验且稳定项目键与 --project 一致
  - --compliance-file 必填: 顶层绑定project/seq/profile_sha256/checked_at；五项各为status=pass + evidence{source,checked_at,detail}
  - 激活前确认: 目标序列 id 逐字核对 + 收件人预期（空序列=只测链路不真发）
  - ★激活后必须回读 sequence-list/sequence-details 确认 status:active（防接口假 success, 2026-09-02 ISS-01 恢复实证）
  - deactivate=回滚(降风险方向): 不要求 S12 审批, 但须明确目标回读(当前状态必须回读为 active 才执行); --confirm 给了就必须过否定/犹豫过滤
"""
import datetime
import json, subprocess, sys, argparse, time, hashlib
import re as _re
from pathlib import Path

KB = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KB / "tools"))
from approval import confirm_quote_ok, require_approval, stable_params_hash
from profile_utils import ensure_same_project_paths, profile_gate
from project_lock import acquire_project_lock
from update_run_state import read_meta, read_status, require_state, update_frontmatter

COMPLIANCE_KEYS = ("market", "list_source", "sender_identity", "unsubscribe", "suppression")

ap = argparse.ArgumentParser()
ap.add_argument("--token", required=True)
ap.add_argument("--org", required=True)
ap.add_argument("--seq", required=True, help="序列id(激活前逐字核对)")
ap.add_argument("--confirm", default="", help="用户确认原话（含'确认激活'/'激活'字样且无否定/犹豫才放行）")
ap.add_argument("--approval", default="", help="★S12凭证id(只能由flow当前TTY节点签发；grant禁止S12)")
ap.add_argument("--project", default="", help="稳定项目键=<operator_key>/<product_key>(激活必填, 须与profile一致)")
ap.add_argument("--profile", default="", help="★产品档案路径(激活必填): 须过结构校验, 项目键一致, 其 sha256/status/version 进入审批哈希")
ap.add_argument("--compliance-file", default="", help="★合规核验JSON(激活必填): market/list_source/sender_identity/unsubscribe/suppression 均pass; 文件sha256进入审批哈希")
ap.add_argument("--record", default="", help="项目operation-record；激活推进S12，回滚推进S11")
ap.add_argument("--status", action="store_true", help="只读查当前状态,不激活")
ap.add_argument("--deactivate", action="store_true", help="回滚为 inactive（空序列测完须回滚,防后续加联系人即真发;降风险方向,不要求S12审批但须明确目标回读）")
args = ap.parse_args()

def api(path, p, t=60):
    r = subprocess.run(["curl","-sSL","-m","55","-X","POST",f"https://web.laifaxin.com/api/{path}?uid={args.org}",
                        "-H","Content-Type: application/json","-H",f"accesstoken: {args.token}","-d",json.dumps(p)],
                       capture_output=True, text=True, timeout=t)
    try: return json.loads(r.stdout)
    except: return {}

def get_status():
    """回读序列状态(sequence-list 遍历命中, 与 build_sequence 同口径)。★间歇空退避重试(ISS-02); 兼容 status(字符串启停态) 与 active 字段。"""
    for attempt in range(3):
        for page in range(1, 4):
            d = api("sequences/sequence-list", {"current": page, "pageSize": 100, "filter": {}, "sort": {}})
            data = d.get("data")
            lst = data if isinstance(data, list) else (data.get("list") if isinstance(data, dict) else [])
            if not isinstance(lst, list):  # 接口间歇空 → 外层重试
                break
            for s in lst:
                if isinstance(s, dict) and str(s.get("id") or s.get("_id") or "") == args.seq:
                    st = s.get("status")
                    if st in ("active", "inactive"):
                        return st
                    act = s.get("active")
                    # 兼容: status 缺失时按 active 字段推断(True/1=active)
                    if act is not None:
                        return "active" if act is True or str(act) == "1" else "inactive"
                    return st if st else "unknown"
            if len(lst) < 100:
                break
        if attempt < 2:
            time.sleep(3)
    return None

# ---- 只读状态模式 ----
if args.status:
    st = get_status()
    print(f"序列 {args.seq} 当前状态: {st if st else '未取到(接口偶发空可重试)'}")
    sys.exit(0 if st else 3)

# ---- 确认原话校验（★对抗P0: 否定句/犹豫词拦截——比 flow_orchestrator 更严: 对向词全局拦截）----
def check_confirm(quote, action_word):
    """返回 (ok, 原因)。action_word='激活'或'暂停'。否定句/犹豫词/对向指令词一律拒绝。"""
    if not quote or not quote.strip():
        return False, "原话为空"
    q = quote.strip().replace("’", "'")
    if not confirm_quote_ok(q):
        return False, "原话不是严格正向确认（含否定/疑问/等待/取消或缺确认词）"
    neg = _re.search(r'(不|别|甭|莫|勿|先不|暂不|不用|不要|无须|无需|没法|无法|还没|暂停|停止|取消|回滚)[^。，,；;。！？!?]{0,12}' + action_word, q) or \
          _re.search(action_word + r'[^。，,；;。！？!?]{0,12}(不|别|否|没)', q)
    hesitate = _re.search(r'(别急|等等|稍等|先看|考虑|想想|再看看|回头|再说|商量|暂缓|犹豫|可能|大概|应该|也许)', q)
    # 对向/撤回指令词全局拦截(与action_word无关, 出现即语义矛盾→拒绝, 让用户给一句干净原话)
    forbid = ("暂停", "停止", "取消", "回滚", "不要", "不行", "先不", "暂不", "暂缓") if action_word == "激活" \
        else ("激活", "取消", "不要", "不行", "先不", "暂缓")
    forbid_hit = [w for w in forbid if w in q and w != action_word]
    if neg:
        return False, f"原话含否定/暂停语义({neg.group(0)})——禁止执行"
    if hesitate:
        return False, f"原话含犹豫词({hesitate.group(0)})——须用户明确指令"
    if forbid_hit:
        return False, f"原话含对向/撤回指令词({forbid_hit})——语义矛盾, 请用户给一句干净的正向原话"
    if action_word not in q and "activate" not in q.lower() and not (action_word == "暂停" and "inactive" in q.lower()):
        return False, f"原话不含'{action_word}'指令"
    return True, ""

# ---- 回滚模式（对抗P0-1: 空序列测完须回滚 inactive; 降风险方向不要求S12审批, 但须明确目标回读）----
if args.deactivate:
    if not args.record:
        print("❌ 回滚必须带 --record <operation-record.md>，确保本地状态与线上同步"); sys.exit(2)
    try: require_state(args.record, ("S11", "S12")); acquire_project_lock(args.record, "deactivate_sequence")
    except (ValueError, RuntimeError) as exc: print(f"❌ {exc}"); sys.exit(4)
    st_pre = get_status()
    if st_pre == "inactive":
        update_frontmatter(args.record, {"status": "S11", "next_state": "S12"}, expected_states=("S11", "S12"))
        print("ℹ️ 序列已是 inactive——无需回滚；本地状态已同步S11"); sys.exit(0)
    if st_pre is None:
        print("❌ 序列状态未能回读——稍等重试,勿盲目操作(明确目标回读失败=拒绝执行)"); sys.exit(3)
    # ★明确目标回读: 打印逐字目标id+回读状态; 只有回读为 active 才执行回滚(其余状态目标不明确)
    print(f"🔻 回滚目标回读: seq={args.seq} | 回读状态={st_pre}")
    if st_pre != "active":
        print(f"❌ 回读状态={st_pre}≠active——目标不明确(仅回滚 active→inactive), 拒绝执行"); sys.exit(3)
    if args.confirm:
        ok, why = check_confirm(args.confirm, "暂停")
        if not ok:
            print(f"❌ 确认原话校验未过: {why}: {args.confirm!r}"); sys.exit(2)
    else:
        print("  (回滚为降风险方向: 不要求 S12 审批; 未提供 --confirm 原话——事后请在 ops 流水登记本次回滚)")
    print(f"🔻 执行回滚: sequence-active {{id:{args.seq}, active:false}}")
    r = api("sequences/sequence-active", {"id": args.seq, "active": False})
    print(f"  接口返回: success={r.get('success')} {r.get('message') or ''}")
    if not r.get("success"):
        print("  ❌ 回滚接口失败——仍处 active,立即人工处理!"); sys.exit(1)
    time.sleep(2)
    st1 = get_status()
    print(f"  回读状态: {st1}")
    if st1 == "inactive":
        update_frontmatter(args.record, {"status": "S11", "next_state": "S12"}, expected_states=("S11", "S12"))
        print(f"✅ 回滚成功且已回读确认: 序列 {args.seq} = inactive；本地状态→S11")
        sys.exit(0)
    print(f"  ❌ 回读 status={st1}≠inactive——假成功!立即人工核查"); sys.exit(4)

# ---- 激活模式（★禁自签发: 凭证必须预先铸造且绑定本次实际参数）----
if not args.record:
    print("❌ 激活必须带 --record <operation-record.md>，确保回读active后本地状态同步推进S12"); sys.exit(2)
try: require_state(args.record, ("S11", "S12")); acquire_project_lock(args.record, "activate_sequence")
except (ValueError, RuntimeError) as exc: print(f"❌ {exc}"); sys.exit(4)
record_meta = read_meta(args.record)
if record_meta.get("sequence_id", "") != args.seq:
    print(f"❌ --seq={args.seq} 与S11已验证的record.sequence_id={record_meta.get('sequence_id')!r}不一致")
    sys.exit(4)
# 0) 激活前逐字核对序列存在 + 回读状态
st0 = get_status()
if st0 is None:
    print(f"❌ 序列 {args.seq} 状态未能回读(接口偶发空——稍等重试,勿盲目激活)"); sys.exit(3)
print(f"激活前状态: {st0}")
if st0 not in ("inactive", "active"):
    print(f"❌ 序列状态={st0!r}，只有明确inactive才允许激活；未知状态fail-closed")
    sys.exit(3)
ALREADY_ACTIVE = st0 == "active"

# 1) 产品档案闸门(必填): 结构校验 + 稳定项目键一致; sha256/status/version 进入审批哈希
if not args.profile:
    print("❌ 激活必填 --profile runs/<operator_key>/<product_key>/product-profile.md(其 sha256/status/version 进入审批哈希)"); sys.exit(2)
PROFILE_PATH = Path(args.profile)
if not PROFILE_PATH.is_absolute():
    PROFILE_PATH = KB / PROFILE_PATH
PROFILE_STATUS, PROFILE_ISSUES, PROFILE_META, PROFILE_SHA = profile_gate(PROFILE_PATH)
if not args.project:
    print("❌ 激活必填 --project <operator_key>/<product_key>(与档案及审批凭证一致)"); sys.exit(2)
EXPECTED_PROJECT = f"{PROFILE_META.get('operator_key', '').strip()}/{PROFILE_META.get('product_key', '').strip()}"
if not PROFILE_ISSUES and args.project != EXPECTED_PROJECT:
    PROFILE_ISSUES.append(f"--project={args.project!r} 与档案稳定项目键 {EXPECTED_PROJECT!r} 不一致——拒绝跨运营方/产品激活")
if PROFILE_ISSUES:
    print(f"❌ 产品档案闸门未过: {PROFILE_PATH}")
    for _i in PROFILE_ISSUES:
        print(f"   - {_i}")
    print("   指引: 档案按 runs/_template/product-profile.md 修好后重跑(状态/hash 校验须通过)。 (exit 4)")
    sys.exit(4)
print(f"  ✅ 档案闸门: status={PROFILE_STATUS} | sha256={PROFILE_SHA[:12]}... | 项目键={EXPECTED_PROJECT}")
if not ensure_same_project_paths(args.record, PROFILE_PATH):
    print("❌ --record 与 --profile 不在同一项目目录——拒绝跨项目同步状态"); sys.exit(4)
if ALREADY_ACTIVE:
    if read_status(args.record) == "S12":
        print("ℹ️ 序列已active且本地已是S12——不重复激活")
        sys.exit(0)
    update_frontmatter(args.record, {"status": "ERROR_BLOCKED", "next_state": "S11"}, expected_states=("S11",))
    print("❌ 线上序列已active，但本地尚未完成S12合规/审批链；已标ERROR_BLOCKED。立即核查发送影响，不能自动洗成S12")
    sys.exit(4)

# 2) 合规核验JSON(必填): 五项均 pass, 文件 sha256 进入审批哈希
if not args.compliance_file:
    print("❌ 激活必填 --compliance-file <合规核验JSON>——含 market/list_source/sender_identity/unsubscribe/suppression 且均pass(RULES 铁律5: 激活前核验目标市场规则/名单来源/发送主体/退订入口/拒收名单)"); sys.exit(2)
comp_path = Path(args.compliance_file)
if not comp_path.is_file():
    print(f"❌ 合规核验JSON不存在: {comp_path}"); sys.exit(2)
try:
    comp_doc = json.loads(comp_path.read_text(encoding="utf-8"))
    COMP_SHA = hashlib.sha256(comp_path.read_bytes()).hexdigest()
except (json.JSONDecodeError, UnicodeDecodeError) as e:
    print(f"❌ 合规核验JSON解析失败: {comp_path} -> {e}"); sys.exit(2)

def _pass(v):
    if not isinstance(v, dict):
        return False
    s = v.get("status", v.get("result"))
    evidence = v.get("evidence")
    if not isinstance(evidence, dict):
        return False
    source = str(evidence.get("source", "")).strip()
    checked = str(evidence.get("checked_at", "")).strip()
    detail = str(evidence.get("detail", "")).strip()
    passed = s is True or (isinstance(s, str) and s.strip().lower() == "pass")
    try:
        dt = datetime.datetime.fromisoformat(checked)
        age = datetime.datetime.now() - dt
        fresh = -300 <= age.total_seconds() <= 72 * 3600
    except (ValueError, TypeError):
        fresh = False
    return passed and len(source) >= 4 and fresh and len(detail) >= 8

if not isinstance(comp_doc, dict):
    print("❌ 合规核验JSON须为对象"); sys.exit(2)
identity_bad = []
for key, expected in (("project", args.project), ("seq", args.seq), ("profile_sha256", PROFILE_SHA)):
    if str(comp_doc.get(key, "")) != str(expected): identity_bad.append(f"{key}不匹配")
try:
    top_checked = datetime.datetime.fromisoformat(str(comp_doc.get("checked_at", "")))
    top_age = datetime.datetime.now() - top_checked
    if top_age.total_seconds() < -300 or top_age.total_seconds() > 72 * 3600: identity_bad.append("checked_at超过72小时/来自未来")
except (ValueError, TypeError): identity_bad.append("checked_at缺失/格式错")
if identity_bad:
    print("❌ 合规文件未绑定当前项目/序列/profile或检查时间: " + ", ".join(identity_bad)); sys.exit(2)
comp_bad = [(k, comp_doc.get(k, "(缺失)")) for k in COMPLIANCE_KEYS if not _pass(comp_doc.get(k))]
if comp_bad:
    print(f"❌ 合规核验未全部通过——禁止激活 (五项均须status=pass，且evidence含source/checked_at/detail):")
    for k, v in comp_bad:
        print(f"   - {k} = {v!r}")
    print(f"   合规文件: {comp_path} (修好五项后重跑; 铁律5——平台技术能力不免除运营方合规责任)"); sys.exit(2)
print(f"  ✅ 合规核验: 五项均 pass | 文件sha256={COMP_SHA[:12]}...")

# 3) 用户确认原话核对（★否定句/犹豫词/对向指令词拦截）
ok, why = check_confirm(args.confirm, "激活")
if not ok:
    print(f"❌ 确认原话校验未过: {why}: {args.confirm!r}\n   仅用户明确正向'确认激活'才激活"); sys.exit(2)

# 4) ★审批硬闸门: S12凭证只能由flow当前TTY节点签发，且memo须匹配本次实际参数
binding = {
    "project": args.project,
    "org_sha256": hashlib.sha256(str(args.org).encode()).hexdigest(),
    "seq": args.seq,
    "profile": {"sha256": PROFILE_SHA, "status": PROFILE_STATUS, "version": PROFILE_META.get("profile_version", "")},
    "compliance": {"sha256": COMP_SHA},
}
approval_row = require_approval(args.approval, args.project, ("S12",), what="激活序列", expected_hash=stable_params_hash(binding))
if " ".join(str(approval_row.get("user_quote", "")).split()) != " ".join(args.confirm.split()):
    print("❌ --confirm 必须与S12审批凭证中的用户原话逐字一致——拒绝替换确认语义")
    sys.exit(2)

# 写入前最后复核：本地档案/合规文件未变，线上仍明确inactive
from profile_utils import profile_sha256 as _profile_sha_now
if _profile_sha_now(PROFILE_PATH) != PROFILE_SHA or hashlib.sha256(comp_path.read_bytes()).hexdigest() != COMP_SHA:
    print("❌ 审批后profile/compliance文件发生变化——拒绝激活，重新确认")
    sys.exit(4)
if get_status() != "inactive":
    print("❌ 激活写入前序列不再明确inactive——fail-closed")
    sys.exit(3)
print(f"🔓 执行激活: sequence-active {{id:{args.seq}, active:true}}")
r = api("sequences/sequence-active", {"id": args.seq, "active": True})
print(f"  接口返回: success={r.get('success')} {r.get('message') or ''}")
if not r.get("success"):
    print("  ❌ 激活接口失败——未激活,勿信半成功"); sys.exit(1)

# ★回读验证防假成功
time.sleep(2)
st1 = get_status()
print(f"  回读状态: {st1}")
if st1 == "active":
    update_frontmatter(args.record, {"status": "S12", "next_state": ""}, expected_states=("S11", "S12"))
    print(f"✅ 激活成功且已回读确认: 序列 {args.seq} = active；本地状态→S12")
    sys.exit(0)
else:
    print(f"  ❌ 接口返回 success 但回读 status={st1}≠active——假成功!立即人工核查(勿当已激活)"); sys.exit(4)
