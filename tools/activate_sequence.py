#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""★S12 激活序列（★用户明确"确认激活"才执行）+ 回读验证防假成功
用法:
  python3 activate_sequence.py --token <T> --org <orgId> --seq <seqId> --project <operator_key>/<product_key> \
      --profile runs/<operator_key>/<product_key>/product-profile.md \
      --compliance-file <合规核验JSON> --record runs/<operator_key>/<product_key>/operation-record.md \
      --confirm "确认激活 <序列名>" --approval <ap-id>
  ★--confirm 原话必须含「确认激活」四个字（仅说「激活」不构成授权，exit 2）；
    --approval 只能由 flow_orchestrator --resume-s12 --confirm "<同一句原话>" 签发，且原话须逐字一致。
  python3 activate_sequence.py --token <T> --org <orgId> --seq <seqId> --status    # 只读查当前状态
  python3 activate_sequence.py --token <T> --org <orgId> --seq <seqId> --sync-manual --record <record>  # ★用户在网页手动激活后，同步本地状态（只读平台+改本地）
  python3 activate_sequence.py --token <T> --org <orgId> --seq <seqId> --deactivate [--confirm "<用户原话>"]  # 回滚(降风险)
铁律(静态红队P0修复):
  - ★禁止自签发审批: S12凭证只能由 flow_orchestrator --resume-s12 --confirm "<用户原话>" 生成（用户亲口说"确认激活"）；approval.py grant 明确拒绝S12。
    绑定参数schema(本工具按本次实际参数重算并逐字比对, 不信CLI传入的哈希; 须逐字段一致):
      {"project":"<operator_key>/<product_key>","seq":"<序列id>",
       "profile":{"sha256":"<档案文件sha256>","status":"confirmed|declined","version":"<profile_version>"},
       "compliance":{"sha256":"<合规核验JSON文件sha256>"}}
  - 仅用户明确正向命令（原话须含「确认激活」四个字）才激活，禁止自行激活（RULES 铁律）; 否定句/犹豫词一律拒绝
    ★只说「激活」不算授权（静态红队P0：旧校验只要求含「激活」，含糊原话即可放行）
  - --profile 必填(激活路径): 档案须过结构校验且稳定项目键与 --project 一致
  - --compliance-file 必填: evidence_mode须为字面量live；顶层绑定project/seq/profile_sha256/checked_at；五项各为status=pass + evidence{source,checked_at,detail}，source/detail不得含非实时证据标记
  - 激活前确认: 目标序列 id 逐字核对 + 收件人预期（空序列=只测链路不真发）
  - ★激活写之前只读结构校验（2026-10-23 任务A-3）: sequence-details 的 rules/notSentTags 关键字段
    + step-list 必须 12 步且每步都绑定模板；不满足中文报错 exit 2，**不发起激活写**、本地状态保持 S11
  - ★激活后必须回读 sequence-list/sequence-details 确认 status:active（防接口假 success, 2026-09-02 ISS-01 恢复实证）
  - deactivate=回滚(降风险方向): 不要求 S12 审批, 但须明确目标回读(当前状态必须回读为 active 才执行); --confirm 给了就必须过否定/犹豫过滤
  - ★sync-manual（2026-09-17 用户要求）: 用户在平台网页上自己看到序列、亲手开了开关 → 回来同步本地状态。
    这条路径**不代替审批**，而是承认"用户已用更直接的方式行使了同一意志"：
    ① 只读回读平台确认真的 active（读不到/非active 一律拒绝，不猜、不替用户激活）
    ② 仍要求 record 处于 S11、seq 与 record 一致（防串台）
    ③ 本地只推进 status→S12，不发起任何平台写操作
    ④ 要求 --confirm <用户原话>（须含"激活"）作为意志凭据；不做审批哈希绑定（平台侧已生效，本地无写操作可授权）
"""
import json, subprocess, sys, argparse, time, hashlib
import re as _re
from pathlib import Path

KB = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KB / "tools"))
from approval import (confirm_quote_ok, require_approval, stable_params_hash,
                       is_approval_used, mark_approval_used)
from compliance_validation import validate_compliance
from profile_utils import ensure_same_project_paths, profile_gate
from project_lock import acquire_project_lock
from update_run_state import read_meta, read_status, require_state, update_frontmatter
from workspace_guard import preflight
from s11_closure import check_s11_closure

ap = argparse.ArgumentParser()
ap.add_argument("--token", required=True)
ap.add_argument("--org", required=True)
ap.add_argument("--seq", required=True, help="序列id(激活前逐字核对)")
ap.add_argument("--confirm", default="", help="用户确认原话（须含「确认激活」四个字且无否定/犹豫才放行；仅说'激活'不算）")
ap.add_argument("--approval", default="", help="★S12凭证id(只能由 flow --resume-s12 --confirm 签发；grant禁止S12)")
ap.add_argument("--project", default="", help="稳定项目键=<operator_key>/<product_key>(激活必填, 须与profile一致)")
ap.add_argument("--profile", default="", help="★产品档案路径(激活必填): 须过结构校验, 项目键一致, 其 sha256/status/version 进入审批哈希")
ap.add_argument("--compliance-file", default="", help="★合规核验JSON(激活必填): market/list_source/sender_identity/unsubscribe/suppression 均pass; 文件sha256进入审批哈希")
ap.add_argument("--record", default="", help="项目operation-record；激活推进S12，回滚推进S11")
ap.add_argument("--status", action="store_true", help="只读查当前状态,不激活")
ap.add_argument("--deactivate", action="store_true", help="回滚为 inactive（空序列测完须回滚,防后续加联系人即真发;降风险方向,不要求S12审批但须明确目标回读）")
ap.add_argument("--check-structure", action="store_true", help="只读：只跑激活前结构闸门（上限/标签身份/12步模板与步长），不激活、不写任何本地状态; exit 0 通过 / 2 不通过")
ap.add_argument("--sync-manual", action="store_true", help="★用户在网页手动激活后同步本地状态：只读回读平台确认active→本地推进S12；不发起任何平台写操作")
args = ap.parse_args()

def api(path, p, t=60):
# LFX_GATE_WRITE
    try:
        from startup_gate import enforce_cli_startup as _lfx_gate
        _lfx_gate()
    except ImportError:
        pass
    except Exception as _lfx_gate_exc:
        __import__("sys").stderr.write("还差一步：请先告诉我怎么称呼您、主要卖什么产品，登记后我马上继续（不是你的账号问题）。\n")
        raise SystemExit(2)
    r = subprocess.run(["curl","-sSL","-m","55","-X","POST",f"https://web.laifaxin.com/api/{path}",
                        "-H","Content-Type: application/json","-H",f"accesstoken: {args.token}",
           "-H", f"uid: {args.org}","-d",json.dumps(p)],
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

STEP_COUNT = 12
_HEX24 = _re.compile(r"[0-9a-f]{24}")


EXPECT_MAX_PER_DAY = 30000      # RULES: 账号每天最多发信上限
EXPECT_DOMAIN_PER_DAY = 5       # RULES: 同一收件域名每天最多


def _root_data(path, payload=None):
    """调用平台只读接口并返回 data（不存在返回 None，供 fail-closed 区分“空”和“读失败”）。"""
    r = api(path, payload or {})
    if not isinstance(r, dict):
        return None
    return r.get("data")


def _rules_limit_issues(rules):
    """三审 S0-1：上限必须实读比对，不许卡面打勾而工具没读。"""
    issues = []
    for key, expect, label in (
        ("max_emails_per_day", EXPECT_MAX_PER_DAY, "账号每天最多发信"),
        ("domain_emails_per_day", EXPECT_DOMAIN_PER_DAY, "同一收件域名每天最多"),
    ):
        raw = rules.get(key)
        try:
            val = int(raw)
        except (TypeError, ValueError):
            val = None
        if val != expect:
            issues.append(f"rules.{key}={raw!r}≠标准 {expect}（{label}）——序列上限被改过或不完整，不得激活")
    return issues


def _tag_identity_issues(rules):
    """三审 S1-1：notSentTags 必须是「询盘」「不发」两个真实标签，不能只验 id 形状。"""
    tags = rules.get("notSentTags")
    if not isinstance(tags, list) or not tags:
        return ["rules.notSentTags 缺失/为空——询盘/不发标签未绑定，不得激活"]
    bad = [t for t in tags if not _HEX24.fullmatch(str(t))]
    if bad:
        return [f"rules.notSentTags 含非法标签id: {bad}——不得激活"]
    data = _root_data("contacts/tags-list", {"type": "contacts"})
    if isinstance(data, list):
        lst = data
    elif isinstance(data, dict) and isinstance(data.get("list"), list):
        lst = data["list"]
    else:
        return ["contacts/tags-list 读取失败——无法确认标签身份，不得激活"]
    id2name = {}
    for item in lst:
        if not isinstance(item, dict):
            continue
        tid = str(item.get("id") or item.get("_id") or "")
        if tid:
            id2name[tid] = str(item.get("name") or "")
    got = {id2name.get(str(t), "") for t in tags}
    wanted = {"询盘", "不发"}
    missing = sorted(wanted - got)
    if missing:
        return [f"notSentTags 未解析到标签名 {missing}（实际解析: {sorted(x for x in got if x)}）——标签身份不符，回复不会停发，不得激活"]
    return []


def _template_binding_issues():
    """三审 S1-2：模板必须真实在模板库、步长必须 30分/5天/15天/30天。
    本函数自带只读实现（不依赖其他脚本），保证任何最小运行副本也能 fail-closed。"""
    issues = []
    steps_r = api("sequences/step-list", {"seqId": args.seq, "current": 1, "pageSize": 50})
    slist = steps_r.get("data") if isinstance(steps_r.get("data"), list) else None
    if slist is None:
        return ["step-list 读取失败（接口异常）——无法确认 12 步与模板绑定，不得激活"]
    if len(slist) != STEP_COUNT:
        issues.append(f"序列步骤数={len(slist)}≠{STEP_COUNT}——不得激活")
    template_ids = set()
    pages = 0
    for page in range(1, 9):
        tr = api("mailbox/templates-list", {"current": page, "pageSize": 100, "filter": {}, "sort": {}})
        td = tr.get("data") if isinstance(tr, dict) else None
        tl = td if isinstance(td, list) else (td.get("list") if isinstance(td, dict) else None)
        if tl is None:
            if pages == 0:
                return ["邮件模板库查询失败（接口异常）——无法确认每步模板真实存在，不得激活"]
            break
        pages += 1
        for item in tl:
            if not isinstance(item, dict):
                continue
            tid = item.get("_id") or item.get("id") or ""
            if tid:
                template_ids.add(str(tid))
        if len(tl) < 100:
            break
    if not template_ids:
        return ["邮件模板库为空/一个模板都没查到——无法确认每步模板真实存在，不得激活"]

    def expected_wait(no):
        return ("minute", 30) if no == 1 else ("day", 5) if no == 2 else ("day", 15) if no == 3 else ("day", 30)

    for step in slist:
        if not isinstance(step, dict):
            issues.append(f"步骤结构异常: {step!r}")
            continue
        no = step.get("step")
        tids = step.get("template_ids") or []
        if not isinstance(tids, list) or not tids:
            issues.append(f"step{no}: 未绑定任何邮件模板（template_ids 为空）——不得激活")
        else:
            bad = [t for t in tids if not _HEX24.fullmatch(str(t)) or str(t) not in template_ids]
            if bad:
                issues.append(f"step{no}: 模板 id 非法或不在邮件模板库: {bad}")
        exp = expected_wait(no)
        if (step.get("wait_mode"), step.get("wait_time")) != exp:
            issues.append(f"step{no}: wait配置={step.get('wait_mode')}/{step.get('wait_time')}，应为 {exp[0]}/{exp[1]}")
    return issues


def check_sequence_structure():
    """★激活前的只读结构校验（任务A-3 + 三审 S0/S1）：
    规则上限实读比对、notSentTags 名称身份、12 步模板真实存在于模板库、步长正确。
    返回中文问题列表（空=通过）。本函数只读；调用方必须在任何激活写之前 fail-closed。"""
    issues = []
    detail = api("sequences/sequence-details", {"id": args.seq})
    data = detail.get("data") if isinstance(detail.get("data"), dict) else {}
    if not detail.get("success") or not data:
        issues.append("sequence-details 读取失败——无法确认规则/notSentTags，不得激活")
    else:
        rules = data.get("rules")
        if not isinstance(rules, dict) or not rules:
            issues.append("序列 rules 为空/缺失——规则未保存的序列不得激活")
        else:
            issues.extend(_rules_limit_issues(rules))
            issues.extend(_tag_identity_issues(rules))
    issues.extend(_template_binding_issues())
    return issues


# ---- 只读结构闸门模式（运维/测试/激活前预检可用；不写任何状态）----
if args.check_structure:
    _issues = check_sequence_structure()
    if _issues:
        print(f"❌ 激活前结构闸门未通过（{len(_issues)} 项）——不得激活：")
        for _i in _issues:
            print(f"   - {_i}")
        sys.exit(2)
    print("✅ 激活前结构闸门通过：上限/标签身份/12步模板与步长均符合标准")
    sys.exit(0)

# ---- 只读状态模式 ----
if args.status:
    st = get_status()
    print(f"序列 {args.seq} 当前状态: {st if st else '未取到(接口偶发空可重试)'}")
    sys.exit(0 if st else 3)

# ---- 确认原话校验（★对抗P0: 否定句/犹豫词拦截——比 flow_orchestrator 更严: 对向词全局拦截）----
# ★P0-B 激活口令(静态红队): 激活路径必须逐字含「确认激活」四个字——只含「激活」的含糊原话
#   （"激活吧"/"激活序列X"）不得授权。required_phrase 由激活调用点显式传入；
#   网页手动激活同步(sync-manual)与回滚(deactivate)是另一条契约，仍按 action_word 判定。
ACTIVATION_CONFIRM_PHRASE = "确认激活"

def check_confirm(quote, action_word, required_phrase=""):
    """返回 (ok, 原因)。action_word='激活'或'暂停'。否定句/犹豫词/对向指令词一律拒绝。
    required_phrase 非空时：原话必须逐字包含该短语（激活路径=「确认激活」，仅说「激活」不通过）。"""
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
    if required_phrase:
        if required_phrase not in q:
            return False, (f"原话不含「{required_phrase}」四个字——仅说「{action_word}」不构成授权，"
                           f"须用户明确回复「{required_phrase} <序列名>」")
        return True, ""
    if action_word not in q and "activate" not in q.lower() and not (action_word == "暂停" and "inactive" in q.lower()):
        return False, f"原话不含'{action_word}'指令"
    return True, ""

# ---- ★手动激活同步模式（用户在平台网页自己开了开关）----
if args.sync_manual:
    if not args.record:
        print("❌ --sync-manual 必须带 --record <operation-record.md>（本地状态要推进到S12）"); sys.exit(2)
    if not args.confirm.strip():
        print("❌ --sync-manual 必须带 --confirm \"<用户原话>\"（须含'激活'）——同步本地状态也是登记用户意志"); sys.exit(2)
    ok_m, why_m = check_confirm(args.confirm, "激活")
    if not ok_m:
        print(f"❌ 确认原话校验未过: {why_m}: {args.confirm!r}"); sys.exit(2)
    try:
        require_state(args.record, ("S11", "S12")); acquire_project_lock(args.record, "sync_manual_activation")
    except (ValueError, RuntimeError) as exc:
        print(f"❌ {exc}"); sys.exit(4)
    rec = read_meta(args.record)
    if rec.get("sequence_id", "") != args.seq:
        print(f"❌ --seq={args.seq} 与 record.sequence_id={rec.get('sequence_id')!r} 不一致——拒绝同步（防串台）"); sys.exit(4)
    # 只读回读（先校验落点：用户在别的空间激活就等于没生效，必须报出来）
    preflight(args.token, args.org, dry_run=False, what="同步手动激活状态", require_verified=True)
    st_now = get_status()
    if st_now is None:
        print("❌ 平台状态未能回读（接口偶发空——稍等重试）；在读到明确 active 之前不改本地状态"); sys.exit(3)
    if st_now != "active":
        print(f"❌ 平台回读状态={st_now}≠active——说明网页上的开关没生效（或还没开/开在了别的工作空间）。")
        print("   本地状态保持 S11 不变。请回 https://web.laifaxin.com/marketing/sequences 确认该序列已开启后重跑本命令。")
        sys.exit(3)
    # ★三审 S0-2：方式二也先跑同一套只读闸门（上限/标签身份/模板与步长）；不通过不得写 S12
    _sync_issues = check_sequence_structure()
    if _sync_issues:
        print("❌ 方式二只读闸门未通过——平台虽已 active，但下列项不成立，先停发/核对，不写本地 S12：")
        for _i in _sync_issues:
            print(f"   - {_i}")
        if read_status(args.record) != "S12":
            try:
                update_frontmatter(args.record, {"status": "ERROR_BLOCKED", "next_state": "S11"}, expected_states=("S11",))
                print("   本地已标 ERROR_BLOCKED；请先 --deactivate 停发，再人工核对。")
            except Exception as _exc:
                print(f"   （本地状态未改：{_exc}）")
        else:
            print("   本地已是 S12，但线上结构与闸门不符——请立即停发并核对。")
        sys.exit(2)
    if read_status(args.record) == "S12":
        print("ℹ️ 平台已 active 且本地已是 S12——无需重复同步"); sys.exit(0)
    update_frontmatter(args.record, {"status": "S12", "next_state": ""}, expected_states=("S11", "S12"))
    print(f"✅ 已确认平台侧 active（序列 {args.seq}），本地状态已同步 → S12")
    print("   本地未发起任何平台写操作：激活开关是您本人在网页上开的。")
    sys.exit(0)

# ---- 回滚模式（对抗P0-1: 空序列测完须回滚 inactive; 降风险方向不要求S12审批, 但须明确目标回读）----
if args.deactivate:
    if not args.record:
        print("❌ 回滚必须带 --record <operation-record.md>，确保本地状态与线上同步"); sys.exit(2)
    # ★三审S0-3/S2-3：停发是降风险动作，任何状态（含 ERROR_BLOCKED）都必须可执行；且必须先校验工作空间落点
    try: require_state(args.record, ("S11", "S12", "ERROR_BLOCKED")); acquire_project_lock(args.record, "deactivate_sequence")
    except (ValueError, RuntimeError) as exc: print(f"❌ {exc}"); sys.exit(4)
    preflight(args.token, args.org, dry_run=False, what="停发/回滚序列", require_verified=True)
    st_pre = get_status()
    if st_pre == "inactive":
        update_frontmatter(args.record, {"status": "S11", "next_state": "S12"}, expected_states=("S11", "S12", "ERROR_BLOCKED"))
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
        update_frontmatter(args.record, {"status": "S11", "next_state": "S12"}, expected_states=("S11", "S12", "ERROR_BLOCKED"))
        print(f"✅ 回滚成功且已回读确认: 序列 {args.seq} = inactive；本地状态→S11")
        sys.exit(0)
    print(f"  ❌ 回读 status={st1}≠inactive——假成功!立即人工核查"); sys.exit(4)

# ---- 激活模式（★所有本地闸门通过后才允许首次联网）----
if not args.record:
    print("❌ 激活必须带 --record <operation-record.md>，确保回读active后本地状态同步推进S12"); sys.exit(2)
try:
    require_state(args.record, ("S11", "S12"))
    acquire_project_lock(args.record, "activate_sequence")
except (ValueError, RuntimeError) as exc:
    print(f"❌ {exc}"); sys.exit(4)
record_meta = read_meta(args.record)
if record_meta.get("sequence_id", "") != args.seq:
    print(f"❌ --seq={args.seq} 与S11已验证的record.sequence_id={record_meta.get('sequence_id')!r}不一致")
    sys.exit(4)
_closure = check_s11_closure(record_meta, max_age_hours=24)
if _closure:
    print("❌ S11 收口证明无效——不能激活（手写 status:S11 不算真实收口）：")
    for _i in _closure:
        print(f"   - {_i}")
    sys.exit(4)

# 1) 产品档案闸门: 标准同目录、结构和项目身份均在首次联网前完成。
if not args.profile:
    print("❌ 激活必填 --profile runs/<operator_key>/<product_key>/product-profile.md(其 sha256/status/version 进入审批哈希)"); sys.exit(2)
PROFILE_PATH = Path(args.profile)
if not PROFILE_PATH.is_absolute():
    PROFILE_PATH = KB / PROFILE_PATH
PROFILE_STATUS, PROFILE_ISSUES, PROFILE_META, PROFILE_SHA = profile_gate(PROFILE_PATH)
if not args.project:
    print("❌ 激活必填 --project <operator_key>/<product_key>(与档案及审批凭证一致)"); sys.exit(2)
EXPECTED_PROJECT = f"{PROFILE_META.get('operator_key', '').strip()}/{PROFILE_META.get('product_key', '').strip()}"
EXPECTED_PROFILE_PATH = KB / "runs" / str(PROFILE_META.get("operator_key", "")).strip() / str(PROFILE_META.get("product_key", "")).strip() / "product-profile.md"
try:
    profile_is_standard = PROFILE_PATH.resolve() == EXPECTED_PROFILE_PATH.resolve()
except OSError:
    profile_is_standard = False
if not profile_is_standard:
    PROFILE_ISSUES.append("--profile 只允许 runs/<operator_key>/<product_key>/product-profile.md 标准路径")
if not PROFILE_ISSUES and args.project != EXPECTED_PROJECT:
    PROFILE_ISSUES.append(f"--project={args.project!r} 与档案稳定项目键 {EXPECTED_PROJECT!r} 不一致——拒绝跨运营方/产品激活")
if PROFILE_ISSUES:
    print(f"❌ 产品档案闸门未过: {PROFILE_PATH}")
    for _i in PROFILE_ISSUES:
        print(f"   - {_i}")
    print("   指引: 档案按 runs/_template/product-profile.md 修好后重跑(状态/hash 校验须通过)。 (exit 4)")
    sys.exit(4)
if not ensure_same_project_paths(args.record, PROFILE_PATH):
    print("❌ --record 与 --profile 不在同一项目目录——拒绝跨项目同步状态"); sys.exit(4)
record_identity_bad = []
for _key in ("operator_key", "product_key"):
    if record_meta.get(_key, "") != PROFILE_META.get(_key, ""):
        record_identity_bad.append(_key)
if record_meta.get("project") and record_meta.get("project") != EXPECTED_PROJECT:
    record_identity_bad.append("project")
if record_identity_bad:
    print("❌ record/profile项目身份不一致: " + ", ".join(record_identity_bad)); sys.exit(4)
print(f"  ✅ 档案闸门: status={PROFILE_STATUS} | sha256={PROFILE_SHA[:12]}... | 项目键={EXPECTED_PROJECT}")

# 2) 合规、确认、审批和文件二次hash均为纯本地闸门。
if not args.compliance_file:
    print("❌ 激活必填 --compliance-file <合规核验JSON>——须为live且五项正式证据均pass"); sys.exit(2)
comp_path = Path(args.compliance_file)
if not comp_path.is_absolute():
    comp_path = KB / comp_path
_comp_doc, comp_issues, COMP_SHA = validate_compliance(
    comp_path, args.project, args.seq, PROFILE_SHA
)
if comp_issues:
    print("❌ 合规核验未通过——禁止激活")
    for issue in comp_issues:
        print(f"   - {issue}")
    sys.exit(2)
print(f"  ✅ 合规核验: evidence_mode=live且五项均pass | 文件sha256={COMP_SHA[:12]}...")

ok, why = check_confirm(args.confirm, "激活", required_phrase=ACTIVATION_CONFIRM_PHRASE)
if not ok:
    print(f"❌ 确认原话校验未过: {why}: {args.confirm!r}\n   仅用户明确正向'确认激活'才激活（只说'激活'不算授权，exit 2）"); sys.exit(2)

binding = {
    "project": args.project,
    "org_sha256": hashlib.sha256(str(args.org).encode()).hexdigest(),
    "seq": args.seq,
    "profile": {"sha256": PROFILE_SHA, "status": PROFILE_STATUS, "version": PROFILE_META.get("profile_version", "")},
    "compliance": {"sha256": COMP_SHA},
}
# ★三审 S1-5：同一凭证只允许成功激活一次；停发后重新激活必须由用户新原话重签
if args.approval and is_approval_used(args.approval):
    print("❌ 该 S12 凭证已用于一次激活，不能复用——请重新 --resume-s12 由用户新原话签发。(exit 2)")
    sys.exit(2)
approval_row = require_approval(args.approval, args.project, ("S12",), what="激活序列", expected_hash=stable_params_hash(binding))
if " ".join(str(approval_row.get("user_quote", "")).split()) != " ".join(args.confirm.split()):
    print("❌ --confirm 必须与S12审批凭证中的用户原话逐字一致——拒绝替换确认语义")
    sys.exit(2)

from profile_utils import profile_sha256 as _profile_sha_now
if _profile_sha_now(PROFILE_PATH) != PROFILE_SHA or hashlib.sha256(comp_path.read_bytes()).hexdigest() != COMP_SHA:
    print("❌ 审批后profile/compliance文件发生变化——拒绝激活，重新确认")
    sys.exit(4)

# 3) 首次联网：只有完整本地证明链通过后才读取在线状态。
# ★先校验工作空间落点(仍只读)：激活=真发信，落点错=用错账号发信——必须在任何写之前阻断。
preflight(args.token, args.org, dry_run=getattr(args, "dry_run", False), what="激活序列")
st0 = get_status()
if st0 is None:
    print(f"❌ 序列 {args.seq} 状态未能回读(接口偶发空——稍等重试,勿盲目激活)"); sys.exit(3)
print(f"激活前状态: {st0}")
if st0 not in ("inactive", "active"):
    print(f"❌ 序列状态={st0!r}，只有明确inactive才允许激活；未知状态fail-closed")
    sys.exit(3)
if st0 == "active":
    if read_status(args.record) == "S12":
        print("ℹ️ 序列已active且本地已是S12——不重复激活")
        sys.exit(0)
    update_frontmatter(args.record, {"status": "ERROR_BLOCKED", "next_state": "S11"}, expected_states=("S11",))
    print("❌ 线上序列已active，但本地尚未完成S12合规/审批链；已标ERROR_BLOCKED。立即核查发送影响，不能自动洗成S12")
    sys.exit(4)

# ★激活前只读结构校验（任务A-3，2026-10-23）：rules/notSentTags + step-list 的 12 步模板绑定。
#   必须在发起任何激活写（sequence-active）之前 fail-closed；这里只读接口，不改平台数据。
_structure_issues = check_sequence_structure()
if _structure_issues:
    print("❌ 激活前只读校验未通过——本次不发起激活请求（序列保持原状态，本地状态保持 S11）")
    for _issue in _structure_issues:
        print(f"   - {_issue}")
    print("   处理: 先在平台补齐 12 步模板与序列规则（询盘/不发），再重跑本工具。 (exit 2)")
    sys.exit(2)
print(f"  ✅ 激活前只读校验: {STEP_COUNT} 步均绑定模板；rules/notSentTags 存在")

# 写入前在线二次回读，确认仍为inactive。
if get_status() != "inactive":
    print("❌ 激活写入前序列不再明确inactive——fail-closed")
    sys.exit(3)
print(f"🔓 执行激活: sequence-active {{id:{args.seq}, active:true}}")
r = api("sequences/sequence-active", {"id": args.seq, "active": True})
print(f"  接口返回: success={r.get('success')} {r.get('message') or ''}")
# ★三审S0-1：接口超时/空响应会被 api() 吞成 {}，不能据此断言「未激活」；无论 success 真假，强制回读三态
st1 = None
for _i in range(3):
    time.sleep(2 if _i == 0 else 3)
    st1 = get_status()
    if st1 in ("active", "inactive"):
        break
print(f"  回读状态: {st1}")
if st1 == "active":
    update_frontmatter(args.record, {"status": "S12", "next_state": ""}, expected_states=("S11", "S12"))
    mark_approval_used(args.approval, args.project, "S12", args.seq)
    print(f"✅ 激活成功且已回读确认: 序列 {args.seq} = active；本地状态→S12")
    sys.exit(0)
if st1 == "inactive":
    if r.get("success"):
        print("  ❌ 接口 success 但回读明确 inactive——平台未生效，本次未激活；可重试或核查后重跑。(exit 4)"); sys.exit(4)
    print("  ❌ 激活接口未成功且回读明确 inactive——本次未激活；计划保持关闭。(exit 1)"); sys.exit(1)
update_frontmatter(args.record, {"status": "ERROR_BLOCKED", "next_state": "S11"}, expected_states=("S11",))
print("  ❌ 回读三态未知（平台可能已在发送）——已标 ERROR_BLOCKED；请先立即停发：--deactivate，再人工核查。(exit 4)")
sys.exit(4)
