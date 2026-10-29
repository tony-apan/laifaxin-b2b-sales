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

# ---- S11 用户核实面板：最小明确字段/取值契约（2026-10-28） ----
# 历史缺口：panel 只出现六个关键词（甚至取值全写“未知”）也会被 finalize_run 当作通过。
# 本契约只做**本地文本自洽校验**：六项都要写成「字段：取值」，取值不能为空、未知、
# 否定或非实时标记；它不证明取值真的来自平台，也不把任何人话包装成密码学证明。
PANEL_FIELDS = ("标签", "客群", "保存", "模板", "配额", "审查")

_PANEL_FIELD_LINE = re.compile(
    r"^[ \t]*(?:[-*+][ \t]*)?(?:\*\*)?[ \t]*(标签|客群|保存|模板|配额|审查)"
    r"[ \t]*(?:\*\*)?[ \t]*[:：][ \t]*(.*?)[ \t]*$",
    re.MULTILINE,
)

# 有界未知/占位值（整值比较，不做无边黑名单）
_UNKNOWN_VALUE_TOKENS = frozenset({
    "-", "--", "—", "?", "？", "无", "空", "暂无", "未知", "未知项", "未核", "未核对",
    "未核实", "待核", "待核对", "待定", "待确认", "未确认", "不适用", "none", "null",
    "n/a", "na", "unknown", "tbd",
})

# 取值中途出现这些词也算该项未核对；先剔除“无未知项/未知数0”等正向汇总，避免误拒。
_UNKNOWN_VALUE_WORDS = re.compile(
    r"(?:未知|暂无|未核|待核|待确认|未确认|未核实|unknown|(?<![a-z])n/?a(?![a-z])|none|null|tbd)",
    re.IGNORECASE,
)
_POSITIVE_ZERO = re.compile(
    r"(?:无未知项|无未核对项|未知数[ \t]*[:：=]?[ \t]*0|未核对项[ \t]*[:：=]?[ \t]*0|0[ \t]*(?:个|项)?未知)"
)
_VERIFIED_SUFFIX = re.compile(r"(?:已核对|已确认|已复核|已核实|已检查|核对无误|确认无误)[ \t。.;；]*$")
# 通用肯定语只证明“点过”，不能充当某一项的取值；汇总词只允许独立汇总行，不在字段值内生效。
_AFFIRMATION_WORDS = re.compile(
    r"(?:确认无误|核对无误|已核对|已确认|已复核|已核实|已检查|确认|通过|合格|无误|"
    r"(?<![a-z])(?:pass(?:ed)?|yes|ok|okay|done|fine|success)(?![a-z]))",
    re.IGNORECASE,
)
# 仅指向别处/省略的取值（“同上”“见汇总”等）同样没有实际内容；有真实数字时仍保留。
_REFERENCE_ONLY = re.compile(
    r"(?:同上|同前|如上|"
    r"详见(?:汇总|上文|明细)?行?|参见(?:汇总|上文|明细)?行?|"
    r"见(?:汇总|明细|上文|上)行?|略)"
)
_NEGATIVE_VALUE_WORDS = re.compile(
    r"(?:未挂|未设置|未配置|未生效|未完成|未成功|未通过|不通过|失败|异常|错误|"
    r"不符|不一致|缺少|缺失|待补|无法确认|不确定)"
)


def _normalize_panel_value(raw):
    value = str(raw or "").strip().strip("\u0060*_ ")
    value = _VERIFIED_SUFFIX.sub("", value)
    return value.strip(" \t\u0060*_。.;；,，、()（）[]【】")


def _panel_value_content(value):
    """字段值去掉正向汇总/通用肯定语后的实质内容；为空说明该项没有实际取值。"""
    content = _POSITIVE_ZERO.sub("", value)
    content = _AFFIRMATION_WORDS.sub("", content)
    content = _REFERENCE_ONLY.sub("", content)
    return content.strip(" \t\u0060*_。.;；,，、()（）[]【】")


def validate_panel_text(text):
    """校验 S11 核实面板：返回 (是否通过, 中文原因)。只做本地文本契约，不证明真实性。"""
    if not isinstance(text, str) or not text.strip():
        return False, "核实面板为空"
    fields, duplicates = {}, []
    for match in _PANEL_FIELD_LINE.finditer(text):
        name, value = match.group(1), match.group(2)
        if name in fields:
            duplicates.append(name)
        else:
            fields[name] = value
    missing = [name for name in PANEL_FIELDS if name not in fields]
    if missing:
        return False, "核实面板缺字段：" + "、".join(missing) + "（须逐项写成『字段：已核对取值』）"
    if duplicates:
        return False, "核实面板字段重复：" + "、".join(sorted(set(duplicates)))
    problems = []
    for name in PANEL_FIELDS:
        raw = fields[name]
        value = _normalize_panel_value(raw)
        if not value:
            problems.append(f"{name} 取值为空或只写“已核对”")
            continue
        content = _panel_value_content(value)
        if not content:
            problems.append(f"{name} 只有汇总/核对声明，没有实际取值：{raw.strip()!r}")
            continue
        if not re.search(r"[0-9A-Za-z\u4e00-\u9fff]", content):
            problems.append(f"{name} 取值没有可核对内容")
            continue
        if content.casefold() == name.casefold():
            problems.append(f"{name} 只重复字段名，没有取值")
            continue
        scan = _POSITIVE_ZERO.sub("", value).strip()
        if scan.casefold() in _UNKNOWN_VALUE_TOKENS:
            problems.append(f"{name} 取值是未知/占位：{raw.strip()!r}")
            continue
        if scan and _UNKNOWN_VALUE_WORDS.search(scan):
            problems.append(f"{name} 取值含未知/未核对：{raw.strip()!r}")
            continue
        if _NEGATIVE_VALUE_WORDS.search(value):
            problems.append(f"{name} 取值是否定/未完成：{raw.strip()!r}")
            continue
    if problems:
        return False, "；".join(problems)
    normalized = [_normalize_panel_value(fields[name]).casefold() for name in PANEL_FIELDS]
    if len(set(normalized)) == 1:
        return False, f"六个字段取值完全相同（{normalized[0]!r}），不能作为六项核对结果"
    return True, ""

