#!/usr/bin/env python3
"""Shared pure helpers for rejecting non-live evidence text.

★单一真源：所有"非实时证据"标记都写在这里；`compliance_validation.py`、
`finalize_audit.py`、`finalize_run.py` 共用同一份，避免各处口径漂移。

2026-09-09 对抗审查补强：原先缺 `test` / `fake` / `dummy` / `demo` 等英文措辞，
实测可用 "fake source data" + "this is test data not real" 通过 live 证据闸门洗白合规核验。
"""
import re

NON_LIVE_EVIDENCE_MARKERS = (
    "模拟", "仿真", "离线", "网络桩", "桩数据", "测试桩", "假数据", "伪造", "占位",
    "placeholder", "mock", "stub", "simulated", "simulation", "not live", "not actual",
    "不代表线上", "未实际", "未联网", "未核验", "仅演练", "测试数据", "离线测试",
    # 2026-09-09 补：常见英文"非真实"措辞
    "dummy", "demo data", "sample data", "not real", "unreal", "sandbox",
    "pretend", "artificial", "not verified", "unverified", "test-only", "for testing",
)

# 独立词标记：用词边界，避免误伤 "latest"（含 test）、"attestation" 等正常词
_WORD_MARKERS = (
    re.compile(r"(?<![a-z0-9])test(?:ing|s)?(?![a-z0-9])", re.IGNORECASE),
    re.compile(r"(?<![a-z0-9])fake(?:d|s)?(?![a-z0-9])", re.IGNORECASE),
    re.compile(r"(?<![a-z0-9])todo(?![a-z0-9])", re.IGNORECASE),
    re.compile(r"(?<![a-z0-9])x{3,}(?![a-z0-9])", re.IGNORECASE),
)


def find_non_live_marker(text):
    """Return the first configured non-live marker found in text, or an empty string."""
    if not isinstance(text, str):
        return ""
    folded = text.casefold()
    hit = next((marker for marker in NON_LIVE_EVIDENCE_MARKERS if marker.casefold() in folded), "")
    if hit:
        return hit
    for pattern in _WORD_MARKERS:
        match = pattern.search(text)
        if match:
            return match.group(0)
    return ""
