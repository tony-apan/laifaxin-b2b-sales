#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""S11 本地终检收口：核对三份验证证据与项目状态后推进 READY_INACTIVE。
不调用平台；线上验证由 verify_sequence / verify_exclude / check_template_diff 先执行并保存输出。
"""
import argparse
import datetime
import hashlib
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from profile_utils import ensure_same_project_paths, parse_frontmatter, profile_gate
from update_run_state import record_matches_project, update_frontmatter


def evidence_ok(path, keywords):
    p = Path(path)
    if not p.is_file() or p.stat().st_size == 0:
        return False, "文件缺失或为空"
    text = p.read_text(encoding="utf-8", errors="replace")
    if re.search(r"(?:不通过|未通过|并未通过|尚未核实|未核实|不合格)", text):
        return False, "文件含否定结论"
    if "❌" in text or re.search(r"(?im)^\s*(?:FAIL(?:ED)?\b(?!\s*=\s*0)|ERROR_BLOCKED\b)", text):
        return False, "文件含失败标记"
    if keywords and not all(word in text for word in keywords):
        return False, "缺必需的类型化通过标记"
    return True, ""


def main():
    ap = argparse.ArgumentParser(description="S11终检收口（证据manifest全过→operation-record=S11 inactive）")
    ap.add_argument("--record", required=True)
    ap.add_argument("--profile", required=True)
    ap.add_argument("--project", required=True)
    ap.add_argument("--org", required=True, help="orgId；只取sha256与manifest核对，不落明文")
    ap.add_argument("--seq", required=True)
    ap.add_argument("--manifest", required=True, help="JSON绑定project/seq/profile_sha256及4份证据path+sha256+status=pass")
    args = ap.parse_args()
    if not ensure_same_project_paths(args.record, args.profile):
        print("❌ --record 与 --profile 不在同一项目目录")
        return 4
    status, issues, meta, sha = profile_gate(args.profile)
    if issues:
        for issue in issues: print("❌ profile: " + issue)
        return 4
    rec = parse_frontmatter(args.record)
    if not record_matches_project(args.record, args.project) or rec.get("sequence_id", "").strip('"') != args.seq:
        print("❌ record的项目键/sequence_id与本次S11收口不一致")
        return 4
    if rec.get("status") != "S10":
        print(f"❌ 当前 operation-record status={rec.get('status')!r}，须 S10 contact-add 对账成功后才能收口 S11")
        return 2
    try:
        manifest = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"❌ manifest无效: {exc}"); return 2
    if manifest.get("project") != args.project or manifest.get("seq") != args.seq or manifest.get("profile_sha256") != sha or manifest.get("org_sha256") != hashlib.sha256(str(args.org).encode()).hexdigest():
        print("❌ manifest未绑定当前project/org/seq/profile_sha256"); return 4
    try:
        generated = datetime.datetime.fromisoformat(str(manifest.get("generated_at", "")))
        age = datetime.datetime.now() - generated
        if age.total_seconds() < -300 or age.total_seconds() > 72 * 3600: raise ValueError("证据manifest超过72小时或来自未来")
    except Exception as exc:
        print(f"❌ manifest生成时间无效/过期: {exc}"); return 2
    specs = {"sequence": ("序列验证", (args.seq, "步骤数: 12", "状态=inactive", "全部12步")),
             "exclude": ("排除4区", ("含4区=0", "排除生效")),
             "diff": ("模板差异", ("模板数: 120", "最大相似度", "差异≥30%达标")),
             "panel": ("用户核实面板", ("标签", "客群", "保存", "模板", "配额", "审查"))}
    failed = []
    seen_paths = set()
    for key, (name, words) in specs.items():
        item = (manifest.get("evidence") or {}).get(key)
        if not isinstance(item, dict) or item.get("status") != "pass":
            failed.append(name + "(manifest非pass)"); continue
        path = Path(item.get("path", ""))
        if not path.is_absolute(): path = Path(args.record).parent / path
        if path.resolve() in seen_paths:
            failed.append(name + "(与其他证据复用同一文件)"); continue
        seen_paths.add(path.resolve())
        if path.resolve().parent != Path(args.record).resolve().parent:
            failed.append(name + "(证据不在项目目录)"); continue
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != item.get("sha256"):
            failed.append(name + "(文件/hash不匹配)"); continue
        ok, why = evidence_ok(path, words)
        print(f"{'✅' if ok else '❌'} {name}: {path}" + (f" ({why})" if why else ""))
        if not ok: failed.append(name)
    if failed:
        print("❌ S11未收口: " + ", ".join(failed))
        return 1
    update_frontmatter(args.record, {"status": "S11", "next_state": "S12",
                                      "profile_version": f'"{meta.get("profile_version", "")}"',
                                      "profile_sha256": f'"{sha}"'}, expected_states=("S10",))
    print(f"✅ S11 READY_INACTIVE 已收口: {args.record}（next=S12；仍未激活）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
