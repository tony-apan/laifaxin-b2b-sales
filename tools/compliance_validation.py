#!/usr/bin/env python3
"""Pure validation for S12 compliance evidence documents."""

import datetime
import hashlib
import json
from pathlib import Path

from evidence_validation import find_non_live_marker


COMPLIANCE_KEYS = ("market", "list_source", "sender_identity", "unsubscribe", "suppression")


def _stable_json_bytes(doc):
    return json.dumps(doc, sort_keys=True, ensure_ascii=True, separators=(",", ":")).encode("utf-8")


def _fresh_iso8601(value, now=None):
    try:
        checked = datetime.datetime.fromisoformat(str(value))
        current = now or datetime.datetime.now(checked.tzinfo)
        if checked.tzinfo is None and current.tzinfo is not None:
            current = current.replace(tzinfo=None)
        age = (current - checked).total_seconds()
        return -300 <= age <= 72 * 3600
    except (TypeError, ValueError):
        return False


def validate_compliance(path_or_doc, expected_project, expected_seq, expected_profile_sha, now=None):
    """Return ``(document, issues, sha256)``; an empty issues list means valid."""
    issues = []
    sha256 = ""
    if isinstance(path_or_doc, (str, bytes, Path)):
        path = Path(path_or_doc)
        try:
            raw = path.read_bytes()
            sha256 = hashlib.sha256(raw).hexdigest()
            doc = json.loads(raw.decode("utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            return None, [f"合规核验JSON读取/解析失败: {path} -> {exc}"], sha256
    else:
        doc = path_or_doc
        try:
            sha256 = hashlib.sha256(_stable_json_bytes(doc)).hexdigest()
        except (TypeError, ValueError) as exc:
            return None, [f"合规核验对象无法序列化: {exc}"], ""

    if not isinstance(doc, dict):
        return None, ["合规核验JSON须为对象"], sha256
    if doc.get("evidence_mode") != "live":
        issues.append("evidence_mode须为字面量live")
    for key, expected in (
        ("project", expected_project),
        ("seq", expected_seq),
        ("profile_sha256", expected_profile_sha),
    ):
        if str(doc.get(key, "")) != str(expected):
            issues.append(f"{key}不匹配")
    if not _fresh_iso8601(doc.get("checked_at", ""), now=now):
        issues.append("checked_at缺失、格式错误、超过72小时或来自未来")

    for key in COMPLIANCE_KEYS:
        item = doc.get(key)
        if not isinstance(item, dict):
            issues.append(f"{key}须为对象")
            continue
        if item.get("status") != "pass":
            issues.append(f"{key}.status须为字面量pass")
        evidence = item.get("evidence")
        if not isinstance(evidence, dict):
            issues.append(f"{key}.evidence须为对象")
            continue
        source = evidence.get("source")
        detail = evidence.get("detail")
        if not isinstance(source, str) or len(source.strip()) < 4:
            issues.append(f"{key}.evidence.source缺失或过短")
        if not isinstance(detail, str) or len(detail.strip()) < 8:
            issues.append(f"{key}.evidence.detail缺失或过短")
        if not _fresh_iso8601(evidence.get("checked_at", ""), now=now):
            issues.append(f"{key}.evidence.checked_at缺失、格式错误、超过72小时或来自未来")
        for field, value in (("source", source), ("detail", detail)):
            marker = find_non_live_marker(value)
            if marker:
                issues.append(f"{key}.evidence.{field}含非实时证据标记『{marker}』")

    return doc, issues, sha256
