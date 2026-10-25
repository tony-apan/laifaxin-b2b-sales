#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""执行卡闸门（L2 加载留痕 / L3 写操作前拒绝）。

规格：specs/product-profile-sop.md「★规则注入三层机制」。
  L2：进入状态先 show 执行卡，回显必读/必填/格式/自检/禁止，并落 loaded 指纹凭据；
  L3：写操作前调用 require_card（等价 check）；未加载、卡片已变更、凭据缺失一律拒绝（exit 2）。

子命令：
  show   --state Sx [--run RUN]   回显卡片，写 {event:"loaded"} 凭据，exit 0
  record --state Sx [--run RUN]   仅当本 run 已 show 且指纹仍一致时写 {event:"consumed"}
  check  --state Sx [--run RUN]   要求存在指纹一致的 consumed 记录；通过 exit 0，否则 exit 2
  status --run RUN                打印本 run 的已加载/已消费清单

账簿：默认 .local/gate/ledger.jsonl（append-only JSONL，一行一事件）。
环境变量：
  DSH_RUN_ID           run_id 缺省来源；再缺省 "default"
  STEP_GATE_CARDS_DIR  卡片目录覆盖（默认 runtime/cards）
  STEP_GATE_LEDGER     账簿路径覆盖（默认 .local/gate/ledger.jsonl）
  ★两个路径覆盖仅在 STEP_GATE_TEST_MODE=1（测试隔离）时生效；
    未置测试模式却设置覆写变量 → E_ENV_FORBIDDEN（exit 2），生产路径不得靠 env 改卡/改账簿。
凭据时效：consumed 记录超 24 小时（或 ts 不可解析）即失效，须重新 show+record。

其他工具 import：
  from step_gate import require_card, StepGateError
  try:
      require_card("S5", run_id)
  except StepGateError as exc:
      print("❌ %s" % exc, file=sys.stderr)
      raise SystemExit(2)
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CARDS_DIR = ROOT / "runtime" / "cards"
DEFAULT_LEDGER = ROOT / ".local" / "gate" / "ledger.jsonl"

ENV_RUN_ID = "DSH_RUN_ID"
ENV_CARDS_DIR = "STEP_GATE_CARDS_DIR"
ENV_LEDGER = "STEP_GATE_LEDGER"
ENV_TEST_MODE = "STEP_GATE_TEST_MODE"

CONSUMED_TTL_SECONDS = 24 * 3600  # consumed 凭据 24h 内有效

_CARD_REQUIRED_FIELDS = ("state", "title", "must_read", "required_fields",
                         "format_rules", "self_check", "forbidden", "next")

STATE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]*$")
EVENT_LOADED = "loaded"
EVENT_CONSUMED = "consumed"

_KNOWN_SECTIONS = (
    ("must_read", "必读（must_read）"),
    ("required_fields", "必填字段（required_fields）"),
    ("format_rules", "格式规则（format_rules）"),
    ("self_check", "自检（self_check）"),
    ("forbidden", "禁止（forbidden）"),
)
_SECTION_KEYS = {key for key, _ in _KNOWN_SECTIONS}
_CARD_META_KEYS = {"state", "title", "next"}


class StepGateError(RuntimeError):
    """执行卡闸门拒绝：message 是面向执行者的中文原因，code 供调用方分支。"""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


# ---------------------------------------------------------------------------
# 路径与运行标识
# ---------------------------------------------------------------------------

def _env_path(name: str) -> Optional[Path]:
    """路径覆写只在 STEP_GATE_TEST_MODE=1 时生效；否则拒绝启动（防生产改卡/改账簿）。"""
    value = os.environ.get(name, "").strip()
    if not value:
        return None
    if os.environ.get(ENV_TEST_MODE, "") != "1":
        raise StepGateError(
            "E_ENV_FORBIDDEN",
            "禁止用环境变量 %s 覆写执行卡路径：该覆写只在测试模式生效；"
            "如确需隔离请设置 %s=1（仅测试环境），生产路径不得改卡/改账簿" % (name, ENV_TEST_MODE))
    return Path(value).expanduser()


def cards_dir() -> Path:
    """执行卡目录：默认仓库内 runtime/cards，可用 STEP_GATE_CARDS_DIR 覆盖。"""
    return _env_path(ENV_CARDS_DIR) or DEFAULT_CARDS_DIR


def ledger_path() -> Path:
    """账簿路径：默认 .local/gate/ledger.jsonl，可用 STEP_GATE_LEDGER 覆盖。"""
    return _env_path(ENV_LEDGER) or DEFAULT_LEDGER


def resolve_run_id(run_id: Optional[str] = None) -> str:
    """run_id：显式参数 → DSH_RUN_ID → "default"。"""
    candidate = run_id if run_id is not None else os.environ.get(ENV_RUN_ID, "")
    candidate = str(candidate or "").strip()
    if not candidate:
        candidate = "default"
    if len(candidate) > 200:
        raise StepGateError("E_BAD_RUN_ID", "运行标识过长（>200 字符），拒绝落账")
    return candidate


def _display_path(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(ROOT))
    except ValueError:
        return str(path)


# ---------------------------------------------------------------------------
# 卡片读取与指纹
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Card:
    state: str
    path: Path
    data: Dict[str, Any]
    sha256: str


def _state_path(state: str) -> Path:
    if not isinstance(state, str) or not STATE_RE.match(state):
        raise StepGateError(
            "E_BAD_STATE",
            "状态名不合法：%r（只允许字母、数字、下划线、连字符，且不得以符号开头）" % (state,))
    path = cards_dir() / (state + ".json")
    if not path.is_file():
        raise StepGateError(
            "E_CARD_MISSING",
            "执行卡不存在：%s（状态 %s）；请确认 runtime/cards 已就位" % (_display_path(path), state))
    return path


def load_card(state: str) -> Card:
    """按状态读取执行卡；sha256 严格等于卡片文件字节的指纹。"""
    path = _state_path(state)
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise StepGateError(
            "E_CARD_UNREADABLE",
            "执行卡读取失败：%s（%s）" % (_display_path(path), exc))
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise StepGateError(
            "E_CARD_INVALID",
            "执行卡不是合法 UTF-8 JSON：%s（%s）" % (_display_path(path), exc))
    if not isinstance(data, dict):
        raise StepGateError(
            "E_CARD_INVALID",
            "执行卡顶层必须是 JSON 对象：%s" % _display_path(path))
    missing = [key for key in _CARD_REQUIRED_FIELDS if key not in data]
    if missing:
        raise StepGateError(
            "E_CARD_INVALID",
            "执行卡字段缺失：%s 缺 %s；卡片必含 %s"
            % (_display_path(path), "、".join(missing), "、".join(_CARD_REQUIRED_FIELDS)))
    card_state = str(data.get("state") or "")
    if card_state != state:
        raise StepGateError(
            "E_CARD_STATE_MISMATCH",
            "执行卡状态不符：请求 %s，但 %s 内 state=%r；拒绝使用错卡"
            % (state, _display_path(path), card_state))
    return Card(state=state, path=path, data=data,
                sha256=hashlib.sha256(raw).hexdigest())


# ---------------------------------------------------------------------------
# 账簿（append-only JSONL）
# ---------------------------------------------------------------------------

def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def append_ledger(event: Dict[str, Any]) -> Dict[str, Any]:
    """原子追加一行事件；目录 0700、新文件 0600，不写任何明文凭据。"""
    path = ledger_path()
    line = json.dumps(event, ensure_ascii=False, separators=(",", ":")) + "\n"
    prefix = b""
    # 半行残尾（上次写到一半/手改）：先补换行，残行作为坏行被 read_ledger 跳过，
    # 避免新事件与残尾拼成一行导致 show 假成功。
    try:
        if path.is_file() and path.stat().st_size:
            with open(path, "rb") as handle:
                handle.seek(-1, os.SEEK_END)
                if handle.read(1) != b"\n":
                    prefix = b"\n"
    except OSError:
        prefix = b""
    payload = prefix + line.encode("utf-8")
    directory = path.parent
    try:
        created = not directory.exists()
        directory.mkdir(parents=True, exist_ok=True)
        if created:
            try:
                directory.chmod(0o700)
            except OSError:
                pass
        fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        try:
            view = memoryview(payload)
            while view:
                written = os.write(fd, view)
                view = view[written:]
            os.fsync(fd)
        finally:
            os.close(fd)
    except OSError as exc:
        raise StepGateError(
            "E_LEDGER_IO",
            "执行卡账簿写入失败：%s（%s）" % (_display_path(path), exc))
    return event


def read_ledger() -> List[Dict[str, Any]]:
    """读全部事件；缺失=空，坏行跳过（不因历史噪声阻断闸门）。"""
    path = ledger_path()
    if not path.is_file():
        return []
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise StepGateError(
            "E_LEDGER_IO",
            "执行卡账簿读取失败：%s（%s）" % (_display_path(path), exc))
    rows: List[Dict[str, Any]] = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict):
            rows.append(row)
    return rows


def _matches(row: Dict[str, Any], event: str, state: str, run_id: str) -> bool:
    return (row.get("event") == event
            and row.get("state") == state
            and row.get("run_id") == run_id)


def _missing_ledger_message(state: str, run_id: str) -> str:
    return ("凭据缺失：未找到执行卡账簿 %s；本次运行（run_id=%s）未加载执行卡 %s；"
            "请先执行 show --state %s --run %s"
            % (_display_path(ledger_path()), run_id, state, state, run_id))


# ---------------------------------------------------------------------------
# 凭据时效与账簿回读
# ---------------------------------------------------------------------------

def _event_age_seconds(row: Dict[str, Any]) -> Optional[float]:
    """事件时间距今秒数；ts 缺失/不可解析返回 None（视为失效）。"""
    raw = str(row.get("ts") or "").strip()
    if not raw:
        return None
    try:
        when = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - when).total_seconds()


def _verify_last_ledger_line(event: Dict[str, Any]) -> bool:
    """show 后回读账簿最后一行，确认本次事件完整可解析（防半行/坏写假成功）。"""
    path = ledger_path()
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return False
    lines = [line for line in text.splitlines() if line.strip()]
    if not lines:
        return False
    try:
        row = json.loads(lines[-1])
    except json.JSONDecodeError:
        return False
    if not isinstance(row, dict):
        return False
    return all(row.get(key) == event.get(key)
               for key in ("event", "state", "run_id", "ts"))


# ---------------------------------------------------------------------------
# 四个动作
# ---------------------------------------------------------------------------

def show_card(state: str, run_id: Optional[str] = None, *,
              echo: bool = True) -> Dict[str, Any]:
    """加载执行卡：回显全部内容并写入 loaded 凭据。返回所写事件。"""
    card = load_card(state)
    run = resolve_run_id(run_id)
    event = {
        "ts": now_iso(),
        "state": state,
        "card_sha256": card.sha256,
        "run_id": run,
        "event": EVENT_LOADED,
    }
    path = ledger_path()
    try:
        before = path.stat().st_size if path.is_file() else 0
    except OSError:
        before = 0
    append_ledger(event)
    # ★回读确认：写后最后一行必须能解析；失败则撤销本次追加，绝不让 show 假成功。
    if not _verify_last_ledger_line(event):
        try:
            os.truncate(str(path), before)
        except OSError:
            pass
        raise StepGateError(
            "E_LEDGER_CORRUPT",
            "账簿写入后回读失败：%s 最后一行不可解析；本次追加已撤销，请检查磁盘空间/权限后重试"
            % _display_path(path))
    if echo:
        print(render_card(card, run))
        print("")
        print("已写入加载凭据：%s（event=loaded）" % _display_path(ledger_path()))
    return event


def record_card(state: str, run_id: Optional[str] = None) -> Dict[str, Any]:
    """写 consumed 凭据：仅当本 run 已 show 且卡片指纹未变。"""
    card = load_card(state)
    run = resolve_run_id(run_id)
    rows = read_ledger()
    loaded = [row for row in rows if _matches(row, EVENT_LOADED, state, run)]
    matching = [row for row in loaded if row.get("card_sha256") == card.sha256]

    if not matching:
        if not ledger_path().is_file():
            raise StepGateError("E_LEDGER_MISSING", _missing_ledger_message(state, run))
        if loaded:
            previous = str(loaded[-1].get("card_sha256") or "（缺失）")
            raise StepGateError(
                "E_CARD_CHANGED",
                "卡片已变更：执行卡 %s 加载时指纹 %s，当前文件指纹 %s；请重新 show 后再 record"
                % (state, previous, card.sha256))
        raise StepGateError(
            "E_NOT_LOADED",
            "未加载：run_id=%s 尚未 show 过执行卡 %s；请先执行 show --state %s --run %s"
            % (run, state, state, run))

    latest_loaded = matching[-1]
    loaded_age = _event_age_seconds(latest_loaded)
    if loaded_age is None or loaded_age > CONSUMED_TTL_SECONDS:
        raise StepGateError(
            "E_CARD_EXPIRED",
            "加载凭据已过期：执行卡 %s（run_id=%s）最近一次 show 已超过 %d 小时；请重新执行 show --state %s --run %s"
            % (state, run, CONSUMED_TTL_SECONDS // 3600, state, run))

    event = {
        "ts": now_iso(),
        "state": state,
        "card_sha256": card.sha256,
        "run_id": run,
        "event": EVENT_CONSUMED,
    }
    append_ledger(event)
    return event


def check_card(state: str, run_id: Optional[str] = None) -> Dict[str, Any]:
    """闸门校验：要求存在 consumed 且指纹等于当前卡片文件；返回命中的事件。

    ★L1 机器强制（2026-10-23）：先过开工必读闸门；未登记/文档已变一律拒绝，
    防止 AI 没读契约就直接跑写操作。
    """
    _require_startup_gate()
    card = load_card(state)
    run = resolve_run_id(run_id)
    rows = read_ledger()
    consumed = [row for row in rows if _matches(row, EVENT_CONSUMED, state, run)]
    matching = [row for row in consumed if row.get("card_sha256") == card.sha256]
    fresh = []
    for row in matching:
        age = _event_age_seconds(row)
        if age is not None and age <= CONSUMED_TTL_SECONDS:
            fresh.append(row)

    if fresh:
        return fresh[-1]
    if matching:
        raise StepGateError(
            "E_CARD_EXPIRED",
            "凭据已过期：执行卡 %s（run_id=%s）的 consumed 凭据超过 %d 小时或 ts 不可解析；"
            "请重新执行 show --state %s --run %s，再 record"
            % (state, run, CONSUMED_TTL_SECONDS // 3600, state, run))

    if not ledger_path().is_file():
        raise StepGateError("E_LEDGER_MISSING", _missing_ledger_message(state, run))

    if consumed:
        previous = str(consumed[-1].get("card_sha256") or "（缺失）")
        raise StepGateError(
            "E_CARD_CHANGED",
            "卡片已变更：执行卡 %s 已消费指纹 %s，当前文件指纹 %s；请重新 show 并 record"
            % (state, previous, card.sha256))

    loaded = [row for row in rows if _matches(row, EVENT_LOADED, state, run)]
    if loaded:
        raise StepGateError(
            "E_NOT_LOADED",
            "未加载：执行卡 %s（run_id=%s）只有 loaded 记录、缺指纹一致的 consumed 凭据；"
            "请先执行 record --state %s --run %s"
            % (state, run, state, run))
    raise StepGateError(
        "E_NOT_LOADED",
        "未加载：执行卡 %s（run_id=%s）尚未 show；"
        "请先执行 show --state %s --run %s，再 record"
        % (state, run, state, run))


def _require_startup_gate() -> None:
    """L1 闸门：惰性导入 startup_gate，避免循环依赖；失败转 StepGateError。"""
    try:
        from startup_gate import require_ack, StartupGateError
    except Exception as exc:  # 模块缺失不得静默放行
        raise StepGateError("E_STARTUP_GATE_MISSING",
            "开工必读闸门模块缺失（startup_gate.py）：%s；请恢复 tools/startup_gate.py" % exc)
    try:
        require_ack()
    except StartupGateError as exc:
        raise StepGateError(exc.code, exc.message)


def require_card(state: str, run_id: Optional[str] = None) -> None:
    """写操作强制入口（等价 check）：失败抛 StepGateError（中文消息），调用方转 exit 2。"""
    check_card(state, run_id)


# ---------------------------------------------------------------------------
# 中文回显
# ---------------------------------------------------------------------------

def _fmt_value(value: Any) -> str:
    if isinstance(value, bool):
        return "是" if value else "否"
    if value is None:
        return "（空）"
    if isinstance(value, (list, tuple)):
        return "；".join(_fmt_value(item) for item in value)
    if isinstance(value, dict):
        return "；".join("%s：%s" % (key, _fmt_value(item))
                        for key, item in value.items())
    return str(value)


def _section_lines(label: str, value: Any) -> List[str]:
    lines = ["【%s】" % label]
    if isinstance(value, dict):
        if value:
            for key, item in value.items():
                lines.append("  - %s：%s" % (key, _fmt_value(item)))
        else:
            lines.append("  -（未声明）")
    elif isinstance(value, (list, tuple)):
        if value:
            for item in value:
                lines.append("  - %s" % _fmt_value(item))
        else:
            lines.append("  -（未声明）")
    elif value in (None, ""):
        lines.append("  -（未声明）")
    else:
        lines.append("  - %s" % _fmt_value(value))
    return lines


def render_card(card: Card, run_id: str) -> str:
    """把执行卡渲染成中文可读文本（含指纹与运行标识）。"""
    data = card.data
    title = str(data.get("title") or "（无标题）")
    lines: List[str] = [
        "=" * 64,
        "执行卡 %s｜%s" % (card.state, title),
        "=" * 64,
        "卡片文件：%s" % _display_path(card.path),
        "",
    ]
    for key, label in _KNOWN_SECTIONS:
        lines.extend(_section_lines(label, data.get(key)))
        lines.append("")
    for key, value in data.items():
        if key in _CARD_META_KEYS or key in _SECTION_KEYS:
            continue
        lines.extend(_section_lines(str(key), value))
        lines.append("")
    if data.get("next"):
        lines.append("下一步：%s" % data["next"])
        lines.append("")
    lines.append("卡片指纹（sha256）：%s" % card.sha256)
    lines.append("运行标识（run_id）：%s" % run_id)
    return "\n".join(lines)


def status_lines(run_id: Optional[str] = None) -> List[str]:
    """本 run 的已加载/已消费清单；同时列出卡片目录里尚未加载的卡。"""
    run = resolve_run_id(run_id)
    path = ledger_path()
    rows = [row for row in read_ledger()
            if row.get("run_id") == run and isinstance(row.get("state"), str)]
    by_state: Dict[str, List[Dict[str, Any]]] = {}
    for row in rows:
        by_state.setdefault(str(row["state"]), []).append(row)

    states = set(by_state)
    try:
        states.update(card_path.stem for card_path in cards_dir().glob("*.json"))
    except OSError:
        pass

    lines = ["执行卡状态清单（run_id=%s）" % run]
    if path.is_file():
        lines.append("账簿：%s" % _display_path(path))
    else:
        lines.append("账簿：%s（不存在：本 run 尚未加载任何执行卡）"
                     % _display_path(path))
    if not states:
        lines.append("（未发现执行卡文件）")
        return lines

    for state in sorted(states):
        events = by_state.get(state, [])
        loaded = [row for row in events if row.get("event") == EVENT_LOADED]
        consumed = [row for row in events if row.get("event") == EVENT_CONSUMED]
        title = ""
        current: Optional[str] = None
        try:
            card = load_card(state)
            title = str(card.data.get("title") or "")
            current = card.sha256
        except StepGateError:
            pass

        if loaded:
            fingerprint = str(loaded[-1].get("card_sha256") or "")
            if current is None:
                match = "当前卡片缺失/不可读"
            elif fingerprint == current:
                match = "指纹一致"
            else:
                match = "指纹已变更"
            loaded_text = "已加载（%s…，%s）" % (fingerprint[:12], match)
        else:
            loaded_text = "未加载"

        if consumed:
            fingerprint = str(consumed[-1].get("card_sha256") or "")
            if current is None:
                match = "当前卡片缺失/不可读"
            elif fingerprint == current:
                match = "当前可执行"
            else:
                match = "指纹已变更，需重新加载"
            consumed_text = "已消费（%s…，%s）" % (fingerprint[:12], match)
        else:
            consumed_text = "未消费"

        label = "｜%s" % title if title else ""
        lines.append("  - %s%s：%s / %s" % (state, label, loaded_text, consumed_text))
    return lines


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="step_gate.py",
        description="执行卡闸门：未加载执行卡（或卡片已变更）不得执行写操作。",
        epilog=("退出码：0 通过；2 拒绝（中文原因）。"
                "环境变量：DSH_RUN_ID；测试隔离才可用 STEP_GATE_CARDS_DIR / STEP_GATE_LEDGER"
                "（须同时设置 STEP_GATE_TEST_MODE=1，否则拒绝）。"),
    )
    sub = parser.add_subparsers(dest="command", required=True)

    def add(name: str, help_text: str, with_state: bool = True) -> argparse.ArgumentParser:
        child = sub.add_parser(name, help=help_text)
        if with_state:
            child.add_argument("--state", required=True, help="执行卡状态，如 S2")
        child.add_argument(
            "--run", default=None,
            help="运行标识；缺省读 DSH_RUN_ID，再缺省 default")
        return child

    add("show", "回显执行卡并写入 loaded 凭据")
    add("record", "写入 consumed 凭据（要求本 run 已 show 且指纹一致）")
    add("check", "校验 consumed 凭据与当前卡片指纹（写操作前调用）")
    add("status", "打印本 run 的已加载/已消费清单", with_state=False)
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "show":
            show_card(args.state, args.run)
        elif args.command == "record":
            event = record_card(args.state, args.run)
            print("✅ 已记录执行卡消费凭据：%s（run_id=%s，卡片指纹=%s）"
                  % (event["state"], event["run_id"], event["card_sha256"]))
        elif args.command == "check":
            event = check_card(args.state, args.run)
            print("✅ 执行卡闸门通过：%s（run_id=%s，卡片指纹=%s）"
                  % (event["state"], event["run_id"], event["card_sha256"]))
        elif args.command == "status":
            print("\n".join(status_lines(args.run)))
        else:  # pragma: no cover - argparse 已挡住未知子命令
            raise StepGateError("E_BAD_COMMAND", "未知子命令：%s" % args.command)
        return 0
    except StepGateError as exc:
        print("❌ %s" % exc, file=sys.stderr)
        return 2
    except OSError as exc:
        print("❌ 执行卡闸门读写失败：%s" % exc, file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
