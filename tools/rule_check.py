#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""S5 真实 payload / plan / 预算的纯函数严格校验（Guard V2 C 组）。

不联网、不读凭据、不承载其他节点规则。实现 GUARD-FIX-V2 §4.3/§4.4：
  * WIRE_FIELDS：唯一 18 字段白名单 + 固定值。
  * validate_select_total：严格 type(value) is int 且 >0。
  * check_save：类型 → 局部 alias 一致性(count) → plan 绑定 → 预算双查。
  * estimate_points：Decimal 定点，P=ceil(N*e*p)。
  * validate_filters：四区真实 schema；顶层 exclude 冒充 → E_FILTER_SCHEMA。
  * canonical_scope：query_scope_key 规范化（仅等价表达归一）。
"""
from __future__ import annotations

import hashlib
import json
import math
import re
from decimal import Decimal, ROUND_CEILING
from typing import Any, Dict, List, Optional, Sequence, Tuple

SCHEMA_VERSION = 2

# §4.3 唯一 18 字段 wire 白名单。
WIRE_FIELDS = (
    "companyTags", "companyOption", "companySave", "contactTags",
    "contactOption", "contactVerifyStatus", "contactPositions",
    "contactExcludes", "contactMaxCount", "contactSave", "selectKeys",
    "selectSort", "selectTotal", "selectOption", "filters", "filter",
    "keyword", "logic",
)
FIXED_VALUES: Dict[str, Any] = {
    "companyOption": "nothing",
    "companySave": True,
    "contactOption": "nothing",
    "contactPositions": [],
    "contactExcludes": [],
    "contactSave": True,
    "selectKeys": [],
    "selectSort": {},
    "selectOption": "front",
    "filter": {},
}
CONTACT_MAX_TIERS = (3, 6, 9)
VERIFY_STATUS_DRAFT = ["valid", "unkown"]  # 平台原拼写 unkown 保留
FOUR_REGIONS = ("CN", "TW", "HK", "MO")
KNOWN_INPUT_BANNED = ("weak_fit", "user_confirmed_count", "batch_plan",
                      "dry_run", "skip_cap", "force", "debug")

RULES_EXCERPT_FILES = ("RULES.md", "CORE-POINTS.md")


class RuleCheckError(ValueError):
    def __init__(self, code: str, reason: str, **extra: Any):
        super().__init__(reason)
        self.code = code
        self.reason = reason
        self.extra = extra


def _fail(code: str, reason: str, **extra: Any) -> None:
    raise RuleCheckError(code, reason, **extra)


def canonical_hash(value: Any) -> str:
    return hashlib.sha256(json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
        allow_nan=False).encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# selectTotal / count
# ---------------------------------------------------------------------------

def validate_select_total(payload: Any) -> int:
    """selectTotal 必填、严格 int 且 >0；缺失/bool/float/str/0/负 → 拒。"""
    if not isinstance(payload, dict):
        _fail("E_PLAN_PAYLOAD_MISMATCH", "payload 必须是 object")
    if "selectTotal" not in payload:
        _fail("E_SELECT_TOTAL_REQUIRED", "payload 缺 selectTotal")
    value = payload["selectTotal"]
    if type(value) is not int:
        _fail("E_SELECT_TOTAL_INVALID",
              "selectTotal 必须严格 int，收到 %s" % type(value).__name__)
    if value <= 0:
        _fail("E_SELECT_TOTAL_INVALID", "selectTotal 必须 >0，收到 %r" % value)
    return value


def check_count_alias(payload: Dict[str, Any], select_total: int) -> None:
    """旧 count 仅相等性校验；不作为缺失回退。"""
    if "count" not in payload:
        return
    count = payload["count"]
    if type(count) is not int or count <= 0 or count != select_total:
        _fail("E_COUNT_MISMATCH",
              "count 与 selectTotal 不一致: count=%r selectTotal=%r" % (count, select_total))


# ---------------------------------------------------------------------------
# 18 字段 wire
# ---------------------------------------------------------------------------

def validate_wire(payload: Dict[str, Any]) -> Dict[str, Any]:
    """严格 18 字段白名单 + 固定值 + 数组/结构类型。"""
    for key in ("exclude", "sort"):
        if isinstance(payload, dict) and key in payload:
            _fail("E_FILTER_SCHEMA", "顶层 %s 不是有效字段，须用 filters/selectSort 表达" % key)
    unknown = [key for key in payload if key not in WIRE_FIELDS]
    if unknown:
        _fail("E_PLAN_PAYLOAD_MISMATCH", "payload 含白名单外字段: %s" % ",".join(sorted(unknown)))
    missing = [key for key in WIRE_FIELDS if key not in payload]
    if missing:
        _fail("E_PLAN_PAYLOAD_MISMATCH", "payload 缺 wire 字段: %s" % ",".join(missing))
    for key, expected in FIXED_VALUES.items():
        actual = payload[key]
        if isinstance(expected, str):
            if actual != expected:
                _fail("E_PLAN_PAYLOAD_MISMATCH",
                      "%s 固定发送 %r，收到 %r" % (key, expected, actual))
        elif isinstance(expected, bool):
            if type(actual) is not bool or actual is not expected:
                _fail("E_PLAN_PAYLOAD_MISMATCH", "%s 必须严格 bool %r" % (key, expected))
        else:
            if actual != expected:
                _fail("E_PLAN_PAYLOAD_MISMATCH",
                      "%s 固定发送 %r" % (key, expected))
    if not isinstance(payload["companyTags"], list) or not payload["companyTags"]:
        _fail("E_PLAN_PAYLOAD_MISMATCH", "companyTags 须为非空 plan 实际 ID 数组")
    if not isinstance(payload["contactTags"], list) or not payload["contactTags"]:
        _fail("E_PLAN_PAYLOAD_MISMATCH", "contactTags 须为非空 plan 实际 ID 数组")
    status = payload["contactVerifyStatus"]
    if not isinstance(status, list) or not status:
        _fail("E_PLAN_PAYLOAD_MISMATCH", "contactVerifyStatus 须为非空数组")
    elif not all(isinstance(item, str) for item in status):
        _fail("E_PLAN_PAYLOAD_MISMATCH", "contactVerifyStatus 须为字符串数组")
    cmc = payload["contactMaxCount"]
    if type(cmc) is not int or cmc not in CONTACT_MAX_TIERS:
        _fail("E_PLAN_PAYLOAD_MISMATCH",
              "contactMaxCount 须为确认档位 %s" % (CONTACT_MAX_TIERS,))
    if not isinstance(payload["keyword"], str) or not payload["keyword"].strip():
        _fail("E_PLAN_PAYLOAD_MISMATCH", "keyword 必须是当前来源原句/已选域名")
    if payload["logic"] not in ("and", "or"):
        _fail("E_PLAN_PAYLOAD_MISMATCH", "logic 须为 and/or")
    validate_filters(payload["filters"], logic=payload["logic"])
    # TASK-20261027：档位通过校验后一并返回，供 plan 层作为唯一真源绑定。
    return {"selectTotal": validate_select_total(payload),
            "contactMaxCount": cmc}


# ---------------------------------------------------------------------------
# filters（四区真实 schema）
# ---------------------------------------------------------------------------

def validate_filters(filters: Any, logic: str = "and") -> List[Dict[str, Any]]:
    """filters 必须是真实 schema 列表；or 致 exclude 失效 → 拒。"""
    if filters is None:
        filters = []
    if not isinstance(filters, list):
        _fail("E_FILTER_SCHEMA", "filters 必须是数组")
    for item in filters:
        if not isinstance(item, dict):
            _fail("E_FILTER_SCHEMA", "filter 项必须是 object")
        for key in ("property", "operator", "value", "values", "valueType"):
            if key not in item:
                _fail("E_FILTER_SCHEMA", "filter 项缺 %s（不以空值掩盖）" % key)
        if item.get("property") != "country_code":
            _fail("E_FILTER_SCHEMA", "未知筛选 property: %r" % item.get("property"))
        if item.get("operator") not in ("exclude", "include"):
            _fail("E_FILTER_SCHEMA", "未知筛选 operator: %r" % item.get("operator"))
        values = item.get("values")
        if not isinstance(values, list) or not values:
            _fail("E_FILTER_SCHEMA", "values 须为非空数组")
        if item.get("valueType") != "select":
            _fail("E_FILTER_SCHEMA", "valueType 须为 select")
        if not isinstance(item.get("value"), str):
            _fail("E_FILTER_SCHEMA", "value 须为字符串")
    has_exclude = any(item.get("operator") == "exclude" for item in filters)
    has_include = any(item.get("operator") == "include" for item in filters)
    if has_exclude and has_include:
        _fail("E_FILTER_SCHEMA", "country include 与 exclude 冲突")
    if has_exclude and logic == "or":
        _fail("E_FILTER_SCHEMA", "logic=or 使 exclude 失效")
    return filters


def normalize_filters(filters: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """确定性排序：集合语义等价的不同 values 排序归一为同一表达。"""
    normalized = []
    for item in filters:
        values = sorted({str(v) for v in item.get("values", [])})
        normalized.append({
            "property": item.get("property"), "operator": item.get("operator"),
            "value": str(item.get("value") or ""), "values": values,
            "valueType": item.get("valueType"),
        })
    return sorted(normalized, key=lambda x: json.dumps(x, ensure_ascii=False,
                                                       sort_keys=True))


def default_four_region_filters(regions: Sequence[str] = FOUR_REGIONS) -> List[Dict[str, Any]]:
    return [{"property": "country_code", "operator": "exclude", "value": "",
             "values": sorted({str(r) for r in regions}), "valueType": "select"}]


# ---------------------------------------------------------------------------
# 估算与预算
# ---------------------------------------------------------------------------

def _as_decimal(value: Any, label: str) -> Decimal:
    if isinstance(value, Decimal):
        if value.is_finite() and value > 0:
            return value
        _fail("E_ESTIMATE_SOURCE", "%s 必须为正有限数: %r" % (label, value))
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        _fail("E_ESTIMATE_SOURCE", "%s 必须是数值/数值串" % label)
    try:
        number = Decimal(str(value))
    except Exception:
        _fail("E_ESTIMATE_SOURCE", "%s 不是可解析数值: %r" % (label, value))
    if not number.is_finite() or number <= 0:
        _fail("E_ESTIMATE_SOURCE", "%s 必须为正有限数: %r" % (label, value))
    return number


def _sourced_number(doc: Any, label: str, *, allow_missing: bool = False) -> Optional[Decimal]:
    """点数值必须携带 source_ref+version；缺失 → E_BUDGET_UNRESOLVED。"""
    if doc is None:
        if allow_missing:
            return None
        _fail("E_BUDGET_UNRESOLVED", "%s 缺失" % label)
    if isinstance(doc, dict):
        if not str(doc.get("source_ref") or "").strip() or not str(doc.get("version") or "").strip():
            _fail("E_BUDGET_UNRESOLVED", "%s 缺来源(source_ref/version)" % label)
        return _as_decimal(doc.get("points" if label == "budget_points" else "value"
                                   if label != "budget_points" else "points"), label)
    return _as_decimal(doc, label)


def estimate_points(select_total: int, e_per_company: Any, p_per_email: Any) -> Dict[str, Decimal]:
    """E = N*e（邮箱）；P = ceil(N*e*p)（点）。Decimal 定点。"""
    n = Decimal(int(select_total))
    e = _as_decimal(e_per_company, "estimated_emails_per_company")
    p = _as_decimal(p_per_email, "estimated_points_per_email")
    emails = n * e
    points = (n * e * p).to_integral_value(rounding=ROUND_CEILING)
    return {"emails": emails, "points": points}


def _budget_value(doc: Any, label: str) -> Optional[Decimal]:
    if doc is None:
        return None
    if isinstance(doc, dict):
        if not str(doc.get("source_ref") or "").strip() or not str(doc.get("version") or "").strip():
            _fail("E_BUDGET_UNRESOLVED", "%s 缺来源(source_ref/version)" % label)
        raw = doc.get("points", doc.get("value"))
        return _as_decimal(raw, label)
    return _as_decimal(doc, label)


def check_budget(select_total: int, estimation: Dict[str, Any],
                 budget_points: Any, max_points: Any) -> Dict[str, Any]:
    """confirm/execute 双重检查：P>max_points → E_MAX_POINTS_EXCEEDED；
    P>B → E_BUDGET_EXCEEDED；B/max 缺失或无来源 → E_BUDGET_UNRESOLVED。"""
    e_doc = (estimation or {}).get("estimated_emails_per_company")
    p_doc = (estimation or {}).get("estimated_points_per_email")
    e = _as_decimal((e_doc or {}).get("value") if isinstance(e_doc, dict) else e_doc,
                    "estimated_emails_per_company")
    p = _as_decimal((p_doc or {}).get("value") if isinstance(p_doc, dict) else p_doc,
                    "estimated_points_per_email")
    computed = estimate_points(select_total, e, p)
    points = computed["points"]
    budget = _budget_value(budget_points, "budget_points")
    cap = _budget_value(max_points, "max_points")
    if budget is None or cap is None:
        _fail("E_BUDGET_UNRESOLVED", "budget_points/max_points 缺失或无来源")
    if points > cap:
        _fail("E_MAX_POINTS_EXCEEDED",
              "P=%s 超过 max_points=%s" % (points, cap), points=points, cap=cap)
    if points > budget:
        _fail("E_BUDGET_EXCEEDED",
              "P=%s 超过 budget=%s" % (points, budget), points=points, budget=budget)
    return {"emails": computed["emails"], "points": points,
            "budget": budget, "cap": cap}


def check_coefficient_sources(estimation: Dict[str, Any]) -> None:
    """N/e/p 三单位各自有值、来源和版本（E_ESTIMATE_SOURCE）。"""
    if not isinstance(estimation, dict):
        _fail("E_ESTIMATE_SOURCE", "estimation 必须是 object")
    for key in ("estimated_emails_per_company", "estimated_points_per_email"):
        doc = estimation.get(key)
        if not isinstance(doc, dict):
            _fail("E_ESTIMATE_SOURCE", "%s 须为带来源的 object" % key)
        if not str(doc.get("source_ref") or "").strip():
            _fail("E_ESTIMATE_SOURCE", "%s 缺 source_ref" % key)
        if not str(doc.get("version") or "").strip():
            _fail("E_ESTIMATE_SOURCE", "%s 缺 version" % key)
        _as_decimal(doc.get("value"), key)


# ---------------------------------------------------------------------------
# 原话数量核验（保存/存/入库 … N 家/条公司）
# ---------------------------------------------------------------------------

_CN_DIGITS = {"零": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4,
              "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}
_SAVE_WORDS = ("保存", "存", "入库", "收录")
_UNIT_COMPANY = ("家", "条公司", "家公司", "家客户")
_NUMBER_RE = re.compile(r"[0-9][0-9,，,\s]*[0-9]|[0-9]")
_BATCH_RE = re.compile(r"第\s*[0-9零一二三四五六七八九十]+\s*批")
_EMAIL_RE = re.compile(r"[0-9][0-9,，,]*\s*(?:个?邮箱|封)")


def _cn_number_to_int(text: str) -> Optional[int]:
    text = text.strip()
    if not text:
        return None
    if text.isdigit():
        return int(text)
    if text == "十":
        return 10
    total = 0
    for char in text:
        if char in _CN_DIGITS:
            total = total * 10 + _CN_DIGITS[char]
        else:
            return None
    return total if total > 0 else None


def extract_save_count(quote: Any) -> Optional[int]:
    """从授权原话提取公司数：只匹配『保存/存/入库…N 家(公司)』。

    多个候选数字（含日期/批次/邮箱数）→ None（歧义交给上层确认）。
    """
    if not isinstance(quote, str) or not quote.strip():
        return None
    matches: List[Tuple[int, int]] = []
    for match in _NUMBER_RE.finditer(quote):
        start, end = match.span()
        window = quote[max(0, start - 8):min(len(quote), end + 6)]
        if _BATCH_RE.search(quote[max(0, start - 4):end]) or _EMAIL_RE.search(window):
            continue
        if not any(word in window for word in _SAVE_WORDS):
            continue
        unit_window = quote[end:min(len(quote), end + 4)]
        if not any(unit in unit_window for unit in _UNIT_COMPANY):
            continue
        digits = match.group(0).replace(",", "").replace("，", "").replace(" ", "")
        value = _cn_number_to_int(digits)
        if value is not None:
            matches.append((value, start))
    for cn in ("六千二百", "三千", "五百"):
        pass  # 中文千级数字走下方通用解析
    cn_re = re.compile(r"[零一二三四五六七八九十百千万两]+")
    for match in cn_re.finditer(quote):
        start, end = match.span()
        window = quote[max(0, start - 8):min(len(quote), end + 6)]
        if not any(word in window for word in _SAVE_WORDS):
            continue
        unit_window = quote[end:min(len(quote), end + 4)]
        if not any(unit in unit_window for unit in _UNIT_COMPANY):
            continue
        value = _cn_number_to_int_complex(match.group(0))
        if value is not None:
            matches.append((value, start))
    unique = {value for value, _ in matches}
    if len(unique) == 1:
        return matches[0][0]
    if len(unique) > 1:
        return None
    return None


# v3（2026-10-27）：卡面已写清 N 家时，用户只回「确认」也应放行。
# 但纯确认原话必须**整句就是确认**、且不含任何数字/别的动作词，
# 数字由卡面 plan 绑定并在 confirmed plan 里留痕（count_bound_by=card）。
_PLAIN_CONFIRM_RE = re.compile(
    r"^\s*(?:确认|确认保存|确定)\s*(?:吧|一下|啦)?\s*[。.!！~～]*\s*$", re.I)


def plain_numeric_save_count(quote: Any) -> Optional[int]:
    """S5 卡上下文里的纯 ASCII 正整数字符串 N（AC1，2026-10-27）。

    只认 strip 后整串为 [1-9][0-9]* 的原话；0/负数/小数/多数字/带单位/
    疑问/否定/中文数字一律 None（不是保存数量授权）。仅限 S5 保存确认
    上下文使用（卡面已展示 N 时）；激活等其他动作不得复用本函数。
    """
    if not isinstance(quote, str):
        return None
    q = quote.strip()
    if not re.fullmatch(r"[1-9][0-9]*", q):
        return None
    return int(q)


def is_plain_save_confirm(quote: Any) -> bool:
    """无数字纯确认原话判定（只给 S5 保存确认用，不用于激活）。"""
    if not isinstance(quote, str):
        return False
    q = " ".join(quote.split()).strip()
    if not q:
        return False
    if re.search(r"[0-9零一二三四五六七八九十百千万两]", q):
        return False
    if re.search(r"(激活|发信|建序列|加人|模板|删除|取消|暂停|不确认|不要|别|等等|稍等)", q):
        return False
    return bool(_PLAIN_CONFIRM_RE.match(q))


_CN_MAGNITUDE = {"十": 10, "百": 100, "千": 1000, "万": 10000}


def _cn_number_to_int_complex(text: str) -> Optional[int]:
    text = text.strip()
    if not text:
        return None
    if text.isdigit():
        return int(text)
    total = 0
    current = 0
    for char in text:
        if char in _CN_DIGITS:
            current = _CN_DIGITS[char] if current == 0 and char != "零" else (current * 10 + _CN_DIGITS[char] if char != "零" else current)
        elif char in _CN_MAGNITUDE:
            magnitude = _CN_MAGNITUDE[char]
            if current == 0:
                current = 1
            total += current * magnitude
            current = 0
        else:
            return None
    total += current
    return total if total > 0 else None


# ---------------------------------------------------------------------------
# plan / payload 绑定
# ---------------------------------------------------------------------------

def check_save(payload: Any, plan: Any, dependencies: Optional[Dict[str, Any]] = None
               ) -> Dict[str, Any]:
    """完整检查：类型 → 局部 alias → plan → 预算。返回 {selectTotal,...}。"""
    if not isinstance(payload, dict):
        _fail("E_PLAN_PAYLOAD_MISMATCH", "payload 必须是 object")
    for key in KNOWN_INPUT_BANNED:
        if key in payload:
            _fail("E_PLAN_PAYLOAD_MISMATCH", "未知输入字段 %s 不免检" % key)
    select_total = validate_select_total(payload)
    check_count_alias(payload, select_total)
    validate_wire(payload)
    if not isinstance(plan, dict):
        _fail("E_PLAN_REQUIRED", "缺少已确认 plan")
    if plan.get("status") != "confirmed":
        _fail("E_PLAN_NOT_CONFIRMED", "plan 未确认（须 confirm 流程产出）")
    # R2-B：execute/confirm 必经路径重校档位；plan 缺省仅兼容 wire=3 legacy。
    plan_top = plan.get("contactMaxCount", 3)
    if type(plan_top) is not int or plan_top != payload.get("contactMaxCount"):
        _fail("E_CONTACT_TIER_MISMATCH",
              "contactMaxCount 不一致：plan=%r wire=%r"
              % (plan_top, payload.get("contactMaxCount")))
    expected = plan.get("wire_payload")
    if not isinstance(expected, dict):
        _fail("E_PLAN_PAYLOAD_MISMATCH", "plan 缺 wire_payload")
    if canonical_hash(expected) != canonical_hash(payload):
        _fail("E_PLAN_PAYLOAD_MISMATCH", "payload 与已确认 plan 的 wire 不一致")
    estimation = plan.get("estimation") or {}
    check_coefficient_sources(estimation)
    check_budget(select_total, estimation, plan.get("budget_points"),
                 plan.get("max_points"))
    deps = dependencies or {}
    dep_sha = plan.get("dependency_sha256")
    if dependencies is not None and dep_sha and canonical_hash(deps) != dep_sha:
        _fail("E_PLAN_DEPENDENCY_CHANGED", "依赖快照与 plan 绑定不一致")
    return {"selectTotal": select_total}


def canonical_scope(workspace_ref: str, product_id: str, generation_id: str,
                    selection_id: str, keyword: str,
                    filters: Sequence[Dict[str, Any]], logic: str,
                    sort: Any = None) -> Dict[str, Any]:
    """query_scope_key：不含 batch/plan/标签/selectTotal/时间。"""
    return {
        "workspace_context_ref": str(workspace_ref),
        "platform_product_id": str(product_id),
        "generation_id": str(generation_id),
        "selection_id": str(selection_id),
        "keyword": str(keyword),
        "filters": normalize_filters(list(filters or [])),
        "logic": str(logic),
        "selectSort": sort if sort is not None else {},
    }


def scope_key(scope: Dict[str, Any]) -> str:
    return canonical_hash(scope)
