#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""★审批凭证模块(审批闸门(工具级)): 写操作工具执行前必须 require_approval 通过, 否则拒绝写入。
approvals.tsv 列: id / project_id / state / decision / user_quote / memo(原parameters_hash,可为备注或真哈希) / time / status
用法(在写工具内):
  import sys; sys.path.insert(0, str(Path(__file__).resolve().parent))
  from approval import require_approval
  require_approval(args.approval, args.project, ("S5",), what="保存前N")
"""
import hashlib, os, time
from pathlib import Path

KB = Path(__file__).resolve().parent.parent
os.makedirs(KB / ".local", exist_ok=True)  # 等价 (KB/".local").mkdir(exist_ok=True)
APPROVALS = KB / ".local" / "approvals.tsv"
VALID_STATUS = ("confirmed", "backfilled")
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


def gen_id(project, state, quote, t=None):
    t = t or time.strftime("%Y-%m-%d %H:%M:%S")
    return "ap-" + hashlib.sha256(f"{project}|{state}|{quote}|{t}".encode()).hexdigest()[:12]


def find_approval(approval_id, project=None, states=None):
    """按 id 精确匹配; project 精确匹配; states 前缀匹配(state.startswith); status ∈ confirmed/backfilled"""
    for r in _rows():
        if r.get("id") != approval_id:
            continue
        if project and r.get("project_id") != project:
            continue
        if states and not any((r.get("state") or "").startswith(s) for s in states):
            continue
        if r.get("status") not in VALID_STATUS:
            continue
        return r
    return None


def require_approval(approval_id, project, states, what=""):
    """写操作硬闸门: 无有效审批 → 打印原因并 exit(1)"""
    if not approval_id:
        print(f"❌ 缺审批凭证 --approval <id>（{what}）。写操作必须先经确认节点，凭证见 .local/approvals.tsv 或编排器输出(审批闸门(工具级))。")
        raise SystemExit(1)
    r = find_approval(approval_id, project, states)
    if not r:
        print(f"❌ 审批凭证无效/状态不符: approval={approval_id} project={project} states={list(states)}。拒绝写操作(审批闸门(工具级))。")
        raise SystemExit(1)
    print(f"  ✅ 审批通过: {r.get('id')} | {r.get('state')} | {r.get('decision','')[:40]} | {r.get('status')}")
    return r


def record(project, state, decision, quote, params_hash, status="confirmed"):
    """追加一行审批并返回 id（编排器/人工确认后调用）"""
    _rows()
    t = time.strftime("%Y-%m-%d %H:%M:%S")
    aid = gen_id(project, state, quote, t)
    line = f"{aid}\t{project}\t{state}\t{decision}\t{quote}\t{params_hash}\t{t}\t{status}\n"
    # ★ISS-51: 首次创建文件须写表头（否则首行数据被当 header，闸门全失效）
    if not APPROVALS.exists() or APPROVALS.stat().st_size == 0:
        with open(APPROVALS, "w") as f:
            f.write("\t".join(COLUMNS) + "\n")
    with open(APPROVALS, "a") as f:
        f.write(line)
    return aid
