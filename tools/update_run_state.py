#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""运行状态记录器：安全更新 operation-record.md frontmatter（本地，不调用平台）。

每个节点成功后由对应工具调用，确保换机/onboard 看到真实当前状态。
"""
import argparse
import datetime
import hashlib
import json
import re
import sys
import time
from pathlib import Path

VALID_STATES = (
    "S0", "S0a_PRODUCT_PROFILE", "S1", "S2", "S3", "S4", "S5", "S6",
    "S7", "S8", "S9", "S9a", "S10", "S11", "S12", "ERROR_BLOCKED",
)


ALLOWED_TRANSITIONS = {
    "S0": {"S0", "S0a_PRODUCT_PROFILE"},
    "S0a_PRODUCT_PROFILE": {"S0a_PRODUCT_PROFILE", "S1"},
    "S1": {"S1", "S2", "S3"},  # S1→S3=有精准网址快速路径
    "S2": {"S2", "S3"}, "S3": {"S3", "S4"}, "S4": {"S4", "S5"},
    "S5": {"S5", "S6"}, "S6": {"S6", "S7", "S8"}, "S7": {"S7", "S8"},
    "S8": {"S8", "S9"}, "S9": {"S9", "S10"}, "S9a": {"S9a", "S10"},
    "S10": {"S10", "S11"}, "S11": {"S11", "S12", "S10"},
    "S12": {"S12", "S11"}, "ERROR_BLOCKED": {"ERROR_BLOCKED"},
}


def read_meta(path):
    meta = {}; lines = Path(path).read_text(encoding="utf-8").splitlines()
    if not lines or lines[0].strip() != "---": return meta
    for line in lines[1:]:
        if line.strip() == "---": break
        if ":" in line and not line.lstrip().startswith("#"):
            key, value = line.split(":", 1); meta[key.strip()] = value.strip().strip('"')
    return meta


def read_status(path):
    return read_meta(path).get("status", "")


def record_project_key(path):
    meta = {}
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if ":" in line and not line.lstrip().startswith("#"):
            key, value = line.split(":", 1)
            if key.strip() in ("operator_key", "product_key"):
                meta[key.strip()] = value.strip().strip('"')
    if meta.get("operator_key") and meta.get("product_key"):
        return f"{meta['operator_key']}/{meta['product_key']}"
    return ""


def record_matches_project(path, project_key):
    try:
        return record_project_key(path) == str(project_key)
    except OSError:
        return False


def require_state(path, allowed_states):
    p = Path(path)
    if not p.is_file():
        raise ValueError(f"operation-record 不存在: {p}")
    current = read_status(p)
    if current not in set(allowed_states):
        raise ValueError(f"当前流程状态={current or '(缺)'}，要求={list(allowed_states)}；禁止跳步写操作")
    return current


def update_frontmatter(path, updates, expected_states=None, allow_recovery=False):
    p = Path(path)
    if not p.is_file():
        raise ValueError(f"operation-record 不存在: {p}")
    text = p.read_text(encoding="utf-8")
    current = read_status(p)
    if expected_states and current not in set(expected_states):
        raise ValueError(f"状态转换不合法: 当前={current or '(缺)'}，期望前置={list(expected_states)}，目标={updates.get('status')}")
    target = str(updates.get("status") or current)
    if target != "ERROR_BLOCKED" and target not in ALLOWED_TRANSITIONS.get(current, set()) and not (current == "ERROR_BLOCKED" and allow_recovery):
        raise ValueError(f"状态机禁止跳步: {current or '(缺)'} → {target}")
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        raise ValueError("operation-record 缺 frontmatter")
    end = next((i for i, line in enumerate(lines[1:], 1) if line.strip() == "---"), None)
    if end is None:
        raise ValueError("operation-record frontmatter 未闭合")
    seen = set()
    out = ["---"]
    for line in lines[1:end]:
        key = line.split(":", 1)[0].strip() if ":" in line else ""
        if key in updates:
            out.append(f"{key}: {updates[key]}")
            seen.add(key)
        else:
            out.append(line)
    for key, value in updates.items():
        if key not in seen:
            out.append(f"{key}: {value}")
    out.extend(["---"] + lines[end + 1:])
    rendered = "\n".join(out) + "\n"
    tmp = p.with_name(p.name + ".tmp-state")
    tmp.write_text(rendered, encoding="utf-8")
    tmp.replace(p)


def main():
    ap = argparse.ArgumentParser(description="更新项目 operation-record 状态（换机续接真源）")
    ap.add_argument("--record", required=True)
    ap.add_argument("--expected-state", action="append", default=[], choices=VALID_STATES, help="允许的前置状态；可重复传")
    ap.add_argument("--project", default="", help="ERROR_BLOCKED恢复时必填稳定项目键")
    ap.add_argument("--recovery-evidence", default="", help="ERROR_BLOCKED恢复时必填 recovery-manifest.json")
    ap.add_argument("--state", required=True, choices=VALID_STATES)
    ap.add_argument("--next-state", default="")
    ap.add_argument("--profile-version", default="")
    ap.add_argument("--profile-sha256", default="")
    args = ap.parse_args()
    if args.state in ("S4", "S11", "S12"):
        print("❌ S4/S11/S12 是受保护收口状态，通用CLI不可推进；分别使用 finalize_audit.py / finalize_run.py / activate_sequence.py")
        return 2
    updates = {
        "status": args.state,
        "next_state": args.next_state,
        "updated": time.strftime("%Y-%m-%d"),
    }
    if args.profile_version:
        updates["profile_version"] = f'"{args.profile_version}"'
    if args.profile_sha256:
        if not re.fullmatch(r"[0-9a-f]{64}", args.profile_sha256):
            print("❌ --profile-sha256 须为64位十六进制")
            return 2
        updates["profile_sha256"] = f'"{args.profile_sha256}"'
    allow_recovery = False
    try:
        current_meta = read_meta(args.record)
        if current_meta.get("status") == "ERROR_BLOCKED":
            evidence = Path(args.recovery_evidence)
            if not evidence.is_file() or not args.project:
                print("❌ ERROR_BLOCKED恢复须带 --project 与 --recovery-evidence <recovery-manifest.json>"); return 2
            try: manifest = json.loads(evidence.read_text(encoding="utf-8"))
            except Exception as exc: print(f"❌ recovery manifest无效: {exc}"); return 2
            expected_target = current_meta.get("next_state", "")
            if manifest.get("project") != args.project or record_project_key(args.record) != args.project or manifest.get("from_state") != "ERROR_BLOCKED" or manifest.get("target_state") != expected_target:
                print("❌ recovery manifest未绑定当前项目/错误状态/目标状态"); return 2
            try:
                resolved = datetime.datetime.fromisoformat(str(manifest.get("resolved_at", "")))
                age = datetime.datetime.now() - resolved
                if age.total_seconds() < -300 or age.total_seconds() > 72 * 3600: raise ValueError("超过72小时或来自未来")
            except Exception as exc:
                print(f"❌ recovery manifest时间无效/过期: {exc}"); return 2
            if len(str(manifest.get("reason", "")).strip()) < 8:
                print("❌ recovery manifest缺详细reason（至少8字符）"); return 2
            item = manifest.get("verification")
            p = Path((item or {}).get("path", "")); p = p if p.is_absolute() else Path(args.record).parent / p
            if not isinstance(item, dict) or item.get("status") != "pass" or p.resolve().parent != Path(args.record).resolve().parent or not p.is_file() or hashlib.sha256(p.read_bytes()).hexdigest() != item.get("sha256"):
                print("❌ recovery verification须为项目内pass证据且文件hash一致"); return 2
            if args.state != expected_target:
                print(f"❌ ERROR_BLOCKED 只能恢复到记录的 next_state={expected_target}，不可跳到{args.state}"); return 2
            allow_recovery = True
        update_frontmatter(args.record, updates, expected_states=args.expected_state or None, allow_recovery=allow_recovery)
    except Exception as exc:
        print(f"❌ 状态更新失败: {exc}")
        return 1
    print(f"✅ 状态已更新: {args.record} → {args.state} (next={args.next_state or '-'})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
