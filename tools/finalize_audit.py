#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""S4 审计收口：审计证据+对抗审查均存在且通过后，推进 operation-record 到 S4。"""
import argparse
import datetime
import hashlib
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from profile_utils import ensure_same_project_paths, profile_gate
from update_run_state import read_meta, record_matches_project, require_state, update_frontmatter


def check_file(path, label, required):
    p = Path(path)
    if not p.is_file() or p.stat().st_size == 0:
        return f"{label}缺失/为空: {p}"
    text = p.read_text(encoding="utf-8", errors="replace")
    if re.search(r"(?:不放行|未放行|拒绝放行|尚未通过|并未通过)", text): return f"{label}含否定结论: {p}"
    if "❌" in text or re.search(r"(?im)^\s*(?:FAIL(?:ED)?\b(?!\s*=\s*0)|P[01]\b(?!\s*[:=]\s*0\b))", text):
        return f"{label}含失败/P0/P1标记: {p}"
    if required and not all(word in text for word in required):
        return f"{label}缺必需内容{required}: {p}"
    return ""


def main():
    ap = argparse.ArgumentParser(description="S4审计证据收口（过审后才能保存）")
    ap.add_argument("--record", required=True)
    ap.add_argument("--profile", required=True)
    ap.add_argument("--project", required=True, help="<operator_key>/<product_key>")
    ap.add_argument("--manifest", required=True, help="audit-manifest.json，绑定project/profile/seed/time及audit/review文件hash")
    args = ap.parse_args()
    if not ensure_same_project_paths(args.record, args.profile) or not record_matches_project(args.record, args.project):
        print("❌ record/profile/project不属于同一项目")
        return 4
    status, issues, meta, sha = profile_gate(args.profile)
    if issues:
        for issue in issues: print("❌ profile: " + issue)
        return 4
    try:
        require_state(args.record, ("S3", "S4"))
    except ValueError as exc:
        print(f"❌ {exc}")
        return 4
    rec = read_meta(args.record)
    try:
        manifest = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"❌ audit manifest无效: {exc}"); return 2
    if manifest.get("project") != args.project or manifest.get("profile_sha256") != sha or manifest.get("seed") != rec.get("seed"):
        print("❌ audit manifest未绑定当前project/profile/seed"); return 4
    try:
        generated = datetime.datetime.fromisoformat(str(manifest.get("generated_at", "")))
        age = datetime.datetime.now() - generated
        if age.total_seconds() < -300 or age.total_seconds() > 72 * 3600: raise ValueError("超过72小时或来自未来")
    except Exception as exc:
        print(f"❌ audit manifest时间无效/过期: {exc}"); return 2
    errors = []
    for key, label, words in (("audit", "审计证据", ("70%", "临界", "50页", "三页平均", "逐页", "敏感性")),
                              ("review", "对抗审查", ("放行", "P0=0", "P1=0"))):
        item = (manifest.get("evidence") or {}).get(key)
        if not isinstance(item, dict) or item.get("status") != "pass": errors.append(label + " manifest非pass"); continue
        p = Path(item.get("path", "")); p = p if p.is_absolute() else Path(args.record).parent / p
        if p.resolve().parent != Path(args.record).resolve().parent: errors.append(label + "不在项目目录"); continue
        if not p.is_file() or hashlib.sha256(p.read_bytes()).hexdigest() != item.get("sha256"): errors.append(label + "文件/hash不匹配"); continue
        err = check_file(p, label, words)
        if err: errors.append(err)
    if errors:
        for error in errors: print("❌ " + error)
        return 1
    update_frontmatter(args.record, {"status": "S4", "next_state": "S5",
                                      "profile_version": f'"{meta.get("profile_version", "")}"',
                                      "profile_sha256": f'"{sha}"'}, expected_states=("S3", "S4"))
    print(f"✅ S4审计已收口: {args.record} (next=S5)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
