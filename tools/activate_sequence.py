#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""★S12 激活序列（★用户明确"确认激活"才执行）+ 回读验证防假成功
用法:
  python3 activate_sequence.py --token <T> --org <orgId> --seq <seqId> --confirm "<用户原话>" --approval <ap-id> --project <产品>
  python3 activate_sequence.py --token <T> --org <orgId> --seq <seqId> --status    # 只读查当前状态
铁律:
  - 仅用户明确正向命令（"确认激活"/"激活序列<名称>"）才激活，禁止自行激活（RULES 铁律）
  - 激活前确认: 目标序列 id 逐字核对 + 收件人预期（空序列=只测链路不真发）
  - ★激活后必须回读 sequence-list/sequence-details 确认 status:active（防接口假 success, 2026-09-02 ISS-01 恢复实证）
"""
import json, subprocess, sys, argparse, time
from pathlib import Path

KB = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KB / "tools"))
from approval import require_approval

ap = argparse.ArgumentParser()
ap.add_argument("--token", required=True)
ap.add_argument("--org", required=True)
ap.add_argument("--seq", required=True, help="序列id(激活前逐字核对)")
ap.add_argument("--confirm", default="", help="用户确认原话（含'确认激活'/'激活'字样才放行）")
ap.add_argument("--approval", default="", help="★S12 审批凭证id")
ap.add_argument("--project", default="", help="产品名(审批匹配)")
ap.add_argument("--status", action="store_true", help="只读查当前状态,不激活")
ap.add_argument("--deactivate", action="store_true", help="回滚为 inactive（空序列测完须回滚,防后续加联系人即真发;同样回读防假）")
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

# ---- 确认原话校验（★对抗P0: 否定句/犹豫词拦截——移植 flow_orchestrator neg_conf/hesitate）----
import re as _re
def check_confirm(quote, action_word):
    """返回 (ok, 原因)。action_word='激活'或'暂停'。否定句/犹豫词一律拒绝。"""
    if not quote:
        return False, "原话为空"
    neg = _re.search(r'(不|别|甭|莫|勿|先不|暂不|不用|不要|无须|无需|没法|无法|还没|暂停|停止|取消|回滚)[^。，,；;。！？!?]{0,12}' + action_word, quote) or \
          _re.search(action_word + r'[^。，,；;。！？!?]{0,12}(不|别|否|没)', quote)
    hesitate = _re.search(r'(别急|等等|稍等|先看|考虑|想想|再看看|回头|再说|商量|暂缓|犹豫|可能|大概|应该|也许)', quote)
    if neg:
        return False, f"原话含否定/暂停语义({neg.group(0)})——禁止执行"
    if hesitate:
        return False, f"原话含犹豫词({hesitate.group(0)})——须用户明确指令"
    if action_word not in quote and "activate" not in quote.lower():
        return False, f"原话不含'{action_word}'指令"
    return True, ""

# 幂等前置: 已是目标状态直接退出(免无谓凭证); 状态取不到不阻断 deactivate 判定前先查
if args.deactivate:
    # ---- 回滚模式（对抗P0-1: 空序列测完须回滚 inactive）----
    st_pre = get_status()
    if st_pre == "inactive":
        print("ℹ️ 序列已是 inactive——无需回滚"); sys.exit(0)
    require_approval(args.approval, args.project, ("S12",), what="暂停序列")
    st0 = st_pre if st_pre is not None else get_status()
    if st0 is None:
        print("❌ 序列状态未能回读——稍等重试,勿盲目操作"); sys.exit(3)
    print(f"当前状态: {st0}")
    ok, why = check_confirm(args.confirm, "暂停") if args.confirm and ("暂停" in args.confirm or "回滚" in args.confirm or "inactive" in args.confirm.lower()) else (True, "")
    # 回滚是降风险方向: 用户此前明确要求"测完回滚"或在审查整改语境下执行; 无原话时允许(记录在 ops)
    print(f"🔻 执行回滚: sequence-active {{id:{args.seq}, active:false}}")
    r = api("sequences/sequence-active", {"id": args.seq, "active": False})
    print(f"  接口返回: success={r.get('success')} {r.get('message') or ''}")
    if not r.get("success"):
        print("  ❌ 回滚接口失败——仍处 active,立即人工处理!"); sys.exit(1)
    time.sleep(2)
    st1 = get_status()
    print(f"  回读状态: {st1}")
    if st1 == "inactive":
        print(f"✅ 回滚成功且已回读确认: 序列 {args.seq} = inactive")
        sys.exit(0)
    print(f"  ❌ 回读 status={st1}≠inactive——假成功!立即人工核查"); sys.exit(4)

# ---- 激活模式 ----
# 激活前逐字核对序列存在
st0 = get_status()
if st0 is None:
    print(f"❌ 序列 {args.seq} 状态未能回读(接口偶发空——稍等重试,勿盲目激活)"); sys.exit(3)
print(f"激活前状态: {st0}")
if st0 == "active":
    print(f"ℹ️ 序列已是 active——无需重复激活"); sys.exit(0)
# 用户确认原话核对（★否定句/犹豫词拦截）
ok, why = check_confirm(args.confirm, "激活")
if not ok:
    print(f"❌ 确认原话校验未过: {why}: {args.confirm!r}\n   仅用户明确正向'确认激活'才激活"); sys.exit(2)

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
    print(f"✅ 激活成功且已回读确认: 序列 {args.seq} = active")
    sys.exit(0)
else:
    print(f"  ❌ 接口返回 success 但回读 status={st1}≠active——假成功!立即人工核查(勿当已激活)"); sys.exit(4)
