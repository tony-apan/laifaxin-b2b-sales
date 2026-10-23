#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""执行护栏 · render 渲染留痕校验（v3）。

定位声明：
  本护栏定位=防走神/跳步，不防恶意攻击。同一进程可以改写任意本地文件，
  因此 .local 下的文件标记/哈希**不是安全边界**，也不承诺防伪造；
  真正的边界是：校验不通过时，调用方不得产生任何网络副作用。

v3 约定：
  * 文件：<repo>/.local/renders/<node>-<task_id>.json，权限 0600，禁止 symlink。
  * 头部：node / task / task_id / operator / product / seed / count /
          params_hash / user_quote / ts / fields / output（可选）/ sha（可选）。
  * task_id 必须由 sha256(operator|product|seed|count|params_hash)[:16] 派生。
  * params_hash 是本进程实际调用参数的 canonical sha256。
  * ts 与文件 mtime 都必须落在 30 分钟内（双重新鲜度）。
  * fields 用“带值捕获”的正则提取值，并与实际 payload 的同名/同义字段比对。
  * 校验通过后把 render_sha256（排除 sha 自身）写入头部 sha；汇报消息必须以
    [render:<sha 前 12 位>] 结尾，且正文必须与 render.output 原样一致。

示例 render（.local/renders/<node>-<task_id>.json，0600）：
  {
    "node": "S5", "task": "<task_id>", "task_id": "<task_id>",
    "operator": "acme", "product": "widget", "seed": "example.com", "count": 100,
    "params_hash": "<canonical sha256(payload)>", "user_quote": "保存100家",
    "ts": "2026-10-21T18:00:00+00:00",
    "fields": {
      "标签ID": "标签: id = 12345",
      "折合点/邮箱": "折合: 6200 点/邮箱",
      "单次上限": "单次上限: 100"
    },
    "output": "S5 保存确认\n客户: 100 家"
  }
  canonical_hash = sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")))
  task_id       = sha256(operator|product|seed|count|params_hash)[:16]

CLI：
  python3 tools/render_guard.py check --node S5 --task <task_id> \
      --params-json '{"tag_id":"12345","points_per_email":6200,"max_per_run":100}' \
      --operator acme --product widget --seed example.com --count 100
  python3 tools/render_guard.py check --node S5 --render .local/renders/S5-<id>.json \
      --require "标签ID,折合点/邮箱,单次上限" --params-json '...'
  python3 tools/render_guard.py report --render <path> --report-text "...[render:<sha12>]"
"""
from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import math
import os
import re
import secrets
import stat
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

ROOT = Path(__file__).resolve().parent.parent
MAX_AGE_SECONDS = 30 * 60
FUTURE_SKEW_SECONDS = 60
MAX_RENDER_BYTES = 512 * 1024

# S5 的必填字段：name 是 render.fields 的键；pattern 必须含 1 个捕获组；
# payload_keys 是实际调用 payload 中允许的键名（可多个别名）。
S5_FIELD_SPECS = (
    {
        "name": "标签ID",
        "pattern": r"标签.*?id\s*=\s*([0-9A-Za-z_-]+)",
        "payload_keys": ("tag_id", "company_tag_id", "companyTagId", "contact_tag_id", "标签ID"),
    },
    {
        "name": "折合点/邮箱",
        "pattern": r"折合.*?(\d+(?:\.\d+)?)\s*点/邮箱",
        "payload_keys": ("points_per_email", "pointsPerEmail", "折合点/邮箱"),
    },
    {
        "name": "单次上限",
        "pattern": r"单次上限\s*[:：=]?\s*(\d+)",
        "payload_keys": ("max_per_run", "maxPerRun", "单次上限", "count", "n", "limit"),
    },
)

# Guard V2 S5 render：保存家数只绑顶层 selectTotal；预算点数只来自 confirmed plan
# （payload 里没有该字段，经 check(extra_candidates=...) 注入，不做 payload 递归匹配）。
S5V2_FIELD_SPECS = (
    {
        "name": "标签ID",
        "pattern": r"标签.*?id\s*=\s*([0-9A-Za-z_-]+)",
        "payload_keys": ("companyTags", "contactTags", "标签ID"),
    },
    {
        "name": "保存家数",
        "pattern": r"保存家数\s*[:：=]?\s*(\d+)",
        "payload_keys": ("selectTotal", "count"),
    },
    {
        "name": "预算点数",
        "pattern": r"(?:预算|估算)点数\s*[:：=]?\s*(\d+(?:\.\d+)?)",
        "payload_keys": (),
    },
)

NODE_FIELD_SPECS = {"S5": S5_FIELD_SPECS, "S5V2": S5V2_FIELD_SPECS}

# v1 CLI 的自由文本正则只做固定别名映射，绝不把任意正则当字段规则运行。
LEGACY_REQUIRE_ALIASES = {
    "标签.*id=": "标签ID",
    "标签.*id": "标签ID",
    "折合.*点/邮箱": "折合点/邮箱",
    "折合.*点": "折合点/邮箱",
    "单次上限": "单次上限",
}

_HEX64_RE = re.compile(r"^[0-9a-fA-F]{64}$")
_HEX16_RE = re.compile(r"^[0-9a-fA-F]{16}$")
_TOKEN_RE = re.compile(r"^[\w.-]{1,128}$", re.UNICODE)


class RenderDenied(Exception):
    def __init__(self, code: str, reason: str, *, aliases: Optional[Sequence[str]] = None,
                 missing: Optional[Sequence[str]] = None):
        super().__init__(reason)
        self.code = code
        self.reason = reason
        self.aliases = list(aliases or ())
        self.missing = list(missing or ())


def canonical_json(value: Any) -> str:
    """稳定 JSON：排序键、无空白、拒绝 NaN/Infinity。"""
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False)


def canonical_hash(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def _normalize_count(value: Any) -> int:
    if isinstance(value, bool):
        raise ValueError("count 不能是 bool")
    if isinstance(value, int):
        number = value
    elif isinstance(value, float) and math.isfinite(value) and value.is_integer():
        number = int(value)
    elif isinstance(value, str) and re.fullmatch(r"\d+", value.strip()):
        number = int(value.strip())
    else:
        raise ValueError("count 必须是整数")
    if number < 0:
        raise ValueError("count 不能为负")
    return number


def derive_task_id(operator: Any, product: Any, seed: Any, count: Any,
                   params_hash: Any) -> str:
    """task_id = sha256(operator|product|seed|count|payload_hash)[:16]。"""
    for label, value in (("operator", operator), ("product", product), ("seed", seed)):
        if not isinstance(value, str) or not value.strip():
            raise ValueError(label + " 不能为空")
    if not isinstance(params_hash, str) or not _HEX64_RE.fullmatch(params_hash.strip()):
        raise ValueError("params_hash 必须是 64 位 sha256")
    material = "|".join((
        operator.strip(),
        product.strip(),
        seed.strip(),
        str(_normalize_count(count)),
        params_hash.strip().lower(),
    ))
    return hashlib.sha256(material.encode("utf-8")).hexdigest()[:16]


def compute_render_sha256(data: Dict[str, Any]) -> str:
    """render 内容哈希：排除 sha 自身，避免自引用。"""
    body = {k: v for k, v in data.items() if k != "sha"}
    return canonical_hash(body)


def report_suffix(sha256: str) -> str:
    return "[render:" + sha256[:12] + "]"


def _safe_token(label: str, value: Any) -> str:
    if not isinstance(value, str) or not value or value in (".", ".."):
        raise RenderDenied("E_RENDER_BAD_ARG", label + " 为空或非法")
    if not _TOKEN_RE.fullmatch(value):
        raise RenderDenied("E_RENDER_BAD_ARG", label + " 含路径分隔符或非法字符")
    return value


def render_path_for(node: str, task: str, root: Optional[Any] = None) -> Path:
    _safe_token("node", node)
    _safe_token("task", task)
    base = Path(root) if root is not None else ROOT
    return base / ".local" / "renders" / (node + "-" + task + ".json")


def _parse_ts(value: Any) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("ts 为空")
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    dt = datetime.fromisoformat(text)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _now_dt(value: Optional[Any]) -> datetime:
    if value is None:
        return datetime.now(timezone.utc)
    if isinstance(value, datetime):
        return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)
    if isinstance(value, str):
        return _parse_ts(value)
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(float(value), tz=timezone.utc)
    raise ValueError("now 非法")


def _read_secure(path: Path) -> Tuple[bytes, os.stat_result]:
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(str(path), flags)
    except FileNotFoundError:
        raise RenderDenied("E_RENDER_NO_FILE", "render 文件不存在: " + str(path),
                           aliases=("E_NO_RENDER",))
    except OSError as exc:
        raise RenderDenied("E_RENDER_BAD_FILE", "render 无法安全打开: " + str(exc))
    try:
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode):
            raise RenderDenied("E_RENDER_BAD_FILE", "render 不是普通文件")
        if stat.S_IMODE(st.st_mode) != 0o600:
            raise RenderDenied("E_RENDER_BAD_FILE",
                               "render 权限必须是 0600，实际 " + oct(stat.S_IMODE(st.st_mode)))
        if st.st_size > MAX_RENDER_BYTES:
            raise RenderDenied("E_RENDER_BAD_FILE", "render 文件过大")
        chunks: List[bytes] = []
        total = 0
        while True:
            chunk = os.read(fd, 65536)
            if not chunk:
                break
            total += len(chunk)
            if total > MAX_RENDER_BYTES:
                raise RenderDenied("E_RENDER_BAD_FILE", "render 文件过大")
            chunks.append(chunk)
        return b"".join(chunks), st
    finally:
        os.close(fd)


def _load_render(path: Path) -> Tuple[Dict[str, Any], os.stat_result]:
    raw, st = _read_secure(path)
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RenderDenied("E_RENDER_BAD_JSON", "render JSON 解析失败: " + str(exc))
    if not isinstance(data, dict):
        raise RenderDenied("E_RENDER_BAD_SCHEMA", "render 顶层必须是 object")
    return data, st


def _validate_schema(data: Dict[str, Any]) -> Dict[str, Any]:
    required = ("node", "operator", "product", "seed", "count",
                "params_hash", "user_quote", "ts", "fields")
    for key in required:
        if key not in data:
            raise RenderDenied("E_RENDER_BAD_SCHEMA", "render 缺头部字段: " + key)
    if not isinstance(data.get("node"), str) or not data["node"].strip():
        raise RenderDenied("E_RENDER_BAD_SCHEMA", "node 必须是非空字符串")
    task = data.get("task")
    task_id = data.get("task_id")
    if task is None and task_id is None:
        raise RenderDenied("E_RENDER_BAD_SCHEMA", "render 缺 task/task_id")
    if task is not None and (not isinstance(task, str) or not _HEX16_RE.fullmatch(task)):
        raise RenderDenied("E_RENDER_BAD_SCHEMA", "task 必须是 16 位派生 id")
    if task_id is not None and (not isinstance(task_id, str) or not _HEX16_RE.fullmatch(task_id)):
        raise RenderDenied("E_RENDER_BAD_SCHEMA", "task_id 必须是 16 位派生 id")
    if task is not None and task_id is not None and task.lower() != task_id.lower():
        raise RenderDenied("E_TASK_NOT_DERIVED", "task 与 task_id 不一致")
    effective_task = (task_id or task).lower()
    for key in ("operator", "product", "seed"):
        value = data.get(key)
        if not isinstance(value, str) or not value.strip():
            raise RenderDenied("E_RENDER_BAD_SCHEMA", key + " 必须是非空字符串")
    try:
        count = _normalize_count(data.get("count"))
    except ValueError as exc:
        raise RenderDenied("E_RENDER_BAD_SCHEMA", "count 非法: " + str(exc))
    params_hash = data.get("params_hash")
    if not isinstance(params_hash, str) or not _HEX64_RE.fullmatch(params_hash):
        raise RenderDenied("E_RENDER_BAD_SCHEMA", "params_hash 必须是 64 位 sha256")
    if not isinstance(data.get("user_quote"), str) or not data["user_quote"].strip():
        raise RenderDenied("E_RENDER_BAD_SCHEMA", "user_quote 必须是非空字符串")
    try:
        _parse_ts(data.get("ts"))
    except (TypeError, ValueError) as exc:
        raise RenderDenied("E_RENDER_BAD_SCHEMA", "ts 非法: " + str(exc))
    if not isinstance(data.get("fields"), dict):
        raise RenderDenied("E_RENDER_BAD_SCHEMA", "fields 必须是 object（v3 禁止自由文本）")
    if data.get("sha") is not None:
        if not isinstance(data["sha"], str) or not _HEX64_RE.fullmatch(data["sha"]):
            raise RenderDenied("E_RENDER_BAD_SCHEMA", "sha 必须是 64 位 sha256")
    if data.get("output") is not None and not isinstance(data["output"], str):
        raise RenderDenied("E_RENDER_BAD_SCHEMA", "output 必须是字符串")
    return {
        "task_id": effective_task,
        "count": count,
        "params_hash": params_hash.lower(),
        "operator": data["operator"].strip(),
        "product": data["product"].strip(),
        "seed": data["seed"].strip(),
    }


def _field_specs(node: str, require: Optional[Any]) -> Tuple[Dict[str, Any], ...]:
    if node not in NODE_FIELD_SPECS:
        raise RenderDenied(
            "E_RENDER_NO_SPECS",
            "节点 {0!r} 未登记字段白名单；v3 只允许 S5".format(node))
    defaults = tuple(NODE_FIELD_SPECS.get(node, ()))
    if require is None:
        if not defaults:
            raise RenderDenied(
                "E_RENDER_NO_SPECS",
                "节点 {0!r} 未登记字段白名单；v3 只允许 S5".format(node))
        return defaults
    if isinstance(require, str):
        raw = [x.strip() for x in require.split(",")]
    elif isinstance(require, (list, tuple)):
        raw = [x.strip() if isinstance(x, str) else x for x in require]
    else:
        raise RenderDenied("E_RENDER_BAD_REQUIRE", "require 必须是字段名列表")
    by_name = {spec["name"]: spec for spec in defaults}
    resolved: List[Dict[str, Any]] = []
    for item in raw:
        if isinstance(item, dict):
            name = item.get("name")
            pattern = item.get("pattern")
            keys = item.get("payload_keys") or (str(name),)
            if not isinstance(name, str) or not name.strip() or not isinstance(pattern, str):
                raise RenderDenied("E_RENDER_BAD_REQUIRE", "字段 spec 缺 name/pattern")
            try:
                compiled = re.compile(pattern, re.MULTILINE)
            except re.error as exc:
                raise RenderDenied("E_RENDER_BAD_REQUIRE", "字段正则非法: " + str(exc))
            if compiled.groups < 1:
                raise RenderDenied("E_RENDER_BAD_REQUIRE", name + " 的 pattern 必须含捕获组")
            resolved.append({"name": name.strip(), "pattern": pattern,
                             "payload_keys": tuple(str(k) for k in keys)})
            continue
        if not isinstance(item, str) or not item.strip():
            raise RenderDenied("E_RENDER_BAD_REQUIRE", "require 含空字段名")
        key = item.strip()
        if key in by_name:
            resolved.append(by_name[key])
        elif key in LEGACY_REQUIRE_ALIASES:
            canonical = LEGACY_REQUIRE_ALIASES[key]
            if canonical not in by_name:
                raise RenderDenied("E_RENDER_BAD_REQUIRE", "节点无此字段: " + canonical)
            resolved.append(by_name[canonical])
        else:
            raise RenderDenied("E_RENDER_BAD_REQUIRE",
                               "v3 只接受字段名或固定别名，不接受自由正则: " + key)
    if not resolved:
        raise RenderDenied(
            "E_RENDER_NO_SPECS",
            "节点 {0!r} 的字段白名单为空；v3 只允许 S5".format(node))
    return tuple(resolved)


def _field_value(fields: Dict[str, Any], spec: Dict[str, Any]) -> Tuple[bool, Any]:
    names = [spec["name"]] + [str(x) for x in spec.get("field_keys", ())]
    for key, value in fields.items():
        if str(key).strip() in names:
            return True, value
    return False, None


def _extract_captured(value: Any, pattern: str) -> Tuple[bool, Any]:
    if isinstance(value, dict):
        if "text" in value:
            value = value.get("text")
        elif "value" in value:
            value = value.get("value")
        else:
            return False, None
    if isinstance(value, bool) or value is None:
        return False, None
    if isinstance(value, (int, float)):
        return True, value
    if not isinstance(value, str):
        return False, None
    match = re.search(pattern, value, re.MULTILINE)
    if not match or match.lastindex is None:
        return False, None
    captured = match.group(1)
    if captured is None or not str(captured).strip():
        return False, None
    return True, captured.strip()


def _scalar_equal(left: Any, right: Any) -> bool:
    def decimal(value: Any):
        if isinstance(value, bool):
            return None
        if isinstance(value, (int, float)):
            if not math.isfinite(float(value)):
                return None
            return str(value)
        if isinstance(value, str):
            text = value.strip()
            if re.fullmatch(r"-?\d+(?:\.\d+)?", text):
                return text
        return None

    a, b = decimal(left), decimal(right)
    if a is not None and b is not None:
        try:
            from decimal import Decimal
            return Decimal(a) == Decimal(b)
        except Exception:
            return a == b
    if isinstance(left, str) and isinstance(right, str):
        return left.strip() == right.strip()
    return str(left).strip() == str(right).strip()


def _payload_candidates(payload: Any, spec: Dict[str, Any]) -> List[Any]:
    if not isinstance(payload, dict):
        return []
    keys = list(spec.get("payload_keys") or (spec["name"],))
    keys += [spec["name"]]
    values: List[Any] = []
    scopes = [payload]
    for nested in ("params", "data", "payload"):
        if isinstance(payload.get(nested), dict):
            scopes.append(payload[nested])
    for scope in scopes:
        for key in keys:
            if key in scope:
                value = scope[key]
                if isinstance(value, list):
                    values.extend(value)
                else:
                    values.append(value)
    # 不允许“值碰巧相等”的兜底：键名不匹配就是不一致（命名差异走 payload_keys 显式别名）。
    return values


def _capture_fields(data: Dict[str, Any],
                    specs: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    fields = data["fields"]
    captured: Dict[str, Any] = {}
    missing: List[str] = []
    for spec in specs:
        present, raw = _field_value(fields, spec)
        if not present:
            missing.append(spec["name"])
            continue
        ok, value = _extract_captured(raw, spec["pattern"])
        if not ok:
            missing.append(spec["name"])
            continue
        captured[spec["name"]] = value
    if missing:
        raise RenderDenied(
            "E_RENDER_MISSING_FIELDS",
            "render 缺少/无法提取字段: " + ", ".join(missing),
            aliases=["E_MISSING_FIELD:" + name for name in missing],
            missing=missing)
    return captured


def _check_output_bound(data: Dict[str, Any], captured: Dict[str, Any]) -> None:
    """R9：汇报正文必须含所有字段捕获值，禁止自创影子输出。"""
    output = data.get("output")
    if output is None:
        return
    if not isinstance(output, str) or not output.strip():
        raise RenderDenied("E_REPORT_NO_OUTPUT", "render.output 必须是非空字符串")
    absent = [name for name, value in captured.items()
              if str(value) not in output]
    if absent:
        raise RenderDenied(
            "E_REPORT_OUTPUT_UNBOUND",
            "render.output 未包含字段捕获值: " + ", ".join(absent))


def _check_fields(data: Dict[str, Any], specs: Sequence[Dict[str, Any]],
                  params: Any, extra_candidates: Any = None) -> Dict[str, Any]:
    captured = _capture_fields(data, specs)
    extra = extra_candidates if isinstance(extra_candidates, dict) else {}
    for spec in specs:
        value = captured[spec["name"]]
        candidates = _payload_candidates(params, spec)
        if spec["name"] in extra:
            # Guard V2：预算点数等只存在于 confirmed plan 的值经显式注入比对，
            # 不对 payload 做递归 any 匹配。
            plan_value = extra[spec["name"]]
            candidates = list(candidates) + [plan_value]
        if not candidates or not any(_scalar_equal(value, c) for c in candidates):
            raise RenderDenied(
                "E_RENDER_PAYLOAD_MISMATCH",
                "字段 {0} 的捕获值 {1!r} 与实际 payload 不一致".format(spec["name"], value))
    _check_output_bound(data, captured)
    return captured


def _write_sha(path: Path, data: Dict[str, Any], sha: str, st: os.stat_result) -> None:
    out = dict(data)
    out["sha"] = sha
    text = json.dumps(out, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    tmp = path.with_name(path.name + ".sha-" + secrets.token_hex(4))
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(str(tmp), flags, 0o600)
    try:
        os.write(fd, text.encode("utf-8"))
        os.fsync(fd)
    finally:
        os.close(fd)
    try:
        os.chmod(tmp, 0o600)
        os.replace(str(tmp), str(path))
        os.chmod(path, 0o600)
        # 写 sha 不得刷新 mtime，否则会把过期 render 洗成新鲜。
        os.utime(path, ns=(st.st_atime_ns, st.st_mtime_ns))
    finally:
        if tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                pass


def _failure(exc: RenderDenied, path: Optional[Any] = None) -> Dict[str, Any]:
    aliases = list(exc.aliases)
    legacy = [a for a in aliases
              if a == "E_NO_RENDER" or a.startswith("E_MISSING_FIELD:")]
    return {
        "ok": False,
        "code": exc.code,
        "reason": exc.reason,
        "aliases": aliases,
        # 原始任务书的两个原因码保留为 legacy_code(s)；v3 主码仍是 E_RENDER_*。
        "legacy_code": legacy[0] if legacy else None,
        "legacy_codes": legacy,
        "missing": list(exc.missing),
        "render_path": str(path) if path is not None else None,
    }


def _check_freshness(data: Dict[str, Any], st: os.stat_result, now: Any,
                     max_age_seconds: int) -> datetime:
    """双新鲜度：render.ts 与文件 mtime 都必须在窗口内。"""
    try:
        now_dt = _now_dt(now)
    except ValueError as exc:
        raise RenderDenied("E_RENDER_BAD_ARG", "now 非法: " + str(exc))
    try:
        ts_dt = _parse_ts(data["ts"])
    except (TypeError, ValueError) as exc:
        raise RenderDenied("E_RENDER_BAD_SCHEMA", "ts 非法: " + str(exc))
    age = (now_dt - ts_dt).total_seconds()
    if age < -FUTURE_SKEW_SECONDS:
        raise RenderDenied("E_RENDER_FUTURE_TS", "render.ts 在未来超过容差")
    if age > max_age_seconds:
        raise RenderDenied("E_RENDER_STALE", "render.ts 超过 30 分钟")
    mtime_age = now_dt.timestamp() - st.st_mtime
    if mtime_age < -FUTURE_SKEW_SECONDS:
        raise RenderDenied("E_RENDER_FUTURE_TS", "render mtime 在未来超过容差")
    if mtime_age > max_age_seconds:
        raise RenderDenied("E_RENDER_STALE", "render mtime 超过 30 分钟")
    return now_dt


def _check_derived_task(normalized: Dict[str, Any]) -> str:
    """render 内的 task/task_id 必须由自身字段 + params_hash 派生。"""
    try:
        derived = derive_task_id(normalized["operator"], normalized["product"],
                                 normalized["seed"], normalized["count"],
                                 normalized["params_hash"])
    except ValueError as exc:
        raise RenderDenied("E_TASK_NOT_DERIVED", "无法派生 task_id: " + str(exc))
    if normalized["task_id"] != derived:
        raise RenderDenied(
            "E_TASK_NOT_DERIVED",
            "render.task_id={0} 与参数派生值 {1} 不一致".format(
                normalized["task_id"], derived))
    return derived


def check(node: str, require: Optional[Any] = None, render_path: Optional[Any] = None,
          *, params: Any = None, task: Optional[str] = None,
          operator: Optional[str] = None, product: Optional[str] = None,
          seed: Optional[str] = None, count: Optional[Any] = None,
          now: Any = None, max_age_seconds: int = MAX_AGE_SECONDS,
          root: Optional[Any] = None, write_sha: bool = True,
          extra_candidates: Any = None) -> Dict[str, Any]:
    """校验一个节点的 render 文件；成功时返回 task_id/sha，并写入 sha 头。"""
    path: Optional[Path] = Path(render_path) if render_path is not None else None
    try:
        _safe_token("node", node)
        if path is None:
            if not isinstance(task, str) or not task:
                raise RenderDenied("E_RENDER_NO_FILE", "未提供 render 路径或 task")
            path = render_path_for(node, task, root)
        actual_params = {} if params is None else params
        try:
            expected_hash = canonical_hash(actual_params)
        except (TypeError, ValueError) as exc:
            raise RenderDenied("E_RENDER_BAD_PARAMS", "实际参数无法 canonical 化: " + str(exc))
        data, st = _load_render(path)
        normalized = _validate_schema(data)
        if data["node"].strip() != node:
            raise RenderDenied("E_RENDER_NODE_MISMATCH",
                               "render.node={0!r}，本次节点={1!r}".format(data["node"], node))
        if not hmac.compare_digest(normalized["params_hash"], expected_hash):
            raise RenderDenied("E_RENDER_PARAMS_MISMATCH",
                               "render.params_hash 与实际调用参数不一致")
        if count is not None:
            try:
                requested_count = _normalize_count(count)
            except ValueError as exc:
                raise RenderDenied("E_RENDER_BAD_ARG", "count 非法: " + str(exc))
            if requested_count != normalized["count"]:
                raise RenderDenied(
                    "E_COUNT_MISMATCH",
                    "render.count={0}，调用方 count={1}".format(
                        normalized["count"], requested_count))
        effective = {
            "operator": operator if operator is not None else normalized["operator"],
            "product": product if product is not None else normalized["product"],
            "seed": seed if seed is not None else normalized["seed"],
            "count": normalized["count"],
        }
        try:
            derived = derive_task_id(effective["operator"], effective["product"],
                                     effective["seed"], effective["count"], expected_hash)
        except ValueError as exc:
            raise RenderDenied("E_TASK_NOT_DERIVED", "无法派生 task_id: " + str(exc))
        if normalized["task_id"] != derived:
            raise RenderDenied("E_TASK_NOT_DERIVED",
                               "render.task_id={0} 与参数派生值 {1} 不一致".format(
                                   normalized["task_id"], derived))
        if task is not None and (not isinstance(task, str) or task.lower() != derived):
            raise RenderDenied("E_TASK_NOT_DERIVED",
                               "调用方 task={0!r} 与参数派生值 {1} 不一致".format(task, derived))

        _check_freshness(data, st, now, max_age_seconds)

        specs = _field_specs(node, require)
        captured = _check_fields(data, specs, actual_params,
                                 extra_candidates=extra_candidates)

        computed = compute_render_sha256(data)
        stored = data.get("sha")
        if stored is not None:
            if not hmac.compare_digest(str(stored).lower(), computed):
                raise RenderDenied("E_RENDER_SHA_MISMATCH", "render.sha 与内容哈希不一致")
            sha = computed
        else:
            sha = computed
            if write_sha:
                try:
                    _write_sha(path, data, sha, st)
                except OSError as exc:
                    raise RenderDenied("E_RENDER_WRITE_FAILED",
                                       "render.sha 写入失败: " + str(exc))
        return {
            "ok": True,
            "code": None,
            "reason": "",
            "render_path": str(path),
            "node": node,
            "task_id": derived,
            "params_hash": expected_hash,
            "render_sha256": sha,
            "sha12": sha[:12],
            "fields": captured,
            "output": data.get("output"),
        }
    except RenderDenied as exc:
        return _failure(exc, path)


def verify_report(report_text: str, render_path: Any, *, root: Optional[Any] = None,
                  now: Any = None,
                  max_age_seconds: int = MAX_AGE_SECONDS) -> Dict[str, Any]:
    """校验汇报消息：新鲜度 + task 派生 + 末尾 [render:<sha12>] + 正文一致。"""
    path = Path(render_path) if render_path is not None else None
    try:
        if path is None:
            raise RenderDenied("E_REPORT_NO_RENDER", "未提供 render 路径")
        data, st = _load_render(path)
        normalized = _validate_schema(data)
        _check_derived_task(normalized)
        _check_freshness(data, st, now, max_age_seconds)
        specs = _field_specs(data["node"].strip(), None)
        captured = _capture_fields(data, specs)
        _check_output_bound(data, captured)
        computed = compute_render_sha256(data)
        stored = data.get("sha")
        if stored is not None and not hmac.compare_digest(str(stored).lower(), computed):
            raise RenderDenied("E_RENDER_SHA_MISMATCH", "render.sha 与内容哈希不一致")
        if not isinstance(report_text, str):
            raise RenderDenied("E_REPORT_MISSING_SUFFIX", "汇报文本不是字符串")
        match = re.search(r"\[render:([0-9a-fA-F]{12})\]\s*$", report_text)
        if not match:
            raise RenderDenied("E_REPORT_MISSING_SUFFIX",
                               "汇报末尾缺少 [render:<sha前12位>]")
        if match.group(1).lower() != computed[:12]:
            raise RenderDenied("E_REPORT_SHA_MISMATCH",
                               "汇报 sha={0} 与 render 实际 sha={1} 不一致".format(
                                   match.group(1), computed[:12]))
        output = data.get("output")
        if not isinstance(output, str) or not output.strip():
            raise RenderDenied("E_REPORT_NO_OUTPUT", "render 未提供 output 原文")
        body = report_text[:match.start()].rstrip()
        if body != output.rstrip():
            raise RenderDenied("E_REPORT_TEXT_MISMATCH",
                               "汇报正文与 render.output 不一致（禁止影子输出）")
        return {"ok": True, "code": None, "reason": "",
                "render_path": str(path), "render_sha256": computed,
                "sha12": computed[:12]}
    except RenderDenied as exc:
        return _failure(exc, path)


def _load_json_arg(json_text: Optional[str], file_path: Optional[str],
                   default: Any = None) -> Any:
    if json_text is not None and file_path is not None:
        raise ValueError("--json 与 --file 只能二选一")
    if file_path is not None:
        return json.loads(Path(file_path).read_text(encoding="utf-8"))
    if json_text is not None:
        return json.loads(json_text)
    return default


def _print_deny(result: Dict[str, Any]) -> None:
    parts = [str(result.get("code"))]
    aliases = result.get("aliases") or []
    if aliases:
        parts.append("(" + ", ".join(aliases) + ")")
    print("DENY " + " ".join(parts) + ": " + str(result.get("reason")), file=sys.stderr)


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="render 留痕校验（v3）")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("check", help="校验 render 文件")
    p.add_argument("--node", required=True)
    p.add_argument("--task", default=None, help="期望的派生 task_id")
    p.add_argument("--render", default=None)
    p.add_argument("--require", default="", help="逗号分隔的字段名；默认按节点")
    p.add_argument("--params-json", default=None)
    p.add_argument("--params-file", default=None)
    p.add_argument("--operator", default=None)
    p.add_argument("--product", default=None)
    p.add_argument("--seed", default=None)
    p.add_argument("--count", type=int, default=None)
    p.add_argument("--root", default=None)
    p.add_argument("--no-write-sha", action="store_true")

    r = sub.add_parser("report", help="校验汇报消息与 render 一致")
    r.add_argument("--render", required=True)
    r.add_argument("--report-text", default=None)
    r.add_argument("--report-file", default=None)
    r.add_argument("--root", default=None)

    args = parser.parse_args(argv)
    if args.command == "check":
        try:
            params = _load_json_arg(args.params_json, args.params_file, default={})
        except Exception as exc:
            print("DENY E_RENDER_BAD_PARAMS: " + str(exc), file=sys.stderr)
            return 2
        require = args.require or None
        result = check(args.node, require, args.render, params=params,
                       task=args.task, operator=args.operator,
                       product=args.product, seed=args.seed, count=args.count,
                       root=args.root, write_sha=not args.no_write_sha)
        if result["ok"]:
            print("OK task_id={0} render={1} sha={2}".format(
                result["task_id"], result["render_path"], result["sha12"]))
            return 0
        _print_deny(result)
        return 2
    if args.command == "report":
        try:
            if args.report_text is not None and args.report_file is not None:
                raise ValueError("--report-text 与 --report-file 只能二选一")
            report_text = args.report_text
            if args.report_file is not None:
                report_text = Path(args.report_file).read_text(encoding="utf-8")
            if report_text is None:
                raise ValueError("必须提供 --report-text 或 --report-file")
        except Exception as exc:
            print("DENY E_REPORT_MISSING_SUFFIX: " + str(exc), file=sys.stderr)
            return 2
        result = verify_report(report_text, args.render, root=args.root)
        if result["ok"]:
            print("OK report_sha=" + result["sha12"])
            return 0
        _print_deny(result)
        return 2
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
