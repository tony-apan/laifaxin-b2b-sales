#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""S2 客群来源闸门（v3）：客群只能逐条来自本次平台返回。

用户裁决（不得违背）：
- 客群推演只能在来发信平台；本地不得生成、选择、暗示任何具体客群/买家类型。
- 平台失败（success=false / 异常超时 / 成功但列表空 / 只拿到旧客群）一律不推进客群
  状态、不执行依赖客群的 S3+ 动作、不本地填充；停在可重试状态。
- 质量不高可主动补推，最多 2 轮（首轮 + 1 次补推），每轮记录轮次/来源/状态/条数/原因。

本模块只做判定与记录（纯函数 + 注入式客户端），不联网、不写文件，便于单测。
客户端协议：call(api_path, payload) -> dict，网络/超时异常直接抛出。
"""
import re
import time

SOURCE_API = "profile/inference-segment-list"
GENERATE_API = "profile/inference-segment-generate"

# 五种情形（B 节）
OUTCOME_OK = "ok"
OUTCOME_API_FAILURE = "api_failure"
OUTCOME_EXCEPTION = "exception"
OUTCOME_EMPTY = "empty"
OUTCOME_STALE = "stale_only"

BLOCKED_OUTCOMES = frozenset({OUTCOME_API_FAILURE, OUTCOME_EXCEPTION, OUTCOME_EMPTY, OUTCOME_STALE})

# 质量判定（J 节三种明确信号）
QUALITY_OK = "ok"
QUALITY_EMPTY = "empty"
QUALITY_OVERLAP = "overlap"
QUALITY_OFF_TOPIC = "off_topic"
QUALITY_BAD = frozenset({QUALITY_EMPTY, QUALITY_OVERLAP, QUALITY_OFF_TOPIC})

MAX_ROUNDS = 2  # 首轮 + 最多 1 次补推

# 失败细分（P1①）：不得把「登录/token 失效」「网络异常」「平台慢未落库」混成一类
FAILURE_AUTH = "auth"
FAILURE_NETWORK = "network"
FAILURE_SLOW = "slow_not_landed"
FAILURE_EMPTY = "empty"
FAILURE_STALE = "stale"
FAILURE_NONE = ""
_AUTH_HINTS = ("token", "登录", "失效", "过期", "401", "403", "unauthor", "expired", "认证")
_DIAGNOSIS = {
    FAILURE_AUTH: "登录状态可能已失效（重新获取两行后再试，不是您的操作问题）",
    FAILURE_NETWORK: "网络/接口异常（不是账号问题）",
    FAILURE_SLOW: "平台慢/结果未落库（已轮询仍为空，稍后重试）",
    FAILURE_EMPTY: "平台本次返回为空",
    FAILURE_STALE: "只拿到历史遗留的旧结果",
}

# 给用户的一句人话（不得出现工具名/状态码）
RETRY_LINE = "平台这次没推出来，我稍后重试，或您稍等再点一次。"
RETRY_NOTICE = "我按「{desc}」理解推的，这次结果不太贴，我再试一次。"
EXHAUSTED_LINE = "这次两轮都没推出合适的买家类型，我先不往下走，免得拿不准的名单浪费您的点数。"
EXITS = (
    "换一种说法描述用途，我再推一次",
    "稍后重试",
    "先从别的方向小批试",
)

def _as_text(value):
    return "" if value is None else str(value).strip()


def segment_name(segment):
    if not isinstance(segment, dict):
        return ""
    for key in ("segment_name", "name", "segment"):
        text = _as_text(segment.get(key))
        if text:
            return text
    return ""


def normalize_name(name):
    """归一化后比较：空白/标点/大小写不参与（同义由调用方给出别名）。"""
    return re.sub(r"[\s\-_/·、,，.。()（）\[\]]+", "", _as_text(name)).lower()


def names_overlap(left, right):
    a, b = normalize_name(left), normalize_name(right)
    if not a or not b:
        return False
    if a == b:
        return True
    return len(a) >= 4 and len(b) >= 4 and (a in b or b in a)


def _matches_any(name, pool):
    return any(names_overlap(name, other) for other in pool if _as_text(other))


def _segments_of(response):
    if not isinstance(response, dict):
        return None
    data = response.get("data")
    if isinstance(data, list):
        return data
    if isinstance(data, dict) and isinstance(data.get("list"), list):
        return data["list"]
    return None


def _declared_product_id(segment):
    if not isinstance(segment, dict):
        return ""
    for key in ("product_id", "productId"):
        text = _as_text(segment.get(key))
        if text:
            return text
    return ""


def freshness(segments, product_id, baseline_names=()):
    """返回 (fresh, basis)。

    basis: product_id=按返回的产品id核对；name_baseline=按历史客群名核对；
    unverified=平台既没带产品id、本地也没有历史基线（无法证明是旧客群，记为不可核验）。
    """
    fresh = []
    basis = "unverified"
    for segment in segments:
        declared = _declared_product_id(segment)
        if declared:
            basis = "product_id"
            if str(declared) == str(product_id):
                fresh.append(segment)
            continue
        if baseline_names:
            if basis == "unverified":
                basis = "name_baseline"
            if not _matches_any(segment_name(segment), baseline_names):
                fresh.append(segment)
            continue
        fresh.append(segment)
    return fresh, basis


def assess_quality(segments, denied_names=(), accepted_names=(), off_topic_names=()):
    """质量判定：返回 (quality, detail_names)。

    三种「不高」信号：返回为空 / 与已否定或已选客群高度重复 / 明显跑偏（调用方给出跑偏名单）。
    本函数只判定，不生成也不补条。
    """
    names = [segment_name(s) for s in segments if segment_name(s)]
    if not segments or not names:
        return QUALITY_EMPTY, []
    repeated = [n for n in names if _matches_any(n, denied_names) or _matches_any(n, accepted_names)]
    if len(repeated) == len(names):
        return QUALITY_OVERLAP, repeated
    if off_topic_names and all(_matches_any(n, off_topic_names) for n in names):
        return QUALITY_OFF_TOPIC, names
    return QUALITY_OK, []


def classify_round(response, product_id, baseline_names=(), denied_names=(),
                   accepted_names=(), off_topic_names=(), waited_out=False):
    """对一次 list 响应做五情形 + 质量判定；不修改、不补条。"""
    base = {
        "source_api": SOURCE_API,
        "product_id": str(product_id),
        "returned_count": 0,
        "accepted_count": 0,
        "segments": [],
        "freshness_basis": "",
        "quality": QUALITY_EMPTY,
        "quality_detail": [],
        "failure_kind": FAILURE_NONE,
    }
    if not isinstance(response, dict):
        base.update(outcome=OUTCOME_API_FAILURE, call_status="failed_network",
                    failure_kind=FAILURE_NETWORK, reason="响应不是对象")
        return base
    if response.get("success") is not True:
        message = _as_text(response.get("message")) or "接口未返回成功"
        kind = diagnose(message)
        base.update(outcome=OUTCOME_API_FAILURE,
                    call_status="failed_auth" if kind == FAILURE_AUTH else "failed_network",
                    failure_kind=kind, reason=message)
        return base
    raw = _segments_of(response)
    base["call_status"] = "success"
    if raw is None:
        base.update(outcome=OUTCOME_EMPTY,
                    call_status="polling_timeout" if waited_out else "success",
                    failure_kind=FAILURE_SLOW if waited_out else FAILURE_EMPTY,
                    reason="响应无列表字段")
        return base
    base["returned_count"] = len(raw)
    if not raw:
        base.update(outcome=OUTCOME_EMPTY,
                    call_status="polling_timeout" if waited_out else "success",
                    failure_kind=FAILURE_SLOW if waited_out else FAILURE_EMPTY,
                    reason="轮询后列表仍为空" if waited_out else "返回列表为空")
        return base
    fresh, basis = freshness(raw, product_id, baseline_names)
    base["freshness_basis"] = basis
    if not fresh:
        base.update(outcome=OUTCOME_STALE, call_status="success",
                    failure_kind=FAILURE_STALE,
                    reason="只拿到非本次的旧客群", segments=[])
        return base
    # 保留本次平台返回，不虚称删除；逐项标记已否定/已选的重复项。
    fresh = [dict(item, repeated_by_user=(
        _matches_any(segment_name(item), denied_names) or
        _matches_any(segment_name(item), accepted_names))) for item in fresh]
    quality, detail = assess_quality(fresh, denied_names, accepted_names, off_topic_names)
    base.update(outcome=OUTCOME_OK, segments=fresh, accepted_count=len(fresh),
                quality=quality, quality_detail=detail, reason="")
    return base


def diagnose(message):
    """把平台 message 归因为登录失效/网络异常（只做提示，不改变用户话术）。"""
    text = _as_text(message).lower()
    return FAILURE_AUTH if any(hint in text for hint in _AUTH_HINTS) else FAILURE_NETWORK


def _poll(call, payload, waits, interval, sleep):
    """轮询 list；返回 (response, error, waited_out)。

    waited_out=True 表示「一直成功但一直空」=平台慢/未落库，不能等同于接口失败。
    """
    response = {}
    for attempt in range(max(1, waits)):
        try:
            response = call(SOURCE_API, payload)
        except Exception as exc:  # 网络/超时/解析异常
            return None, "{}: {}".format(type(exc).__name__, exc), False
        if isinstance(response, dict) and response.get("success") is not True:
            return response, "", False
        if _segments_of(response):
            return response, "", False
        if attempt + 1 < waits:
            sleep(interval)
    return response, "", True


def _failed_round(status, failure_kind=FAILURE_NETWORK):
    return {"outcome": OUTCOME_EXCEPTION if status == "exception" else OUTCOME_API_FAILURE,
            "call_status": status, "failure_kind": failure_kind, "segments": [],
            "returned_count": 0, "accepted_count": 0, "quality": QUALITY_EMPTY,
            "source_api": SOURCE_API, "quality_detail": []}


def infer_with_retry(call, product_id, product_desc_zh, baseline_names=(), denied_names=(),
                     accepted_names=(), off_topic_names=(), max_rounds=MAX_ROUNDS,
                     poll_waits=6, poll_interval=10, sleep=time.sleep, notice_sink=None,
                     notice_desc=""):
    """调用平台推演并按质量最多补推 1 轮；每次调用都记录轮次与原因。

    返回 dict：outcome/quality/segments/rounds/advance_allowed/user_message...
    advance_allowed 仅在「本次返回、质量合格」时为 True；其余一律 False（可重试状态）。
    """
    ceiling = max(1, min(int(max_rounds or 1), MAX_ROUNDS))
    payload = {"product_id": product_id}
    rounds = []
    notices = []
    last = {}
    retry_reason = ""
    desc = _as_text(notice_desc or product_desc_zh)[:40]
    for index in range(1, ceiling + 1):
        record = {"round": index, "source_api": SOURCE_API, "call_status": "failed",
                  "returned_count": 0, "accepted_count": 0, "retry": index > 1,
                  "retry_reason": retry_reason if index > 1 else ""}
        try:
            generated = call(GENERATE_API, payload)
        except Exception as exc:
            record.update(call_status="exception", failure_kind=FAILURE_NETWORK,
                          reason="generate {}: {}".format(type(exc).__name__, exc))
            rounds.append(record)
            last = _failed_round("exception", FAILURE_NETWORK)
            break
        if not isinstance(generated, dict) or generated.get("success") is not True:
            reason = _as_text(generated.get("message")) if isinstance(generated, dict) else "生成接口无响应"
            kind = diagnose(reason) if reason else FAILURE_NETWORK
            record.update(call_status="failed_auth" if kind == FAILURE_AUTH else "failed_network",
                          failure_kind=kind, reason=reason or "生成接口未返回成功")
            rounds.append(record)
            last = _failed_round("failed_auth" if kind == FAILURE_AUTH else "failed_network", kind)
            break
        response, error, waited_out = _poll(call, payload, poll_waits, poll_interval, sleep)
        if error:
            record.update(call_status="exception", failure_kind=FAILURE_NETWORK, reason=error)
            rounds.append(record)
            last = _failed_round("exception", FAILURE_NETWORK)
            break
        verdict = classify_round(response, product_id, baseline_names, denied_names,
                                 accepted_names, off_topic_names, waited_out=waited_out)
        record.update(call_status=verdict["call_status"], returned_count=verdict["returned_count"],
                      accepted_count=verdict["accepted_count"], outcome=verdict["outcome"],
                      quality=verdict["quality"], failure_kind=verdict.get("failure_kind", ""),
                      reason=verdict.get("reason", ""))
        rounds.append(record)
        last = verdict
        bad_quality = verdict["outcome"] == OUTCOME_EMPTY or (
            verdict["outcome"] == OUTCOME_OK and verdict["quality"] in QUALITY_BAD)
        if not bad_quality or index >= ceiling:
            break
        retry_reason = verdict["quality"] if verdict["outcome"] == OUTCOME_OK else verdict["outcome"]
        notice = RETRY_NOTICE.format(desc=desc or "您说的用途")
        notices.append(notice)
        if notice_sink is not None:
            notice_sink(notice)
    outcome = last.get("outcome", OUTCOME_EXCEPTION)
    quality = last.get("quality", QUALITY_EMPTY)
    advance = outcome == OUTCOME_OK and quality == QUALITY_OK
    result = {
        "outcome": outcome,
        "quality": quality,
        "segments": list(last.get("segments") or []),
        "rounds": rounds,
        "source_api": SOURCE_API,
        "call_status": last.get("call_status", "failed"),
        "returned_count": last.get("returned_count", 0),
        "accepted_count": last.get("accepted_count", 0),
        "raw_returned_count": last.get("returned_count", 0),
        "repeated_count": sum(bool(s.get("repeated_by_user")) for s in last.get("segments") or []),
        "quality_detail": list(last.get("quality_detail") or []),
        "failure_kind": last.get("failure_kind", ""),
        "diagnosis": _DIAGNOSIS.get(last.get("failure_kind", ""), ""),
        # 展示条数=本次平台返回且被接受（过滤历史遗留）的条数；不得混入旧结果
        "display_count": len(last.get("segments") or []),
        "retried": len(rounds) > 1,
        "retry_reason": retry_reason,
        "notices": notices,
        "advance_allowed": advance,
        "dependent_work_allowed": advance,
    }
    if advance:
        result["user_message"] = ""
        result["exits"] = []
    else:
        exhausted = len(rounds) >= 2 and outcome in (OUTCOME_OK, OUTCOME_EMPTY)
        result["user_message"] = EXHAUSTED_LINE if exhausted else RETRY_LINE
        result["exits"] = list(EXITS) if exhausted else []
    return result


def evidence_record(result):
    """可落盘的审计记录：轮次/来源接口/调用成功状态/返回条数/是否补推及原因。"""
    return {
        "source_api": result.get("source_api", SOURCE_API),
        "failure_kind": result.get("failure_kind", ""),
        "display_count": result.get("display_count", 0),
        "returned_count": result.get("returned_count", 0),
        "raw_returned_count": result.get("raw_returned_count", 0),
        "repeated_count": result.get("repeated_count", 0),
        "rounds": [
            {
                "round": item.get("round"),
                "source_api": item.get("source_api", SOURCE_API),
                "call_status": item.get("call_status", "failed"),
                "failure_kind": item.get("failure_kind", ""),
                "returned_count": item.get("returned_count", 0),
                "accepted_count": item.get("accepted_count", 0),
                "retry": bool(item.get("retry")),
                "retry_reason": item.get("retry_reason", ""),
                "reason": item.get("reason", ""),
            }
            for item in result.get("rounds", [])
        ],
        "advance_allowed": bool(result.get("advance_allowed")),
    }
