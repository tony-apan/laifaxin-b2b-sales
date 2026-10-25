#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""S11 收口证明校验（三审 S1-8/S2-4）：只认 finalize_run 写的收口字段，不认手写 status: S11。

finalize_run 成功收口时写入 operation-record：
  s11_finalized_at: ISO 时间
  s11_manifest_sha256: 64 位十六进制（verification manifest 文件字节 sha256）
本模块供 flow_orchestrator --resume-s12 与 activate_sequence 在签发/激活前复用；
缺字段、格式错、超过 max_age_hours 一律返回问题列表，调用方 fail-closed。
"""
import datetime
import re

_HEX64 = re.compile(r"[0-9a-f]{64}")


def check_s11_closure(record_meta, max_age_hours=24):
    """返回中文问题列表（空=收口证明有效）。只读，不修改任何文件。"""
    if not isinstance(record_meta, dict):
        return ["record 元数据不可读——无法确认 S11 收口"]
    issues = []
    raw_at = str(record_meta.get("s11_finalized_at") or "").strip().strip('"')
    if not raw_at:
        issues.append("record 缺 s11_finalized_at——S11 不是由 finalize_run 真实收口（手写状态不算）")
    else:
        try:
            when = datetime.datetime.fromisoformat(raw_at)
        except ValueError:
            issues.append(f"s11_finalized_at 格式无效: {raw_at!r}")
            when = None
        if when is not None:
            now = datetime.datetime.now()
            age = (now - when).total_seconds()
            if age < -300:
                issues.append("s11_finalized_at 来自未来——拒绝")
            elif age > max_age_hours * 3600:
                issues.append(f"S11 收口已超过 {max_age_hours} 小时——请重跑 finalize_run 重新收口")
    raw_sha = str(record_meta.get("s11_manifest_sha256") or "").strip().strip('"')
    if not raw_sha:
        issues.append("record 缺 s11_manifest_sha256——无法证明验证证据来自 live manifest")
    elif not _HEX64.fullmatch(raw_sha):
        issues.append(f"s11_manifest_sha256 形状非法: {raw_sha!r}")
    return issues
