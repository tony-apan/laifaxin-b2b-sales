#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把「用途 + 推演来源」写进 operation-record，保证换会话/重跑可复现（v3 K6）。

只写一行表格记录，不改 status/next_state：
    | 用途与推演来源 | 已确认用途=…；待验证用途=…；payload=…；轮次=…；来源接口=…；调用=…；返回=…条；展示=…条；补推=…；复现=… |

失败/空/旧客群时同样记录（供审计与重试），但**不推进任何状态**。
"""
import json
import re
from pathlib import Path

ROW_LABEL = "用途与推演来源"
_REPRO = ("换会话/重跑时读本行 payload，原样作为推演描述（--infer-desc/--purpose）传给平台重取，"
          "不重新生成用途")
_MAX_CELL = 1200


def _cell(value):
    text = " ".join(str(value or "").split())
    return text.replace("|", "／")[:_MAX_CELL]


def render_row(product_desc_zh, evidence, confirmed="无", pending="无", purpose_source="用户确认",
               excluded_facts=None):
    rounds = (evidence or {}).get("rounds") or []
    last = rounds[-1] if rounds else {}
    retried = "是" if len(rounds) > 1 else "否"
    reason = last.get("retry_reason") or last.get("reason") or "-"
    cell = "；".join([
        "已确认用途=" + (confirmed or "无"),
        "待验证用途=" + (pending or "无"),
        "用途来源=" + (purpose_source or "用户确认"),
        "payload=" + (product_desc_zh or ""),
        "轮次=" + str(len(rounds)),
        "来源接口=" + str((evidence or {}).get("source_api", "")),
        "调用=" + str(last.get("call_status", "")),
        "返回=" + str(last.get("returned_count", 0)) + "条",
        "展示=" + str((evidence or {}).get("display_count", 0)) + "条",
        "补推=" + retried + ("（" + str(reason) + "）" if retried == "是" else ""),
        "复现=" + _REPRO,
    ])
    if excluded_facts:
        cell += "；" + _excluded_cell(excluded_facts)
    return "| {} | {} |".format(ROW_LABEL, _cell(cell))


def record_usage(record_path, product_desc_zh, evidence, confirmed="无", pending="无",
                 purpose_source="用户确认", excluded_facts=None):
    """插入或更新本行；返回写入的单元格文本。只动这一行，不碰 frontmatter/状态。"""
    path = Path(record_path)
    text = path.read_text(encoding="utf-8")
    line = render_row(product_desc_zh, evidence, confirmed, pending, purpose_source, excluded_facts)
    pattern = re.compile(r"^\|\s*" + re.escape(ROW_LABEL) + r"\s*\|.*$", re.M)
    if pattern.search(text):
        text = pattern.sub(lambda _m: line, text, count=1)
    else:
        anchor = re.search(r"^\|\s*客群\s*\|.*$", text, re.M)
        if anchor:
            text = text[:anchor.end()] + "\n" + line + text[anchor.end():]
        else:
            text = text.rstrip("\n") + "\n" + line + "\n"
    path.write_text(text, encoding="utf-8")
    return line.split("|")[2].strip()


def _excluded_cell(excluded_facts):
    """④ 只做本地备注：记录它被排除，不进 payload。"""
    labels = [str(item.get("label") or item.get("key") or "") for item in excluded_facts]
    reasons = sorted({str(item.get("reason") or "") for item in excluded_facts if item.get("reason")})
    return "④已排除=" + "、".join(labels) + ("（" + "、".join(reasons) + "）" if reasons else "")


def load_evidence(path):
    """读取 segments/segment-source.jsonl 的最后一行（重跑/换会话时复现用）。"""
    target = Path(path)
    if not target.is_file():
        return {}
    lines = [line for line in target.read_text(encoding="utf-8").splitlines() if line.strip()]
    if not lines:
        return {}
    try:
        return json.loads(lines[-1])
    except json.JSONDecodeError:
        return {}
