#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""只读搜索 prepare/execute（Guard V2 B 组）。

两模式（GUARD-FIX-V2 §4.2/§5.1）：
  discover —— S3 首次平台选种：当前活跃 generation 的 segment，keyword 逐字
              query_en（不 trim/不改大小写/不折叠空白），不加四区排除。
  expand   —— 选定 candidate id → base-info → 选择事件，或用户自带域名关联；
              keyword=选定域名；默认四区真实 filters。

prepare 纯本地：输出 mode/规则原文摘录（文件+行号+sha）/registry 字段原文/
推导 keyword+filters/依赖摘要，不联网。execute 重读当前记录/规则，核对 request
引用的同一 generation/selection/query/filters，全部验证后才构建只读 transport；
依赖变化 → E_SOURCE_STALE。endpoint 限制 refine/company-list、domain/base-info；
不提供 similar-list。只读请求不索要保存授权。
"""
from __future__ import annotations

def _utf8_stdout():
    """Windows 控制台/管道默认 GBK：输出 emoji 会抛 UnicodeEncodeError；显式改 UTF-8。"""
    import sys as _sys
    for _s in (_sys.stdout, _sys.stderr):
        try:
            _s.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
_utf8_stdout()

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

TOOLS_DIR = Path(__file__).resolve().parent
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

import segment_fields
import segment_registry as registry
import rule_check
from api_base_url import api_url

SCHEMA_VERSION = 2
ALLOWED_ENDPOINTS = ("refine/company-list", "domain/base-info")
BANNED_ENDPOINTS = ("domain/similar-list",)
SEARCH_PAGE_SIZE_DEFAULT = 10
RULE_EXCERPTS = (
    ("RULES.md", ("搜索来源", "S3", "S4")),
    ("CORE-POINTS.md", ("S3", "S4", "域名")),
)


class SearchError(ValueError):
    def __init__(self, code: str, reason: str, **extra: Any):
        super().__init__(reason)
        self.code = code
        self.reason = reason
        self.extra = extra


def _fail(code: str, reason: str, **extra: Any) -> None:
    raise SearchError(code, reason, **extra)


def _excerpt_lines(text: str, keywords: Sequence[str], limit: int = 6) -> List[str]:
    hits = []
    for number, line in enumerate(text.splitlines(), 1):
        if any(word in line for word in keywords):
            hits.append({"line": number, "text": line.strip()[:200]})
        if len(hits) >= limit:
            break
    return hits


def rule_excerpts(kb_root: Path) -> List[Dict[str, Any]]:
    """读 RULES/CORE 与本任务相关原文摘录（文件/标题/行号/sha）。"""
    excerpts = []
    for name, keywords in RULE_EXCERPTS:
        path = Path(kb_root) / name
        if not path.is_file():
            continue
        raw = path.read_bytes()
        excerpts.append({
            "file": name, "sha256": __import__("hashlib").sha256(raw).hexdigest(),
            "hits": _excerpt_lines(raw.decode("utf-8", errors="replace"), keywords),
        })
    return excerpts


def normalize_domain(value: str) -> str:
    text = str(value or "").strip().lower()
    for prefix in ("https://", "http://"):
        if text.startswith(prefix):
            text = text[len(prefix):]
    text = text.split("/", 1)[0].split("?", 1)[0].split("#", 1)[0]
    if text.startswith("www."):
        text = text[4:]
    return text.strip(".")


# ---------------------------------------------------------------------------
# prepare
# ---------------------------------------------------------------------------

def prepare_search(root: Path, *, project: str, platform_product_id: str,
                   generation_id: str, segment_id: str,
                   mode: str, selection_id: Optional[str] = None,
                   page: int = 1, page_size: int = SEARCH_PAGE_SIZE_DEFAULT,
                   keep_regions: Optional[Sequence[str]] = None) -> Dict[str, Any]:
    """纯本地推导：mode/来源记录/keyword/filters/依赖摘要。无网络。"""
    if mode not in ("discover", "expand"):
        _fail("E_SOURCE_STALE", "mode 必须是 discover|expand")
    record = registry.validate_source(
        root, project=project, platform_product_id=platform_product_id,
        generation_id=generation_id, segment_id=segment_id)
    filters: List[Dict[str, Any]] = []
    query_en = record.get("query_en")
    if not isinstance(query_en, str) or not query_en.strip():
        _fail("E_SEGMENT_QUERY_EN_MISSING",
              "来源记录缺 query_en 原文；先跑 segments_infer 生成登记（禁止本地自写英文）")
    # 返工单 🔴1/⚡8：搜索 keyword 只允许 query_en 归一化整句。
    try:
        segment_fields.assert_search_keyword(query_en, query_en)
    except segment_fields.SegmentFieldError as exc:
        _fail(exc.code, exc.reason)
    keyword = query_en
    selection: Optional[Dict[str, Any]] = None
    if mode == "discover":
        if len(keyword.split()) < 8:
            pass  # <8 词只 WARN，不拒（拒绝理由是未绑定来源，不是长度）
        warn_short = len(keyword.split()) < 8
    else:
        selection = registry.load_selection(
            root, project=project, selection_id=selection_id,
            generation_id=generation_id, segment_id=segment_id)
        keyword = ""
        if selection.get("seed_origin") == "platform_id":
            domain = str(selection.get("resolved_domain") or "").strip()
            if not domain:
                _fail("E_SEED_NOT_SELECTED", "platform 选择缺 resolved_domain")
            keyword = domain
        else:
            keyword = normalize_domain(selection.get("user_url") or selection.get("resolved_domain") or "")
            if not keyword:
                _fail("E_SEED_NOT_SELECTED", "用户域名分支缺可规范化域名")
        # S4 默认四区 exclude；keep_regions=用户明确保留的区（须重审）。
        exclude = ([r for r in rule_check.FOUR_REGIONS
                    if r not in keep_regions] if keep_regions
                   else list(rule_check.FOUR_REGIONS))
        filters = rule_check.default_four_region_filters(exclude)
        warn_short = False
    dependencies = {
        "schema_version": SCHEMA_VERSION,
        "project": project,
        "platform_product_id": str(platform_product_id),
        "generation_id": str(generation_id),
        "segment_id": str(segment_id),
        "query_en_sha256": record.get("query_en_sha256"),
        "query_en": record.get("query_en"),
        "response_sha256": record.get("response_sha256"),
        "selection_id": (selection or {}).get("selection_id"),
        "mode": mode, "keyword": keyword, "filters": filters,
    }
    return {
        "schema_version": SCHEMA_VERSION, "kind": "prepared_search",
        "mode": mode, "project": project,
        "platform_product_id": str(platform_product_id),
        "generation_id": str(generation_id), "segment_id": str(segment_id),
        "selection_id": selection_id, "keyword": keyword, "filters": filters,
        "logic": "and", "page": int(page), "pageSize": int(page_size),
        "endpoint": "refine/company-list",
        "warn_short_query": bool(mode == "discover" and keyword and len(keyword.split()) < 8),
        "dependencies": dependencies,
        "dependency_sha256": rule_check.canonical_hash(dependencies),
        "rule_excerpts": rule_excerpts(root),
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }


def validate_prepared(root: Path, request: Dict[str, Any]) -> Dict[str, Any]:
    """execute 前重读当前记录，核对 request 引用；变化 → E_SOURCE_STALE。"""
    if not isinstance(request, dict):
        _fail("E_SOURCE_STALE", "request 必须是 object")
    for key in ("project", "platform_product_id", "generation_id", "segment_id",
                "mode", "dependencies", "dependency_sha256"):
        if key not in request:
            _fail("E_SOURCE_STALE", "request 缺 %s" % key)
    fresh = prepare_search(
        root, project=request["project"],
        platform_product_id=request["platform_product_id"],
        generation_id=request["generation_id"], segment_id=request["segment_id"],
        mode=request["mode"], selection_id=request.get("selection_id"),
        page=int(request.get("page", 1)),
        page_size=int(request.get("pageSize", SEARCH_PAGE_SIZE_DEFAULT)))
    if fresh["dependency_sha256"] != request["dependency_sha256"]:
        _fail("E_SOURCE_STALE", "依赖变化，须重新 prepare")
    if fresh["keyword"] != request.get("keyword"):
        _fail("E_SOURCE_STALE", "keyword 与来源推导不一致")
    if rule_check.canonical_hash(fresh["filters"]) != rule_check.canonical_hash(request.get("filters", [])):
        _fail("E_SOURCE_STALE", "filters 与来源推导不一致")
    return fresh


# ---------------------------------------------------------------------------
# execute
# ---------------------------------------------------------------------------

def normalize_response(raw: Any) -> Dict[str, Any]:
    """集中只读解析：list/records/data 数组差异保留完整响应；缺失报结构错误。"""
    if not isinstance(raw, dict):
        _fail("E_SOURCE_STALE", "响应不是 object")
    if raw.get("success") is not True:
        _fail("E_SOURCE_STALE", "接口未返回 success")
    data = raw.get("data")
    items: List[Dict[str, Any]]
    if isinstance(data, list):
        items = data
    elif isinstance(data, dict):
        for key in ("list", "records", "data"):
            if isinstance(data.get(key), list):
                items = data[key]
                break
        else:
            _fail("E_SOURCE_STALE", "响应缺 list/records/data 数组")
    else:
        _fail("E_SOURCE_STALE", "响应 data 结构异常")
    total = None
    if isinstance(data, dict):
        total = data.get("total")
    return {"items": items, "total": total, "raw": raw}


def execute_search(request: Dict[str, Any], transport_factory: Any = None,
                   transport: Any = None) -> Dict[str, Any]:
    """验证来源后才构建只读 transport；不索要保存授权。"""
    if transport_factory is not None and transport is not None:
        _fail("E_SOURCE_STALE", "transport_factory/transport 只能给一个")
    if transport is None and transport_factory is not None:
        transport = transport_factory()  # 仅在来源复验后由调用方传入工厂
    if transport is None:
        _fail("E_SOURCE_STALE", "缺少只读 transport")
    endpoint = str(request.get("endpoint") or "refine/company-list")
    if endpoint not in ALLOWED_ENDPOINTS:
        _fail("E_SOURCE_STALE", "endpoint 不在允许列表: %s" % endpoint)
    for banned in BANNED_ENDPOINTS:
        if banned in endpoint:
            _fail("E_SOURCE_STALE", "endpoint 被禁: %s" % endpoint)
    payload = {
        "keyword": request["keyword"], "current": int(request.get("page", 1)),
        "pageSize": int(request.get("pageSize", SEARCH_PAGE_SIZE_DEFAULT)),
        "filters": request.get("filters", []), "logic": request.get("logic", "and"),
    }
    response = transport(endpoint, payload)
    normalized = normalize_response(response)
    return {
        "schema_version": SCHEMA_VERSION, "kind": "search_executed",
        "mode": request.get("mode"), "endpoint": endpoint,
        "request_payload": payload,
        "total": normalized["total"], "items": normalized["items"],
        "response_sha256": rule_check.canonical_hash(response),
        "executed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }


def make_transport(root: Path, token: str, org: str, timeout: int = 60) -> Any:
    """基于 curl 的只读 transport（子进程 argv 与现役习惯一致）。"""
    import subprocess

    def call(endpoint: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        cmd = ["curl", "-sSL", "-m", str(int(timeout)), "-X", "POST",
               api_url(endpoint), "-H", "Content-Type: application/json",
               "-H", "accesstoken: " + token, "-H", "uid: " + org,
               "-d", json.dumps(payload, ensure_ascii=False)]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout + 10)
        try:
            return json.loads(result.stdout)
        except Exception:
            return {"success": False, "message": (result.stdout or result.stderr)[:200]}
    return call


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="受控只读搜索（discover/expand）")
    sub = parser.add_subparsers(dest="cmd", required=True)
    prep = sub.add_parser("prepare", help="纯本地推导，无网络")
    prep.add_argument("--root", default=str(Path(__file__).resolve().parent.parent))
    prep.add_argument("--project", required=True)
    prep.add_argument("--platform-product-id", required=True)
    prep.add_argument("--generation-id", required=True)
    prep.add_argument("--segment-id", required=True)
    prep.add_argument("--mode", required=True, choices=("discover", "expand"))
    prep.add_argument("--selection-id", default=None)
    prep.add_argument("--page", type=int, default=1)
    prep.add_argument("--out", default=None, help="可选写本机 prepared-search.json")
    exe = sub.add_parser("execute", help="按 prepared request 只读搜索")
    exe.add_argument("--root", default=str(Path(__file__).resolve().parent.parent))
    exe.add_argument("--request", required=True)
    exe.add_argument("--token", default="")
    exe.add_argument("--org", default="")
    args = parser.parse_args(argv)
    root = Path(args.root)
    try:
        if args.cmd == "prepare":
            prepared = prepare_search(
                root, project=args.project,
                platform_product_id=args.platform_product_id,
                generation_id=args.generation_id, segment_id=args.segment_id,
                mode=args.mode, selection_id=args.selection_id, page=args.page)
            text = json.dumps(prepared, ensure_ascii=False, indent=2)
            if args.out:
                Path(args.out).write_text(text, encoding="utf-8")
            print(text)
            return 0
        request = json.loads(Path(args.request).read_text(encoding="utf-8"))
        validated = validate_prepared(root, request)
        if not args.token or not args.org:
            print("DENY E_CREDENTIAL: execute 需要 --token/--org", file=sys.stderr)
            return 2
        result = execute_search(validated, transport=make_transport(root, args.token, args.org))
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (SearchError, registry.RegistryError, rule_check.RuleCheckError) as exc:
        print("DENY %s: %s" % (getattr(exc, "code", "E_SOURCE_STALE"), exc),
              file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
