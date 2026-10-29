#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""执行护栏 · auth 授权票据（v3）。

定位声明：
  本护栏定位=防走神/跳步，不防恶意攻击。同一进程可以改写任意本地文件，
  因此 .local 下的 ticket/lock/ok **不是安全边界**，也不承诺防伪造；
  真正的边界是：拒绝路径不得产生任何网络副作用。

v3 约定：
  * authorize(action, quote, payload, task=...) -> ticket{action,payload_hash,nonce,ts}
    票据写 .local/auth/ticket-<nonce>.json（0600）。quote 只做人工追溯，不是凭据。
  * 消费是两阶段：
      begin  : O_CREAT|O_EXCL 建 ticket-<nonce>.lock（并发只有一个能拿到）
      HTTP   : 调用方执行真正的写操作
      commit : HTTP 成功 -> 写 ticket-<nonce>.ok（+ <action>-<task>.ok）并删 lock
      abort  : HTTP/网络失败 -> 删 lock，不写 ok，允许同参数重试
  * ticket 绑 payload_hash；换参数 -> E_AUTH_PAYLOAD_MISMATCH，票不烧，可改回原参数。
  * 同 nonce 二次/并发消费 -> E_AUTH_REUSED（退出码 3）。
  * 动作白名单：save/send/sequence/template/activate/delete/purge。
  * 动作词支持同义词；代词（全部/这批/...）必须有 render fields 的明确对象，
    否则 E_AUTH_NO_TARGET。否定式（不要保存100家）-> E_AUTH_NEGATED。

CLI：
  python3 tools/auth_guard.py authorize --action save --quote "保存100家" \
      --payload-json '{"n":100}' --task <task_id>
  python3 tools/auth_guard.py consume --ticket-file <path> --payload-json '{"n":100}'
  python3 tools/auth_guard.py check --action save --quote "好的，这批全部入库吧" \
      --payload-json '{"n":100}' --fields-json '{"对象":"..."}'
"""
from __future__ import annotations

import argparse
import hmac
import json
import os
import re
import secrets
import stat
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

TOOLS_DIR = Path(__file__).resolve().parent
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

from render_guard import canonical_hash  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
MAX_TICKET_BYTES = 64 * 1024

ACTIONS = ("save", "send", "sequence", "template", "activate", "delete", "purge")

ACTION_KEYWORDS = {
    "save": ("保存", "存入", "入库", "收录", "写入", "留存"),
    "send": ("发信", "发送", "投递", "寄出", "群发", "推送"),
    "sequence": ("序列", "流程"),
    "template": ("模板", "话术", "邮件模板"),
    "activate": ("激活", "启动", "开启", "跑起来"),
    "delete": ("删除", "删掉", "清理", "移除"),
    "purge": ("彻底删除", "清空", "清除", "销毁", "清洗"),
}

PRONOUNS = ("全部", "所有", "全量", "这批", "刚才的", "上面这些")

OBJECT_FIELD_KEYS = {
    "对象", "客户", "公司", "域名", "标签", "标签ID", "标签id", "seed", "种子",
    "产品", "名单", "邮箱", "数量", "count", "domain", "tag_id", "company_tag",
    "contact_tag", "operator", "product",
}

_HEX64_RE = re.compile(r"^[0-9a-fA-F]{64}$")
_TOKEN_RE = re.compile(r"^[\w.-]{1,128}$", re.UNICODE)
# R8 定稿规则：按句切分；否定词与动作词距离 ≤6 字才判否；后置撤回词单独处理。
# 不含裸“不”、不含“不含”，避免把“不够再补/不含4区”误拒。
_NEGATION_WORDS = (
    "不要", "别", "不用", "不需要", "禁止", "不许", "暂缓", "取消",
    "先不", "不可以", "算了", "免了",
)
_ACTION_WORDS = ("保存", "入库", "收录", "存入", "写")
_WITHDRAW_WORDS = ("别", "算了", "取消", "暂缓")
_CLAUSE_SPLIT_RE = re.compile(r"[，。；、\n（）()]+")
_STANDALONE_BU_RE = re.compile(r"(?:^|[，。；、\n（）()—-])不(?:[，。；、\n（）()—-]|$)")
_BU_ACTION_RE = re.compile(r"不(?:再|直接|立即|马上|现在)?(?:保存|入库|收录|存入|写)")
_DOMAIN_RE = re.compile(
    r"\b(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)+[A-Za-z]{2,}\b"
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _parse_ts(value: Any) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("ts 为空")
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    dt = datetime.fromisoformat(text)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _safe_task(task: Any) -> Optional[str]:
    if task is None:
        return None
    if not isinstance(task, str) or not task or task in (".", "..") or not _TOKEN_RE.fullmatch(task):
        raise ValueError("task 非法")
    return task


def _auth_dir(root: Optional[Any] = None) -> Path:
    base = Path(root) if root is not None else ROOT
    directory = base / ".local" / "auth"
    directory.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(directory, 0o700)
    except OSError:
        pass
    return directory


def ticket_path(nonce: str, root: Optional[Any] = None) -> Path:
    return _auth_dir(root) / ("ticket-" + nonce + ".json")


def lock_path(nonce: str, root: Optional[Any] = None) -> Path:
    return _auth_dir(root) / ("ticket-" + nonce + ".lock")


def ok_path(nonce: str, root: Optional[Any] = None) -> Path:
    return _auth_dir(root) / ("ticket-" + nonce + ".ok")


def task_ok_path(action: str, task: str, root: Optional[Any] = None) -> Path:
    return _auth_dir(root) / (action + "-" + task + ".ok")


def task_lock_path(action: str, task: str, root: Optional[Any] = None) -> Path:
    return _auth_dir(root) / (action + "-" + task + ".lock")


def payload_ok_path(action: str, payload_hash: str, root: Optional[Any] = None) -> Path:
    """payload 级幂等标记：同一 action + payload 只能成功一次。"""
    return _auth_dir(root) / (action + "-payload-" + payload_hash + ".ok")


def payload_lock_path(action: str, payload_hash: str, root: Optional[Any] = None) -> Path:
    return _auth_dir(root) / (action + "-payload-" + payload_hash + ".lock")


def _read_secure_json(path: Path, missing_code: str = "E_AUTH_NO_TICKET") -> Dict[str, Any]:
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(str(path), flags)
    except FileNotFoundError:
        raise _Denied(missing_code, "票据文件不存在: " + str(path))
    except OSError as exc:
        raise _Denied("E_AUTH_BAD_TICKET", "票据无法安全打开: " + str(exc))
    try:
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode):
            raise _Denied("E_AUTH_BAD_TICKET", "票据不是普通文件")
        # Windows 不提供 POSIX 0600 语义：os.stat 的 mode 恒为 0666/0444。
        # 票据只落在 .local/auth（用户目录）且由本工具生成；Windows 侧以路径+ACL 为边界。
        if os.name != "nt" and stat.S_IMODE(st.st_mode) != 0o600:
            raise _Denied("E_AUTH_BAD_TICKET", "票据权限必须是 0600")
        raw = b""
        while True:
            chunk = os.read(fd, 4096)
            if not chunk:
                break
            raw += chunk
            if len(raw) > MAX_TICKET_BYTES:
                raise _Denied("E_AUTH_BAD_TICKET", "票据文件过大")
    finally:
        os.close(fd)
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise _Denied("E_AUTH_BAD_TICKET", "票据 JSON 解析失败: " + str(exc))
    if not isinstance(data, dict):
        raise _Denied("E_AUTH_BAD_TICKET", "票据顶层必须是 object")
    return data


def _write_new(path: Path, data: Dict[str, Any]) -> None:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(str(path), flags, 0o600)
    try:
        os.write(fd, (json.dumps(data, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8"))
        os.fsync(fd)
    finally:
        os.close(fd)


def _unlink_quietly(path: Optional[Path]) -> None:
    if path is None:
        return
    try:
        path.unlink()
    except OSError:
        pass


def _append_log(action: Optional[str], quote: Optional[str], allow: bool,
                reason: str, root: Optional[Any] = None) -> None:
    path = _auth_dir(root) / "log.jsonl"
    entry = {
        "ts": _now_iso(),
        "action": action if isinstance(action, str) else "",
        "quote": quote if isinstance(quote, str) else "",
        "allow": bool(allow),
        "reason": reason,
    }
    line = json.dumps(entry, ensure_ascii=False) + "\n"
    flags = os.O_WRONLY | os.O_APPEND | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(str(path), flags, 0o600)
    try:
        os.write(fd, line.encode("utf-8"))
    finally:
        os.close(fd)


class _Denied(Exception):
    def __init__(self, code: str, reason: str):
        super().__init__(reason)
        self.code = code
        self.reason = reason


def _fail(code: str, reason: str, **extra: Any) -> Dict[str, Any]:
    result = {"ok": False, "code": code, "reason": reason, "ticket": None}
    result.update(extra)
    return result


def _deny(action: Any, quote: Any, code: str, reason: str,
          root: Optional[Any] = None, **extra: Any) -> Dict[str, Any]:
    try:
        _append_log(action if isinstance(action, str) else "", quote, False,
                    code + ": " + reason, root)
    except OSError:
        pass
    return _fail(code, reason, **extra)


def _keyword_hits(quote: str, action: str) -> List[Tuple[str, int]]:
    hits: List[Tuple[str, int]] = []
    for keyword in ACTION_KEYWORDS[action]:
        start = 0
        while True:
            index = quote.find(keyword, start)
            if index < 0:
                break
            hits.append((keyword, index))
            start = index + len(keyword)
    return hits


def _distance(left_start: int, left_end: int, right_start: int,
              right_end: int) -> int:
    if left_end <= right_start:
        return right_start - left_end
    if right_end <= left_start:
        return left_start - right_end
    return 0


def _clause_negates(clause: str) -> bool:
    """分句内否定词与动作词距离 ≤6 字 → 该分句否。"""
    if _BU_ACTION_RE.search(clause):
        return True
    actions = [(word, m.start(), m.end())
               for word in _ACTION_WORDS
               for m in re.finditer(re.escape(word), clause)]
    if not actions:
        return False
    for neg in _NEGATION_WORDS:
        for nm in re.finditer(re.escape(neg), clause):
            for _word, start, end in actions:
                if _distance(nm.start(), nm.end(), start, end) <= 6:
                    return True
    return False


def _is_negated(quote: str, index: Optional[int] = None) -> bool:
    """R8：按句判否；后置撤回词在全文有正向动作时也判否。"""
    if not isinstance(quote, str):
        return False
    if _STANDALONE_BU_RE.search(quote):
        return True
    clauses = [c for c in _CLAUSE_SPLIT_RE.split(quote) if c.strip()]
    if any(_clause_negates(c) for c in clauses):
        return True
    full_has_action = any(word in quote for word in _ACTION_WORDS)
    if full_has_action:
        for clause in clauses:
            has_action = any(word in clause for word in _ACTION_WORDS)
            if not has_action and any(word in clause for word in _WITHDRAW_WORDS):
                return True
    return False


def _has_number(quote: str) -> bool:
    return bool(re.search(r"\d", quote))


def _has_domain(quote: str) -> bool:
    return bool(_DOMAIN_RE.search(quote))


def _has_tag(quote: str) -> bool:
    patterns = (
        r"标签\s*(?:名|ID|id|编号)?\s*[:：=]\s*[^\s，,。；;]+",
        r"标签\s*[「“\"'][^」”\"']+[」”\"']",
        r"(?:companyTag|contactTag|tagId|tag_id)\s*[:=]\s*\S+",
        r"标签\s*[^\s，,。；;]*[-－][^\s，,。；;]*",
        r"[^\s，,。；;]*[-－][^\s，,。；;]*\s*标签",
    )
    return any(re.search(pattern, quote) for pattern in patterns)


def _has_pronoun(quote: str) -> bool:
    return any(word in quote for word in PRONOUNS)


def _meaningful(value: Any) -> bool:
    if value is None or isinstance(value, bool):
        return False
    if isinstance(value, str):
        text = value.strip()
        return bool(text) and text.lower() not in {"none", "null", "tbd", "todo", "unknown", "n/a", "na", "-", "?"}
    if isinstance(value, (int, float)):
        return True
    if isinstance(value, (list, dict, tuple)):
        return bool(value)
    return False


def needs_render_fields(quote: Any) -> bool:
    """quote 只有代词（这批/全部…）而没有数量/域名/标签时，必须由 render 补对象。"""
    if not isinstance(quote, str):
        return False
    return (_has_pronoun(quote)
            and not (_has_number(quote) or _has_domain(quote) or _has_tag(quote)))


def _fields_have_object(fields: Any) -> bool:
    if not isinstance(fields, dict):
        return False
    for key, value in fields.items():
        if str(key).strip() in OBJECT_FIELD_KEYS and _meaningful(value):
            return True
    return False


def _test_mode_ticket_ok():
    """一次性票据校验：票据文件存在、10 分钟内、内容与 nonce 一致。"""
    ticket = os.environ.get("LFX_GATE_TEST_TICKET") or ""
    nonce = os.environ.get("LFX_GATE_TEST_NONCE") or ""
    if not ticket or not nonce:
        return False
    try:
        p = Path(ticket)
        if not p.is_file():
            return False
        import time as _time
        if _time.time() - p.stat().st_mtime > 600:
            return False
        return p.read_text(encoding="utf-8").strip() == nonce
    except OSError:
        return False


def _test_mode_allowed():
    """进程内 unittest 放行；跨进程必须带一次性票据（防真实 shell 残留 env 静默放行）。"""
    if os.environ.get("LFX_GATE_TEST_MODE") != "1":
        return False
    return _test_mode_ticket_ok()


def _require_startup_ack() -> None:
    """开工必读门（L1）：未登记开工必读就拒绝铸票，任何写操作都过不去。

    放在授权中枢而不是每个脚本里：save/template/sequence/contact-add/activate
    都要先拿到票据，统一在这里拦一次。测试模式与 unittest 进程内放行（不改生产行为）。
    """
    if _test_mode_allowed():
        return
    try:
        from startup_gate import require_ack
    except Exception as exc:  # 模块缺失不得静默放行
        raise RuntimeError("开工必读闸门缺失（tools/startup_gate.py）：%s" % exc)
    require_ack()


def authorize(action: Any, quote: Any, payload: Any, *, task: Optional[str] = None,
              fields: Any = None, root: Optional[Any] = None,
              plan: Any = None, action_verified: bool = False) -> Dict[str, Any]:
    _require_startup_ack()
    if not isinstance(action, str) or action.strip().lower() not in ACTIONS:
        return _deny(action, quote, "E_AUTH_NO_ACTION",
                     "未知 action，必须是 " + "/".join(ACTIONS), root)
    act = action.strip().lower()
    if not isinstance(quote, str) or not quote.strip():
        return _deny(act, quote, "E_AUTH_NO_ACTION", "缺少用户授权原话", root)

    # v3：S5 纯确认（「确认」）不含动作词，由 authorize_save_plan 校完卡面绑定后置位，
    # 这里不再重复要求“保存/存入”等动作词；否定式检查仍然执行。
    # ★2026-10-23：编号选项（A/B/C/D 或 1/2/3/4）是用户对已展示选项的明确选择，视为显式授权。
    if action_verified:
        hits = [str(quote).strip()]
    elif act == "activate" and isinstance(payload, dict) and str(payload.get("seq") or "").strip() and "激活" in str(quote or ""):
        hits = [str(quote).strip()]
    elif re.fullmatch(r"[A-Da-d1-4]", str(quote or "").strip()):
        hits = [str(quote).strip()]
    else:
        hits = _keyword_hits(quote, act)
    if not hits:
        return _deny(act, quote, "E_AUTH_NO_ACTION",
                     "quote 不含动作关键词: " + "/".join(ACTION_KEYWORDS[act]), root)
    if _is_negated(quote):
        return _deny(act, quote, "E_AUTH_NEGATED", "否定式授权不得通过", root)

    # Guard V2（§5.2）：save 的 S5 票据只能由 confirm 流程经 authorize_save_plan
    # 铸造；缺 confirmed plan 的裸 payload 一律拒绝，不给直写后门。
    if act == "save":
        if not isinstance(plan, dict):
            return _deny(act, quote, "E_PLAN_REQUIRED",
                         "S5 保存必须携带 confirmed plan（save_company_cli confirm 产出）",
                         root)
        if plan.get("status") != "confirmed":
            return _deny(act, quote, "E_PLAN_NOT_CONFIRMED",
                         "plan 未经 confirm 确认", root)
        from approval import authorize_quote
        if quote != plan.get("quote") or not authorize_quote(quote, "S5", {"count": payload.get("selectTotal") if isinstance(payload, dict) else None}):
            return _deny(act, quote, "E_AUTH_QUOTE_MISMATCH", "原话与已确认卡不一致", root)

    try:
        payload_hash = canonical_hash(payload)
    except (TypeError, ValueError) as exc:
        return _deny(act, quote, "E_AUTH_BAD_PAYLOAD",
                     "payload 无法 canonical 化: " + str(exc), root)

    select_total = payload.get("selectTotal") if isinstance(payload, dict) else None
    if act == "save" and isinstance(plan, dict) and plan.get("status") == "confirmed":
        wire = plan.get("wire_payload")
        if not isinstance(wire, dict) or canonical_hash(wire) != payload_hash:
            return _deny(act, quote, "E_PLAN_PAYLOAD_MISMATCH",
                         "payload 与 plan.wire_payload 不一致", root)
        if type(select_total) is not int or select_total <= 0:
            return _deny(act, quote, "E_SELECT_TOTAL_INVALID",
                         "selectTotal 必须严格正 int", root)
        count = payload.get("count") if isinstance(payload, dict) else None
        if count is not None and (type(count) is not int or count != select_total):
            return _deny(act, quote, "E_COUNT_MISMATCH",
                         "count=%r 与 selectTotal=%r 不一致" % (count, select_total), root)

    # ★2026-10-23：编号选项（A-D / 1-4）指代已展示的完整选项卡，具体目标在 payload 中，
    # 不能再要求 quote 里出现数量/域名/标签。
    # v3：S5 纯确认的目标=plan 卡面 N（authorize_save_plan 已校验），此处视为已带对象。
    if action_verified:
        has_target = True
    elif re.fullmatch(r"[A-Da-d1-4]", str(quote or "").strip()):
        has_target = True
    else:
        has_target = _has_number(quote) or _has_domain(quote) or _has_tag(quote)
    if not has_target:
        if _has_pronoun(quote) and _fields_have_object(fields):
            has_target = True
        else:
            reason = "quote 缺数量/域名/标签对象"
            if _has_pronoun(quote):
                reason += "；代词需要 render.fields 中的明确对象"
            return _deny(act, quote, "E_AUTH_NO_TARGET", reason, root)

    try:
        payload_hash = canonical_hash(payload)
    except (TypeError, ValueError) as exc:
        return _deny(act, quote, "E_AUTH_BAD_PAYLOAD",
                     "payload 无法 canonical 化: " + str(exc), root)

    try:
        task = _safe_task(task)
    except ValueError as exc:
        return _deny(act, quote, "E_AUTH_BAD_TICKET", str(exc), root)
    if task is not None and task_ok_path(act, task, root).exists():
        return _deny(act, quote, "E_AUTH_REUSED",
                     "同 action + task 已成功消费过", root)
    if payload_ok_path(act, payload_hash, root).exists():
        return _deny(act, quote, "E_AUTH_REUSED",
                     "同 action + payload 已成功消费过", root)

    nonce = secrets.token_hex(16)
    ticket = {
        "action": act,
        "payload_hash": payload_hash,
        "nonce": nonce,
        "ts": _now_iso(),
    }
    file_data = dict(ticket)
    file_data["quote"] = quote
    file_data["task"] = task
    path = ticket_path(nonce, root)
    try:
        _write_new(path, file_data)
    except FileExistsError:
        # nonce 碰撞概率极低；直接拒绝，避免覆盖已有票据。
        return _deny(act, quote, "E_AUTH_BAD_TICKET", "nonce 碰撞，请重试", root)
    try:
        _append_log(act, quote, True, "ticket issued nonce=" + nonce, root)
    except OSError as exc:
        try:
            path.unlink()
        except OSError:
            pass
        return _fail("E_AUTH_LOG_FAILED", "授权日志写入失败: " + str(exc))
    return {
        "ok": True,
        "code": None,
        "reason": "",
        "ticket": ticket,
        "ticket_path": str(path),
        "payload_hash": payload_hash,
        "task": task,
    }


def _load_ticket(ticket: Any, root: Optional[Any] = None) -> Dict[str, Any]:
    if isinstance(ticket, dict):
        data = dict(ticket)
        path = None
    elif isinstance(ticket, (str, os.PathLike)):
        path = Path(ticket)
        data = _read_secure_json(path)
    else:
        raise _Denied("E_AUTH_BAD_TICKET", "ticket 必须是 object 或路径")
    for key in ("action", "payload_hash", "nonce", "ts"):
        if key not in data:
            raise _Denied("E_AUTH_BAD_TICKET", "ticket 缺字段: " + key)
    if data["action"] not in ACTIONS:
        raise _Denied("E_AUTH_BAD_TICKET", "ticket.action 非法")
    if not isinstance(data["payload_hash"], str) or not _HEX64_RE.fullmatch(data["payload_hash"]):
        raise _Denied("E_AUTH_BAD_TICKET", "ticket.payload_hash 非法")
    if not isinstance(data["nonce"], str) or not _TOKEN_RE.fullmatch(data["nonce"]):
        raise _Denied("E_AUTH_BAD_TICKET", "ticket.nonce 非法")
    try:
        _parse_ts(data["ts"])
    except (TypeError, ValueError) as exc:
        raise _Denied("E_AUTH_BAD_TICKET", "ticket.ts 非法: " + str(exc))
    expected_path = ticket_path(data["nonce"], root)
    file_data = _read_secure_json(expected_path)
    for key in ("action", "payload_hash", "nonce", "ts"):
        if file_data.get(key) != data.get(key):
            raise _Denied("E_AUTH_BAD_TICKET", "传入 ticket 与磁盘票据不一致: " + key)
    return {
        "ticket": {k: file_data[k] for k in ("action", "payload_hash", "nonce", "ts")},
        "file_data": file_data,
        "ticket_path": expected_path,
    }


def _check_not_consumed(loaded: Dict[str, Any], task: Optional[str],
                        root: Optional[Any] = None) -> None:
    nonce = loaded["ticket"]["nonce"]
    action = loaded["ticket"]["action"]
    if ok_path(nonce, root).exists():
        raise _Denied("E_AUTH_REUSED", "同 nonce 已消费")
    if payload_ok_path(action, loaded["ticket"]["payload_hash"], root).exists():
        raise _Denied("E_AUTH_REUSED", "同 action + payload 已成功消费过")
    effective_task = task if task is not None else loaded["file_data"].get("task")
    if effective_task is not None:
        if not isinstance(effective_task, str) or not _TOKEN_RE.fullmatch(effective_task):
            raise _Denied("E_AUTH_BAD_TICKET", "task 非法")
        action = loaded["ticket"]["action"]
        if task_ok_path(action, effective_task, root).exists():
            raise _Denied("E_AUTH_REUSED", "同 action + task 已成功消费过")


def verify(ticket: Any, payload: Any, *, task: Optional[str] = None,
           root: Optional[Any] = None) -> Dict[str, Any]:
    _require_startup_ack()
    try:
        loaded = _load_ticket(ticket, root)
    except _Denied as exc:
        return _fail(exc.code, exc.reason)
    try:
        payload_hash = canonical_hash(payload)
    except (TypeError, ValueError) as exc:
        return _fail("E_AUTH_BAD_PAYLOAD", "payload 无法 canonical 化: " + str(exc))
    if not hmac.compare_digest(loaded["ticket"]["payload_hash"], payload_hash):
        return _fail("E_AUTH_PAYLOAD_MISMATCH",
                     "ticket.payload_hash 与本次 payload 不一致")
    try:
        _check_not_consumed(loaded, task, root)
    except _Denied as exc:
        return _fail(exc.code, exc.reason)
    return {
        "ok": True,
        "code": None,
        "reason": "",
        "ticket": loaded["ticket"],
        "file_data": loaded["file_data"],
        "ticket_path": str(loaded["ticket_path"]),
        "payload_hash": payload_hash,
        "task": task if task is not None else loaded["file_data"].get("task"),
        "quote": loaded["file_data"].get("quote", ""),
        "action": loaded["ticket"]["action"],
    }


def begin(ticket: Any, payload: Any, *, task: Optional[str] = None,
          root: Optional[Any] = None, expected_quote: Optional[str] = None) -> Dict[str, Any]:
    verified = verify(ticket, payload, task=task, root=root)
    if not verified["ok"]:
        return verified
    if expected_quote is not None and verified.get("quote") != expected_quote:
        return _fail("E_AUTH_QUOTE_MISMATCH", "票据原话与审批不一致")
    nonce = verified["ticket"]["nonce"]
    action = verified["action"]
    task = verified["task"]
    payload_hash = verified["payload_hash"]
    nonce_lock = lock_path(nonce, root)
    task_lock = None
    if task is not None:
        task_lock = task_lock_path(action, task, root)
        try:
            _write_new(task_lock, {
                "nonce": nonce,
                "action": action,
                "task": task,
                "ts": _now_iso(),
            })
        except FileExistsError:
            return _fail("E_AUTH_REUSED",
                         "同 action + task 正在消费（task lock 已存在）")
        except OSError as exc:
            return _fail("E_AUTH_IO", "task lock 创建失败: " + str(exc))
    payload_lock = payload_lock_path(action, payload_hash, root)
    try:
        _write_new(payload_lock, {
            "nonce": nonce,
            "action": action,
            "payload_hash": payload_hash,
            "ts": _now_iso(),
        })
    except FileExistsError:
        _unlink_quietly(task_lock)
        return _fail("E_AUTH_REUSED",
                     "同 action + payload 正在消费（payload lock 已存在）")
    except OSError as exc:
        _unlink_quietly(task_lock)
        return _fail("E_AUTH_IO", "payload lock 创建失败: " + str(exc))
    try:
        _write_new(nonce_lock, {
            "nonce": nonce,
            "action": action,
            "task": task,
            "ts": _now_iso(),
        })
    except FileExistsError:
        _unlink_quietly(task_lock)
        _unlink_quietly(payload_lock)
        return _fail("E_AUTH_REUSED", "同 nonce 正在消费或已消费（lock 已存在）")
    except OSError as exc:
        _unlink_quietly(task_lock)
        _unlink_quietly(payload_lock)
        return _fail("E_AUTH_IO", "lock 创建失败: " + str(exc))
    return {
        "ok": True,
        "code": None,
        "reason": "",
        "ticket": verified["ticket"],
        "ticket_path": verified["ticket_path"],
        "lock_path": str(nonce_lock),
        "task_lock_path": str(task_lock) if task_lock is not None else None,
        "payload_lock_path": str(payload_lock),
        "root": root,
        "nonce": nonce,
        "action": action,
        "task": task,
        "quote": verified.get("quote", ""),
        "payload_hash": payload_hash,
    }


def commit(handle: Dict[str, Any]) -> Dict[str, Any]:
    if not handle or not handle.get("ok"):
        return handle or _fail("E_AUTH_BAD_TICKET", "无效 handle")
    nonce = handle["nonce"]
    action = handle["action"]
    task = handle.get("task")
    lock = Path(handle["lock_path"])
    task_lock = (Path(handle["task_lock_path"])
                 if handle.get("task_lock_path") else None)
    payload_hash = handle.get("payload_hash")
    payload_lock = (Path(handle["payload_lock_path"])
                    if handle.get("payload_lock_path") else None)
    if not lock.exists():
        return _fail("E_AUTH_LOCK_LOST", "lock 已不存在，拒绝提交")
    root = handle.get("root")
    ok = ok_path(nonce, root)
    try:
        _write_new(ok, {"nonce": nonce, "action": action, "task": task,
                        "ts": _now_iso()})
    except FileExistsError:
        _unlink_quietly(lock)
        _unlink_quietly(task_lock)
        _unlink_quietly(payload_lock)
        return _fail("E_AUTH_REUSED", "同 nonce 已消费")
    except OSError as exc:
        _unlink_quietly(task_lock)
        _unlink_quietly(payload_lock)
        return _fail("E_AUTH_IO", "ok 创建失败: " + str(exc))
    payload_ok = None
    if payload_hash:
        payload_ok = payload_ok_path(action, payload_hash, root)
        try:
            _write_new(payload_ok, {"nonce": nonce, "action": action,
                                    "payload_hash": payload_hash,
                                    "ts": _now_iso()})
        except FileExistsError:
            _unlink_quietly(lock)
            _unlink_quietly(task_lock)
            _unlink_quietly(payload_lock)
            return _fail("E_AUTH_REUSED", "同 action + payload 已成功消费过")
        except OSError as exc:
            _unlink_quietly(lock)
            _unlink_quietly(task_lock)
            _unlink_quietly(payload_lock)
            return _fail("E_AUTH_IO", "payload ok 创建失败: " + str(exc))
    task_ok = None
    if task is not None:
        task_ok = task_ok_path(action, task, root)
        try:
            _write_new(task_ok, {"nonce": nonce, "action": action, "task": task,
                                 "ts": _now_iso()})
        except FileExistsError:
            _unlink_quietly(lock)
            _unlink_quietly(task_lock)
            _unlink_quietly(payload_lock)
            return _fail("E_AUTH_REUSED", "同 action + task 已成功消费过")
        except OSError as exc:
            _unlink_quietly(lock)
            _unlink_quietly(task_lock)
            _unlink_quietly(payload_lock)
            return _fail("E_AUTH_IO", "task ok 创建失败: " + str(exc))
    _unlink_quietly(lock)
    _unlink_quietly(task_lock)
    _unlink_quietly(payload_lock)
    if lock.exists():
        return _fail("E_AUTH_IO", "lock 删除失败")
    return {
        "ok": True,
        "code": None,
        "reason": "",
        "nonce": nonce,
        "action": action,
        "task": task,
        "ok_path": str(ok),
        "task_ok_path": str(task_ok) if task_ok is not None else None,
        "payload_ok_path": str(payload_ok) if payload_ok is not None else None,
    }


def abort(handle: Dict[str, Any], reason: str = "E_HTTP_FAILED") -> Dict[str, Any]:
    if not handle:
        return _fail("E_HTTP_FAILED", reason)
    root = handle.get("root")
    _unlink_quietly(Path(handle["lock_path"]) if handle.get("lock_path") else None)
    _unlink_quietly(Path(handle["task_lock_path"])
                    if handle.get("task_lock_path") else None)
    _unlink_quietly(Path(handle["payload_lock_path"])
                    if handle.get("payload_lock_path") else None)
    try:
        _append_log(handle.get("action"), handle.get("quote", ""), False,
                    "E_HTTP_FAILED: " + str(reason), root)
    except OSError:
        pass
    return {
        "ok": False,
        "code": "E_HTTP_FAILED",
        "reason": str(reason),
        "nonce": handle.get("nonce"),
        "action": handle.get("action"),
    }


def consume(ticket: Any, payload: Any, *, task: Optional[str] = None,
            root: Optional[Any] = None) -> Dict[str, Any]:
    _require_startup_ack()
    handle = begin(ticket, payload, task=task, root=root)
    if not handle["ok"]:
        return handle
    handle["root"] = root
    return commit(handle)


def hold_unknown(handle: Dict[str, Any], reason: str = "E_SAVE_UNCERTAIN") -> Dict[str, Any]:
    """Guard V2：save 提交后结果不明时保留全部锁（nonce/task/payload），不删不写 ok。

    只为 S5 save 路径调用；与 abort（删锁允许重试）语义相反——已开始 HTTP 的
    占用不得因异常被清。返回的 handle 供调用方继续对账；不改变非 save 路径。
    """
    if not handle or not handle.get("ok"):
        return _fail("E_SAVE_UNCERTAIN", "无效 handle，无法标记 unknown")
    if handle.get("action") not in (None, "save"):
        return _fail("E_SAVE_UNCERTAIN",
                     "hold_unknown 仅用于 save（收到 %r）" % handle.get("action"))
    root = handle.get("root")
    try:
        _append_log(handle.get("action"), handle.get("quote", ""), False,
                    "E_SAVE_UNCERTAIN: " + str(reason), root)
    except OSError:
        pass
    held = dict(handle)
    held["held_unknown"] = True
    held["held_reason"] = str(reason)[:500]
    return {"ok": False, "code": "E_SAVE_UNCERTAIN", "reason": str(reason)[:500],
            "handle": held}


def authorize_save_plan(action: Any, quote: Any, payload: Any, *,
                        plan: Any = None, task: Optional[str] = None,
                        fields: Any = None, root: Optional[Any] = None) -> Dict[str, Any]:
    """Guard V2：save 的唯一 authorize 入口（仅 confirm 流程调用铸票）。

    与裸 authorize 的区别：必须携带 confirmed plan（含 wire_payload_sha256 与
    dependency_sha256），quote 数量须与 plan selectTotal 一致；缺 plan / plan 未
    confirmed / payload 与 plan wire 不一致 / 原话数量不一致均拒绝。非 save 动作
    不经过本函数。票据结构与 authorize 完全一致，供 verify/begin/commit 复用。
    """
    if action != "save":
        return _deny(action, quote, "E_AUTH_ACTION_MISMATCH",
                     "authorize_save_plan 仅接受 action=save", root)
    if not isinstance(plan, dict):
        return _deny(action, quote, "E_PLAN_REQUIRED",
                     "S5 保存必须携带已确认 plan（confirm 流程产出）", root)
    if plan.get("status") != "confirmed":
        return _deny(action, quote, "E_PLAN_NOT_CONFIRMED",
                     "plan 未经 confirm 确认", root)
    if not isinstance(quote, str) or quote != plan.get("quote"):
        return _deny(action, quote, "E_AUTH_QUOTE_MISMATCH", "原话与已确认保存计划不一致", root)
    from approval import authorize_quote
    if not authorize_quote(quote, "S5", {"count": payload.get("selectTotal") if isinstance(payload, dict) else None}):
        from rule_check import extract_save_count
        requested = extract_save_count(quote)
        if requested is not None and isinstance(payload, dict) and requested != payload.get("selectTotal"):
            return _deny(action, quote, "E_AUTH_COUNT_MISMATCH", "原话数量与当前卡不一致", root)
        return _deny(action, quote, "E_AUTH_QUOTE_MISMATCH", "原话不是当前卡的整句确认", root)
    wire = plan.get("wire_payload")
    if not isinstance(wire, dict):
        return _deny(action, quote, "E_PLAN_PAYLOAD_MISMATCH",
                     "plan 缺 wire_payload", root)
    if canonical_hash(wire) != canonical_hash(payload):
        return _deny(action, quote, "E_PLAN_PAYLOAD_MISMATCH",
                     "payload 与 plan.wire_payload 不一致", root)
    if plan.get("wire_payload_sha256") and plan["wire_payload_sha256"] != canonical_hash(payload):
        return _deny(action, quote, "E_PLAN_PAYLOAD_MISMATCH",
                     "plan.wire_payload_sha256 与 payload 不一致", root)
    select_total = payload.get("selectTotal") if isinstance(payload, dict) else None
    if type(select_total) is not int or select_total <= 0:
        return _deny(action, quote, "E_SELECT_TOTAL_INVALID",
                     "payload selectTotal 必须严格正 int", root)
    count = payload.get("count") if isinstance(payload, dict) else None
    if count is not None and (type(count) is not int or count != select_total):
        return _deny(action, quote, "E_COUNT_MISMATCH",
                     "count=%r 与 selectTotal=%r 不一致" % (count, select_total), root)
    from rule_check import extract_save_count, is_plain_save_confirm  # noqa: WPS433 - 延迟导入避免环
    quoted_count = extract_save_count(quote)
    # AC1（2026-10-27）：S5 当前展示计划上下文里，纯 ASCII 正整数字符串 N
    # 也是数量授权（用户明确允许只回数字）；只在 confirmed plan 自带卡面
    # 绑定（confirm_plan 已验卡）时成立，裸数字仍拒。
    numeric_n = None
    if isinstance(quote, str) and re.fullmatch(r"[1-9][0-9]*", quote.strip()):
        numeric_n = int(quote.strip())
    card_bound = (plan.get("count_bound_by") == "card"
                  and plan.get("count_bound_n") == select_total)
    if quoted_count is None and numeric_n is None:
        # v3（2026-10-27）：卡面已写清 N 家、用户只回「确认」时，
        # confirmed plan 必须自带卡面绑定，才放行。
        plain_bound = card_bound and is_plain_save_confirm(quote)
        # B2：数量歧义/缺失默认拒；例外=卡面绑定，或代词+render.fields 明确对象。
        if not plain_bound and not (_has_pronoun(quote) and _fields_have_object(fields)):
            return _deny(action, quote, "E_AUTH_COUNT_AMBIGUOUS",
                         "原话未给出可确定的公司数（歧义/缺失），须明确 N 家或给明确对象",
                         root)
        card_bound = plain_bound
    elif quoted_count is not None and numeric_n is not None and quoted_count != numeric_n:
        return _deny(action, quote, "E_AUTH_COUNT_MISMATCH",
                     "原话同时含带单位数量与裸数字且不一致：%d vs %d" % (quoted_count, numeric_n),
                     root)
    elif numeric_n is not None and numeric_n != select_total:
        return _deny(action, quote, "E_AUTH_COUNT_MISMATCH",
                     "原话 %d 家与 plan selectTotal=%d 不一致" % (numeric_n, select_total),
                     root)
    elif quoted_count is not None and numeric_n is None and quoted_count != select_total:
        return _deny(action, quote, "E_AUTH_COUNT_MISMATCH",
                     "原话 %d 家与 plan selectTotal=%d 不一致" % (quoted_count, select_total),
                     root)
    return authorize(action, quote, payload, task=task, fields=fields,
                     plan=plan, root=root, action_verified=card_bound)


def check(action: Any, quote: Any, payload: Any, *, task: Optional[str] = None,
          fields: Any = None, root: Optional[Any] = None,
          plan: Any = None) -> Dict[str, Any]:
    issued = authorize(action, quote, payload, task=task, fields=fields,
                       plan=plan, root=root)
    if not issued["ok"]:
        return issued
    result = consume(issued["ticket"], payload, task=task, root=root)
    if result.get("ok"):
        result["ticket"] = issued["ticket"]
    return result


def bundle_plan_hash(doc: Dict[str, Any]) -> str:
    """联合计划 hash：覆盖项目/org/S9配置/S10批次/依赖文件 hash。"""
    return canonical_hash({k: doc.get(k) for k in ("project", "org_sha256", "s9", "s10", "deps")})


def authorize_bundle_contact(bundle: Dict[str, Any], payload: Dict[str, Any], *,
                             root: Optional[Any] = None) -> Dict[str, Any]:
    """联合确认下的 S10 加人票据：不接受调用者自报 bool，全部在内部对 bundle 验证后才调用 authorize。

    验证：计划 hash 未变；确认记录存在且卡文件 sha 与确认时一致；建序列机器回执与计划一致且已回读 inactive；
    payload 恰为 {seqId=回执seq, tags=计划唯一标签, views=[]}。动作固定 sequence，不涉及激活/S12。
    """
    def deny(why: str) -> Dict[str, Any]:
        return _fail("E_BUNDLE_DENIED", why)
    if not isinstance(bundle, dict) or bundle.get("status") not in ("confirmed", "partial"):
        return deny("联合计划未确认")
    if bundle.get("plan_hash") != bundle_plan_hash(bundle):
        return deny("联合计划已被改动")
    conf = bundle.get("confirmation") or {}
    card = Path(str(conf.get("card_path") or ""))
    try:
        card_sha = hashlib.sha256(card.read_bytes()).hexdigest()
        card_doc = json.loads(card.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return deny("确认卡缺失")
    if card_sha != conf.get("card_sha256") or card_doc.get("plan_hash") != bundle["plan_hash"]:
        return deny("确认卡与联合计划不符")
    quote = conf.get("quote")
    import approval
    s9 = bundle.get("s9") or {}
    binding = {"project": bundle.get("project"), "org_sha256": bundle.get("org_sha256"),
               "name": s9.get("name"), "from_name": s9.get("from_name"),
               "profile": s9.get("profile"), "tmap": {"sha256": s9.get("tmap_sha256")}, "rules": s9.get("rules")}
    row = approval.find_approval(bundle.get("s9_approval"), bundle.get("project"), ("S9",),
                                 expected_hash=approval.stable_params_hash(binding))
    if not row or row.get("user_quote") != quote or not approval.authorize_quote(quote, "S9", {}):
        return deny("确认原话与S9审批不一致")
    rc = bundle.get("receipt") or {}
    steps = bundle.get("steps") or {}
    seq = steps.get("seq_id")
    if not seq or rc.get("seq_id") != seq or rc.get("plan_hash") != bundle["plan_hash"] or rc.get("readback_status") != "inactive":
        return deny("建序列回执/回读与计划不符")
    s10 = bundle.get("s10") or {}
    if payload != {"seqId": seq, "tags": s10.get("tags"), "views": []}:
        return deny("加人参数与联合计划不符")
    return authorize("sequence", quote, payload, root=root, action_verified=True)


def release_bundle_payload_after_zero(bundle: Dict[str, Any], payload: Dict[str, Any], *,
                                      root: Optional[Any] = None) -> Dict[str, Any]:
    """仅当联合计划记录了"平台回读本序列联系人数=0"的证据时，释放该 payload 的已消费标记，
    允许为同一 binding 重新铸一张精确新票。其余情况（含不确定）一律拒绝。"""
    if not isinstance(bundle, dict) or bundle.get("kind") != "sequence_contact_bundle":
        return _fail("E_BUNDLE_DENIED", "不是联合计划")
    if bundle.get("plan_hash") != bundle_plan_hash(bundle):
        return _fail("E_BUNDLE_DENIED", "联合计划已被改动")
    steps = bundle.get("steps") or {}
    seq = steps.get("seq_id"); rb = steps.get("contact_readback") or {}
    rc = steps.get("contact_receipt") or {}
    if bundle.get("status") != "partial":
        return _fail("E_BUNDLE_DENIED", "联合计划不是部分完成态")
    if steps.get("contact") == "done":
        return _fail("E_BUNDLE_DENIED", "加人已完成，无需续发")
    # ★只允许"写前被拒"(rejected 且从无 sending 阶段)的零写路径；发送后结果不确定(sending)绝不释放
    if steps.get("contact_state") != "rejected" or rc.get("phase") == "sending":
        return _fail("E_BUNDLE_DENIED", "上次加人非写前被拒（发送后结果不确定），不得仅凭回读释放重放")
    if not seq or rb.get("seq") != seq or rb.get("count") != 0:
        return _fail("E_BUNDLE_DENIED", "没有该序列联系人数为0的回读证据，不得续发")
    if (bundle.get("receipt") or {}).get("seq_id") != seq:
        return _fail("E_BUNDLE_DENIED", "序列身份与建序列回执不符")
    if payload != {"seqId": seq, "tags": (bundle.get("s10") or {}).get("tags"), "views": []}:
        return _fail("E_BUNDLE_DENIED", "加人参数与联合计划不符")
    _unlink_quietly(payload_ok_path("sequence", canonical_hash(payload), root))
    return {"ok": True, "code": None, "reason": "released after zero-write rejection readback"}


def _load_json_arg(json_text: Optional[str], file_path: Optional[str],
                   default: Any = None) -> Any:
    if json_text is not None and file_path is not None:
        raise ValueError("--json 与 --file 只能二选一")
    if file_path is not None:
        return json.loads(Path(file_path).read_text(encoding="utf-8"))
    if json_text is not None:
        return json.loads(json_text)
    return default


def _exit_code(result: Dict[str, Any]) -> int:
    return 3 if result.get("code") == "E_AUTH_REUSED" else 2


def _print_deny(result: Dict[str, Any]) -> None:
    print("DENY " + str(result.get("code")) + ": " + str(result.get("reason")),
          file=sys.stderr)


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="auth 授权票据（v3）")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("authorize")
    p.add_argument("--action", required=True)
    p.add_argument("--quote", required=True)
    p.add_argument("--payload-json", default=None)
    p.add_argument("--payload-file", default=None)
    p.add_argument("--task", default=None)
    p.add_argument("--fields-json", default=None)
    p.add_argument("--fields-file", default=None)
    p.add_argument("--plan-json", default=None)
    p.add_argument("--plan-file", default=None)
    p.add_argument("--root", default=None)

    c = sub.add_parser("consume")
    c.add_argument("--ticket-json", default=None)
    c.add_argument("--ticket-file", default=None)
    c.add_argument("--payload-json", default=None)
    c.add_argument("--payload-file", default=None)
    c.add_argument("--task", default=None)
    c.add_argument("--root", default=None)

    k = sub.add_parser("check")
    k.add_argument("--action", required=True)
    k.add_argument("--quote", required=True)
    k.add_argument("--payload-json", default=None)
    k.add_argument("--payload-file", default=None)
    k.add_argument("--task", default=None)
    k.add_argument("--fields-json", default=None)
    k.add_argument("--fields-file", default=None)
    k.add_argument("--plan-json", default=None)
    k.add_argument("--plan-file", default=None)
    k.add_argument("--root", default=None)

    args = parser.parse_args(argv)
    try:
        payload = _load_json_arg(args.payload_json, args.payload_file, default={})
    except Exception as exc:
        print("DENY E_AUTH_BAD_PAYLOAD: " + str(exc), file=sys.stderr)
        return 2
    if args.command == "authorize":
        try:
            fields = _load_json_arg(args.fields_json, args.fields_file, default=None)
            plan = _load_json_arg(args.plan_json, args.plan_file, default=None)
        except Exception as exc:
            print("DENY E_AUTH_BAD_TICKET: " + str(exc), file=sys.stderr)
            return 2
        result = authorize(args.action, args.quote, payload, task=args.task,
                           fields=fields, plan=plan, root=args.root)
        if result["ok"]:
            print(json.dumps(result["ticket"], ensure_ascii=False, sort_keys=True))
            return 0
        _print_deny(result)
        return _exit_code(result)
    if args.command == "consume":
        try:
            ticket = _load_json_arg(args.ticket_json, args.ticket_file, default=None)
        except Exception as exc:
            print("DENY E_AUTH_BAD_TICKET: " + str(exc), file=sys.stderr)
            return 2
        if ticket is None:
            print("DENY E_AUTH_BAD_TICKET: 缺少 --ticket-json/--ticket-file",
                  file=sys.stderr)
            return 2
        result = consume(ticket, payload, task=args.task, root=args.root)
        if result["ok"]:
            print("OK nonce=" + result["nonce"])
            return 0
        _print_deny(result)
        return _exit_code(result)
    if args.command == "check":
        try:
            fields = _load_json_arg(args.fields_json, args.fields_file, default=None)
            plan = _load_json_arg(args.plan_json, args.plan_file, default=None)
        except Exception as exc:
            print("DENY E_AUTH_BAD_TICKET: " + str(exc), file=sys.stderr)
            return 2
        result = check(args.action, args.quote, payload, task=args.task,
                       fields=fields, plan=plan, root=args.root)
        if result["ok"]:
            print("OK nonce=" + result["nonce"])
            return 0
        _print_deny(result)
        return _exit_code(result)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
