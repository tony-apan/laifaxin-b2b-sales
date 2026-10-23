#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""当前产品/轮次来源登记（Guard V2 A 组）。

职责（GUARD-FIX-V2 §4.1/§6.A）：
  * .local/segments.jsonl 追加事件流：generation 快照、候选、选择、域名解析、
    用户自带域名关联、生成路径占位（product-add/generate attempt）。
  * load_current(project, ...) 按 project+platform_product_id+generation_id+
    segment_id+inf_id 取记录，不能按"最后一条"。
  * validate_source 只判定不登记：旧轮/跨产品/superseded/缺生成证据 → 拒绝。
  * 首次无 platform_product_id 时以 project+local_product_key 稳定键占位；
    O_EXCL 互斥，胜者外调、败者拒绝或复用已完成活跃 generation。

约束：不联网、不读凭据、不承载保存规则；写事件前取项目级互斥锁；坏行/同键
冲突拒绝，不静默跳过。本模块是防误操作/追溯工具，不防同机恶意修改。
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

TOOLS_DIR = Path(__file__).resolve().parent
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

SCHEMA_VERSION = 2
EVENT_FILE = ".local/segments.jsonl"
PROJECT_MARKER = "project.json"  # .local/guard_v2/<slug>/ 的项目归属标记（防目录碰撞）
_SLUG_RE = re.compile(r"[^0-9A-Za-z._-]+")
# 项目键：每段允许 Unicode 字母/数字（\w）与 . _ -；必须恰好一个 /。
# 中文产品名（如 tony/户外帐篷）是正式键；目录落点由 slugify 转 ASCII。
_PROJECT_RE = re.compile(r"^[\w.-]+/[\w.-]+$")
MAX_EVENT_BYTES = 1024 * 1024


class RegistryError(ValueError):
    """登记/取记录失败（带 code）。"""

    def __init__(self, code: str, reason: str):
        super().__init__(reason)
        self.code = code
        self.reason = reason


def _fail(code: str, reason: str) -> None:
    raise RegistryError(code, reason)


def _check_project(project: str) -> str:
    text = str(project or "").strip()
    if not text or not _PROJECT_RE.fullmatch(text):
        _fail("E_SOURCE_BAD_PROJECT", "project 必须形如 <operator_key>/<product_key>: %r" % (project,))
    if ".." in text or text.startswith(("/", ".")):
        _fail("E_SOURCE_BAD_PROJECT", "project 含路径片段: %r" % (project,))
    return text


def _safe_component(value: Any, label: str) -> str:
    text = str(value or "").strip()
    if not text or text in (".", "..") or "/" in text or chr(92) in text:
        _fail("E_SOURCE_BAD_PROJECT", "%s 非法: %r" % (label, value))
    return text


def slugify(value: Any) -> str:
    """ASCII 目录名：base + raw 的 sha256 前 16 hex（确定性、跨键防碰撞）。

    * 无论原文是否 ASCII 都追加 hash（tony/widget 与 tony-widget 不会撞目录）。
    * 纯中文/无可用 ASCII 基名时用 p-<hash>，不再直接报错。
    """
    raw = str(value or "").strip()
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]
    text = _SLUG_RE.sub("-", raw).strip("-")[:80 - 17]
    if not text:
        text = "p"
    return "%s-%s" % (text, digest)


def _local_dir(root: Path, project: str) -> Path:
    """项目级目录。写入 project marker；目录已有 marker 且项目不同 → 拒绝。"""
    base = Path(root)
    directory = base / ".local" / "guard_v2" / slugify(project)
    directory.mkdir(parents=True, exist_ok=True)
    marker = directory / PROJECT_MARKER
    expected = {"project": str(project)}
    try:
        fd = os.open(str(marker), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        try:
            existing = json.loads(marker.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            _fail("E_PROJECT_DIR_COLLISION",
                  "项目目录 marker 损坏，拒绝复用: %s" % marker)
        if not isinstance(existing, dict) or existing.get("project") != expected["project"]:
            _fail("E_PROJECT_DIR_COLLISION",
                  "项目目录 %s 已归属 %r，拒绝写入 %r"
                  % (directory, (existing or {}).get("project"), project))
        return directory
    try:
        os.write(fd, json.dumps(expected, ensure_ascii=False,
                                separators=(",", ":")).encode("utf-8"))
        os.fsync(fd)
    finally:
        os.close(fd)
    return directory


def _event_path(root: Path) -> Path:
    base = Path(root)
    target = base / EVENT_FILE
    target.parent.mkdir(parents=True, exist_ok=True)
    return target


def _atomic_write(path: Path, text: str, mode: int = 0o600) -> None:
    tmp = path.with_name(path.name + ".tmp-" + secrets.token_hex(6))
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(str(tmp), flags, mode)
    try:
        os.write(fd, text.encode("utf-8"))
        os.fsync(fd)
    finally:
        os.close(fd)
    os.replace(str(tmp), str(path))
    os.chmod(path, mode)


def _project_lock(root: Path, project: str) -> Any:
    """项目级互斥：fcntl 有则用，无则 O_EXCL 提示文件（尽力互斥）。"""
    directory = _local_dir(root, project)
    path = directory / "registry.lock"
    class _Lock:
        def __enter__(self_inner):
            self_inner.fd = os.open(str(path), os.O_WRONLY | os.O_CREAT, 0o600)
            try:
                import fcntl
                fcntl.flock(self_inner.fd, fcntl.LOCK_EX)
                self_inner.fcntl = True
            except (ImportError, OSError):
                self_inner.fcntl = False
            return self_inner
        def __exit__(self_inner, *_):
            try:
                if self_inner.fcntl:
                    import fcntl
                    fcntl.flock(self_inner.fd, fcntl.LOCK_UN)
            finally:
                os.close(self_inner.fd)
            return False
    return _Lock()


def _append_events(root: Path, events: Sequence[Dict[str, Any]]) -> None:
    path = _event_path(root)
    with _project_lock(root, events[0].get("project", "unknown/unknown") if events else "unknown/unknown"):
        for event in events:
            line = json.dumps(event, ensure_ascii=False, sort_keys=True,
                              separators=(",", ":"))
            if len(line.encode("utf-8")) > MAX_EVENT_BYTES:
                _fail("E_SOURCE_BAD_PROJECT", "事件过大拒绝写入")
            with path.open("a", encoding="utf-8") as handle:
                handle.write(line + "\n")


def _read_events(root: Path, project: str) -> List[Dict[str, Any]]:
    path = _event_path(root)
    if not path.exists():
        return []
    events: List[Dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for number, line in enumerate(handle, 1):
            text = line.strip()
            if not text:
                continue
            try:
                event = json.loads(text)
            except ValueError:
                _fail("E_SOURCE_BAD_ROW", "segments.jsonl 第 %d 行坏 JSON" % number)
            if not isinstance(event, dict):
                _fail("E_SOURCE_BAD_ROW", "segments.jsonl 第 %d 行不是 object" % number)
            if event.get("project") == project:
                events.append(event)
    return events


def sha256_text(text: str) -> str:
    return hashlib.sha256(str(text).encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# 本地产品键：project+local_product_key 稳定占位（先占位再外调）
# ---------------------------------------------------------------------------

def ensure_local_product_key(root: Path, project: str) -> str:
    """取或建 project 级稳定产品键（一次创建，重入读同一键）。"""
    _check_project(project)
    directory = _local_dir(root, project)
    path = directory / "product-key.json"
    if path.exists():
        doc = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(doc, dict) and doc.get("local_product_key"):
            return str(doc["local_product_key"])
    key = "lpk-" + secrets.token_hex(12)
    _atomic_write(path, json.dumps({"local_product_key": key, "project": project},
                                   ensure_ascii=False, indent=2))
    return key


def product_slot_path(root: Path, project: str, local_product_key: str) -> Path:
    _check_project(project)
    key = _safe_component(local_product_key, "local_product_key")
    return _local_dir(root, project) / ("slot-" + slugify(key) + ".json")


def acquire_product_add_slot(root: Path, project: str, local_product_key: str,
                             phase: str = "product-add") -> Dict[str, Any]:
    """O_EXCL 占位；持有者才能外调；返回 {ok, owner, attempt_id, path}。

    已存在 → ok=False（E_FRONT 借用错误码语义：占位已被占用），带现占用者信息。
    """
    path = product_slot_path(root, project, local_product_key)
    owner = "owner-" + secrets.token_hex(8)
    attempt_id = "att-" + secrets.token_hex(8)
    payload = {
        "schema_version": SCHEMA_VERSION, "kind": "product_add_slot",
        "project": project, "local_product_key": local_product_key,
        "owner": owner, "attempt_id": attempt_id,
        "phase": phase, "state": "attempted", "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(str(path), flags, 0o600)
    except FileExistsError:
        current = _read_slot(path)
        return {"ok": False, "code": "E_SLOT_HELD", "reason": "产品槽位已被占用",
                "slot": current, "path": str(path)}
    try:
        os.write(fd, (json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))
    finally:
        os.close(fd)
    return {"ok": True, "code": None, "owner": owner, "attempt_id": attempt_id,
            "path": str(path), "slot": payload}


def _read_slot(path: Path) -> Dict[str, Any]:
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
        return doc if isinstance(doc, dict) else {"state": "unknown"}
    except (OSError, ValueError):
        return {"state": "unknown"}


def update_product_slot(root: Path, project: str, local_product_key: str,
                        owner: str, attempt_id: str, updates: Dict[str, Any]) -> bool:
    """仅 owner+attempt 一致才允许更新槽位；返回是否更新成功。"""
    path = product_slot_path(root, project, local_product_key)
    current = _read_slot(path)
    if current.get("owner") != owner or current.get("attempt_id") != attempt_id:
        return False
    merged = dict(current)
    merged.update(updates)
    merged["updated_ts"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    _atomic_write(path, json.dumps(merged, ensure_ascii=False, indent=2) + "\n")
    return True


def release_product_slot(root: Path, project: str, local_product_key: str,
                         owner: str, attempt_id: str) -> bool:
    """仅当明确 transport 未开始且 owner/attempt 一致才允许释放预占。"""
    path = product_slot_path(root, project, local_product_key)
    current = _read_slot(path)
    if current.get("owner") != owner or current.get("attempt_id") != attempt_id:
        return False
    if current.get("transport_started"):
        return False
    try:
        path.unlink()
        return True
    except OSError:
        return False


def persist_product_mapping(root: Path, project: str, local_product_key: str,
                            platform_product_id: str) -> Dict[str, Any]:
    """持久化 local_product_key → platform_product_id 映射（重入复用）。"""
    directory = _local_dir(root, project)
    path = directory / ("map-" + slugify(local_product_key) + ".json")
    doc = {"schema_version": SCHEMA_VERSION, "project": project,
           "local_product_key": local_product_key,
           "platform_product_id": str(platform_product_id),
           "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    _atomic_write(path, json.dumps(doc, ensure_ascii=False, indent=2) + "\n")
    return doc


def find_product_mapping(root: Path, project: str, local_product_key: str) -> Optional[str]:
    path = _local_dir(root, project) / ("map-" + slugify(local_product_key) + ".json")
    if not path.exists():
        return None
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
        pid = doc.get("platform_product_id")
        return str(pid) if pid else None
    except (OSError, ValueError):
        return None


# ---------------------------------------------------------------------------
# generation 快照 / 候选 / 选择 / 域名
# ---------------------------------------------------------------------------

def _now_ts() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def persist_generation(root: Path, *, project: str, platform_product_id: str,
                       generation_id: str, segments: Sequence[Dict[str, Any]],
                       response_sha256: str, profile_sha256: str = "",
                       generate_rounds_requested: Any = None,
                       round_kind: str = "run_final_snapshot",
                       before_ids: Optional[Sequence[str]] = None,
                       after_ids: Optional[Sequence[str]] = None,
                       unchanged: bool = False,
                       supersede_previous: bool = False) -> Dict[str, Any]:
    """登记一次 generation 快照：每条 segment 一条事件 + 一条 generation 头事件。

    成功才调用（生成失败不得登记）；supersede_previous 时把旧活跃 generation 标记。
    """
    _check_project(project)
    if not str(platform_product_id or "").strip():
        _fail("E_SOURCE_BAD_PROJECT", "platform_product_id 缺失不可登记")
    generation = str(generation_id or "").strip()
    if not generation:
        generation = "gen-" + secrets.token_hex(10)
    now = _now_ts()
    events: List[Dict[str, Any]] = []
    if supersede_previous:
        for old in _active_generations(root, project, platform_product_id):
            events.append({"schema_version": SCHEMA_VERSION, "kind": "generation_superseded",
                           "project": project, "platform_product_id": str(platform_product_id),
                           "generation_id": old, "superseded_by": generation, "ts": now})
    header = {
        "schema_version": SCHEMA_VERSION, "kind": "generation_snapshot",
        "project": project, "platform_product_id": str(platform_product_id),
        "generation_id": generation, "round_kind": round_kind,
        "generate_rounds_requested": generate_rounds_requested,
        "before_ids": list(before_ids or []), "after_ids": list(after_ids or []),
        "unchanged": bool(unchanged), "response_sha256": response_sha256,
        "profile_sha256": profile_sha256, "segment_count": len(segments), "ts": now,
    }
    events.append(header)
    for segment in segments:
        if not isinstance(segment, dict):
            _fail("E_SOURCE_BAD_PROJECT", "segment 必须是 object")
        inf_id = str(segment.get("inf_id") or segment.get("id") or segment.get("_id") or "").strip()
        if not inf_id:
            _fail("E_SOURCE_BAD_PROJECT", "segment 缺平台 inf_id 不可登记")
        query_en = segment.get("query_en")
        if not isinstance(query_en, str) or not query_en.strip():
            _fail("E_SOURCE_BAD_PROJECT", "segment 缺 query_en 原文不可登记")
        segment_id = str(segment.get("segment_id") or segment.get("local_id") or "").strip()
        if not segment_id:
            segment_id = "S" + sha256_text(project + "|" + inf_id)[:10]
        event = {
            "schema_version": SCHEMA_VERSION, "kind": "segment_registered",
            "project": project, "platform_product_id": str(platform_product_id),
            "generation_id": generation, "segment_id": segment_id,
            "inf_id": inf_id,
            "segment_name": str(segment.get("segment_name") or segment.get("name") or ""),
            "platform_name": str(segment.get("segment_name") or segment.get("name") or ""),
            "query_en": query_en, "query_en_sha256": sha256_text(query_en),
            "query_total": segment.get("query_total"),
            "ai_reason": str(segment.get("ai_reason") or ""),
            "value_path": str(segment.get("value_path") or ""),
            "segment_definition": str(segment.get("segment_definition") or ""),
            "target_entity_categories": (
                list(segment.get("target_entity_categories"))
                if isinstance(segment.get("target_entity_categories"), (list, tuple))
                else ([segment["target_entity_categories"]]
                      if isinstance(segment.get("target_entity_categories"), str)
                      and segment["target_entity_categories"] else [])),
            "response_sha256": response_sha256, "observed_at": now,
        }
        events.append(event)
    _append_events(root, events)
    _write_projection(root, project)
    return {"ok": True, "generation_id": generation, "segment_count": len(segments),
            "events": len(events)}


def _write_projection(root: Path, project: str) -> None:
    events = _read_events(root, project)
    directory = _local_dir(root, project)
    lines = ["# 当前项目客群投影（机器真源=.local/segments.jsonl）", ""]
    seen = set()
    for event in reversed(events):
        if event.get("kind") != "segment_registered":
            continue
        key = (event.get("generation_id"), event.get("segment_id"))
        if key in seen:
            continue
        seen.add(key)
        lines.append("- %s | inf_id=%s | generation=%s | query_en=%r" % (
            event.get("segment_id"), event.get("inf_id"),
            event.get("generation_id"), event.get("query_en")))
    _atomic_write(directory / "segments-projection.md", "\n".join(lines) + "\n", 0o644)


def _active_generations(root: Path, project: str,
                       platform_product_id: str = "") -> List[str]:
    """按产品隔离：给了 platform_product_id 就只看该产品的 generation。"""
    generations: List[str] = []
    superseded = set()
    for event in _read_events(root, project):
        if (platform_product_id
                and str(event.get("platform_product_id")) != str(platform_product_id)):
            continue
        if event.get("kind") == "generation_snapshot":
            gen = event.get("generation_id")
            if gen and gen not in generations:
                generations.append(gen)
        if event.get("kind") == "generation_superseded":
            superseded.add(event.get("generation_id"))
    return [gen for gen in generations if gen not in superseded]


def current_generation(root: Path, project: str,
                       platform_product_id: Optional[str] = None) -> str:
    """当前项目/产品最近一次仍活跃的 generation_id；没有则返回空串。"""
    _check_project(project)
    active = _active_generations(root, project, str(platform_product_id or ""))
    return active[-1] if active else ""


def is_generation_superseded(root: Path, project: str, generation_id: str) -> bool:
    """只读判定：该 generation 是否已被新轮 supersede（旧轮不得再落档）。"""
    _check_project(project)
    for event in _read_events(root, project):
        if (event.get("kind") == "generation_superseded"
                and str(event.get("generation_id")) == str(generation_id)):
            return True
    return False


def generation_segments(root: Path, project: str,
                        generation_id: Optional[str] = None) -> List[Dict[str, Any]]:
    """按 generation 取已登记的 segment 快照（含 query_en 全文）；只读不写。"""
    _check_project(project)
    rows: List[Dict[str, Any]] = []
    for event in _read_events(root, project):
        if event.get("kind") != "segment_registered":
            continue
        if generation_id is not None and str(event.get("generation_id")) != str(generation_id):
            continue
        rows.append(dict(event))
    return rows


def load_current(root: Path, *, project: str, platform_product_id: Optional[str] = None,
                 generation_id: Optional[str] = None, segment_id: Optional[str] = None,
                 inf_id: Optional[str] = None) -> Dict[str, Any]:
    """按维度取当前记录；找不到 → E_SOURCE_STALE。"""
    _check_project(project)
    for event in _read_events(root, project):
        if event.get("kind") != "segment_registered":
            continue
        if platform_product_id is not None and str(event.get("platform_product_id")) != str(platform_product_id):
            continue
        if generation_id is not None and str(event.get("generation_id")) != str(generation_id):
            continue
        if segment_id is not None and str(event.get("segment_id")) != str(segment_id):
            continue
        if inf_id is not None and str(event.get("inf_id")) != str(inf_id):
            continue
        return dict(event)
    _fail("E_SOURCE_STALE", "未找到匹配的当前来源记录")


def validate_source(root: Path, *, project: str, platform_product_id: str,
                    generation_id: str, segment_id: str) -> Dict[str, Any]:
    """只判定不登记：返回当前记录；旧轮/跨产品/superseded → E_SOURCE_STALE。"""
    _check_project(project)
    events = _read_events(root, project)
    superseded = {e.get("generation_id") for e in events if e.get("kind") == "generation_superseded"}
    match = None
    for event in events:
        if event.get("kind") != "segment_registered":
            continue
        if (str(event.get("platform_product_id")) == str(platform_product_id)
                and str(event.get("generation_id")) == str(generation_id)
                and str(event.get("segment_id")) == str(segment_id)):
            match = event
    if match is None:
        # 本项目的 generation/segment 记录里找不到：伪造/旧轮/跨产品一律 stale
        # （跨产品引用在本项目事件流中同样不可见，统一按来源失效拒绝）。
        _fail("E_SOURCE_STALE", "当前项目无此 generation/segment 记录")
    if match.get("generation_id") in superseded:
        _fail("E_SOURCE_STALE", "generation 已 superseded")
    return dict(match)


def record_candidates(root: Path, *, project: str, generation_id: str,
                      segment_id: str, candidates: Sequence[Dict[str, Any]],
                      response_sha256: str, query_en: str = "") -> Dict[str, Any]:
    events = []
    now = _now_ts()
    for candidate in candidates:
        cid = str(candidate.get("id") or candidate.get("candidate_id") or "").strip()
        if not cid:
            _fail("E_SOURCE_BAD_PROJECT", "candidate 缺 id")
        events.append({
            "schema_version": SCHEMA_VERSION, "kind": "candidate_recorded",
            "project": project, "generation_id": generation_id,
            "segment_id": segment_id, "candidate_id": cid,
            "company_name": str(candidate.get("company_name") or ""),
            "query_en": query_en, "response_sha256": response_sha256,
            "observed_at": now,
        })
    if events:
        _append_events(root, events)
    return {"ok": True, "count": len(events)}


def record_base_info(root: Path, *, project: str, generation_id: str,
                     segment_id: str, candidate_id: str, resolved_domain: str,
                     response_sha256: str) -> Dict[str, Any]:
    if not str(resolved_domain or "").strip():
        _fail("E_SOURCE_BAD_PROJECT", "resolved_domain 缺失")
    _append_events(root, [{
        "schema_version": SCHEMA_VERSION, "kind": "base_info_recorded",
        "project": project, "generation_id": generation_id, "segment_id": segment_id,
        "candidate_id": str(candidate_id), "resolved_domain": str(resolved_domain),
        "base_info_response_sha256": response_sha256, "observed_at": _now_ts(),
    }])
    return {"ok": True}


def select_seed(root: Path, *, project: str, generation_id: str, segment_id: str,
                seed_origin: str, candidate_id: str = "", resolved_domain: str = "",
                user_url: str = "", user_quote_ref: str = "",
                selection_quote_ref: str = "") -> Dict[str, Any]:
    """记录选择事件：platform_id 或 user_url 两分支。"""
    if seed_origin not in ("platform_id", "user_url"):
        _fail("E_SOURCE_BAD_PROJECT", "seed_origin 必须是 platform_id/user_url")
    if seed_origin == "platform_id" and not str(candidate_id or "").strip():
        _fail("E_SEED_NOT_SELECTED", "platform_id 分支缺 candidate_id")
    if seed_origin == "user_url" and not str(user_url or "").strip():
        _fail("E_SEED_NOT_SELECTED", "user_url 分支缺原始网址")
    selection_id = "sel-" + sha256_text(
        "|".join([project, generation_id, segment_id,
                  str(candidate_id), str(resolved_domain), str(user_url)]))[:12]
    _append_events(root, [{
        "schema_version": SCHEMA_VERSION, "kind": "seed_selected",
        "project": project, "generation_id": generation_id, "segment_id": segment_id,
        "selection_id": selection_id, "seed_origin": seed_origin,
        "candidate_id": str(candidate_id or ""), "resolved_domain": str(resolved_domain or ""),
        "user_url": str(user_url or ""), "user_quote_ref": str(user_quote_ref or ""),
        "selection_quote_ref": str(selection_quote_ref or ""),
        "observed_at": _now_ts(),
    }])
    return {"ok": True, "selection_id": selection_id}


def load_selection(root: Path, *, project: str, selection_id: Optional[str] = None,
                   generation_id: Optional[str] = None,
                   segment_id: Optional[str] = None) -> Dict[str, Any]:
    for event in reversed(_read_events(root, project)):
        if event.get("kind") != "seed_selected":
            continue
        if selection_id is not None and str(event.get("selection_id")) != str(selection_id):
            continue
        if generation_id is not None and str(event.get("generation_id")) != str(generation_id):
            continue
        if segment_id is not None and str(event.get("segment_id")) != str(segment_id):
            continue
        return dict(event)
    _fail("E_SEED_NOT_SELECTED", "未找到匹配的选择记录")


def record_user_domain(root: Path, *, project: str, generation_id: str,
                       segment_id: str, user_url: str, normalized_domain: str,
                       user_quote_ref: str = "") -> Dict[str, Any]:
    """用户自带域名关联同 segment（不捏造平台 candidate id）。"""
    return select_seed(root, project=project, generation_id=generation_id,
                       segment_id=segment_id, seed_origin="user_url",
                       user_url=user_url, resolved_domain=normalized_domain,
                       user_quote_ref=user_quote_ref)
