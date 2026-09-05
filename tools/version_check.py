#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""版本检查（轻量·零依赖·永不阻塞主流程）：
本地版本 = SKILL.md frontmatter version；远端 = GitHub Releases latest。
比较结果缓存 24h（.local/version-check.json），避免每次启动都打 GitHub API（匿名限流 60次/h）。
失败（无网/限流/文件缺）一律静默返回 None——升级提醒绝不阻塞或干扰获客主流程。
"""
import json
import re
import time
from pathlib import Path

KB = Path(__file__).resolve().parent.parent
REPO_API = "https://api.github.com/repos/tony-apan/laifaxin-b2b-sales/releases/latest"
CACHE = KB / ".local" / "version-check.json"
CACHE_TTL = 24 * 3600


def local_version():
    """读 SKILL.md frontmatter version；缺/坏返回 None。"""
    try:
        m = re.search(r"(?m)^version:\s*v?(\d+\.\d+\.\d+)", (KB / "SKILL.md").read_text(encoding="utf-8"))
        return m.group(1) if m else None
    except Exception:
        return None


def _parse_ver(v):
    try:
        return tuple(int(x) for x in str(v).split("."))
    except Exception:
        return None


def _remote_version_cached():
    """24h 缓存优先；过期才 curl GitHub API（5s 超时）。任何失败静默 None。"""
    try:
        if CACHE.is_file():
            data = json.loads(CACHE.read_text(encoding="utf-8"))
            if time.time() - data.get("checked_at", 0) < CACHE_TTL:
                return data.get("remote_version")
    except Exception:
        pass
    import subprocess
    remote = None
    try:
        r = subprocess.run(["curl", "-sSL", "-m", "5", REPO_API], capture_output=True, text=True, timeout=8)
        tag = (json.loads(r.stdout) or {}).get("tag_name", "")
        m = re.search(r"v?(\d+\.\d+\.\d+)", tag)
        remote = m.group(1) if m else None
    except Exception:
        remote = None
    try:
        CACHE.parent.mkdir(parents=True, exist_ok=True)
        CACHE.write_text(json.dumps({"checked_at": time.time(), "remote_version": remote}), encoding="utf-8")
    except Exception:
        pass
    return remote


def check_update(force=False):
    """返回 (local, remote, newer: bool|None)。None=无法判断（静默跳过）。force=True 跳过缓存。"""
    local = local_version()
    if not local:
        return None, None, None
    if force:
        try:
            CACHE.unlink(missing_ok=True)
        except Exception:
            pass
    remote = _remote_version_cached()
    if not remote:
        return local, None, None
    lv, rv = _parse_ver(local), _parse_ver(remote)
    if not lv or not rv:
        return local, remote, None
    return local, remote, rv > lv


def print_notice_if_newer(stream=None):
    """有新版时打印一次升级提醒（人话+可复制动作）；无新版打印一行确认；判断失败静默。"""
    out = stream or print
    local, remote, newer = check_update()
    if newer is None:
        return
    if newer:
        out(f"📢 有新版本 v{remote}（当前 v{local}）")
        out(f"   更新内容: https://github.com/tony-apan/laifaxin-b2b-sales/releases/tag/v{remote}")
        out("   升级方法: 对 AI 说「帮我把这个获客系统更新到最新版，保留我的数据」")
        out("   （升级只替换规则和工具，不会动你的本地数据）")
    else:
        out(f"✅ 版本已是最新（v{local}）")


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="版本检查（可独立运行）")
    ap.add_argument("--force", action="store_true", help="跳过24h缓存强制查远端")
    a = ap.parse_args()
    print_notice_if_newer()
