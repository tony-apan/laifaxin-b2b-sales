#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""保存预算自动校准（Auto-Cal v11 定稿口径）。

任务书：.tasks/GUARD-AUTOCAL-SPEC.md（本机 SHA 60432de7…）。
核心口径：
  预算账 spent_all  = Σ 全部 settled(carry) 批次 batch_cost（含 unprovable）
  校准账 spent_calib = Σ settled 且 external_risk=confirmed 的干净批次
  per_company_est = spent_calib/companies_calib（>0 才可用）
  per_company_upper = max(干净批次 batch_cost/companies_saved)
  budget_left = B_plan − spent_all
  N_cons = floor(budget_left/per_company_upper)  ← 用户确认不得超过
  N_est  = floor(budget_left/per_company_est)
  停止：budget_left < per_company_upper×1 → E_BUDGET_EXHAUSTED

账簿 kind 固定 7 个：probe/sample_ack/batch_begin/settle/carry/plan/audit_clear；
org_hash = sha256(orgId)[:16]；必需字段 at/org_hash/project/kind/batch_id/
state/source_ref/late/external_risk/sample_ack_at；同 batch_id 重复
batch_begin 或 settle 无 begin → E_LEDGER_REPLAY（禁止覆盖）。
余额口径：优先只读 `account/current.creditCount`（通用点数，可花），
probe 账簿写明 source=<endpoint.field>；不可用才降级 `benefits/refine-data`
的查看配额（monthlyLimit/monthlyUsed，source_kind=view_quota）——查看配额不是
保存点数，plan 在无显式预算时对非点数来源 fail-closed，禁止拿配额推导预算。
本模块不发保存请求（无 write 端点）。
"""
from __future__ import annotations

def _utf8_stdout():
    """Windows 控制台/管道默认 GBK：输出 emoji 会抛 UnicodeEncodeError；显式改 UTF-8。"""
    import sys as _sys
    for _s in (_sys.stdout, _sys.stderr):
        try:
            _s.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
_utf8_stdout()

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from decimal import Decimal, ROUND_CEILING, ROUND_FLOOR, ROUND_HALF_UP
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib import request as _urlrequest

TOOLS_DIR = Path(__file__).resolve().parent
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

import api_base_url  # noqa: E402

SCHEMA_VERSION = 2
BALANCE_STALE_SECONDS = 10 * 60
DEFAULT_BUDGET_RATIO = "0.5"
SUGGEST_MAX_POINTS = 20000
SIX = Decimal("0.000001")
BOOTSTRAP_N0 = 20
BOOTSTRAP_BUDGET_FLOOR = 20
POINTS_ENDPOINT = "account/current"
POINTS_FIELD = "creditCount"
POINTS_SOURCE = "account/current.creditCount"
POINTS_SOURCE_KIND = "points"
QUOTA_ENDPOINT = "benefits/refine-data"
QUOTA_SOURCE = "benefits/refine-data.monthlyLimit-monthlyUsed"
QUOTA_SOURCE_KIND = "view_quota"
ALLOWED_ENDPOINTS = (POINTS_ENDPOINT, QUOTA_ENDPOINT,
                     "operation/backend-task-status")
LEDGER_REL = Path(".local") / "budget-ledger.jsonl"
LOCK_REL = Path(".local") / "budget.lock"
ALLOWED_KINDS = ("probe", "sample_ack", "batch_begin", "settle", "carry",
                 "plan", "audit_clear")
_CREDENTIAL_KEYS = {"token", "accesstoken", "access_token", "authorization",
                    "credential", "credentials", "secret", "password",
                    "cookie", "set-cookie"}


class BudgetError(ValueError):
    def __init__(self, code: str, reason: str, **extra: Any):
        super().__init__(reason)
        self.code = code
        self.reason = reason
        self.extra = extra


def _fail(code: str, reason: str, **extra: Any) -> None:
    raise BudgetError(code, reason, **extra)


def _now(value: Optional[Any] = None) -> datetime:
    if value is None:
        return datetime.now(timezone.utc)
    if isinstance(value, datetime):
        return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)
    if isinstance(value, str):
        text = value.strip()
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        dt = datetime.fromisoformat(text)
        return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)
    raise BudgetError("E_BALANCE_UNAVAILABLE", "now 非法")


def _iso(value: Optional[Any] = None) -> str:
    return _now(value).replace(microsecond=0).isoformat()


def org_hash(org: Any) -> str:
    """固定算法：sha256(orgId)[:16]。"""
    return hashlib.sha256(str(org).encode("utf-8")).hexdigest()[:16]


def token_fp(token: Any) -> str:
    """仅内存内比较；不写账簿。"""
    return hashlib.sha256(str(token).encode("utf-8")).hexdigest()[:16]


def _six(value: Decimal) -> str:
    return str(value.quantize(SIX, rounding=ROUND_HALF_UP))


def _floor(value: Decimal) -> int:
    return int(value.to_integral_value(rounding=ROUND_FLOOR))


def _ceil(value: Decimal) -> int:
    return int(value.to_integral_value(rounding=ROUND_CEILING))


# ---------------------------------------------------------------------------
# 账簿
# ---------------------------------------------------------------------------

def _sanitize(value: Any) -> Any:
    if isinstance(value, dict):
        out = {}
        for key, item in value.items():
            if str(key).strip().lower() in _CREDENTIAL_KEYS:
                out[key] = "[REDACTED]"
            else:
                out[key] = _sanitize(item)
        return out
    if isinstance(value, list):
        return [_sanitize(item) for item in value]
    if isinstance(value, str) and value.count("&") == 2 and len(value) > 20:
        return "[REDACTED]"
    return value


def append_ledger(root: Path, *, org_hash: str, project: str, kind: str,
                  payload: Dict[str, Any], source_ref: str,
                  batch_id: str = "", state: str = "", late: Any = None,
                  external_risk: str = "",
                  sample_ack_at: str = "", round_id: str = "") -> Dict[str, Any]:
    if kind not in ALLOWED_KINDS:
        _fail("E_BAD_INPUT", "kind 不在固定枚举: %r" % kind)
    if not round_id:
        for row in reversed(read_ledger(Path(root), project)):
            if (row.get("kind") == "plan"
                    and row.get("state") == "round_open"):
                round_id = str((row.get("payload") or {}).get("round_id") or "")
                break
    record = {
        "schema_version": SCHEMA_VERSION,
        "at": _iso(),
        "org_hash": org_hash,
        "project": str(project),
        "kind": str(kind),
        "batch_id": str(batch_id or ""),
        "state": str(state or ""),
        "source_ref": str(source_ref),
        "late": None if late is None else str(late),
        "external_risk": str(external_risk or ""),
        "sample_ack_at": str(sample_ack_at or ""),
        "round_id": str(round_id or ""),
        "payload": _sanitize(payload),
    }
    directory = Path(root) / ".local"
    directory.mkdir(parents=True, exist_ok=True)
    path = Path(root) / LEDGER_REL
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True,
                                separators=(",", ":")) + "\n")
    try:
        path.chmod(0o600)
    except OSError:
        pass
    return record


def read_ledger(root: Path, project: Optional[str] = None) -> List[Dict[str, Any]]:
    path = Path(root) / LEDGER_REL
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if project is None or row.get("project") == project:
            rows.append(row)
    return rows


STALE_LOCK_SECONDS = 2 * 3600


def acquire_round_lock(root: Path):
    """轮次互斥（O_EXCL）：陈旧 >2h 可接管并记审计；否则 E_ROUND_CONFLICT。"""
    import os as _os
    import secrets as _secrets
    import time as _time
    path = Path(root) / LOCK_REL
    path.parent.mkdir(parents=True, exist_ok=True)
    owner = "lock-" + _secrets.token_hex(8)
    flags = _os.O_WRONLY | _os.O_CREAT | _os.O_EXCL | getattr(_os, "O_NOFOLLOW", 0)
    try:
        fd = _os.open(str(path), flags, 0o600)
    except FileExistsError:
        age = _time.time() - path.stat().st_mtime
        if age <= STALE_LOCK_SECONDS:
            _fail("E_ROUND_CONFLICT", "已存在 budget.lock（另一轮正在运行）")
        old = ""
        try:
            old = path.read_text(encoding="utf-8", errors="replace")[:64]
        except OSError:
            old = "(unreadable)"
        try:
            path.unlink()
        except OSError as exc:
            _fail("E_ROUND_CONFLICT", "陈旧锁清理失败: %s" % exc)
        project_guess = ""
        try:
            project_guess = str(root.name)
        except Exception:
            project_guess = ""
        try:
            last_probe = [r for r in read_ledger(Path(root))
                          if r.get("kind") == "probe"][-1]
            stale_project = last_probe.get("project") or project_guess
            stale_org = last_probe.get("org_hash") or ""
        except Exception:
            stale_project, stale_org = project_guess, ""
        append_ledger(Path(root), org_hash=stale_org, project=stale_project,
                      kind="plan", source_ref="lock_audit",
                      state="lock_stale_cleared",
                      payload={"old_owner": old, "age_seconds": int(age)})
        try:
            fd = _os.open(str(path), flags, 0o600)
        except FileExistsError:
            _fail("E_ROUND_CONFLICT", "陈旧锁被他人抢先接管")
    try:
        _os.write(fd, owner.encode("utf-8"))
    finally:
        _os.close(fd)
    return {"path": str(path), "owner": owner}


def release_round_lock(handle) -> None:
    """仅 owner 可释放；他人锁拒绝删除并报 E_LOCK_OWNER_MISMATCH。"""
    try:
        path = Path(handle["path"])
        owner = str(handle.get("owner") or "")
    except (KeyError, TypeError):
        return
    if not path.exists():
        return
    try:
        current = path.read_text(encoding="utf-8", errors="replace").strip()
    except OSError:
        return
    if current != owner:
        _fail("E_LOCK_OWNER_MISMATCH",
              "锁已属于他人（当前=%r），拒绝删除" % current[:32])
    try:
        path.unlink()
    except OSError:
        pass


def _release_quiet(handle) -> None:
    try:
        release_round_lock(handle)
    except BudgetError:
        pass


# ---------------------------------------------------------------------------
# 余额
# ---------------------------------------------------------------------------

def _int_field(data: Dict[str, Any], key: str) -> int:
    value = data.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        _fail("E_BALANCE_UNAVAILABLE", "余额字段缺失或非整数: %s" % key)
    return value


def _is_points_source(source: Any) -> bool:
    """来源是否为「通用点数」余额（可当保存预算基数）。"""
    text = str(source or "")
    return text == POINTS_SOURCE or text.startswith(POINTS_ENDPOINT + ".")


def _read_points_balance(http: Any) -> tuple:
    """只读 account/current.creditCount；不可用返回 (None, 原因)。"""
    try:
        response = http(POINTS_ENDPOINT, {})
    except Exception as exc:  # 端点不可用 → 降级查看配额（plan 会 fail-closed）
        return None, "请求失败(%s)" % type(exc).__name__
    if not isinstance(response, dict) or response.get("success") is not True:
        return None, "接口未返回成功"
    data = response.get("data")
    if not isinstance(data, dict):
        return None, "缺 data"
    value = data.get(POINTS_FIELD)
    if isinstance(value, bool) or not isinstance(value, int):
        return None, "%s 缺失或非整数" % POINTS_FIELD
    if value < 0:
        return None, "%s 为负" % POINTS_FIELD
    return value, ""


def read_balance(http: Any, *, token: str, org: str,
                 now: Optional[Any] = None) -> Dict[str, Any]:
    """余额快照：优先通用点数（可花），不可用才降级查看配额（非保存点数）。

    source 固定写明 `<endpoint>.<field>`：account/current.creditCount 或
    benefits/refine-data.monthlyLimit-monthlyUsed；后者 source_kind=view_quota，
    plan 在无显式预算时对非点数来源 fail-closed，禁止拿查看配额当保存点数。
    """
    points, reason = _read_points_balance(http)
    if points is not None:
        return {
            "schema_version": SCHEMA_VERSION,
            "source": POINTS_SOURCE,
            "source_kind": POINTS_SOURCE_KIND,
            "points": points,
            "b_avail": str(Decimal(points)),
            "read_at": _iso(now),
            "org_hash": org_hash(org),
            "token_fp": token_fp(token),
        }
    response = http(QUOTA_ENDPOINT, {})
    if not isinstance(response, dict) or response.get("success") is not True:
        _fail("E_BALANCE_UNAVAILABLE",
              "通用点数不可用（%s），查看配额接口也未返回成功" % reason)
    data = response.get("data")
    if not isinstance(data, dict):
        _fail("E_BALANCE_UNAVAILABLE",
              "通用点数不可用（%s），查看配额接口缺 data" % reason)
    limit = _int_field(data, "monthlyLimit")
    used = _int_field(data, "monthlyUsed")
    if limit <= 0:
        _fail("E_BALANCE_UNAVAILABLE", "monthlyLimit<=0，无法确定查看配额")
    if used < 0:
        _fail("E_BALANCE_UNAVAILABLE", "monthlyUsed<0，查看配额口径异常")
    if used > limit:
        _fail("E_BALANCE_OVER_LIMIT",
              "monthlyUsed=%s > monthlyLimit=%s（查看配额超额/统计越界）"
              % (used, limit))
    return {
        "schema_version": SCHEMA_VERSION,
        "source": QUOTA_SOURCE,
        "source_kind": QUOTA_SOURCE_KIND,
        "points_fallback_reason": reason,
        "monthly_limit": limit,
        "monthly_used": used,
        "b_avail": str(Decimal(limit - used)),
        "read_at": _iso(now),
        "org_hash": org_hash(org),
        "token_fp": token_fp(token),
    }


def make_http(token: str, org: str, timeout: int = 60) -> Any:
    def call(endpoint: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        if endpoint not in ALLOWED_ENDPOINTS:
            raise BudgetError("E_ENDPOINT_NOT_ALLOWED", "只允许只读端点: %s" % endpoint)
        req = _urlrequest.Request(
            api_base_url.api_url(endpoint),
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json",
                     "accesstoken": token, "uid": org},
            method="POST")
        with _urlrequest.urlopen(req, timeout=timeout) as response:
            value = json.loads(response.read().decode("utf-8"))
        return value if isinstance(value, dict) else {}
    return call


def probe(root: Path, *, project: str, org: str, token: str, http: Any = None,
          now: Optional[Any] = None) -> Dict[str, Any]:
    lock = acquire_round_lock(Path(root))
    try:
        return _probe_locked(root, project=project, org=org, token=token,
                             http=http, now=now)
    finally:
        _release_quiet(lock)


def _probe_locked(root, *, project, org, token, http=None, now=None):
    http = http or make_http(token, org)
    snapshot = read_balance(http, token=token, org=org, now=now)
    source = str(snapshot.get("source") or "")
    payload = {"source": source,
               "source_kind": str(snapshot.get("source_kind") or ""),
               "b_avail": str(snapshot["b_avail"]),
               "read_at": snapshot["read_at"]}
    if snapshot.get("source_kind") == POINTS_SOURCE_KIND:
        payload["points"] = int(snapshot["points"])
    else:
        payload["monthly_limit"] = int(snapshot["monthly_limit"])
        payload["monthly_used"] = int(snapshot["monthly_used"])
        if snapshot.get("points_fallback_reason"):
            payload["points_fallback_reason"] = str(
                snapshot["points_fallback_reason"])
    append_ledger(
        Path(root), org_hash=snapshot["org_hash"], project=project,
        kind="probe", source_ref=source, payload=payload)
    if Decimal(snapshot["b_avail"]) == 0:
        if snapshot.get("source_kind") == POINTS_SOURCE_KIND:
            _fail("E_BUDGET_EXHAUSTED",
                  "通用点数为 0（account/current.creditCount）")
        _fail("E_BUDGET_EXHAUSTED",
              "查看配额已用尽（monthlyUsed==monthlyLimit），且非保存点数口径")
    return snapshot


# ---------------------------------------------------------------------------
# 批次：begin → settle → carry
# ---------------------------------------------------------------------------

def _batch_id_for(task_id: str) -> str:
    return "batch-" + hashlib.sha256(str(task_id).encode("utf-8")).hexdigest()[:12]


def _rows(root, project, org, kind=None):
    return [r for r in read_ledger(root, project)
            if r.get("org_hash") == org_hash(org)
            and (kind is None or r.get("kind") == kind)]


def begin_batch(root, *, project, org, task_id, b0, exec_quote="",
                exec_quote_ref="", batch_id=None, sample_batch=False,
                probe_level=None, now=None):
    lock = acquire_round_lock(Path(root))
    try:
        return _begin_batch_locked(
            root, project=project, org=org, task_id=task_id, b0=b0,
            exec_quote=exec_quote, exec_quote_ref=exec_quote_ref,
            batch_id=batch_id, sample_batch=sample_batch,
            probe_level=probe_level, now=now)
    finally:
        _release_quiet(lock)


def _begin_batch_locked(root, *, project, org, task_id, b0, exec_quote="",
                        exec_quote_ref="", batch_id=None, sample_batch=False,
                        probe_level=None, now=None):
    """执行前登记（第一条 batch_begin）；重复 batch_id → E_LEDGER_REPLAY。

    v14：探针批必须已有更早的 sample_ack（时序严格小于），否则批 void +
    E_LEDGER_REPLAY；probe_level 供"只用最新一级"计算上限。
    """
    bid = batch_id or _batch_id_for(task_id)
    if any(r.get("batch_id") == bid for r in _rows(root, project, org, "batch_begin")):
        _fail("E_LEDGER_REPLAY", "同一 batch_id 重复 batch_begin: %s" % bid)
    if not isinstance(b0, dict) or "b_avail" not in b0:
        _fail("E_BALANCE_UNAVAILABLE", "缺执行前余额快照 B0")
    exec_ack = bool(str(exec_quote or "").strip()
                    and str(exec_quote_ref or "").strip())
    record = {
        "task_id": str(task_id),
        "b0_b_avail": str(b0["b_avail"]),
        "b0_source": str(b0.get("source") or ""),
        "exec_ack": exec_ack,
        "exec_quote_ref": str(exec_quote_ref or ""),
        "probe_level": probe_level,
        "sample_batch": bool(sample_batch),
    }
    if sample_batch:
        current_round = ""
        for row in reversed(read_ledger(Path(root), project)):
            if (row.get("kind") == "plan"
                    and row.get("state") == "round_open"
                    and row.get("org_hash") == org_hash(org)):
                current_round = str((row.get("payload") or {}).get("round_id") or "")
                break
        acks = [r for r in _rows(root, project, org, "sample_ack")
                if (r.get("payload") or {}).get("probe_level") == probe_level
                and str((r.get("payload") or {}).get("round_id") or "") == current_round
                and current_round]
        ack_ok = bool(acks) and _now(acks[-1]["at"]) < _now(now)
        if not ack_ok:
            append_ledger(Path(root), org_hash=org_hash(org), project=project,
                          kind="batch_begin", source_ref="sample_ack_missing",
                          batch_id=bid, state="void", payload=record)
            _fail("E_LEDGER_REPLAY",
                  "sample_ack 缺失或晚于 batch_begin：探针批置 void")
    append_ledger(Path(root), org_hash=org_hash(org), project=project,
                  kind="batch_begin", source_ref="exec_ack",
                  batch_id=bid, state="executing", payload=record)
    return {"batch_id": bid, "state": "executing",
            "task_id": str(task_id), "exec_ack": exec_ack,
            "b0_b_avail": str(b0["b_avail"]),
            "probe_level": probe_level,
            "sample_batch": bool(sample_batch)}


def settle_balance(http: Any, *, token: str, org: str, clock: Any, sleep: Any,
                   stable_seconds: float = 10.0, max_wait: float = 120.0,
                   poll_interval: float = 1.0) -> Dict[str, Any]:
    started = clock()
    previous = read_balance(http, token=token, org=org)
    equality_since = None
    while True:
        now = clock()
        if now - started > max_wait:
            _fail("E_BALANCE_NOT_SETTLED",
                  "余额在 %ss 内未稳定，本批保持 preliminary" % max_wait)
        sleep(poll_interval)
        current = read_balance(http, token=token, org=org)
        # 口径也必须一致（点数 vs 查看配额）；口径切换视为未稳定，绝不混算。
        same = (current.get("source") == previous.get("source")
                and current.get("monthly_used") == previous.get("monthly_used")
                and current["b_avail"] == previous["b_avail"])
        if same:
            if equality_since is None:
                equality_since = now
            if clock() - equality_since >= stable_seconds:
                return current
        else:
            equality_since = None
        previous = current


def _count_errors(companies, contacts) -> None:
    for label, value in (("companySaveCount", companies),
                         ("contactSaveCount", contacts)):
        if isinstance(value, bool) or not isinstance(value, int):
            _fail("E_CALIB_BAD_COUNT", "%s 非整数: %r" % (label, value))
        if value < 0:
            _fail("E_CALIB_BAD_COUNT", "%s 负数: %r" % (label, value))
    if companies == 0:
        _fail("E_CALIB_NO_COMPANIES", "companySaveCount=0，样本无公司")
    if contacts == 0:
        _fail("E_CALIB_NO_EMAILS", "contactSaveCount=0，拒绝 0 成本外推")


def _read_task(http: Any, task_id: str) -> Dict[str, Any]:
    try:
        response = http("operation/backend-task-status",
                        {"type": "cluesSave", "id": str(task_id)})
    except BudgetError:
        raise
    except Exception as exc:
        _fail("E_TASK_STATE_INCONSISTENT", "任务回读失败/超时: %r" % (exc,))
    if not isinstance(response, dict) or response.get("success") is not True:
        _fail("E_TASK_STATE_INCONSISTENT", "保存任务状态未返回成功")
    data = response.get("data")
    if not isinstance(data, dict):
        _fail("E_TASK_STATE_INCONSISTENT", "任务状态缺 data")
    finished = data.get("finished")
    status = data.get("status")
    if not isinstance(finished, bool):
        _fail("E_TASK_STATE_INCONSISTENT", "finished 字段缺失/非布尔")
    if isinstance(status, str) and status.strip():
        text = status.strip().lower()
        done = ("finished", "finish", "success", "completed", "done")
        if finished and text not in done:
            _fail("E_TASK_STATE_INCONSISTENT", "finished=true 但 status=%r" % status)
        if (not finished) and text in done:
            _fail("E_TASK_STATE_INCONSISTENT", "finished=false 但 status=%r" % status)
    if not finished:
        _fail("E_CALIB_TASK_INCOMPLETE", "保存任务未 finished")
    companies = data.get("companySaveCount")
    contacts = data.get("contactSaveCount")
    _count_errors(companies, contacts)
    return {"company_save_count": companies,
            "contact_save_count": contacts, "status": status}


def _settle_locked(root, *, project, org, token, task_id, http=None,
           concurrent_tasks=0, active_save_tasks=None,
           settle_stable_seconds=10.0, settle_max_wait=120.0,
           clock=None, sleep=None, batch_id=None):
    """结算取样（必须对应 batch_begin；重复 settle → E_LEDGER_REPLAY）。"""
    import time as _time
    bid = batch_id or _batch_id_for(task_id)
    begins = [r for r in _rows(root, project, org, "batch_begin")
              if r.get("batch_id") == bid]
    if not begins:
        _fail("E_LEDGER_REPLAY", "settle 无对应 batch_begin: %s" % bid)
    settles = [r for r in _rows(root, project, org, "settle")
               if r.get("batch_id") == bid]
    if settles:
        _fail("E_LEDGER_REPLAY", "同一 batch 重复 settle: %s" % bid)
    payload0 = begins[-1].get("payload") or {}
    b0 = {"b_avail": payload0.get("b0_b_avail"),
          "source": str(payload0.get("b0_source") or ""),
          "org_hash": org_hash(org),
          "token_fp": token_fp(token),
          "read_at": "1970-01-01T00:00:00+00:00"}
    active = [t for t in (active_save_tasks or []) if str(t) != str(task_id)]
    if concurrent_tasks or active:
        append_ledger(Path(root), org_hash=org_hash(org), project=project,
                      kind="settle", source_ref="window",
                      batch_id=bid, state="void",
                      payload={"reason": "concurrent/active", "active": active,
                               "task_id": str(task_id)})
        _fail("E_CALIB_WINDOW_POLLUTED", "窗口内有其它 in-flight 任务，该批 void")
    http = http or make_http(token, org)
    task = _read_task(http, task_id)
    b_settle = settle_balance(http, token=token, org=org,
                              clock=clock or _time.monotonic,
                              sleep=sleep or _time.sleep,
                              stable_seconds=settle_stable_seconds,
                              max_wait=settle_max_wait)
    if org_hash(org) != b_settle["org_hash"]:
        _fail("E_CALIB_WINDOW_POLLUTED", "B_settle 不是同一 org")
    # 口径必须与执行前一致：点数 vs 查看配额不能混算（否则差额不是扣点）。
    if (b0.get("source") and b_settle.get("source")
            and b0["source"] != b_settle["source"]):
        append_ledger(Path(root), org_hash=org_hash(org), project=project,
                      kind="settle",
                      source_ref=str(b_settle.get("source") or "balance_diff"),
                      batch_id=bid, state="void",
                      payload={"reason": "余额口径切换",
                               "b0_source": b0["source"],
                               "b_settle_source": b_settle["source"],
                               "task_id": str(task_id)})
        _fail("E_CALIB_WINDOW_POLLUTED",
              "B0 与 B_settle 余额口径不同（%s vs %s），不得混算"
              % (b0["source"], b_settle["source"]))
    b0_avail = Decimal(str(b0["b_avail"]))
    b1_avail = Decimal(str(b_settle["b_avail"]))
    if b1_avail > b0_avail:
        append_ledger(Path(root), org_hash=org_hash(org), project=project,
                      kind="settle",
                      source_ref=str(b_settle.get("source") or "balance_diff"),
                      batch_id=bid, state="void",
                      payload={"reason": "余额反增", "b0": str(b0_avail),
                               "b1": str(b1_avail), "task_id": str(task_id)})
        _fail("E_CALIB_COST_ZERO", "余额反增，标记 uncertain，停止外推")
    batch_cost_lo = b0_avail - b1_avail
    companies = Decimal(task["company_save_count"])
    contacts = Decimal(task["contact_save_count"])
    record = {
        "task_id": str(task_id),
        "batch_cost_lo": str(batch_cost_lo),
        "company_save_count": str(task["company_save_count"]),
        "contact_save_count": str(task["contact_save_count"]),
        "cost_per_company_lo": _six(batch_cost_lo / companies) if companies else "0.000000",
        "emails_per_company": str(contacts / companies),
        "b0_b_avail": str(b0_avail),
        "b_settle": str(b1_avail),
        "exec_ack": bool(payload0.get("exec_ack")),
        "probe_level": payload0.get("probe_level"),
        "unresolved_upper": str(batch_cost_lo),
    }
    append_ledger(Path(root), org_hash=org_hash(org), project=project,
                  kind="settle", source_ref="balance_diff",
                  batch_id=bid, state="preliminary", payload=record)
    return {"schema_version": SCHEMA_VERSION, "batch_id": bid,
            "state": "preliminary", "preliminary": True,
            "probe_level": payload0.get("probe_level"),
            "batch_cost_lo": str(batch_cost_lo),
            "company_save_count": str(task["company_save_count"]),
            "contact_save_count": str(task["contact_save_count"]),
            "cost_per_company_lo": record["cost_per_company_lo"],
            "emails_per_company": record["emails_per_company"],
            "b0_b_avail": str(b0_avail), "b_settle": str(b1_avail),
            "exec_ack": record["exec_ack"], "settled_at": None}


def settle(root, **kwargs):
    """抢锁后执行 settle；已有 budget.lock → E_ROUND_CONFLICT（零网络）。"""
    lock = acquire_round_lock(Path(root))
    try:
        return _settle_locked(root, **kwargs)
    finally:
        _release_quiet(lock)


def carry(root, *, project, org, batch_id, b_after, settle_quote="",
          settle_quote_ref="", now=None):
    lock = acquire_round_lock(Path(root))
    try:
        return _carry_locked(root, project=project, org=org,
                             batch_id=batch_id, b_after=b_after,
                             settle_quote=settle_quote,
                             settle_quote_ref=settle_quote_ref, now=now)
    finally:
        _release_quiet(lock)


def _carry_locked(root, *, project, org, batch_id, b_after, settle_quote="",
                  settle_quote_ref="", now=None):
    """结转（必须对应 settle；重复 carry → E_LEDGER_REPLAY）。"""
    settles = [r for r in _rows(root, project, org, "settle")
               if r.get("batch_id") == batch_id
               and r.get("state") == "preliminary"]
    if not settles:
        _fail("E_LEDGER_REPLAY", "carry 无对应 settle: %s" % batch_id)
    if any(r.get("batch_id") == batch_id
           for r in _rows(root, project, org, "carry")):
        _fail("E_LEDGER_REPLAY", "同一 batch 重复 carry: %s" % batch_id)
    payload = settles[-1].get("payload") or {}
    b_settle = Decimal(str(payload.get("b_settle")))
    b_after_dec = Decimal(str(b_after))
    late = max(Decimal("0"), b_settle - b_after_dec)
    batch_cost = max(Decimal("0"),
                     Decimal(str(payload.get("b0_b_avail"))) - b_settle) + late
    companies = int(payload.get("company_save_count") or 0)
    contacts = int(payload.get("contact_save_count") or 0)
    exec_ack = bool(payload.get("exec_ack"))
    settle_ack = bool(str(settle_quote or "").strip()
                      and str(settle_quote_ref or "").strip())
    external_risk = "confirmed" if (exec_ack and settle_ack) else "unprovable"
    # 零成本判定前置：抛错不落账，避免污染校准账分母且可重结转。
    if batch_cost == 0 and companies > 0:
        _fail("E_CALIB_COST_ZERO",
              "结转后成本仍为 0（去重/未扣点），该批不得用于外推")
    record = {
        "batch_cost": str(batch_cost),
        "company_save_count": str(companies),
        "contact_save_count": str(contacts),
        "exec_ack": exec_ack,
        "settle_ack": settle_ack,
        "settle_quote_ref": str(settle_quote_ref or ""),
        "settled_at": _iso(now),
        "probe_level": payload.get("probe_level"),
    }
    append_ledger(Path(root), org_hash=org_hash(org), project=project,
                  kind="carry", source_ref="late_carryover",
                  batch_id=batch_id, state="settled", late=late,
                  external_risk=external_risk, payload=record)
    return {"batch_id": batch_id, "state": "settled",
            "batch_cost": str(batch_cost), "late": str(late),
            "company_save_count": str(companies),
            "contact_save_count": str(contacts),
            "external_risk": external_risk,
            "exec_ack": exec_ack, "settle_ack": settle_ack,
            "settled_at": record["settled_at"]}


# ---------------------------------------------------------------------------
# 统计与决策
# ---------------------------------------------------------------------------

def _preliminary_batches(root, project, org):
    carried = {r.get("batch_id") for r in _rows(root, project, org, "carry")}
    cleared = {r.get("batch_id")
               for r in _rows(root, project, org, "audit_clear")}
    return [r for r in _rows(root, project, org, "settle")
            if r.get("state") == "preliminary"
            and r.get("batch_id") not in carried
            and r.get("batch_id") not in cleared]


def audit_clear(root, *, project, org, batch_id, value, basis,
                quote="", quote_ref=""):
    lock = acquire_round_lock(Path(root))
    try:
        return _audit_clear_locked(root, project=project, org=org,
                                   batch_id=batch_id, value=value,
                                   basis=basis, quote=quote,
                                   quote_ref=quote_ref)
    finally:
        _release_quiet(lock)


def _audit_clear_locked(root, *, project, org, batch_id, value, basis,
                        quote="", quote_ref=""):
    """清除 unresolved 的三条路径之②③：核销实际消耗或确认未扣点（记 0）。"""
    if not str(basis or "").strip():
        _fail("E_BAD_INPUT", "audit_clear 必须记录依据")
    settles = [r for r in _rows(root, project, org, "settle")
               if r.get("batch_id") == batch_id]
    voids = [r for r in _rows(root, project, org, "batch_begin")
             if r.get("batch_id") == batch_id and r.get("state") == "void"]
    if not settles and not voids:
        _fail("E_BAD_INPUT", "audit_clear 批次不存在或无可清除的窗口: %s" % batch_id)
    if any(r.get("batch_id") == batch_id
           for r in _rows(root, project, org, "carry")):
        _fail("E_BAD_INPUT", "该批已结转，不能再 audit_clear: %s" % batch_id)
    batch_value = Decimal(str(value))
    if batch_value < 0:
        _fail("E_BAD_INPUT", "audit_clear 值不能为负")
    record = {"batch_id": str(batch_id), "value": str(batch_value),
              "cleared_value": str(batch_value),
              "evidence": str(basis) + ("|" + str(quote_ref) if quote_ref else ""),
              "basis": str(basis), "quote": str(quote),
              "quote_ref": str(quote_ref), "mode": "not_charged"
              if batch_value == 0 else "audit_value"}
    append_ledger(Path(root), org_hash=org_hash(org), project=project,
                  kind="audit_clear", source_ref=str(quote_ref or "audit_clear"),
                  batch_id=str(batch_id), state="cleared", payload=record)
    return record


# v3（2026-10-27）：探针改「一次 100 家」——1→10→50 阶梯实测太慢（用户要跑几十轮）。
# 100 家一次拿到单价与联系人率后，直接按预算推导 N 全量；探针失败/校准不可信才再交用户决策。
PROBE_LEVELS = (100,)


def _probe_planned(root, *, project, org, round_id, level):
    """同 project/org/round/level 是否已落过探针行（用于幂等，防重试重复记账）。"""
    for row in read_ledger(root, project):
        payload = row.get("payload") or {}
        if (row.get("kind") == "plan" and row.get("state") == "probe_level"
                and str(row.get("org_hash") or "") == org_hash(org)
                and str(payload.get("round_id") or "") == str(round_id)
                and payload.get("probe_level") == level):
            return True
    return False


def next_probe_level(root, *, project, org, round_id):
    """探针只跑一次 100 家：重复调用必须幂等返回 100（重试/重放不判死）。"""
    return PROBE_LEVELS[0]


def round_accounts(root, *, project, org, b_now=None):

    carried = _rows(root, project, org, "carry")
    clean = [r for r in carried if r.get("external_risk") == "confirmed"]
    spent_settled = sum((Decimal(str((r.get("payload") or {}).get("batch_cost", "0")))
                         for r in carried), Decimal("0"))
    spent_calib = sum((Decimal(str((r.get("payload") or {}).get("batch_cost", "0")))
                       for r in clean), Decimal("0"))
    companies = sum(int((r.get("payload") or {}).get("company_save_count") or 0)
                    for r in clean)
    emails = sum(int((r.get("payload") or {}).get("contact_save_count") or 0)
                 for r in clean)
    # v14/v17：per_company_upper——正常批（probe_level=None）恒参与 max；
    # 仅探针级之间取最新一级；同时存在正常批与探针批 → 只用正常批。
    def _upper(row):
        payload = row.get("payload") or {}
        count = int(payload.get("company_save_count") or 0)
        if count <= 0:
            return None
        return (Decimal(str(payload.get("batch_cost", "0"))) / Decimal(count)
                ).quantize(SIX, rounding=ROUND_CEILING)

    probe_rows = [r for r in clean
                  if isinstance((r.get("payload") or {}).get("probe_level"), int)]
    normal_rows = [r for r in clean
                   if not isinstance((r.get("payload") or {}).get("probe_level"), int)]
    latest_level = None
    for row in probe_rows:
        level = row["payload"]["probe_level"]
        if latest_level is None or level > latest_level:
            latest_level = level
    if normal_rows:
        upper_rows = normal_rows
    else:
        upper_rows = [r for r in probe_rows
                      if r["payload"]["probe_level"] == latest_level]
    uppers = [u for u in (_upper(r) for r in upper_rows) if u is not None]
    # v14：unresolved 按该批自身窗口计，且支持三种清除（结转/audit_clear/未扣点记0）。
    carried_ids = {r.get("batch_id") for r in carried}
    clears = {}
    for row in _rows(root, project, org, "audit_clear"):
        clears[row.get("batch_id")] = row
    unresolved_rows = []
    for row in _rows(root, project, org, "settle"):
        if row.get("batch_id") in carried_ids:
            continue
        unresolved_rows.append(row)
    for row in _rows(root, project, org, "batch_begin"):
        if row.get("state") == "void" and row.get("batch_id") not in carried_ids:
            unresolved_rows.append(row)
    unresolved_total = Decimal("0")
    unresolved_count = 0
    for row in unresolved_rows:
        batch_id = row.get("batch_id")
        payload = row.get("payload") or {}
        if batch_id in clears:
            cleared = Decimal(str((clears[batch_id].get("payload") or {}).get("value", "0")))
            if cleared <= 0:
                continue  # 仅 audit_clear 明确核销为 0 才彻底清除
            unresolved_count += 1
            unresolved_total += cleared
            continue
        if "unresolved_upper" in payload:
            value = Decimal(str(payload.get("unresolved_upper", "0")))
        elif "b0_b_avail" in payload and "b_settle" in payload:
            value = max(Decimal("0"), Decimal(str(payload["b0_b_avail"]))
                        - Decimal(str(payload["b_settle"])))
        else:
            value = Decimal("0")
        # 值为 0 也计入 unresolved_count（只跳过金额累加），冻结不可被绕过。
        unresolved_count += 1
        if value > 0:
            unresolved_total += value
    spent_all = spent_settled + unresolved_total
    return {
        "carry_count": len(carried),
        "clean_count": len(clean),
        "preliminary_count": len(_preliminary_batches(root, project, org)),
        "spent_settled": spent_settled,
        "spent_all": spent_all,
        "spent_calib": spent_calib,
        "companies_calib": companies,
        "emails_calib": emails,
        "per_company_upper": max(uppers) if uppers else None,
        "latest_probe_level": latest_level,
        "unresolved_count": unresolved_count,
        "unresolved_total": unresolved_total,
    }


def frozen_b_plan(root, *, project, org):
    """锚定**首轮**冻结值（不是最后一条 freeze 行）。"""
    for row in read_ledger(root, project):
        if (row.get("kind") == "plan"
                and row.get("org_hash") == org_hash(org)
                and (row.get("payload") or {}).get("b_plan") is not None
                and (row.get("payload") or {}).get("freeze")):
            return str(row["payload"]["b_plan"])
    return None


def freeze_b_plan(root, *, project, org, b_avail, ratio=DEFAULT_BUDGET_RATIO,
                  override=None, override_source="", new_round=False):
    if not new_round:
        frozen = frozen_b_plan(root, project=project, org=org)
        if frozen is not None:
            return Decimal(frozen), "frozen"
    if override is not None:
        if not str(override_source or "").strip():
            _fail("E_BUDGET_UNRESOLVED", "显式预算覆盖必须记录来源")
        value = Decimal(str(override)).to_integral_value(rounding=ROUND_FLOOR)
        source = str(override_source)
    else:
        value = (Decimal(str(b_avail)) * Decimal(str(ratio))).to_integral_value(
            rounding=ROUND_FLOOR)
        source = "b_avail*%s" % ratio
    return value, source


def bootstrap_sample(*, b_plan, b_avail, history_upper=None,
                     sample_ack_quote="", sample_ack_ref="", sample_n0=100):
    """v3：无历史先生成 100 家探针（一次拿单价/联系人率），随后直接推导全量；
    旧的 B_plan<20 点门槛已删除（量纲无关）。"""
    budget = Decimal(str(b_plan))
    if history_upper is None:
        n0 = 1 if sample_n0 is None else int(sample_n0)
        # 保守封顶：按「每家公司至少 1 点」估，探针量不得超过本轮预算点数。
        try:
            cap = int(budget)
        except Exception:
            cap = n0
        if cap > 0 and n0 > cap:
            n0 = max(1, cap)
        warning = ("首批 %d 家为成本实测样本，实际扣点未知；样本本身可能耗掉"
                   "本轮预算的大部分甚至全部余额。" % n0)
        affordable = None
    else:
        upper = Decimal(str(history_upper))
        if upper <= 0:
            _fail("E_CALIB_NOT_READY", "历史单位成本<=0，不能规划样本")
        affordable = _floor(budget / upper)
        n0 = min(100, max(1, min(BOOTSTRAP_N0, affordable))) if affordable >= 1 else 0
        if affordable < BOOTSTRAP_N0:
            warning = ("按历史上限该批可能接近/超出本轮预算：可负担 %d 家，"
                       "已取 %d 家（不强制 20 家），请确认。" % (affordable, n0))
        else:
            warning = ("首批 %d 家为成本实测样本，实际扣点未知；样本本身可能"
                       "耗掉本轮预算的大部分甚至全部余额。" % n0)
    ack = bool(str(sample_ack_quote or "").strip()
               and str(sample_ack_ref or "").strip())
    return {
        "status": "sample_ready" if ack else "sample_needs_ack",
        "sample_n": n0,
        "bootstrap": True,
        "b_plan": str(budget),
        "b_avail": str(b_avail),
        "history_upper": None if history_upper is None else str(history_upper),
        "affordable_n": affordable,
        "risk_notice": warning,
        "requires_confirmation": not ack,
        "sample_ack": ack,
        "sample_ack_ref": str(sample_ack_ref or ""),
    }


def plan(root, **kwargs):
    """写账簿/出数量入口：先抢 round 锁；冲突 → E_ROUND_CONFLICT（零网络）。"""
    lock = acquire_round_lock(Path(root))
    try:
        return _plan_locked(root, **kwargs)
    finally:
        _release_quiet(lock)


def make_ready_row_payload(*, b_plan, confirm_n, n_cons, n_est, risk_ack,
                           cap_ack, exec_quote_ref, batch_points_upper,
                           round_id, spent_all, budget_left,
                           per_company_upper):
    """ready 台账行的唯一生产者；字段变更有回归测试盯住 count_guard 消费端。"""
    return {
        "b_plan": str(b_plan), "freeze": False, "confirm_n": confirm_n,
        "n_cons": n_cons, "n_est": n_est, "risk_ack": bool(risk_ack),
        "cap_ack": bool(cap_ack), "exec_quote_ref": str(exec_quote_ref),
        "batch_points_upper": str(batch_points_upper),
        "round_id": str(round_id),
        "spent_all": str(spent_all),
        "budget_left": str(budget_left),
        "per_company_upper": str(per_company_upper),
    }


def _plan_locked(root, *, project, org, b_plan, b_avail, read_at=None,
         target_companies=0, already_saved=0, max_points_suggest=None,
         balance_source=None,
         confirm_n=None, exec_quote="", exec_quote_ref="",
         cap_quote="", cap_quote_ref="", risk_quote="", risk_ref="",
         sample_ack_quote="", sample_ack_ref="", now=None,
         balance_read_at=None, new_round=False, ratio=DEFAULT_BUDGET_RATIO,
         override=None, override_source="", round_id=None,
         cumulative_cap=None):
    if balance_read_at or read_at:
        age = (_now(now) - _now(balance_read_at or read_at)).total_seconds()
        if age > BALANCE_STALE_SECONDS:
            _fail("E_BALANCE_STALE", "余额快照超过 10 分钟，请重读后再算")
    open_rounds = [r for r in read_ledger(root, project)
                   if r.get("kind") == "plan"
                   and r.get("state") == "round_open"
                   and r.get("org_hash") == org_hash(org)]
    current_round = None if new_round else (open_rounds[-1] if open_rounds else None)
    need_open_round = False
    explicit_budget = None  # 本次调用显式给出的点数预算（回续轮为 None）
    if current_round is not None:
        frozen = Decimal(str((current_round.get("payload") or {}).get("b_plan")))
        source = "frozen_round"
        round_id = str((current_round.get("payload") or {}).get("round_id"))
        cumulative_cap = (current_round.get("payload") or {}).get(
            "cumulative_cap", cumulative_cap)
    else:
        need_open_round = True
        explicit_budget = override if override is not None else b_plan
        if explicit_budget is None and not _is_points_source(balance_source):
            _fail(
                "E_BUDGET_UNRESOLVED",
                "余额来源=%s 不是通用点数（查看配额≠保存点数），"
                "必须提供显式点数预算（budget_points/max_points，"
                "如「点数预算 3 万」）" % (balance_source or "未知"))
        if override is not None:
            if not str(override_source or "").strip():
                _fail("E_BUDGET_UNRESOLVED", "显式预算覆盖必须记录来源")
            frozen = Decimal(str(override)).to_integral_value(rounding=ROUND_FLOOR)
            source = str(override_source)
        else:
            frozen = (Decimal(str(b_plan)) if b_plan is not None
                      else (Decimal(str(b_avail)) * Decimal(str(ratio))).to_integral_value(
                          rounding=ROUND_FLOOR))
            source = "provided" if b_plan is not None else "b_avail*%s" % ratio
        # D1：新轮 B_plan 必须等于首轮冻结值，否则拒绝（跨轮重算被拒）。
        first_frozen = frozen_b_plan(root, project=project, org=org)
        if first_frozen is not None and frozen != Decimal(str(first_frozen)):
            _fail("E_LEDGER_REPLAY",
                  "新轮 B_plan=%s 必须等于首轮冻结值 %s（跨轮重算被拒）"
                  % (frozen, first_frozen))
        if round_id is None:
            round_id = "round-" + hashlib.sha256(
                ("%s|%s|%s" % (org_hash(org), project, _iso(now))).encode("utf-8")
            ).hexdigest()[:12]
    spent_cumulative_all_rounds = Decimal("0")  # 在 accounts 之后补齐
    accounts = round_accounts(root, project=project, org=org, b_now=b_avail)
    # v16 AC-B12：跨轮累计 = 全部 settled + 当前 unresolved 上界；参与 cap 判定。
    spent_cumulative_all_rounds = (
        sum((Decimal(str((r.get("payload") or {}).get("batch_cost", "0")))
             for r in _rows(root, project, org, "carry")), Decimal("0"))
        + accounts["unresolved_total"])
    if cumulative_cap is not None and spent_cumulative_all_rounds >= Decimal(
            str(cumulative_cap)):
        _fail("E_ROUND_CAP_EXHAUSTED",
              "跨轮累计已花 %s（含未结清上界 %s）>= 上限 %s"
              % (spent_cumulative_all_rounds, accounts["unresolved_total"],
                 cumulative_cap))
    # v14：存在 unresolved → 冻结后续批次；零成本 preliminary → NOT_READY。
    if accounts["unresolved_count"] > 0:
        _fail("E_UNRESOLVED_BATCH",
              "%d 批未结清（按上界 %s 点计），冻结后续保存"
              % (accounts["unresolved_count"], accounts["unresolved_total"]))
    if accounts["preliminary_count"] > 0:
        _fail("E_CALIB_NOT_READY", "当前批尚未结转，不给数量")
    # D1：校验通过前不落 freeze 行——失败轮不得改写首轮锚点。
    if need_open_round:
        append_ledger(Path(root), org_hash=org_hash(org), project=project,
                      kind="plan", source_ref=source, state="round_open",
                      payload={"round_id": str(round_id), "b_plan": str(frozen),
                               "freeze": True, "b_avail": str(b_avail),
                               "b_plan_source": source,
                               "cumulative_cap": None if cumulative_cap is None
                               else str(cumulative_cap)})
        need_open_round = False
    if accounts["carry_count"] == 0:
        # 校准账空：先跑一次 100 家探针（单独确认），拿到单价后直接推导全量。
        level = next_probe_level(root, project=project, org=org,
                                 round_id=round_id)
        sample = bootstrap_sample(b_plan=frozen, b_avail=b_avail,
                                  sample_ack_quote=sample_ack_quote,
                                  sample_ack_ref=sample_ack_ref,
                                  sample_n0=level)
        ack_at = _iso(now) if sample["sample_ack"] else ""
        append_ledger(Path(root), org_hash=org_hash(org), project=project,
                      kind="sample_ack" if sample["sample_ack"] else "plan",
                      source_ref="bootstrap_sample",
                      state=sample["status"], sample_ack_at=ack_at,
                      payload={"round_id": str(round_id), "probe_level": level,
                               "b_plan": str(frozen), "freeze": False,
                               "b_plan_source": source,
                               "sample_n": sample["sample_n"],
                               "risk_notice": sample["risk_notice"],
                               "sample_ack_ref": str(sample_ack_ref or "")})
        if sample["sample_ack"] and not _probe_planned(
                root, project=project, org=org, round_id=round_id, level=level):
            append_ledger(Path(root), org_hash=org_hash(org), project=project,
                          kind="plan", source_ref="probe_ladder",
                          state="probe_level",
                          payload={"round_id": str(round_id),
                                   "probe_level": level,
                                   "sample_n": sample["sample_n"]})
        sample["probe_level"] = level
        sample["round_id"] = round_id
        return sample
    if accounts["clean_count"] == 0:
        _fail("E_CALIB_NOT_READY",
              "没有干净批次（external_risk=confirmed），不得外推")
    if (accounts["spent_calib"] <= 0 or accounts["companies_calib"] <= 0
            or accounts["emails_calib"] <= 0):
        _fail("E_CALIB_NOT_READY",
              "校准账为空（spent/companies/emails 需均>0），禁止 0/0 外推")
    per_company_est = accounts["spent_calib"] / Decimal(accounts["companies_calib"])
    per_email_est = accounts["spent_calib"] / Decimal(accounts["emails_calib"])
    emails_per_company = (Decimal(accounts["emails_calib"])
                          / Decimal(accounts["companies_calib"]))
    upper = accounts["per_company_upper"]
    budget_left = frozen - accounts["spent_all"]
    if budget_left < upper:
        _fail("E_BUDGET_EXHAUSTED",
              "剩余预算 %s < 单家上限 %s，停止保存" % (budget_left, upper))
    n_est = _floor(budget_left / per_company_est)
    n_cons = _floor(budget_left / upper)
    target_remaining = max(0, int(target_companies) - int(already_saved))
    n_est = min(n_est, target_remaining)
    n_cons = min(n_cons, target_remaining)
    if n_cons < 1:
        _fail("E_BUDGET_EXHAUSTED",
              "保守上限可存 0 家（预算余量 %s）" % budget_left)
    batch_points_upper = _ceil(Decimal(n_cons) * upper)
    if max_points_suggest is None:
        # 建议上限默认 2 万点；用户显式点数预算即明确放开（取较大值），
        # 避免 30000 点预算的单次执行被 20000 建议上限误拒。
        max_points_suggest = (max(Decimal(SUGGEST_MAX_POINTS),
                                  Decimal(str(explicit_budget)))
                              if explicit_budget is not None
                              else Decimal(SUGGEST_MAX_POINTS))
    cap_limit = Decimal(str(max_points_suggest))
    cap_hit = batch_points_upper > cap_limit
    cap_ack = bool(str(cap_quote or "").strip() and str(cap_quote_ref or "").strip())
    result = {
        "schema_version": SCHEMA_VERSION,
        "status": "needs_quantity_confirmation",
        "project": str(project),
        "org_hash": org_hash(org),
        "b_plan": str(frozen),
        "b_plan_source": source,
        "spent_all": str(accounts["spent_all"]),
        "spent_calib": str(accounts["spent_calib"]),
        "companies_calib": accounts["companies_calib"],
        "emails_calib": accounts["emails_calib"],
        "per_company_est": str(per_company_est),
        "per_email_est": str(per_email_est),
        "emails_per_company": str(emails_per_company),
        "per_company_upper": str(upper),
        "budget_left": str(budget_left),
        "n_cons": n_cons,
        "n_est": n_est,
        "range": [n_cons, n_est],
        "range_kind": "estimate",
        "target_remaining": target_remaining,
        "max_points_suggest": int(cap_limit),
        "balance_source": str(balance_source or ""),
        "batch_points_upper": str(batch_points_upper),
        "max_points_suggest_hit": cap_hit,
        "requires_confirmation": True,
        "display": {
            "balance_source": str(balance_source or ""),
            "b_avail": str(b_avail),
            "read_at": str(read_at or balance_read_at or ""),
            "b_plan": str(frozen),
            "spent_all": str(accounts["spent_all"]),
            "companies_calib": accounts["companies_calib"],
            "emails_calib": accounts["emails_calib"],
            "per_company_est": _six(per_company_est),
            "per_email_est": _six(per_email_est),
            "emails_per_company": _six(emails_per_company),
            "n_cons": n_cons,
            "n_est": n_est,
            "b_now_minus_upper": str(Decimal(str(b_avail)) - batch_points_upper),
            "pct": (_six((Decimal(str(accounts["spent_all"])) + batch_points_upper)
                         / Decimal(str(b_avail)) * Decimal("100")) + "%")
                   if Decimal(str(b_avail)) > 0 else "0%",
            "spent_cumulative_all_rounds": str(spent_cumulative_all_rounds),
            "cumulative_cap": None if cumulative_cap is None else str(cumulative_cap),
            "round_id": str(round_id),
            "unresolved_count": accounts["unresolved_count"],
            "unresolved_total": str(accounts["unresolved_total"]),
        },
        "round_id": str(round_id),
        "spent_cumulative_all_rounds": str(spent_cumulative_all_rounds),
        "cumulative_cap": None if cumulative_cap is None else str(cumulative_cap),
        "unresolved_count": accounts["unresolved_count"],
        "unresolved_total": str(accounts["unresolved_total"]),
        "risk_notice": "若本批单位成本高于历史最大值，可能提前耗尽本轮预算。",
    }
    if confirm_n is None:
        append_ledger(Path(root), org_hash=org_hash(org), project=project,
                      kind="plan", source_ref="interval_only",
                      state="needs_quantity_confirmation",
                      payload={"b_plan": str(frozen), "freeze": False,
                               "n_cons": n_cons, "n_est": n_est})
        return result
    if type(confirm_n) is not int or confirm_n <= 0:
        _fail("E_PLAN_TARGET_INVALID", "confirm_n 必须是正 int")
    if confirm_n > n_est:
        _fail("E_QUANTITY_EXCEEDS_EST",
              "确认数量 %d > 估算上限 %d" % (confirm_n, n_est))
    risk_ack = bool(str(risk_quote or "").strip() and str(risk_ref or "").strip())
    if confirm_n > n_cons and not risk_ack:
        _fail("E_QUANTITY_EXCEEDS_CONS",
              "确认数量 %d > 保守上限 %d；须显式冒险确认或改小"
              % (confirm_n, n_cons))
    if not (str(exec_quote or "").strip() and str(exec_quote_ref or "").strip()):
        _fail("E_PLAN_NOT_CONFIRMED", "执行前必须有用户确认原话与引用")
    if cap_hit and not cap_ack:
        _fail("E_CAP_CONFIRMATION_REQUIRED",
              "一次执行预计扣点 %s > 建议上限 %s，须用户确认（只提示不硬拒）"
              % (batch_points_upper, int(cap_limit)))
    assert_ledger = make_ready_row_payload(
        b_plan=str(frozen), confirm_n=confirm_n, n_cons=n_cons, n_est=n_est,
        risk_ack=risk_ack, cap_ack=cap_ack, exec_quote_ref=str(exec_quote_ref),
        batch_points_upper=str(batch_points_upper), round_id=str(round_id),
        spent_all=str(accounts["spent_all"]), budget_left=str(budget_left),
        per_company_upper=str(upper))
    append_ledger(Path(root), org_hash=org_hash(org), project=project,
                  kind="plan", source_ref=str(exec_quote_ref), state="ready",
                  payload=assert_ledger)
    result.update({"status": "ready", "confirm_n": confirm_n,
                   "selectTotal": confirm_n, "requires_confirmation": False,
                   "exec_quote_ref": str(exec_quote_ref), "risk_ack": risk_ack})
    return result


def to_execution(plan_doc: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(plan_doc, dict):
        _fail("E_PLAN_REQUIRED", "缺 plan")
    if plan_doc.get("bootstrap"):
        _fail("E_SAMPLE_ACK_REQUIRED",
              "引导样本不能当批量 plan 执行；须先确认样本并结转")
    if plan_doc.get("requires_confirmation") or plan_doc.get("status") != "ready":
        _fail("E_PLAN_NOT_CONFIRMED", "plan 未经用户确认，不得执行")
    n = plan_doc.get("selectTotal")
    if type(n) is not int or n <= 0:
        _fail("E_PLAN_REQUIRED", "selectTotal 非法")
    return {"selectTotal": n, "b_plan": plan_doc.get("b_plan")}


def to_sample_execution(sample_doc: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(sample_doc, dict):
        _fail("E_PLAN_REQUIRED", "缺样本方案")
    if sample_doc.get("requires_confirmation"):
        _fail("E_SAMPLE_ACK_REQUIRED", "样本未单独确认，不得执行")
    n = sample_doc.get("sample_n")
    if type(n) is not int or n <= 0:
        _fail("E_BUDGET_TOO_SMALL", "预算不足以支撑样本")
    return {"selectTotal": n}


def check_stop(b_plan, spent_all, per_company_upper) -> None:
    remaining = Decimal(str(b_plan)) - Decimal(str(spent_all))
    if remaining < Decimal(str(per_company_upper)):
        _fail("E_BUDGET_EXHAUSTED",
              "剩余预算 %s < 单家上限 %s×1，停止保存"
              % (remaining, per_company_upper))


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def latest_probe_snapshot(root, *, project, org, now=None):
    """同 project+org 的最新 probe 快照；无 → E_BALANCE_UNAVAILABLE（先跑 probe）。"""
    rows = [r for r in read_ledger(Path(root), project)
            if r.get("kind") == "probe"
            and r.get("org_hash") == org_hash(org)]
    if not rows:
        _fail("E_BALANCE_UNAVAILABLE",
              "本 project+org 无 probe 快照：先跑 save_budget.py probe（不要人工抄余额）")
    payload = rows[-1].get("payload") or {}
    read_at = str(payload.get("read_at") or "")
    b_avail = str(payload.get("b_avail") or "")
    if not b_avail:
        _fail("E_BALANCE_UNAVAILABLE", "probe 快照缺 b_avail")
    try:
        age = (_now(now) - _now(read_at)).total_seconds()
    except BudgetError:
        _fail("E_BALANCE_UNAVAILABLE", "probe 快照 read_at 非法")
    if age > BALANCE_STALE_SECONDS:
        _fail("E_BALANCE_STALE", "probe 快照超过 10 分钟（%s）：重读后再算" % read_at)
    return {"b_avail": b_avail, "read_at": read_at,
            "org_hash": rows[-1]["org_hash"],
            "source": payload.get("source"),
            "source_kind": payload.get("source_kind")}


def render_human(result):
    """按任务书第4节模板输出（带单位的人类可读渲染）。"""
    if result.get("bootstrap"):
        return "\n".join([
            "引导样本        : 首批 %d 家" % (result.get("sample_n") or 0),
            "风险            : %s" % result.get("risk_notice", ""),
            "确认            : %s" % ("已确认（sample_ready）"
                                      if result.get("sample_ack")
                                      else "未确认——须用户单独确认后才执行"),
        ])
    display = result.get("display") or {}
    balance_source = str(display.get("balance_source") or "")
    points_source = _is_points_source(balance_source) or not balance_source
    lines = [
        "%s: %s 点（读于 %s）"
        % ("账户余额        " if points_source
           else "查看配额剩余（非保存点数）",
           display.get("b_avail", "?"), display.get("read_at", "?")),
        "本轮保存预算    : %s 点（已冻结）" % result.get("b_plan", "?"),
        "本轮已花(预算账): %s 点（含全部 settled 批次）" % result.get("spent_all", "?"),
        "校准样本        : %s 家 / %s 个邮箱（仅干净批次）"
        % (result.get("companies_calib", "?"), result.get("emails_calib", "?")),
        "实测单位成本    : %s 点/家（%s 点/邮箱，%s 邮箱/家）"
        % (display.get("per_company_est", "?"), display.get("per_email_est", "?"),
           display.get("emails_per_company", "?")),
        "按保守上限还能存: %d 家；按均值估算: %d 家（区间 [%d, %d]，均标 estimate）"
        % (result.get("n_cons", 0), result.get("n_est", 0),
           result.get("n_cons", 0), result.get("n_est", 0)),
        "执行后预计余额  : ≈ %s 点（基于 %s 于 %s；实际可能更低）"
        % (display.get("b_now_minus_upper", "?"), display.get("b_avail", "?"),
           display.get("read_at", "?")),
        "风险            : 本次约占余额 %s；若本批单位成本高于历史最大值，可能提前耗尽本轮预算"
        % display.get("pct", "?"),
    ]
    if not points_source:
        lines.append(
            "余额口径        : 查看配额（非保存点数），不能推导保存预算；"
            "本次按显式预算 %s 点执行" % result.get("b_plan", "?"))
    return "\n".join(lines)


def _load(path: str) -> Dict[str, Any]:
    doc = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(doc, dict):
        raise BudgetError("E_BAD_INPUT", "JSON 必须是 object")
    return doc


def _run(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="保存预算自动校准（只读余额+实测成本）")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("probe")
    p.add_argument("--root", default=str(TOOLS_DIR.parent))
    p.add_argument("--project", required=True)
    p.add_argument("--org", default="")
    p.add_argument("--token", default="")
    p.add_argument("--from-session", action="store_true",
                   help="从本机会话读取 token/org（免 argv 明文）")
    p.add_argument("--out", default=None)

    b = sub.add_parser("begin")
    b.add_argument("--root", default=str(TOOLS_DIR.parent))
    b.add_argument("--project", required=True)
    b.add_argument("--org", required=True)
    b.add_argument("--task-id", required=True)
    b.add_argument("--b0-file", required=True)
    b.add_argument("--exec-quote", default="")
    b.add_argument("--exec-quote-ref", default="")

    st = sub.add_parser("settle")
    st.add_argument("--root", default=str(TOOLS_DIR.parent))
    st.add_argument("--project", required=True)
    st.add_argument("--org", default="")
    st.add_argument("--token", default="")
    st.add_argument("--from-session", action="store_true",
                    help="从本机会话读取 token/org（免 argv 明文）")
    st.add_argument("--task-id", required=True)
    st.add_argument("--concurrent-tasks", type=int, default=0)
    st.add_argument("--out", default=None)

    ca = sub.add_parser("carry")
    ca.add_argument("--root", default=str(TOOLS_DIR.parent))
    ca.add_argument("--project", required=True)
    ca.add_argument("--org", required=True)
    ca.add_argument("--batch-id", required=True)
    ca.add_argument("--b-after", required=True)
    ca.add_argument("--settle-quote", default="")
    ca.add_argument("--settle-quote-ref", default="")
    ca.add_argument("--out", default=None)

    q = sub.add_parser("plan")
    q.add_argument("--root", default=str(TOOLS_DIR.parent))
    q.add_argument("--project", required=True)
    q.add_argument("--org", required=True)
    q.add_argument("--b-plan", default=None, help="可选覆盖（测试用）；缺省从账簿最新 probe 快照取")
    q.add_argument("--b-avail", default=None, help="可选覆盖（测试用）；缺省从账簿最新 probe 快照取")
    q.add_argument("--format", default="human", choices=("human", "json"))
    q.add_argument("--read-at", default=None)
    q.add_argument("--target", type=int, default=0)
    q.add_argument("--saved", type=int, default=0)
    q.add_argument("--max-points-suggest", type=int, default=None,
                   help="单次建议上限（点）；缺省：显式 --b-plan 时取预算与 20000 较大值，否则 20000")
    q.add_argument("--confirm-n", type=int, default=None)
    q.add_argument("--exec-quote", default="")
    q.add_argument("--exec-quote-ref", default="")
    q.add_argument("--cap-quote", default="")
    q.add_argument("--cap-quote-ref", default="")
    q.add_argument("--risk-quote", default="")
    q.add_argument("--risk-ref", default="")
    q.add_argument("--sample-ack-quote", default="")
    q.add_argument("--sample-ack-ref", default="")
    q.add_argument("--new-round", action="store_true")
    q.add_argument("--cumulative-cap", default=None,
                   help="跨轮累计上限（点）；--new-round 缺省时按上一轮冻结预算强校验")
    q.add_argument("--out", default=None)

    ac = sub.add_parser("audit-clear", help="核销未结清批次（0=确认未扣点）")
    ac.add_argument("--root", default=str(TOOLS_DIR.parent))
    ac.add_argument("--project", required=True)
    ac.add_argument("--org", required=True)
    ac.add_argument("--batch-id", required=True)
    ac.add_argument("--value", required=True)
    ac.add_argument("--reason", required=True)
    ac.add_argument("--quote-ref", default="")

    s = sub.add_parser("status")
    s.add_argument("--root", default=str(TOOLS_DIR.parent))
    s.add_argument("--project", default=None)

    args = parser.parse_args(argv)
    if getattr(args, "from_session", False):
        from session_store import load_ready
        _host, args.token, args.org = load_ready(TOOLS_DIR.parent)
    if args.cmd in ("probe", "settle") and (not args.token or not args.org):
        print("❌ 需要 --token/--org，或用 --from-session 读取本机会话")
        return 2
    root = Path(args.root)
    # 时钟注入（测试/审计）：LFX_BUDGET_NOW 供用例对齐快照时间；缺省真实 now。
    import os as _os
    _env_now = _os.environ.get('LFX_BUDGET_NOW', '').strip()
    cli_now = _now(_env_now) if _env_now else None
    if args.cmd == "probe":
        snapshot = probe(root, project=args.project, org=args.org,
                         token=args.token)
        print(json.dumps(snapshot, ensure_ascii=False, indent=2))
        return 0
    if args.cmd == "begin":
        b0 = _load(args.b0_file)
        print(json.dumps(begin_batch(
            root, project=args.project, org=args.org, task_id=args.task_id,
            b0=b0, exec_quote=args.exec_quote,
            exec_quote_ref=args.exec_quote_ref), ensure_ascii=False, indent=2))
        return 0
    if args.cmd == "settle":
        batch = settle(root, project=args.project, org=args.org,
                       token=args.token, task_id=args.task_id,
                       concurrent_tasks=args.concurrent_tasks)
        print(json.dumps(batch, ensure_ascii=False, indent=2))
        return 0
    if args.cmd == "carry":
        print(json.dumps(carry(
            root, project=args.project, org=args.org,
            batch_id=args.batch_id, b_after=args.b_after,
            settle_quote=args.settle_quote,
            settle_quote_ref=args.settle_quote_ref),
            ensure_ascii=False, indent=2))
        return 0
    if args.cmd == "plan":
        b_source = "manual_override"
        balance_source = "manual_override"
        if args.b_avail is None or args.b_plan is None:
            snapshot = latest_probe_snapshot(root, project=args.project, now=cli_now,
                                             org=args.org)
            if args.b_avail is None:
                args.b_avail = snapshot["b_avail"]
                b_source = "ledger_probe_snapshot"
                balance_source = snapshot.get("source")
            if args.read_at is None:
                args.read_at = snapshot["read_at"]
        cumulative_cap = args.cumulative_cap
        if args.new_round and cumulative_cap is None:
            prior = frozen_b_plan(root, project=args.project, org=args.org)
            cumulative_cap = prior  # §2.2 强校验：新轮累计不得超过首轮冻结预算
        result = plan(root, now=cli_now, project=args.project, org=args.org,
                      b_plan=args.b_plan, b_avail=args.b_avail,
                      read_at=args.read_at, target_companies=args.target,
                      new_round=args.new_round,
                      cumulative_cap=cumulative_cap,
                      already_saved=args.saved,
                      max_points_suggest=args.max_points_suggest,
                      balance_source=balance_source,
                      confirm_n=args.confirm_n,
                      exec_quote=args.exec_quote,
                      exec_quote_ref=args.exec_quote_ref,
                      cap_quote=args.cap_quote, cap_quote_ref=args.cap_quote_ref,
                      risk_quote=args.risk_quote, risk_ref=args.risk_ref,
                      sample_ack_quote=args.sample_ack_quote,
                      sample_ack_ref=args.sample_ack_ref)
        result["b_source"] = b_source
        if getattr(args, "format", "human") == "json":
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            print(render_human(result))
        return 3 if result.get("requires_confirmation") else 0
    if args.cmd == "audit-clear":
        record = audit_clear(root, project=args.project, org=args.org,
                             batch_id=args.batch_id,
                             value=Decimal(str(args.value)),
                             basis=args.reason,
                             quote=args.reason,
                             quote_ref=args.quote_ref)
        print(json.dumps(record, ensure_ascii=False, indent=2))
        return 0
    if args.cmd == "status":
        print(json.dumps(read_ledger(root, args.project),
                         ensure_ascii=False, indent=2))
        return 0
    return 2


def main(argv: Optional[List[str]] = None) -> int:
    try:
        return _run(argv)
    except BudgetError as exc:
        print("❌ %s: %s" % (exc.code, exc.reason), file=sys.stderr)
        return 2
    except (OSError, ValueError) as exc:
        print("❌ E_BAD_INPUT: %s" % exc, file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
