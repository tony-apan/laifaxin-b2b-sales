#!/usr/bin/env python3
"""Shared pure helpers for rejecting non-live evidence text."""


NON_LIVE_EVIDENCE_MARKERS = (
    "模拟", "仿真", "离线", "网络桩", "桩数据", "测试桩", "假数据", "伪造", "占位",
    "placeholder", "mock", "stub", "simulated", "simulation", "not live", "not actual",
    "不代表线上", "未实际", "未联网", "未核验", "仅演练", "测试数据", "离线测试",
)


def find_non_live_marker(text):
    """Return the first configured non-live marker found in text, or an empty string."""
    if not isinstance(text, str):
        return ""
    folded = text.casefold()
    return next((marker for marker in NON_LIVE_EVIDENCE_MARKERS if marker.casefold() in folded), "")
