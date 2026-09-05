#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""★审批凭证模块(审批闸门(工具级)): 写操作工具执行前必须 require_approval 通过, 否则拒绝写入。
approvals.tsv 列(8列, 换机兼容): id / project_id / state / decision / user_quote / memo(参数哈希或备注) / time / status
授权规则(2026-09-04 静态红队P0修复):
  - 只有 decision=confirm 且 status=confirmed 的凭证可授权写操作
  - backfilled(换机恢复的历史审计行)/modified(修改意见)/pending(参数不全的 decision_pending) 一律不可授权
  - record(decision="modify") 强制写 status=modified
参数绑定(防审批与执行参数不一致):
  - 工具端: require_approval(..., expected_hash=stable_params_hash(本次实际参数dict)) —— 哈希由工具按本次实际参数重算, 不信调用者/CLI传入的哈希
  - 铸造端: flow_orchestrator 确认节点(参数齐全时) 或专门审批命令:
      python3 tools/approval.py grant --project <operator_key>/<product_key> --state S10_加联系人 \
          --quote "<用户确认原话>" --params-file <实际参数.json>
    ★S12禁止grant，只能由flow_orchestrator当前TTY交互节点签发。
    参数JSON须与工具端绑定schema逐字段一致(工具不认路径类字段, 见各工具docstring)
用法(在写工具内):
  import sys; sys.path.insert(0, str(Path(__file__).resolve().parent))
  from approval import require_approval, stable_params_hash
  binding = {"project": args.project, "seq": args.seq, ...}   # 本次实际参数(工具自算, 不信CLI给的hash)
  require_approval(args.approval, args.project, ("S10",), what="加联系人", expected_hash=stable_params_hash(binding))
"""
import hashlib, json, os, re, time
from pathlib import Path

KB = Path(__file__).resolve().parent.parent
os.makedirs(KB / ".local", exist_ok=True)  # 等价 (KB/".local").mkdir(exist_ok=True)
APPROVALS = KB / ".local" / "approvals.tsv"
AUTH_DECISION = "confirm"   # 只有 confirm 决定可授权
AUTH_STATUS = "confirmed"   # 只有 confirmed 状态可授权(backfilled/modified/pending 不可)
VALID_STATUS = ("confirmed", "backfilled")  # 历史读取兼容; backfilled 只作审计不再授权
COLUMNS = ["id","project_id","state","decision","user_quote","memo","time","status"]


def _rows():
    if not APPROVALS.exists():
        return []
    lines = [l.rstrip("\n").split("\t") for l in APPROVALS.read_text().splitlines() if l.strip()]
    if not lines:
        return []
    header = lines[0]
    # ★ISS-51: 首行若以 ap- 开头 = 无表头(record 曾首次建文件不写表头) → 用标准列名, 不把数据行当 header
    if str(header[0]).lower().startswith("ap-"):
        return [dict(zip(COLUMNS, l)) for l in lines if len(l) == len(COLUMNS)]
    return [dict(zip(header, l)) for l in lines[1:] if len(l) == len(header)]


def stable_params_hash(params):
    """对参数 dict 计算稳定哈希(审批↔执行参数绑定用)。
    canonical JSON(sort_keys+ensure_ascii+紧凑分隔符, default=str) → sha256 前16位, 加 sha256: 前缀便于目视识别。
    同一 dict 任意键序/换机重算结果一致; 工具端永远用本函数按本次实际参数重算, 不信外部传入的哈希。"""
    canonical = json.dumps(params, sort_keys=True, ensure_ascii=True, separators=(",", ":"), default=str)
    return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


def gen_id(project, state, quote, t=None):
    t = t or time.strftime("%Y-%m-%d %H:%M:%S")
    return "ap-" + hashlib.sha256(f"{project}|{state}|{quote}|{t}".encode()).hexdigest()[:12]


def _unique_id(project, state, quote, t):
    """id 唯一化(静态红队P0): 同一秒内同 project/state/quote 的两次铸造(如对错参数各铸一条)不得共享 id,
    否则按 id 找凭证会让错误参数的凭证搭正确参数凭证的便车, 参数绑定失效。"""
    seen = {r.get("id") for r in _rows()}
    aid = gen_id(project, state, quote, t)
    salt = 0
    while aid in seen:
        salt += 1
        aid = gen_id(project, state, quote, f"{t}#{salt}")
    return aid


def _state_matches(actual, expected):
    actual, expected = str(actual or ""), str(expected or "")
    return actual == expected or actual.startswith(expected + "_")


def find_approval(approval_id, project=None, states=None, expected_hash=None):
    """按 id 精确匹配; project 精确匹配; states 前缀匹配(state.startswith);
    expected_hash 非空时 memo 须逐字一致(参数绑定); ★只有 decision=confirm 且 status=confirmed 才返回(可授权)。"""
    for r in _rows():
        if r.get("id") != approval_id:
            continue
        if project and r.get("project_id") != project:
            continue
        if states and not any(_state_matches(r.get("state"), s) for s in states):
            continue
        if expected_hash is not None and (r.get("memo") or "").strip() != expected_hash:
            continue
        if r.get("decision") != AUTH_DECISION or r.get("status") != AUTH_STATUS:
            continue
        return r
    return None


def _deny_reasons(r, project, states, expected_hash):
    reasons = []
    if project and r.get("project_id") != project:
        reasons.append(f"project={r.get('project_id')!r}≠{project!r}")
    if states and not any((r.get("state") or "").startswith(s) for s in states):
        reasons.append(f"state={r.get('state')!r} 不在 {list(states)}")
    if expected_hash is not None and (r.get("memo") or "").strip() != expected_hash:
        reasons.append(f"参数哈希不匹配: memo={str(r.get('memo'))[:27]}… ≠ 本次实际参数重算 {expected_hash}(审批与本次执行参数不一致)")
    if r.get("decision") != AUTH_DECISION:
        reasons.append(f"decision={r.get('decision')!r}(只有 confirm 可授权; modify/decision_pending/gate_ok 不可)")
    if r.get("status") != AUTH_STATUS:
        reasons.append(f"status={r.get('status')!r}(只有 confirmed 可授权; backfilled/modified/pending 不可)")
    return reasons


def require_approval(approval_id, project, states, what="", expected_hash=None):
    """写操作硬闸门: 无有效审批 → 打印原因并 exit(1)。
    expected_hash: 工具按本次实际参数用 stable_params_hash() 重算的哈希; 凭证 memo 须逐字一致, 否则拒绝(参数绑定)。"""
    if not approval_id:
        print(f"❌ 缺审批凭证 --approval <id>（{what}）。写操作必须先经确认节点或专门审批命令(tools/approval.py grant)铸造, 凭证见 .local/approvals.tsv(审批闸门(工具级))。")
        raise SystemExit(1)
    r = find_approval(approval_id, project, states, expected_hash=expected_hash)
    if not r:
        print(f"❌ 审批凭证无效/状态不符/参数绑定不匹配: approval={approval_id} project={project} states={list(states)}。拒绝写操作(审批闸门(工具级))。")
        cands = [x for x in _rows() if x.get("id") == approval_id]
        if not cands:
            print("   - 凭证 id 不存在于 .local/approvals.tsv")
        for x in cands[:3]:
            for why in _deny_reasons(x, project, states, expected_hash) or ["状态不符"]:
                print(f"   - {why}")
        if expected_hash is not None:
            print(f"   参数绑定: 本工具按本次实际参数重算哈希 {expected_hash}, 须与凭证 memo 一致。按本次实际参数重新铸造:")
            print(f"   python3 tools/approval.py grant --project {project} --state <节点> --quote \"<用户确认原话>\" --params-file <本次实际参数.json>")
        raise SystemExit(1)
    print(f"  ✅ 审批通过: {r.get('id')} | {r.get('state')} | {r.get('decision','')[:40]} | {r.get('status')}"
          + (f" | 参数哈希绑定 {expected_hash}" if expected_hash else ""))
    return r


def _tsv_cell(value, limit=1000):
    """审批字段固定为单行 TSV 单元格，防用户原话中的换行/制表符破坏换机后的8列解析。"""
    return " ".join(str(value or "").replace("\t", " ").replace("\r", " ").replace("\n", " ").split())[:limit]


def record(project, state, decision, quote, params_hash, status="confirmed"):
    """追加一行审批并返回 id（编排器/专门审批命令铸造时调用）。
    ★decision="modify" 强制 status="modified"(不可授权); 其余非 confirm 的 decision 建议显式传 pending 等不可授权状态。"""
    if decision == "modify":
        status = "modified"  # ★修改记录不可授权
    _rows()
    project, state = _tsv_cell(project, 200), _tsv_cell(state, 100)
    decision, quote = _tsv_cell(decision, 100), _tsv_cell(quote)
    params_hash, status = _tsv_cell(params_hash, 200), _tsv_cell(status, 50)
    t = time.strftime("%Y-%m-%d %H:%M:%S")
    aid = _unique_id(project, state, quote, t)
    line = f"{aid}\t{project}\t{state}\t{decision}\t{quote}\t{params_hash}\t{t}\t{status}\n"
    # ★ISS-51: 首次创建文件须写表头（否则首行数据被当 header，闸门全失效）
    if not APPROVALS.exists() or APPROVALS.stat().st_size == 0:
        with open(APPROVALS, "w") as f:
            f.write("\t".join(COLUMNS) + "\n")
    with open(APPROVALS, "a") as f:
        f.write(line)
    return aid


# ---------- 专门审批命令(对应工具执行前按实际参数铸造绑定凭证) ----------

def confirm_quote_ok(quote):
    """严格正向确认：否定、疑问、等待/取消语义优先拒绝。"""
    q = " ".join(str(quote or "").replace("’", "'").split()).strip()
    if not q or re.search(r"[?？]", q) or re.search(r"(?:是否|能否|可否|要不要|是不是|确认吗|可以吗)", q):
        return False
    if re.search(r"(?:^|[，,。；;！？!?\s])(?:否|拒绝|不同意)(?:$|[，,。；;！？!?\s])", q): return False
    if re.search(r"(?:不|别|不要|不用|先不|暂不|尚未|还没|未确认|等等|稍等|考虑|再说|取消|暂停|停止|回滚)", q): return False
    if re.search(r"\b(?:no|not|never|won'?t|don'?t|do not|cannot|can'?t|wait|later|pending|cancel|stop|pause)\b", q, re.I): return False
    return bool(re.search(r"确认|确定|同意|通过|可以|好的|没问题|激活|^是$|^好$|^行$|\b(?:yes|ok|okay|confirm(?:ed)?|approve[de]?|activate)\b", q, re.I))


def _load_params(args):
    raw = ""
    if getattr(args, "params_file", ""):
        p = Path(args.params_file)
        if not p.is_file():
            print(f"❌ --params-file 不存在: {p}"); raise SystemExit(2)
        raw = p.read_text(encoding="utf-8")
    elif getattr(args, "params", ""):
        raw = args.params
    else:
        print("❌ 须提供 --params-file <实际参数.json> 或 --params '<内联JSON>'——凭证必须绑定实际参数, 不允许无参铸造"); raise SystemExit(2)
    try:
        obj = json.loads(raw)
    except json.JSONDecodeError as e:
        print(f"❌ 参数JSON解析失败: {e}"); raise SystemExit(2)
    if not isinstance(obj, dict):
        print("❌ 参数JSON须为对象(dict)——键结构须与对应工具的绑定schema逐字段一致(见各工具docstring)"); raise SystemExit(2)
    return obj


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(prog="approval.py", description="审批凭证铸造/查询(专门审批命令): 对应写工具执行前按实际参数铸造绑定凭证; 工具端会按本次实际参数重算哈希比对, 不信本命令之外传入的哈希")
    sub = ap.add_subparsers(dest="cmd", required=True)
    g = sub.add_parser("grant", help="铸造一条绑定实际参数的审批凭证")
    g.add_argument("--project", required=True, help="稳定项目键=<operator_key>/<product_key>(与工具 --project 一致)")
    g.add_argument("--state", required=True, help="节点状态前缀, 如 S5_保存参数/S7_模板预览/S9_序列配置/S10_加联系人/S12_激活(工具按前缀匹配)")
    g.add_argument("--quote", required=True, help="用户确认原话(逐字)")
    g.add_argument("--decision", default="confirm", choices=["confirm", "modify"], help="默认 confirm; modify 强制 status=modified(不可授权)")
    g.add_argument("--params-file", default="", help="实际参数JSON文件(与 --params 二选一)")
    g.add_argument("--params", default="", help="内联参数JSON(与 --params-file 二选一)")
    h = sub.add_parser("hash", help="只计算参数稳定哈希(不落账), 供预填/比对")
    h.add_argument("--params-file", default="")
    h.add_argument("--params", default="")
    s = sub.add_parser("show", help="查看凭证行(诊断授权失败原因)")
    s.add_argument("--id", required=True)
    d = sub.add_parser("demote-migrated", help="换机恢复后把全部confirmed降为backfilled(只审计不可授权)")
    d.add_argument("--confirm", required=True, help="必须逐字 MIGRATION-DEMOTE")
    args = ap.parse_args(argv)

    if args.cmd == "demote-migrated":
        if args.confirm != "MIGRATION-DEMOTE":
            print("❌ 须 --confirm MIGRATION-DEMOTE"); raise SystemExit(2)
        rows = _rows()
        changed = 0
        for row in rows:
            if row.get("status") == "confirmed": row["status"] = "backfilled"; changed += 1
        APPROVALS.parent.mkdir(parents=True, exist_ok=True)
        tmp = APPROVALS.with_suffix(".tsv.tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            f.write("\t".join(COLUMNS) + "\n")
            for row in rows: f.write("\t".join(_tsv_cell(row.get(c, "")) for c in COLUMNS) + "\n")
        tmp.replace(APPROVALS)
        print(f"✅ 已将{changed}条旧confirmed凭证降为backfilled；仅历史审计，不可授权")
        return

    if args.cmd == "hash":
        obj = _load_params(args)
        print(stable_params_hash(obj))
        return
    if args.cmd == "show":
        for r in _rows():
            if r.get("id") == args.id:
                print("\t".join(r.get(c, "") for c in COLUMNS))
                return
        print(f"(未找到 {args.id})"); raise SystemExit(1)
    # grant
    if str(args.state).upper().startswith("S12"):
        print("❌ S12 激活凭证禁止通过 approval.py grant 铸造；只能在 flow_orchestrator 的当前交互式S12节点由用户现场确认生成")
        raise SystemExit(2)
    obj = _load_params(args)
    if args.decision == "confirm" and not confirm_quote_ok(args.quote):
        print("❌ --quote 不是明确正向确认（含否定/犹豫/疑问或缺确认词）——拒绝铸造可授权凭证")
        raise SystemExit(2)
    ph = stable_params_hash(obj)
    status = "modified" if args.decision == "modify" else "confirmed"
    aid = record(args.project, args.state, args.decision, args.quote, ph, status)
    print(f"✅ 凭证已铸造: {aid}")
    print(f"   project={args.project} | state={args.state} | decision={args.decision} | status={status} | 参数哈希={ph}")
    print("   参数JSON(工具端将按本次实际参数重算并逐字比对, 不一致即拒绝):")
    print("   " + json.dumps(obj, ensure_ascii=False, sort_keys=True))
    print(f"   → 工具执行须带: --approval {aid} --project {args.project} (且工具实际参数与本JSON逐字段一致)")
    if status != "confirmed":
        print("   ⚠️ status=modified——本凭证不可授权任何写操作, 仅作修改意见留痕")


if __name__ == "__main__":
    main()
