#!/usr/bin/env python3
"""Strict parser for the two-line credential handoff format.

值本身保持严格（禁空白/控制字符/null/多段 token）；但真实用户会手拼粘贴
（2026-09-23 真机截图：`accesstoken:` 键独占一行、值在下一行；`orgId：z44422` 全角冒号），
旧解析器只认 `key=value` 单行，把这些打成 "unknown line"，AI 随之反复索要用户已给的值。
故分隔符与分行做容错：`=`/`:`/`：` 均可；键可独占一行、值取下一非空行；键大小写不敏感；
键值首尾空白剥掉。解析失败的兜底原则不变：宁可拒绝也不猜值。
"""

import unicodedata


class Invalid(ValueError):
    """Credential input violates the accepted format."""


_ALIASES = {
    "accesstoken": "token",
    "token": "token",
    "orgid": "org",
    "org": "org",
}

_SEPARATORS = ("=", ":", "：")


def _alias_for(key):
    canonical = _ALIASES.get(key) or _ALIASES.get(key.lower())
    return canonical


def _split_line(line):
    """按第一个合法分隔符切开；返回 (key, value, had_separator)，均已 strip。"""
    for sep in _SEPARATORS:
        if sep in line:
            key, _, value = line.partition(sep)
            return key.strip(), value.strip(), True
    return line.strip(), "", False


def _decode(blob, max_bytes):
    if isinstance(blob, str):
        try:
            raw = blob.encode("utf-8")
        except UnicodeEncodeError as exc:
            raise Invalid("credentials are not valid UTF-8") from exc
    elif isinstance(blob, (bytes, bytearray)):
        raw = bytes(blob)
    else:
        raise Invalid("credentials must be bytes or text")
    if len(raw) > max_bytes:
        raise Invalid("credentials exceed the byte limit")
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise Invalid("credentials are not valid UTF-8") from exc


def _valid_value(value):
    return bool(value) and value.lower() != "null" and all(
        not char.isspace() and not unicodedata.category(char).startswith("C")
        for char in value
    )


def parse_credentials(blob, max_bytes=8192):
    """Return ``(token, org_id)`` from exactly one token/org key pair."""
    text = _decode(blob, max_bytes)
    found = {}
    pending = None  # 已见键、等下一非空行作为值的槽位
    for raw_line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        line = raw_line.strip()
        if not line:
            continue
        key, value, had_separator = _split_line(line)
        if pending is not None:
            if had_separator and _alias_for(key) is not None:
                # 键后没值、下一行又是键 → 悬空键缺值，禁止把下一个键行吞成值
                raise Invalid("credential key line is missing its value on the next line")
            canonical = pending
            pending = None
            value = line  # 悬空键的值就是这一整行（已 strip），不再重新切分
        else:
            canonical = _alias_for(key)
            if canonical is None:
                raise Invalid("unknown credential key" if had_separator else "unknown non-empty credential line")
        if canonical in found:
            raise Invalid("duplicate credential key")
        if not value:
            pending = canonical
            continue
        if not _valid_value(value):
            raise Invalid("credential value is empty, null, or contains whitespace/control characters")
        found[canonical] = value
    if pending is not None:
        raise Invalid("credential value is empty, null, or contains whitespace/control characters")
    if set(found) != {"token", "org"}:
        if "token" in found and "org" not in found:
            raise Invalid("orgId line is missing (only accesstoken was provided)")
        if "org" in found and "token" not in found:
            raise Invalid("accesstoken line is missing (only orgId was provided)")
        raise Invalid("exactly one token and one org key are required")
    segments = found["token"].split("&")
    if len(segments) != 3 or not all(segments):
        raise Invalid("token must have exactly three non-empty segments")
    return found["token"], found["org"]
