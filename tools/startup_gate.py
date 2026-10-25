#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""开工必读闸门 L1（机器强制）：没登记就先读文档，写操作一律拒绝。

机制（三层里的第一层）：
  L1 本闸门：必读文档集合 + 指纹登记（.local/gate/startup.jsonl）；未登记 → 写操作阻断
  L2 执行卡：step_gate.py show/record（每个状态先加载卡片）
  L3 写操作：step_gate.require_card（消费凭据后才放行）
本闸门被 step_gate.check_card 调用：没有有效 ack，任何执行卡校验/写操作都 exit 2。

必读清单（全部是仓库内文件）：
  SKILL.md、RULES.md、CORE-POINTS.md、specs/beginner-flow.md、
  specs/novice-flow-contract.md、specs/problems-and-fixes-2026-10-23.md
ack 后若任一文件内容变了（sha256 不一致），须重新 ack——防止读的是旧规则。

用法：
  python3 tools/startup_gate.py check
  python3 tools/startup_gate.py ack --nickname Tony --product 户外帐篷
  python3 tools/startup_gate.py status

测试隔离（仅 LFX_GATE_TEST_MODE=1 生效，生产路径不得靠 env 改）：
  LFX_GATE_LEDGER、LFX_GATE_DOCS_DIR
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_LEDGER = ROOT / ".local" / "gate" / "startup.jsonl"

ENV_TEST = "LFX_GATE_TEST_MODE"
ENV_LEDGER = "LFX_GATE_LEDGER"
ENV_DOCS_DIR = "LFX_GATE_DOCS_DIR"

MANDATORY: List[tuple] = [
    ("SKILL.md", "入口路由与铁律"),
    ("RULES.md", "唯一真源：强制流程与确认闸门"),
    ("CORE-POINTS.md", "核心要点与实测数值"),
    ("specs/beginner-flow.md", "新手 6 步全景与回复点"),
    ("specs/novice-flow-contract.md", "回复次数与确认闸门契约"),
    ("specs/problems-and-fixes-2026-10-23.md", "踩坑台账：已发生过的坑"),
]
ACK_EVENT = "ack"


class StartupGateError(Exception):
    """闸门拒绝：消息面向 AI/人，中文。"""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def _test_mode() -> bool:
    return os.environ.get(ENV_TEST) == "1"


def docs_dir() -> Path:
    override = os.environ.get(ENV_DOCS_DIR) or ""
    if override:
        if not _test_mode():
            raise StartupGateError("E_ENV_FORBIDDEN",
                "禁止用环境变量改必读目录（非测试模式）：%s" % ENV_DOCS_DIR)
        return Path(override)
    return ROOT


def ledger_path() -> Path:
    override = os.environ.get(ENV_LEDGER) or ""
    if override:
        if not _test_mode():
            raise StartupGateError("E_ENV_FORBIDDEN",
                "禁止用环境变量改账簿路径（非测试模式）：%s" % ENV_LEDGER)
        return Path(override)
    return DEFAULT_LEDGER


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def doc_hashes() -> Dict[str, str]:
    """返回 {相对路径: sha256}；文件缺失直接拒绝（不许缺文档也 ack）。"""
    base = docs_dir()
    out: Dict[str, str] = {}
    missing = []
    for rel, _label in MANDATORY:
        path = base / rel
        if not path.is_file():
            missing.append(rel)
            continue
        out[rel] = hashlib.sha256(path.read_bytes()).hexdigest()
    if missing:
        raise StartupGateError(
            "E_DOC_MISSING",
            "必读文档缺失：%s；请先恢复仓库文件再 ack" % "、".join(missing))
    return out


def read_acks() -> List[Dict[str, Any]]:
    path = ledger_path()
    if os.path.islink(str(path)):
        raise StartupGateError(
            "E_LEDGER_SYMLINK",
            "开工必读账本不能是符号链接；请删除后重新 ack")
    if not path.is_file():
        return []
    rows: List[Dict[str, Any]] = []
    try:
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
        fd = os.open(str(path), flags)
        try:
            with os.fdopen(fd, "r", encoding="utf-8") as fh:
                lines = fh.read().splitlines()
        finally:
            pass
    except OSError:
        return []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict) and row.get("event") == ACK_EVENT:
            rows.append(row)
    return rows


def latest_ack() -> Optional[Dict[str, Any]]:
    rows = read_acks()
    return rows[-1] if rows else None


def append_ack(nickname: str, product: str, hashes: Dict[str, str]) -> Dict[str, Any]:
    path = ledger_path()
    event = {
        "ts": now_iso(),
        "event": ACK_EVENT,
        "nickname": nickname,
        "product": product,
        "doc_sha256": hashes,
        "session": os.environ.get("DSH_SESSION_ID") or os.environ.get("LFX_SESSION_ID") or "",
    }
    line = json.dumps(event, ensure_ascii=False, separators=(",", ":")) + "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    try:
        os.write(fd, line.encode("utf-8"))
        os.fsync(fd)
    finally:
        os.close(fd)
    return event


def check() -> Dict[str, Any]:
    """校验 ack 是否存在且文档指纹未变；通过返回 ack 事件，否则抛错。"""
    ack = latest_ack()
    if not ack:
        raise StartupGateError(
            "E_STARTUP_NOT_ACKED",
            "还差一步：先告诉我您的昵称和产品，我登记后再继续（内部：未完成开工必读登记）")
    current_session = os.environ.get("DSH_SESSION_ID") or os.environ.get("LFX_SESSION_ID") or ""
    ack_session = str(ack.get("session") or "")
    if current_session and ack_session and current_session != ack_session:
        raise StartupGateError(
            "E_STARTUP_SESSION",
            "开工必读登记属于另一个会话；请在本会话重新 ack（读文档→ack）后再继续")
    current = doc_hashes()
    recorded = ack.get("doc_sha256") or {}
    if not isinstance(recorded, dict):
        raise StartupGateError(
            "E_STARTUP_CORRUPT",
            "开工必读账本损坏：doc_sha256 不是字典；请删除账本后重新登记")
    changed = [rel for rel, _label in MANDATORY
               if str(recorded.get(rel) or "") != current[rel]]
    if changed:
        raise StartupGateError(
            "E_STARTUP_STALE",
            "必读文档已变化：%s；请重新阅读后再 ack（防止按旧规则执行）" % "、".join(changed))
    return ack


def require_ack() -> None:
    """写操作前调用：未 ack 或文档已变 → 抛 StartupGateError。"""
    check()


def enforce_cli_startup() -> None:
    """CLI 脚本入口强制：生产进程未登记开工必读 → 立即拒绝（exit 2）。

    unittest 进程与 LFX_GATE_TEST_MODE=1 放行（只用于测试隔离）。
    生产命令不会带 unittest，因此该门在生产必过。
    """
    if os.environ.get("LFX_GATE_TEST_MODE") == "1" or "unittest" in sys.modules:
        return
    check()


def _fmt_ack(ack: Dict[str, Any]) -> str:
    return "开工必读已登记：昵称=%s｜产品=%s｜时间=%s" % (
        ack.get("nickname") or "（未填）", ack.get("product") or "（未填）", ack.get("ts") or "（无时间）")


def cmd_check() -> int:
    try:
        ack = check()
    except StartupGateError as exc:
        print("❌ %s" % exc.message, file=sys.stderr)
        return 2
    print("✅ %s" % _fmt_ack(ack))
    return 0


def cmd_ack(nickname: str, product: str) -> int:
    nickname = (nickname or "").strip()
    product = (product or "").strip()
    if not nickname or not product:
        print("❌ 登记开工必读需要 --nickname 和 --product（用户第一条回复的两样）", file=sys.stderr)
        return 2
    try:
        hashes = doc_hashes()
        event = append_ack(nickname, product, hashes)
    except StartupGateError as exc:
        print("❌ %s" % exc.message, file=sys.stderr)
        return 2
    print("✅ 已登记开工必读（%d 份文档已读并锁定指纹）" % len(MANDATORY))
    print(_fmt_ack(event))
    print("现在可以进入第 1 步；未登记前所有写操作都会被拒绝。")
    return 0


def cmd_status() -> int:
    ack = latest_ack()
    if not ack:
        print("未登记开工必读（写操作会被拒绝）")
        return 2
    print(_fmt_ack(ack))
    recorded = ack.get("doc_sha256") or {}
    try:
        current = doc_hashes()
    except StartupGateError as exc:
        print("❌ %s" % exc.message)
        return 2
    stale = [rel for rel, _ in MANDATORY if str(recorded.get(rel) or "") != current.get(rel)]
    print("文档状态：%s" % ("全部未变" if not stale else "已变化：" + "、".join(stale)))
    return 0 if not stale else 2


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="开工必读闸门（机器强制）")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("check", help="校验开工必读登记（exit 0/2）")
    ack = sub.add_parser("ack", help="登记已读必读文档")
    ack.add_argument("--nickname", required=True)
    ack.add_argument("--product", required=True)
    sub.add_parser("status", help="查看登记与文档指纹状态")
    args = parser.parse_args(argv)
    if args.command == "check":
        return cmd_check()
    if args.command == "status":
        return cmd_status()
    return cmd_ack(args.nickname, args.product)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except StartupGateError as exc:
        print("❌ %s" % exc.message, file=sys.stderr)
        raise SystemExit(2)
