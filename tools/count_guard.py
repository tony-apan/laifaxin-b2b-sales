#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""保存数量的机器推导闸门（S5）。

铁律：selectTotal 不是自由输入，只能由「S4 收口证据 + 预算上界 + 数量模式」推导。
本模块只做纯函数校验，不联网、不读凭据、不写盘。

证据来源（count_evidence）必须包含：
  threshold_page / pool_total / evidence_mode / page_rows
  page_rows 中必须有 threshold_page 那一页的实际 returned；末页不足 10 按实际数收口。
预算上界：calibrated 必须绑定 save_budget 的 ready 账簿行（budget_ledger），
  以 confirm_n 为唯一数量、n_cons/n_est/batch_points_upper 为硬上界；
  budget_points/max_points 只作遗留兼容，不能再替代账簿。
  e/p 必须带 source_ref/version，kind=user_estimate 不能作为上界。
模式：
  sample         未校准时只允许 1 家样本；
  calibrated     必须绑定 save_budget ready 台账，以 confirm_n 为数量并受 Y/n_cons/n_est/batch 上界约束；
  explicit_small 用户显式小批量（<=50），必须有 sample_ack + 原话，且仍受 Y/B 约束；
  probe          首轮成本探针（<=100 家，默认 100），必须有 sample_ack + 原话；
"""
from __future__ import annotations

import hashlib
import json
import math
from decimal import Decimal, ROUND_CEILING
from pathlib import Path
from typing import Any, Dict, List, Optional

COUNT_MODES = ("sample", "calibrated", "explicit_small", "probe")
STRICT_MODES = ("live", "strict", "rigorous", "严谨", "严格")


class CountError(ValueError):
    def __init__(self, code: str, reason: str):
        super().__init__(reason)
        self.code = code
        self.reason = reason


def _fail(code: str, reason: str) -> None:
    raise CountError(code, reason)


def _as_decimal(value: Any, label: str) -> Decimal:
    if isinstance(value, bool) or value is None:
        _fail("E_COUNT_BAD_NUMBER", "%s 必须是数字，实际 %r" % (label, value))
    try:
        d = Decimal(str(value))
    except Exception:
        _fail("E_COUNT_BAD_NUMBER", "%s 必须是数字，实际 %r" % (label, value))
    if not d.is_finite():
        _fail("E_COUNT_BAD_NUMBER", "%s 必须是有限数字" % label)
    return d


def _strict_int(value: Any, label: str, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        _fail("E_COUNT_BAD_NUMBER", "%s 必须是整数，实际 %r" % (label, value))
    if value < minimum:
        _fail("E_COUNT_BAD_NUMBER", "%s 必须 >= %d，实际 %d" % (label, minimum, value))
    return value


def _canonical(value: Any) -> str:
    return hashlib.sha256(json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
        allow_nan=False).encode("utf-8")).hexdigest()


def _budget_value(doc: Any, label: str) -> Decimal:
    if isinstance(doc, dict):
        if not str(doc.get("source_ref") or "").strip():
            _fail("E_BUDGET_UNRESOLVED", "%s 缺 source_ref" % label)
        if not str(doc.get("version") or "").strip():
            _fail("E_BUDGET_UNRESOLVED", "%s 缺 version" % label)
        raw = doc.get("points", doc.get("value"))
        return _as_decimal(raw, label)
    return _as_decimal(doc, label)


def _coefficient(doc: Any, label: str) -> Decimal:
    if not isinstance(doc, dict):
        _fail("E_COUNT_COEFFICIENT", "%s 必须是带来源的对象" % label)
    kind = str(doc.get("kind") or "").strip()
    if kind == "user_estimate":
        _fail("E_COUNT_COEFFICIENT", "%s 是用户估值，不能作为预算上界" % label)
    if not str(doc.get("source_ref") or "").strip():
        _fail("E_COUNT_COEFFICIENT", "%s 缺 source_ref" % label)
    if not str(doc.get("version") or "").strip():
        _fail("E_COUNT_COEFFICIENT", "%s 缺 version" % label)
    return _as_decimal(doc.get("value"), label)


def audit_window(evidence: Dict[str, Any]) -> Dict[str, Any]:
    """校验 S4 收口证据，返回 Y 与证据摘要。"""
    if not isinstance(evidence, dict):
        _fail("E_COUNT_EVIDENCE_REQUIRED", "缺 count_evidence（S4 收口证据）")
    mode = str(evidence.get("evidence_mode") or "").strip()
    if mode not in STRICT_MODES:
        _fail("E_COUNT_EVIDENCE_MODE", "evidence_mode 必须是 live/strict 严谨口径，实际 %r" % mode)
    boundary = evidence.get("boundary") if isinstance(evidence.get("boundary"), dict) else {}
    threshold = evidence.get("threshold_page", boundary.get("critical_page"))
    threshold = _strict_int(threshold, "threshold_page", 1)
    data = evidence.get("data") if isinstance(evidence.get("data"), dict) else {}
    pool = evidence.get("pool_total", data.get("total"))
    pool = _strict_int(pool, "pool_total", 1)
    rows = evidence.get("page_rows")
    if rows is None and isinstance(evidence.get("window"), dict):
        rows = evidence["window"].get("page_rows")
    if rows is None:
        rows = evidence.get("rows")
    if isinstance(rows, dict):
        rows = rows.get("page_rows") or rows.get("rows")
    if not isinstance(rows, list) or not rows:
        _fail("E_COUNT_EVIDENCE_REQUIRED", "缺 page_rows（必须有逐页实测）")
    by_page: Dict[int, Dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        page = row.get("page")
        returned = row.get("returned", row.get("total"))
        if isinstance(page, int) and not isinstance(page, bool) and isinstance(returned, int) and not isinstance(returned, bool):
            by_page[page] = row
    if threshold not in by_page:
        _fail("E_COUNT_EVIDENCE_REQUIRED", "page_rows 缺临界页 %d 的实测" % threshold)
    if max(by_page) < threshold:
        _fail("E_COUNT_EVIDENCE_REQUIRED", "临界页 %d 超出已采样页" % threshold)
    returned = by_page[threshold].get("returned", by_page[threshold].get("total"))
    returned = _strict_int(returned, "临界页 returned", 1)
    if returned > 10:
        _fail("E_COUNT_EVIDENCE_MODE", "临界页 returned=%d 超过每页 10 家" % returned)
    y = min(threshold * 10, pool)
    if returned < 10:
        y = min(y, (threshold - 1) * 10 + returned)
    if y <= 0:
        _fail("E_COUNT_Y_ZERO", "S4 证据推导出的 Y=0")
    return {
        "y": y, "threshold_page": threshold, "pool_total": pool,
        "threshold_returned": returned, "evidence_mode": mode,
        "page_rows_sha256": _canonical(rows),
    }


def _budget(plan: Dict[str, Any]) -> Dict[str, Any]:
    est = plan.get("estimation") or {}
    e = _coefficient(est.get("estimated_emails_per_company"),
                     "estimated_emails_per_company")
    p = _coefficient(est.get("estimated_points_per_email"),
                     "estimated_points_per_email")
    unit = e * p
    if unit <= 0:
        _fail("E_COUNT_COEFFICIENT", "e*p 必须 >0")
    budget = _budget_value(plan.get("budget_points"), "budget_points")
    cap = _budget_value(plan.get("max_points"), "max_points")
    if budget <= 0 or cap <= 0:
        _fail("E_BUDGET_EXHAUSTED", "budget_points/max_points 必须 >0")
    effective = min(budget, cap)
    n_budget = int((effective / unit).to_integral_value(rounding="ROUND_FLOOR"))
    if n_budget <= 0:
        _fail("E_BUDGET_EXHAUSTED", "预算不足以保存 1 家（B=%s, e*p=%s）" % (effective, unit))
    return {"e": e, "p": p, "unit": unit, "budget": budget, "cap": cap,
            "effective_budget": effective, "n_budget": n_budget}


def _ledger(plan: Dict[str, Any], unit: Decimal) -> Dict[str, Any]:
    """校验 S5 预算台账 ready 行；预算数量只能来自 confirm_n。"""
    ledger = plan.get("budget_ledger")
    if not isinstance(ledger, dict):
        _fail("E_LEDGER_REQUIRED",
              "calibrated 必须带 budget_ledger（save_budget plan 的 ready 结果），"
              "禁止用 budget_points 手工替代")
    if str(ledger.get("status") or "") != "ready":
        _fail("E_LEDGER_NOT_READY", "budget_ledger.status 必须是 ready")
    if str(ledger.get("org_hash") or "").strip() == "":
        _fail("E_LEDGER_INVALID", "budget_ledger 缺 org_hash")
    if str(ledger.get("round_id") or "").strip() == "":
        _fail("E_LEDGER_INVALID", "budget_ledger 缺 round_id")
    if not str(ledger.get("exec_quote_ref") or "").strip():
        _fail("E_LEDGER_NOT_CONFIRMED", "budget_ledger 缺用户确认引用 exec_quote_ref")
    confirmed = _strict_int(ledger.get("confirm_n"), "budget_ledger.confirm_n", 1)
    n_cons = _strict_int(ledger.get("n_cons"), "budget_ledger.n_cons", 1)
    n_est = _strict_int(ledger.get("n_est"), "budget_ledger.n_est", 1)
    if n_cons > n_est:
        _fail("E_LEDGER_INVALID", "budget_ledger.n_cons > n_est")
    b_plan = _as_decimal(ledger.get("b_plan"), "budget_ledger.b_plan")
    spent = _as_decimal(ledger.get("spent_all"), "budget_ledger.spent_all")
    left = _as_decimal(ledger.get("budget_left"), "budget_ledger.budget_left")
    risk_ack = ledger.get("risk_ack")
    if not isinstance(risk_ack, bool):
        _fail("E_LEDGER_INVALID", "budget_ledger.risk_ack 必须是 bool，实际 %r" % (risk_ack,))
    upper = _as_decimal(ledger.get("per_company_upper"), "budget_ledger.per_company_upper")
    batch_upper = _as_decimal(ledger.get("batch_points_upper"),
                              "budget_ledger.batch_points_upper")
    if b_plan - spent != left:
        _fail("E_LEDGER_INVALID",
              "budget_ledger 对账不平：b_plan-spent_all=%s != budget_left=%s"
              % (b_plan - spent, left))
    if b_plan <= 0 or left < 0 or spent < 0:
        _fail("E_LEDGER_INVALID", "budget_ledger 预算/已花/剩余不能为负（b_plan 必须 >0）")
    if upper <= 0 or batch_upper <= 0:
        _fail("E_LEDGER_INVALID", "budget_ledger 上界必须 >0")
    # v18：per_company_upper 是台账历史单客成本上界，也是 N_cons 的分母。
    # 若本次计划单价 e*p 高于它，N_cons 会被高估，预算可能不够；必须 fail closed。
    if unit > upper:
        _fail("E_LEDGER_UPPER_TOO_LOW",
              "e*p=%s > 台账 per_company_upper=%s，预算分母偏小，不能算数量"
              % (unit, upper))
    if confirmed > n_cons and not risk_ack:
        _fail("E_LEDGER_QUANTITY_EXCEEDS_CONS",
              "confirm_n=%d > n_cons=%d，且没有 risk_ack" % (confirmed, n_cons))
    if confirmed > n_est:
        _fail("E_LEDGER_QUANTITY_EXCEEDS_EST",
              "confirm_n=%d > n_est=%d" % (confirmed, n_est))
    if Decimal(confirmed) * unit > batch_upper:
        _fail("E_BUDGET_EXCEEDED",
              "confirm_n=%d × 单价 %s > 台账批上界 %s" % (confirmed, unit, batch_upper))
    return {
        "confirm_n": confirmed, "n_cons": n_cons, "n_est": n_est,
        "risk_ack": risk_ack,
        "b_plan": b_plan, "spent_all": spent, "budget_left": left,
        "per_company_upper": upper, "batch_points_upper": batch_upper,
        "org_hash": str(ledger.get("org_hash")),
        "round_id": str(ledger.get("round_id")),
        "exec_quote_ref": str(ledger.get("exec_quote_ref")),
        "ledger_hash": _canonical(ledger),
    }


def verify_ledger_file(root: Any, plan: Dict[str, Any]) -> None:
    """只读核对：plan 里的 budget_ledger 必须真实存在于仓库账簿。"""
    ledger = (plan or {}).get("budget_ledger")
    if not isinstance(ledger, dict):
        _fail("E_LEDGER_REQUIRED", "缺 budget_ledger")
    try:
        import save_budget  # 延迟导入，避免纯函数测试依赖
        rows = save_budget.read_ledger(Path(root))
    except Exception as exc:
        _fail("E_LEDGER_UNAVAILABLE", "读预算账簿失败：%s" % exc)
    wanted = {
        "project": str((plan or {}).get("project") or ""),
        "org_hash": str(ledger.get("org_hash") or ""),
        "confirm_n": ledger.get("confirm_n"),
        "b_plan": str(ledger.get("b_plan")),
        "spent_all": str(ledger.get("spent_all")),
        "budget_left": str(ledger.get("budget_left")),
        "per_company_upper": str(ledger.get("per_company_upper")),
        "n_cons": ledger.get("n_cons"),
        "n_est": ledger.get("n_est"),
        "batch_points_upper": str(ledger.get("batch_points_upper")),
        "exec_quote_ref": str(ledger.get("exec_quote_ref") or ""),
        "round_id": str(ledger.get("round_id") or ""),
        "risk_ack": ledger.get("risk_ack"),
    }
    for row in rows:
        if row.get("kind") != "plan" or row.get("state") != "ready":
            continue
        payload = row.get("payload") or {}
        if (str(row.get("project") or "") == wanted["project"]
                and str(row.get("org_hash") or "") == wanted["org_hash"]
                and payload.get("confirm_n") == wanted["confirm_n"]
                and str(payload.get("b_plan")) == wanted["b_plan"]
                and str(payload.get("spent_all")) == wanted["spent_all"]
                and str(payload.get("budget_left")) == wanted["budget_left"]
                and str(payload.get("per_company_upper")) == wanted["per_company_upper"]
                and payload.get("n_cons") == wanted["n_cons"]
                and payload.get("n_est") == wanted["n_est"]
                and str(payload.get("batch_points_upper")) == wanted["batch_points_upper"]
                and str(payload.get("round_id") or "") == wanted["round_id"]
                and str(payload.get("exec_quote_ref") or "") == wanted["exec_quote_ref"]
                and payload.get("risk_ack") is wanted["risk_ack"]):
            return
    _fail("E_LEDGER_ROW_NOT_FOUND",
          "budget_ledger 在 .local/budget-ledger.jsonl 中找不到同内容 ready 行")


def derive(evidence: Dict[str, Any], plan: Dict[str, Any], *,
           mode: str, explicit_count: Optional[int] = None,
           sample_ack: str = "", quote: str = "") -> Dict[str, Any]:
    window = audit_window(evidence)
    budget = _budget(plan)
    mode = str(mode or "").strip()
    if mode not in COUNT_MODES:
        _fail("E_COUNT_MODE", "count_mode 必须是 %s，实际 %r" % (COUNT_MODES, mode))
    y = window["y"]
    n_budget = budget["n_budget"]
    ledger = _ledger(plan, budget["unit"]) if plan.get("budget_ledger") is not None else None
    if mode == "sample":
        n = min(1, y, n_budget)
    elif mode == "probe":
        if explicit_count is None:
            _fail("E_COUNT_EXPLICIT", "探针必须给 explicit_count")
        explicit_count = _strict_int(explicit_count, "explicit_count", 1)
        if explicit_count > 100:
            _fail("E_COUNT_EXPLICIT", "探针上限 100，实际 %d" % explicit_count)
        if not str(sample_ack or "").strip() or not str(quote or "").strip():
            _fail("E_SAMPLE_ACK_REQUIRED", "探针必须同时有 sample_ack 和用户原话")
        n = min(explicit_count, y, n_budget)
    elif mode == "explicit_small":
        if explicit_count is None:
            _fail("E_COUNT_EXPLICIT", "显式小批量必须给 explicit_count")
        explicit_count = _strict_int(explicit_count, "explicit_count", 1)
        if explicit_count > 50:
            _fail("E_COUNT_EXPLICIT", "显式小批量上限 50，实际 %d" % explicit_count)
        if not str(sample_ack or "").strip() or not str(quote or "").strip():
            _fail("E_SAMPLE_ACK_REQUIRED", "显式小批量必须同时有 sample_ack 和用户原话")
        n = min(explicit_count, y, n_budget)
    else:
        if ledger is None:
            _fail("E_LEDGER_REQUIRED",
                  "calibrated 必须绑定 save_budget 的 ready 台账，禁止用 budget_points 手工算数量")
        n = ledger["confirm_n"]
        if n > y:
            _fail("E_LEDGER_QUANTITY_EXCEEDS_Y",
                  "台账确认 %d 家 > S4 证据 Y=%d 家，不能超卖" % (n, y))
    if n <= 0:
        _fail("E_BUDGET_EXHAUSTED", "按证据/预算推导可存 0 家")
    points = int((Decimal(n) * budget["unit"]).to_integral_value(rounding=ROUND_CEILING))
    if points > budget["effective_budget"]:
        _fail("E_BUDGET_EXCEEDED",
              "P=%d 超过可用预算=%s" % (points, budget["effective_budget"]))
    if ledger is not None:
        if points > ledger["batch_points_upper"]:
            _fail("E_BUDGET_EXCEEDED",
                  "P=%d 超过台账批上界=%s" % (points, ledger["batch_points_upper"]))
        if points > ledger["budget_left"]:
            _fail("E_BUDGET_EXCEEDED",
                  "P=%d 超过台账剩余预算=%s" % (points, ledger["budget_left"]))
        if n > ledger["n_cons"] and not ledger.get("risk_ack"):
            _fail("E_LEDGER_QUANTITY_EXCEEDS_CONS",
                  "数量 %d > 台账保守上限 %d，且没有 risk_ack" % (n, ledger["n_cons"]))
    material = {
        "evidence": window, "mode": mode, "explicit_count": explicit_count,
        "sample_ack": bool(str(sample_ack or "").strip()),
        "y": y, "n_budget": n_budget, "select_total": n,
        "e": str(budget["e"]), "p": str(budget["p"]),
        "effective_budget": str(budget["effective_budget"]),
        "points": points,
        "ledger_hash": ledger["ledger_hash"] if ledger else None,
    }
    return {
        "select_total": n, "y": y, "n_budget": n_budget, "points": points,
        "mode": mode, "evidence": window,
        "unit": str(budget["unit"]), "effective_budget": str(budget["effective_budget"]),
        "ledger_hash": ledger["ledger_hash"] if ledger else None,
        "ledger": ledger,
        "count_hash": _canonical(material),
    }


def validate_plan(plan: Dict[str, Any]) -> Dict[str, Any]:
    """confirm/execute 重算并校验五处数量一致；不信任 plan 自报。"""
    if not isinstance(plan, dict):
        _fail("E_COUNT_EVIDENCE_REQUIRED", "plan 不是对象")
    evidence = plan.get("count_evidence")
    mode = plan.get("count_mode")
    explicit = plan.get("explicit_count")
    ack = plan.get("sample_ack") or ""
    quote = plan.get("count_quote") or ""
    derived = derive(evidence, plan, mode=mode, explicit_count=explicit,
                     sample_ack=ack, quote=quote)
    n = derived["select_total"]
    checks = {
        "plan.selectTotal": plan.get("selectTotal"),
        "plan.derived_select_total": plan.get("derived_select_total"),
        "wire.selectTotal": (plan.get("wire_payload") or {}).get("selectTotal"),
        "estimation.selectTotal": (plan.get("estimation") or {}).get("selectTotal"),
    }
    for label, got in checks.items():
        if got != n:
            _fail("E_SELECT_TOTAL_DERIVED_MISMATCH",
                  "%s=%r，按证据应为 %d" % (label, got, n))
    if plan.get("count_hash") != derived["count_hash"]:
        _fail("E_COUNT_HASH_MISMATCH", "count_hash 与证据重算不一致")
    if plan.get("budget_ledger") is not None:
        if plan.get("budget_ledger_hash") != derived.get("ledger_hash"):
            _fail("E_LEDGER_HASH_MISMATCH", "budget_ledger_hash 与台账重算不一致")
    return derived
