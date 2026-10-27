#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""S5 保存计划与账簿（Guard V2 C 组核心）。

draft → confirmed → attempted/uncertain/accepted（GUARD-FIX-V2 §5.2/§5.3）：
  * prepare_save：纯本地，输出来源/审计/预算/系数/规则摘录 + 实际 wire 推导；
    不取凭据、不构造 transport、不签 auth。
  * confirm_plan：验证 draft 依赖、数量原话与估算；登记 approval；唯一调用
    auth_guard.authorize(action="save")（由 CLI confirm 流程调用）。
  * reserve_scope / mark_attempt / mark_uncertain / record_accepted / reconcile：
    front prefix 占位与结果不明账簿；scope 文件 O_EXCL，仅 owner+attempt 释放。
  * status：唯一自动对账生产者（operation/backend-task-status, type=cluesSave）。

约束：不新增布尔免检；revision 变更须重新 confirm；已发送 scope 不自动释放。
"""
from __future__ import annotations

import calendar
import math
import hashlib
import json
import os
import re
import secrets
import sys
import time
import unicodedata
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

TOOLS_DIR = Path(__file__).resolve().parent
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

import count_guard
import rule_check

SCHEMA_VERSION = 2
PLAN_TTL_SECONDS = 30 * 60
STATUS_ENDPOINT = "operation/backend-task-status"


class PlanError(ValueError):
    def __init__(self, code: str, reason: str, **extra: Any):
        super().__init__(reason)
        self.code = code
        self.reason = reason
        self.extra = extra


def _fail(code: str, reason: str, **extra: Any) -> None:
    raise PlanError(code, reason, **extra)


# ---------------------------------------------------------------------------
# 铁律 7：标签闸门（标签 = 语言-行业-角色，不是客群名/产品名）
# ---------------------------------------------------------------------------

TAG_LANGUAGES = (
    "英语", "西语", "德语", "法语", "日语", "韩语", "葡语", "俄语",
    "阿语", "意语", "荷语", "泰语", "越南语", "土耳其语",
)
TAG_ROLE_BLACKLIST = ("客群", "服务商", "运营商", "供应商", "渠道商")
TAG_EXAMPLE = "英语-户外露营-营地运营"
TAG_SEGMENT_MIN = 2
TAG_SEGMENT_MAX = 20
# 平台标签 ID 只认明确形态 + 台账已登记 ID，不再把任意 ASCII 串当 ID。
_CANONICAL_TAG_ID_RE = re.compile(r"^ctag[0-9]+$")
_HEX_TAG_ID_RE = re.compile(r"^[0-9a-f]{24}$")
_TAG_SPACE_RE = re.compile(r"\s")
_RECORD_PRODUCT_RE = re.compile(r"^product_key:\s*[\"']?([^\"'\n#]+)", re.MULTILINE)
_PRODUCT_IN_RECORD_RE = re.compile(r"产品\s*[：:=]\s*([^\n；;，,。|]{1,40})")
_SEGMENT_IN_RECORD_RE = re.compile(r"客群[^\n]*?[（(]\s*([^（）()\n]+?)\s*[）)]")
_TAG_ID_PAIR_RE = re.compile(r"([A-Za-z0-9_-]{2,64})\s*[（(]\s*([^（）()\n]{1,60}?)\s*[）)]")
_CONNECTOR_SPLIT_RE = re.compile(r"[与和及、,，/;；]")


def _strip_invisible(text: str) -> str:
    """删除全部 Unicode Cf（零宽/Bidi）字符。"""
    return "".join(ch for ch in text if unicodedata.category(ch) != "Cf")


def _normalize_label(text: Any) -> str:
    """去空白/标点 + NFKC + 小写，用于包含式比对。"""
    cleaned = _strip_invisible(str(text or ""))
    normalized = unicodedata.normalize("NFKC", cleaned)
    return "".join(ch for ch in normalized
                   if not ch.isspace()
                   and not unicodedata.category(ch).startswith("P")).lower()


def _clean_tag_text(value: Any):
    """返回 (原串, NFKC+去Cf+去首尾空白后的串)；两者不一致即视为非法字符。"""
    raw = str(value if value is not None else "")
    cleaned = _strip_invisible(raw)
    return raw, unicodedata.normalize("NFKC", cleaned).strip()


def _tag_values(value: Any) -> List[str]:
    """标签输入归一化为字符串列表（不做 strip，便于识别首尾空白）。"""
    if value is None:
        return []
    if isinstance(value, str):
        value = [value]
    try:
        return [str(item) for item in value]
    except TypeError:
        return [str(value)]


def looks_like_platform_tag_id(value: Any,
                               known_tag_ids: Sequence[str] = ()) -> bool:
    """平台标签 ID：ctagN / 24 位十六进制 / 台账已登记 ID。"""
    raw, text = _clean_tag_text(value)
    if not text or raw != text:
        return False
    if _CANONICAL_TAG_ID_RE.match(text):
        return True
    if _HEX_TAG_ID_RE.match(text):
        return True
    return text in {str(item).strip() for item in (known_tag_ids or ())}


def _tag_form(value: Any, known_tag_ids: Sequence[str] = ()) -> str:
    return "id" if looks_like_platform_tag_id(value, known_tag_ids) else "name"


def _segment_name_fragments(segment_names: Sequence[str]):
    """客群名 → (原客群名, 归一化整名/连接词切出的 >=4 字片段)。"""
    fragments = []
    for name in segment_names or ():
        raw = str(name or "").strip()
        if not raw:
            continue
        normalized = _normalize_label(raw)
        if normalized:
            fragments.append((raw, normalized, False))
        for chunk in _CONNECTOR_SPLIT_RE.split(unicodedata.normalize("NFKC", raw)):
            chunk_norm = _normalize_label(chunk)
            if len(chunk_norm) >= 4:
                fragments.append((raw, chunk_norm, True))
    seen = set()
    result = []
    for item in fragments:
        if item[1] in seen:
            continue
        seen.add(item[1])
        result.append(item)
    return result


def tag_name_problems(name: Any, product_name: str = "",
                      segment_names: Sequence[str] = (),
                      product_names: Sequence[str] = ()) -> List[str]:
    """校验单个标签名；返回问题列表（空列表 = 通过）。"""
    problems: List[str] = []
    raw, text = _clean_tag_text(name)
    if raw != text:
        problems.append("「%s」含不可见或非标准字符（首尾空白/全角变体/零宽或 Bidi 字符），平台标签不会包含这些字符"
                        % raw)
    if not text:
        problems.append("标签名为空")
        return problems
    if _TAG_SPACE_RE.search(text):
        problems.append("「%s」含空白；标签名不得含空格" % text)
    segments = text.split("-")
    if len(segments) != 3:
        problems.append("「%s」不是三段「语言-行业-角色」，也不是平台标签 ID"
                        "（ctag1 / 24 位十六进制 / operation-record 已登记 ID）" % text)
        return problems
    language, industry, role = segments
    segments_info = (("语言", language), ("行业", industry), ("角色", role))
    for label, segment in segments_info:
        if not segment:
            problems.append("「%s」的%s段为空（三段都必须有值）" % (text, label))
            continue
        if _TAG_SPACE_RE.search(segment):
            problems.append("「%s」的%s段「%s」含空白" % (text, label, segment))
        if not (TAG_SEGMENT_MIN <= len(segment) <= TAG_SEGMENT_MAX):
            problems.append("「%s」的%s段「%s」长度 %d，须在 %d..%d 字之间"
                            % (text, label, segment, len(segment),
                               TAG_SEGMENT_MIN, TAG_SEGMENT_MAX))
    if language and language not in TAG_LANGUAGES:
        problems.append("语言段「%s」不在白名单（可用：%s）"
                        % (language, "/".join(TAG_LANGUAGES)))
    # I1：产品名「包含 + 归一化」——等值、包含、片段（子串）都算。
    candidates = []
    for item in list(product_names or ()) + [product_name]:
        normalized = _normalize_label(item)
        if len(normalized) >= 2:
            candidates.append((str(item), normalized))
    for label, segment in segments_info:
        if not segment:
            continue
        segment_norm = _normalize_label(segment)
        for source, candidate in candidates:
            if candidate and segment_norm and (
                    candidate in segment_norm or segment_norm in candidate):
                problems.append("「%s」的%s段「%s」含产品名（「%s」）；铁律7 要求写买家行业/角色，不是我们的产品"
                                % (text, label, segment, source))
                break
    # R1：客群名整段或连接词片段被标签段包含 → 拒；读不到客群名时保守拒绝。
    fragments = _segment_name_fragments(segment_names)
    for label, segment in segments_info:
        if not segment:
            continue
        segment_norm = _normalize_label(segment)
        hit = None
        for source, fragment, is_chunk in fragments:
            if not fragment or fragment not in segment_norm:
                continue
            if is_chunk and len(fragment) == 4 and segment_norm == fragment:
                # 4 字通用片段恰为整段时放行（避免误伤 canonical：户外露营）。
                continue
            hit = source
            break
        if hit is not None:
            problems.append("「%s」的%s段「%s」包含客群名「%s」；标签不得用客群名或客群名片段"
                            % (text, label, segment, hit))
            break
    if not segment_names:
        for label, segment in segments_info:
            if len(segment) >= 8 and any(term in segment
                                        for term in TAG_ROLE_BLACKLIST):
                problems.append("读不到平台客群名，且%s段「%s」较长并含描述词（%s）；按保守策略拒绝，请改用买家行业/角色"
                                % (label, segment, "/".join(TAG_ROLE_BLACKLIST)))
                break
    # I2：角色黑名单从等值改包含（服务商A/客群运营 也拒）。
    if role:
        bad = [term for term in TAG_ROLE_BLACKLIST if term in role]
        if bad:
            problems.append("角色段「%s」含描述词（%s），不是买家角色"
                            % (role, "/".join(bad)))
    return problems


def _tag_rule_fail(problems: List[str]) -> None:
    reason = ("标签不合格，已拒绝（铁律7：标签=语言-行业-角色，不是客群名/产品名）：\n"
              + "\n".join("  - " + item for item in problems)
              + "\n正确示例：%s" % TAG_EXAMPLE
              + "\n平台标签 ID：ctag1（或 24 位十六进制 / operation-record 已登记 ID）")
    raise PlanError("E_TAG_RULE", reason, problems=list(problems),
                    example=TAG_EXAMPLE)


def validate_save_tag_pair(company_tags: Any, contact_tags: Any, *,
                           product_name: str = "",
                           product_names: Sequence[str] = (),
                           segment_names: Sequence[str] = (),
                           known_tag_ids: Sequence[str] = ()) -> None:
    """S5 标签闸门：公司/联系人各 1 个；名称必须三段且同名成对。

    * 允许两种形态：①名称=语言-行业-角色（逐段校验）；②平台 ID=ctagN /
      24 位十六进制 / operation-record 已登记 ID；
    * 两侧形态必须一致（都名称或都 ID）；一侧名称一侧 ID → 拒；
    * 两侧都是名称时同名成对；两侧都是 ID 时不强求同名（体系不同）。
    """
    company = _tag_values(company_tags)
    contact = _tag_values(contact_tags)
    problems: List[str] = []
    if len(company) != 1:
        problems.append("公司标签必须恰好 1 个（当前 %d 个：%s）"
                        % (len(company), company or "空"))
    if len(contact) != 1:
        problems.append("联系人标签必须恰好 1 个（当前 %d 个：%s）"
                        % (len(contact), contact or "空"))
    if problems:
        _tag_rule_fail(problems)
    company_value, contact_value = company[0], contact[0]
    if not company_value.strip():
        problems.append("公司标签为空")
    if not contact_value.strip():
        problems.append("联系人标签为空")
    if problems:
        _tag_rule_fail(problems)
    known = [str(item).strip() for item in (known_tag_ids or ())
             if str(item).strip()]
    company_form = _tag_form(company_value, known)
    contact_form = _tag_form(contact_value, known)
    if company_form != contact_form:
        problems.append("公司标签与联系人标签形态不一致（%s / %s）：必须都写「语言-行业-角色」名称，或都写平台标签 ID"
                        % (company_value, contact_value))
    for label, value, form in (("公司标签", company_value, company_form),
                               ("联系人标签", contact_value, contact_form)):
        if form == "id":
            continue
        problems.extend("%s：%s" % (label, item)
                        for item in tag_name_problems(
                            value, product_name, segment_names, product_names))
    if company_form == contact_form == "name":
        _, company_text = _clean_tag_text(company_value)
        _, contact_text = _clean_tag_text(contact_value)
        if company_text != contact_text:
            problems.append("公司标签与联系人标签必须同名成对（当前：%s / %s）"
                            % (company_text, contact_text))
    if problems:
        _tag_rule_fail(problems)


def _record_candidates(root: Path, project: str) -> List[Path]:
    key = str(project or "").strip().strip("/")
    if not key:
        return []
    return [Path(root) / "runs" / key / "operation-record.md",
            Path(root) / "runs" / Path(key).name / "operation-record.md"]


def _read_text(path: Path) -> str:
    try:
        return Path(path).read_text(encoding="utf-8")
    except OSError:
        return ""


def resolve_product_name(root: Path, project: str) -> str:
    """从 operation-record 读产品名（frontmatter product_key），读不到用项目键末段兜底。"""
    for candidate in _record_candidates(root, project):
        match = _RECORD_PRODUCT_RE.search(_read_text(candidate))
        if match and match.group(1).strip():
            return match.group(1).strip().strip("\"'")
    key = str(project or "").strip().strip("/")
    return Path(key).name if key else ""


def resolve_product_names(root: Path, project: str) -> List[str]:
    """I1 三重来源：operation-record 的 product_key/「产品：」中文名、
    项目目录名、product-profile 的 ②产品线首行。"""
    raw_names: List[str] = []

    def add(value: Any) -> None:
        text = str(value or "").strip().strip("\"'")
        if not text or any(token in text for token in ("<", ">", "{", "}")):
            return
        if text in ("（待补）", "(待补)", "待补", "无", "none", "None", "UNKNOWN"):
            return
        raw_names.append(text)

    key = str(project or "").strip().strip("/")
    if key:
        add(Path(key).name)
    for candidate in _record_candidates(root, project):
        text = _read_text(candidate)
        if not text:
            continue
        match = _RECORD_PRODUCT_RE.search(text)
        if match:
            add(match.group(1))
        for match in _PRODUCT_IN_RECORD_RE.finditer(text):
            add(match.group(1))
    if key:
        profile = _read_text(Path(root) / "runs" / key / "product-profile.md")
        for line in profile.splitlines():
            if line.startswith("# "):
                title = line[2:].strip()
                for word in ("产品知识档案", "product-profile", "机读", "📇",
                             "—", "·", "（", "）", "(", ")"):
                    title = title.replace(word, "")
                add(title.strip())
                break
        in_product_line = False
        for line in profile.splitlines():
            if line.startswith("## ②"):
                in_product_line = True
                continue
            if in_product_line and line.startswith("## "):
                break
            if in_product_line and line.strip().startswith("- 内容："):
                content = line.split("内容：", 1)[1].strip()
                add(content)
                add(re.split(r"[（(]|——", content)[0].strip(" ：:"))
                break
    seen = set()
    result: List[str] = []
    for name in raw_names:
        normalized = _normalize_label(name)
        if len(normalized) < 2 or normalized in seen:
            continue
        seen.add(normalized)
        result.append(name)
    return result


def load_segment_names(root: Path, project: str) -> List[str]:
    """R1 客群名来源：.local/segments.jsonl → operation-record 客群行 →
    runs/<project>/**/segments/*.json（回退 runs/**/segments/*.json）。"""
    root = Path(root)
    names: List[str] = []

    def add(value: Any) -> None:
        text = str(value or "").strip()
        if text and text not in names:
            names.append(text)

    key = str(project or "").strip().strip("/")
    for line in _read_text(root / ".local" / "segments.jsonl").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            doc = json.loads(line)
        except ValueError:
            continue
        if not isinstance(doc, dict) or doc.get("kind") != "segment_registered":
            continue
        event_project = str(doc.get("project") or "")
        if event_project and key and event_project != key:
            continue
        add(doc.get("platform_name") or doc.get("segment_name") or doc.get("name"))
    for candidate in _record_candidates(root, project):
        for line in _read_text(candidate).splitlines():
            if "客群" not in line:
                continue
            for match in _SEGMENT_IN_RECORD_RE.finditer(line):
                add(match.group(1))
    runs = root / "runs"
    paths = []
    if key and (runs / key).is_dir():
        paths = sorted((runs / key).glob("**/segments/*.json"))
    if not paths and runs.is_dir():
        paths = sorted(runs.glob("**/segments/*.json"))
    for path in paths:
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        for item in (doc if isinstance(doc, list) else [doc]):
            if not isinstance(item, dict):
                continue
            item_project = str(item.get("project") or "")
            if item_project and key and item_project != key:
                continue
            add(item.get("segment_name") or item.get("name")
                or item.get("platform_name"))
    return names


def _iter_tag_records(root: Path, project: str):
    """产出 (标签ID, 标签名)：operation-record 的 id(名称) 行 + .local/tags.json。"""
    root = Path(root)
    for candidate in _record_candidates(root, project):
        for line in _read_text(candidate).splitlines():
            if "标签" not in line:
                continue
            for match in _TAG_ID_PAIR_RE.finditer(line):
                yield match.group(1).strip(), match.group(2).strip()
    tags_path = root / ".local" / "tags.json"
    if not tags_path.is_file():
        return
    try:
        doc = json.loads(tags_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return

    def walk(node):
        if isinstance(node, dict):
            identifier = ""
            for field in ("id", "_id", "tag_id", "tagId", "tagID"):
                if isinstance(node.get(field), str) and node[field].strip():
                    identifier = node[field].strip()
                    break
            name = node.get("name") or node.get("tag_name") or node.get("label")
            if identifier and isinstance(name, str) and name.strip():
                yield identifier, name.strip()
            for value in node.values():
                yield from walk(value)
        elif isinstance(node, list):
            for item in node:
                yield from walk(item)

    yield from walk(doc)


_LEDGER_TAG_ID_RE = re.compile(r"^[A-Za-z][A-Za-z0-9]{4,15}$")


def load_known_tag_ids(root: Path, project: str) -> List[str]:
    """本地台账已登记的平台标签 ID。

    平台标签 ID 是随机短串（如 z2asngp / zcknehp / zhiwjox），约 14% 不含数字，
    因此不能以「含数字」作为判定条件；改为形状判定（字母开头 + 5–16 位字母数字），
    排除「（待补）」「无」「none」等占位词。
    """
    known: List[str] = []
    for tag_id, _ in _iter_tag_records(Path(root), project):
        if not tag_id or not _LEDGER_TAG_ID_RE.match(tag_id):
            continue
        if tag_id not in known:
            known.append(tag_id)
    return known


def load_tag_ledger(root: Path, project: str) -> Dict[str, List[str]]:
    """本地标签台账：ID → 名称列表（operation-record 的 id(名称) / tags.json）。"""
    ledger: Dict[str, List[str]] = {}
    for tag_id, name in _iter_tag_records(Path(root), project):
        if not tag_id or not name:
            continue
        names = ledger.setdefault(tag_id, [])
        if name not in names:
            names.append(name)
    return ledger


def validate_offline_tags(root: Path, project: str,
                          offline_input: Dict[str, Any]) -> None:
    """prepare/confirm 共用入口：卡片名称 + wire ID 双侧校验与绑定。"""
    if not isinstance(offline_input, dict):
        return
    root = Path(root)
    wire = offline_input.get("wire_payload")
    wire = wire if isinstance(wire, dict) else {}
    top_company = offline_input.get("companyTags")
    if top_company is None:
        top_company = offline_input.get("company_tags")
    top_contact = offline_input.get("contactTags")
    if top_contact is None:
        top_contact = offline_input.get("contact_tags")
    wire_company = wire.get("companyTags")
    wire_contact = wire.get("contactTags")
    top_values = _tag_values(top_company) + _tag_values(top_contact)
    wire_values = _tag_values(wire_company) + _tag_values(wire_contact)
    top_present = any(value.strip() for value in top_values)
    wire_present = any(value.strip() for value in wire_values)
    if not top_present and not wire_present:
        # 老 draft / 非标签请求：不新增死锁；真实 wire 由 rule_check 强校验非空。
        return
    if top_present != wire_present:
        _tag_rule_fail(["公司/联系人标签必须同时提供：卡片名称（顶层 companyTags/contactTags）"
                        "与 wire 标签 ID 不能只给一边"])
    known = load_known_tag_ids(root, project)
    wire_problems: List[str] = []
    for label, value in (("wire companyTags", wire_company),
                         ("wire contactTags", wire_contact)):
        for item in _tag_values(value):
            if not looks_like_platform_tag_id(item, known):
                wire_problems.append("%s 的「%s」不是平台标签 ID"
                                     "（ctag1 / 24 位十六进制 / operation-record 已登记 ID）"
                                     % (label, item))
    if wire_problems:
        _tag_rule_fail(wire_problems)
    validate_save_tag_pair(wire_company, wire_contact, known_tag_ids=known)
    top_has_name = any(value.strip()
                       and not looks_like_platform_tag_id(value, known)
                       for value in top_values)
    product_names: Sequence[str] = ()
    segment_names: Sequence[str] = ()
    product_name = ""
    if top_has_name:
        product_name = resolve_product_name(root, project)
        product_names = resolve_product_names(root, project)
        segment_names = load_segment_names(root, project)
    validate_save_tag_pair(top_company, top_contact, product_name=product_name,
                           product_names=product_names,
                           segment_names=segment_names, known_tag_ids=known)
    if not top_has_name:
        return
    ledger = load_tag_ledger(root, project)
    binding_problems: List[str] = []
    for label, names_value, ids_value in (
            ("公司标签", top_company, wire_company),
            ("联系人标签", top_contact, wire_contact)):
        name_values = _tag_values(names_value)
        id_values = _tag_values(ids_value)
        if not name_values or not id_values:
            continue
        name, tag_id = name_values[0].strip(), id_values[0].strip()
        if looks_like_platform_tag_id(name, known):
            continue
        mapped = {_normalize_label(item) for item in ledger.get(tag_id, [])}
        if _normalize_label(name) not in mapped:
            binding_problems.append("%s：名称「%s」与 wire 标签 ID「%s」在 operation-record/.local/tags.json 中无绑定记录"
                                    % (label, name, tag_id))
    if binding_problems:
        _tag_rule_fail(binding_problems)


def _now_ts() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _plans_dir(root: Path, project: str) -> Path:
    directory = Path(root) / ".local" / "guard_v2" / "plans" / rule_check.canonical_hash(project)[:16]
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def _atomic_write(path: Path, doc: Dict[str, Any], mode: int = 0o600) -> None:
    tmp = path.with_name(path.name + ".tmp-" + secrets.token_hex(6))
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(str(tmp), flags, mode)
    try:
        os.write(fd, (json.dumps(doc, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))
        os.fsync(fd)
    finally:
        os.close(fd)
    os.replace(str(tmp), str(path))
    os.chmod(path, mode)


def plan_path(root: Path, plan_id: str, revision: int) -> Path:
    return _plans_dir(root, plan_id) / ("plan-%s-r%03d.json" % (rule_check.canonical_hash(plan_id)[:16], int(revision)))


def scope_dir(root: Path) -> Path:
    directory = Path(root) / ".local" / "guard_v2" / "scopes"
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def scope_file(root: Path, query_scope_key: str) -> Path:
    return scope_dir(root) / ("scope-" + query_scope_key[:64] + ".json")


# ---------------------------------------------------------------------------
# prepare
# ---------------------------------------------------------------------------

def _resolve_manifest(root: Path, plan: Dict[str, Any]) -> Path:
    raw = str(plan.get("audit_manifest") or "").strip()
    if not raw:
        _fail("E_AUDIT_SCOPE", "plan 缺 audit_manifest（审计证据未绑定，不能确认/执行）")
    path = Path(raw)
    if not path.is_absolute():
        path = Path(root) / raw
    if not path.is_file():
        _fail("E_AUDIT_SCOPE", "audit manifest 不存在: %s" % path)
    return path


def build_dependencies(root: Path, plan: Dict[str, Any]) -> Dict[str, Any]:
    """从当前 registry + audit manifest 重建依赖快照。

    prepare 用它生成 dependency_sha256；confirm 与 execute 必须重跑本函数并比对，
    这样伪造 generation_id / 篡改审计窗口或 filters / 换来源都会在写路径前失败
    （E_SOURCE_STALE / E_PLAN_DEPENDENCY_CHANGED），不是死代码。
    """
    import segment_registry as registry
    project = str(plan.get("project") or "")
    manifest_path = _resolve_manifest(root, plan)
    try:
        record = registry.validate_source(
            Path(root), project=project,
            platform_product_id=str(plan.get("platform_product_id") or ""),
            generation_id=str(plan.get("generation_id") or ""),
            segment_id=str(plan.get("segment_id") or ""))
        selection = None
        if str(plan.get("selection_id") or "").strip():
            selection = registry.load_selection(
                Path(root), project=project,
                selection_id=str(plan["selection_id"]))
    except registry.RegistryError as exc:
        raise PlanError(exc.code, exc.reason)
    raw = manifest_path.read_bytes()
    try:
        manifest = json.loads(raw.decode("utf-8"))
    except ValueError:
        _fail("E_AUDIT_SCOPE", "audit manifest JSON 解析失败")
    wire = plan.get("wire_payload")
    if not isinstance(wire, dict):
        _fail("E_PLAN_PAYLOAD_MISMATCH", "plan 缺 wire_payload")
    return {
        "source": {
            "project": project,
            "platform_product_id": record.get("platform_product_id"),
            "generation_id": record.get("generation_id"),
            "segment_id": record.get("segment_id"),
            "inf_id": record.get("inf_id"),
            "query_en": record.get("query_en"),
            "query_en_sha256": record.get("query_en_sha256"),
            "response_sha256": record.get("response_sha256"),
            "selection_id": (selection or {}).get("selection_id"),
            "selection_origin": (selection or {}).get("seed_origin"),
            "selection_domain": (selection or {}).get("resolved_domain")
                                or (selection or {}).get("user_url"),
        },
        "audit": {
            "path": str(manifest_path),
            "sha256": hashlib.sha256(raw).hexdigest(),
            "window": manifest.get("window"),
            "query_scope": manifest.get("query_scope"),
            "evidence_mode": manifest.get("evidence_mode"),
        },
        "wire_payload_sha256": rule_check.canonical_hash(wire),
        "rule_excerpts_sha256": rule_check.canonical_hash(
            plan.get("rule_excerpts") or []),
        "budget_points": plan.get("budget_points"),
        "max_points": plan.get("max_points"),
        "estimation": plan.get("estimation"),
        "count": {
            "select_total": plan.get("selectTotal"),
            "derived_select_total": plan.get("derived_select_total"),
            "count_mode": plan.get("count_mode"),
            "count_hash": plan.get("count_hash"),
            "budget_ledger_hash": plan.get("budget_ledger_hash"),
            "count_evidence": plan.get("count_evidence"),
            "sample_ack": bool(str(plan.get("sample_ack") or "").strip()),
            "count_quote": plan.get("count_quote"),
        },
    }

def prepare_save(root: Path, *, project: str, source: Dict[str, Any],
                 audit: Dict[str, Any], budget: Dict[str, Any],
                 coefficients: Dict[str, Any], rule_excerpts: List[Dict[str, Any]],
                 offline_input: Dict[str, Any],
                 audit_manifest_path: str = "") -> Dict[str, Any]:
    """纯本地推导 draft。可缺预算出 draft，但 confirm 会 E_BUDGET_UNRESOLVED。"""
    for key in ("platform_product_id", "generation_id", "segment_id", "keyword"):
        if not str(source.get(key) or "").strip():
            _fail("E_PLAN_REQUIRED", "source 缺 %s" % key)
    # 铁律7 标签闸门：先于来源/预算推导；不合格立即 E_TAG_RULE（exit 2），不落盘。
    validate_offline_tags(Path(root), project, offline_input)
    # B1：prepare 即校验当前来源（旧 generation/跨产品/未登记 → E_SOURCE_STALE）。
    import segment_registry as registry
    try:
        registry.validate_source(
            Path(root), project=project,
            platform_product_id=str(source["platform_product_id"]),
            generation_id=str(source["generation_id"]),
            segment_id=str(source["segment_id"]))
        if str(source.get("selection_id") or "").strip():
            registry.load_selection(
                Path(root), project=project,
                selection_id=str(source["selection_id"]))
    except registry.RegistryError as exc:
        raise PlanError(exc.code, exc.reason)
    # 数量只能由 S4 收口证据 + 预算上界推导；selectTotal 不再是自由输入。
    evidence = offline_input.get("count_evidence")
    count_mode = str(offline_input.get("count_mode") or "").strip()
    explicit_count = offline_input.get("explicit_count")
    sample_ack = str(offline_input.get("sample_ack") or "").strip()
    count_quote = str(offline_input.get("count_quote") or "").strip()
    estimation = {
        "estimated_emails_per_company": coefficients.get("estimated_emails_per_company"),
        "estimated_points_per_email": coefficients.get("estimated_points_per_email"),
        "selectTotal": None,
    }
    ledger_doc = offline_input.get("budget_ledger") or budget.get("ledger")
    guard_plan = {"project": project,
                  "budget_points": budget.get("budget_points"),
                  "max_points": budget.get("max_points"),
                  "estimation": estimation}
    if ledger_doc is not None:
        guard_plan["budget_ledger"] = ledger_doc
    try:
        derived = count_guard.derive(
            evidence, guard_plan,
            mode=count_mode, explicit_count=explicit_count,
            sample_ack=sample_ack, quote=count_quote)
        if ledger_doc is not None:
            count_guard.verify_ledger_file(root, guard_plan)
    except count_guard.CountError as exc:
        _fail(exc.code, exc.reason)
    select_total = derived["select_total"]
    estimation["selectTotal"] = select_total
    manual = offline_input.get("selectTotal")
    if manual is not None:
        manual = rule_check.validate_select_total({**offline_input, "selectTotal": manual})
        if manual != select_total:
            _fail("E_SELECT_TOTAL_DERIVED_MISMATCH",
                  "手工 selectTotal=%d 与证据推导=%d 不一致" % (manual, select_total))
        count = offline_input.get("count")
        if count is not None:
            rule_check.check_count_alias({**offline_input, "selectTotal": select_total}, select_total)
    wire = rule_check.validate_wire(offline_input["wire_payload"]) if offline_input.get("wire_payload") else None
    if not isinstance(wire, dict):
        _fail("E_PLAN_REQUIRED", "缺 wire_payload，无法绑定保存数量")
    # TASK-20261027：档位唯一真源=wire.contactMaxCount；top-level 若提供必须一致。
    wire_tier = wire.get("contactMaxCount")
    top_tier = offline_input.get("contactMaxCount")
    if top_tier is not None and (type(top_tier) is not int or top_tier != wire_tier):
        _fail("E_CONTACT_TIER_MISMATCH",
              "contactMaxCount 不一致：top=%r wire=%r（唯一真源是 wire_payload）"
              % (top_tier, wire_tier))
    if wire.get("selectTotal") != select_total:
        _fail("E_SELECT_TOTAL_DERIVED_MISMATCH",
              "wire.selectTotal=%r 与证据推导=%d 不一致" % (wire.get("selectTotal"), select_total))
    plan_id = offline_input.get("plan_id") or ("plan-" + secrets.token_hex(8))
    revision = int(offline_input.get("revision") or 1)
    computed: Dict[str, Any] = {}
    unresolved: List[str] = []
    try:
        rule_check.check_coefficient_sources(estimation)
    except rule_check.RuleCheckError as exc:
        unresolved.append(exc.code)
    try:
        if select_total is not None:
            e = (estimation["estimated_emails_per_company"] or {}).get("value")
            p = (estimation["estimated_points_per_email"] or {}).get("value")
            values = rule_check.estimate_points(select_total, e, p)
            computed = {"estimated_emails": str(values["emails"]),
                        "estimated_points": str(values["points"])}
    except rule_check.RuleCheckError as exc:
        unresolved.append(exc.code)
    try:
        if select_total is not None:
            rule_check.check_budget(select_total, estimation,
                                    budget.get("budget_points"), budget.get("max_points"))
    except rule_check.RuleCheckError as exc:
        unresolved.append(exc.code)
    dependency_sha = None
    draft = {
        "schema_version": SCHEMA_VERSION, "kind": "save_plan",
        "plan_id": plan_id, "revision": revision, "status": "draft",
        "project": project, "profile_sha256": offline_input.get("profile_sha256", ""),
        "platform_product_id": source.get("platform_product_id"),
        "generation_id": source.get("generation_id"),
        "segment_id": source.get("segment_id"),
        "selection_id": source.get("selection_id", ""),
        "keyword": source.get("keyword"), "filters": source.get("filters", []),
        "logic": source.get("logic", "and"), "selectSort": source.get("selectSort", {}),
        "company_tags": offline_input.get("companyTags", []),
        "contact_tags": offline_input.get("contactTags", []),
        "contactMaxCount": wire_tier,
        "contactVerifyStatus": offline_input.get("contactVerifyStatus",
                                                 list(rule_check.VERIFY_STATUS_DRAFT)),
        "selectTotal": select_total,
        "derived_select_total": select_total,
        "count_mode": count_mode,
        "explicit_count": explicit_count,
        "sample_ack": sample_ack,
        "count_quote": count_quote,
        "count_evidence": evidence,
        "count_hash": derived["count_hash"],
        "budget_ledger": ledger_doc,
        "budget_ledger_hash": derived.get("ledger_hash"),
        "count_derivation": {
            "y": derived["y"], "n_budget": derived["n_budget"],
            "points": derived["points"], "unit": derived["unit"],
            "effective_budget": derived["effective_budget"],
        },
        "audit_manifest": audit.get("path", audit_manifest_path),
        "audit_window": audit.get("window"),
        "estimation": estimation, "budget_points": budget.get("budget_points"),
        "max_points": budget.get("max_points"),
        "computed": computed, "unresolved": sorted(set(unresolved)),
        "wire_payload": offline_input.get("wire_payload"),
        "wire_payload_sha256": (rule_check.canonical_hash(offline_input["wire_payload"])
                                 if offline_input.get("wire_payload") else None),
        "dependency_sha256": dependency_sha,
        "rule_excerpts": rule_excerpts,
        "query_scope": source.get("query_scope"),
        "expires_at": time.strftime("%Y-%m-%dT%H:%M:%SZ",
                                    time.gmtime(time.time() + PLAN_TTL_SECONDS)),
        "generated_at": _now_ts(),
    }
    dependencies = build_dependencies(Path(root), draft)
    draft["dependencies"] = dependencies
    draft["dependency_sha256"] = rule_check.canonical_hash(dependencies)
    return draft


def write_draft(root: Path, draft: Dict[str, Any], path: Optional[str] = None) -> str:
    target = Path(path) if path else plan_path(root, draft["plan_id"], draft["revision"])
    _atomic_write(target, draft)
    return str(target)


def load_plan(path: Any) -> Dict[str, Any]:
    doc = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(doc, dict) or doc.get("kind") != "save_plan":
        _fail("E_PLAN_REQUIRED", "不是有效 save_plan 文件")
    return doc


# ---------------------------------------------------------------------------
# 保存确认卡（present → confirm 显式绑定；TASK-20261027-count-card）
# ---------------------------------------------------------------------------

CARD_TTL_SECONDS = PLAN_TTL_SECONDS  # 卡有效期与 plan TTL 同口径（30 分钟）
CARD_FIELDS = ("plan_id", "revision", "project", "n", "wire_payload_sha256",
               "dependency_sha256", "budget_points", "max_points",
               "contactMaxCount")


def card_material(plan: Dict[str, Any],
                 presented_at: Optional[str] = None,
                 expires_at: Optional[str] = None) -> Dict[str, Any]:
    """规范化卡内容材料：绑定字段 + 时间元数据（R2：时间入指纹）。

    时间戳由 present_card 生成并一并纳入内容指纹；改动任意字段（含把
    expires_at 改远未来）而不重算 content_sha256 都会在校验时被拒。
    指纹只保内容一致性，不防恶意本机伪造（定位声明同 auth_guard）。
    """
    return {
        "action": "save",
        "plan_id": plan.get("plan_id"),
        "revision": plan.get("revision"),
        "project": plan.get("project"),
        "n": int(plan.get("selectTotal") or 0),
        "wire_payload_sha256": plan.get("wire_payload_sha256"),
        "dependency_sha256": plan.get("dependency_sha256"),
        "budget_points": plan.get("budget_points"),
        "max_points": plan.get("max_points"),
        "contactMaxCount": plan.get("contactMaxCount", 3),
        "presented_at": presented_at,
        "expires_at": expires_at,
    }


def card_content_hash(plan: Dict[str, Any],
                      presented_at: Optional[str] = None,
                      expires_at: Optional[str] = None) -> str:
    return rule_check.canonical_hash(card_material(plan, presented_at=presented_at,
                                                   expires_at=expires_at))


def _cards_dir(root: Path) -> Path:
    directory = Path(root) / ".local" / "guard_v2" / "cards"
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def card_path(root: Path, card_ref: str) -> Path:
    ref = str(card_ref or "").strip()
    if not re.fullmatch(r"card-[0-9a-f]{16}", ref):
        _fail("E_CARD_REQUIRED", "card_ref 非法（须 card-<16hex>）")
    return _cards_dir(root) / ("%s.json" % ref)


def _load_card(root: Path, card_ref: str) -> Dict[str, Any]:
    path = card_path(root, card_ref)
    if not path.is_file():
        _fail("E_CARD_UNKNOWN", "确认引用的保存卡不存在：%s" % ref_of(card_ref))
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except ValueError:
        _fail("E_CARD_TAMPERED", "保存卡 JSON 损坏")
    if not isinstance(doc, dict) or doc.get("kind") != "save_card":
        _fail("E_CARD_TAMPERED", "保存卡结构非法")
    return doc


def ref_of(card_ref: str) -> str:
    """引用原文（错误信息用），不做任何变换。"""
    return str(card_ref or "")


def _parse_utc_strict(value: Any, *, what: str) -> float:
    """R2：严格解析 "%Y-%m-%dT%H:%M:%SZ" UTC 时间。

    缺失/非字符串/空串/非法格式一律 E_CARD_TIME_INVALID（fail-closed），
    不再退化 deadline=0 跳过校验。
    """
    if not isinstance(value, str) or not value.strip():
        _fail("E_CARD_TIME_INVALID", "%s 缺失或非字符串: %r" % (what, value))
    try:
        return float(calendar.timegm(time.strptime(value.strip(),
                                                   "%Y-%m-%dT%H:%M:%SZ")))
    except ValueError:
        _fail("E_CARD_TIME_INVALID", "%s 非法时间: %r" % (what, value))
    return 0.0  # unreachable（_fail 必抛）


def _assert_tier_consistent(doc: Dict[str, Any]) -> None:
    """R2-B：wire.contactMaxCount 唯一真源；顶层存在须严格 int 且相等，
    缺省仅兼容 wire=3 的 legacy。出卡前/授权落盘前必经。"""
    wire = doc.get("wire_payload")
    if not isinstance(wire, dict):
        return
    wire_tier = wire.get("contactMaxCount")
    if "contactMaxCount" in doc:
        top = doc.get("contactMaxCount")
        ok = type(top) is int and top == wire_tier
    else:
        ok = wire_tier == 3
    if not ok:
        _fail("E_CONTACT_TIER_MISMATCH",
              "contactMaxCount 不一致：plan=%r wire=%r（唯一真源是 wire_payload）"
              % (doc.get("contactMaxCount", "<缺省>"), wire_tier))


def present_card(root: Path, draft_path: Any, *, now: Optional[float] = None) -> Dict[str, Any]:
    """持久化确认前保存卡，返回用户可读卡面与 card_ref。

    绑定字段（plan/revision/project/N/wire hash/dependency hash/预算）+
    时间元数据（presented_at/expires_at）一并进内容指纹；不铸票不写平台。
    R2-AC1：now 非有限拒；卡有效期=min(计划有效期, presented+CARD_TTL)；
    计划时间非法拒（fail-closed，不再 deadline=0 跳过）。
    R2-AC3：card_text 只输出白话，内部 ID/hash 只进 JSON metadata。
    哈希只证明「卡内容与 confirm 时一致」，不证明真人已读、不防恶意本机篡改。
    """
    draft = load_plan(draft_path)
    _assert_tier_consistent(draft)
    if draft.get("status") not in ("draft", "confirmed"):
        _fail("E_PLAN_NOT_CONFIRMED", "plan 状态非法，无法出卡")
    clock = time.time() if now is None else float(now)
    if not math.isfinite(clock):
        _fail("E_CARD_TIME_INVALID", "present now 非有限: %r" % now)
    presented_at = _now_ts()
    card_deadline = clock + CARD_TTL_SECONDS
    plan_expires = draft.get("expires_at")
    if isinstance(plan_expires, str) and plan_expires.strip():
        plan_deadline = _parse_utc_strict(plan_expires, what="draft expires_at")
        card_deadline = min(card_deadline, plan_deadline)
    if card_deadline <= clock:
        _fail("E_CARD_EXPIRED", "计划已过期，无法出卡，须重新 prepare")
    expires_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(card_deadline))
    material = card_material(draft, presented_at=presented_at,
                             expires_at=expires_at)
    content_hash = rule_check.canonical_hash(material)
    ref = "card-" + content_hash[:16]
    n = material["n"]
    if n <= 0:
        _fail("E_SELECT_TOTAL_INVALID", "卡面 N 必须为正整数")
    doc = {
        "schema_version": SCHEMA_VERSION, "kind": "save_card",
        "card_ref": ref, "content_sha256": content_hash,
        "card": material,
        "presented_at": presented_at,
        "expires_at": expires_at,
        "note": "hash 只绑定卡内容一致性（含时间元数据），不证明真人已读",
    }
    _atomic_write(card_path(root, ref), doc)
    # R2-AC3：白话卡面。预计扣点只取 computed.estimated_points（不明写未知），
    # 不把 budget_points 冒充预计扣点、max_points 冒充账户余额。
    computed = draft.get("computed") or {}
    est_points = computed.get("estimated_points")
    est_emails = computed.get("estimated_emails")

    def _clean(v):
        return v if isinstance(v, str) and v.strip() else None

    def _points_of(value):
        """budget_points 可能是 {"points": N,...} 或标量；只取数字，取不到=未知。"""
        if isinstance(value, dict):
            value = value.get("points")
        if isinstance(value, bool) or not isinstance(value, (int, float, str)):
            return None
        text = str(value).strip()
        return text if text else None

    points_text = ("约 %s 点（点＝平台用量额度，用一点扣一点，不是人民币；"
                   "首批实际可能略有出入，以平台为准）" % _clean(est_points)
                   if _clean(est_points) else "未知")
    emails_text = ("约 %s 个" % _clean(est_emails)) if _clean(est_emails) else "未知"
    budget_text = "%s 点" % (_points_of(material["budget_points"]) or "未知")
    tier = material.get("contactMaxCount", 3)
    tier_text = "每家公司最多 %s 个邮箱（可选 3/6/9，本批按 %s）" % (tier, tier)
    readable = (
        "【保存确认】\n"
        "保存家数：**%d 家**\n"
        "%s\n"
        "预计邮箱：%s\n"
        "预计扣点：%s\n"
        "本次预算上限：%s（超出会拒绝保存）\n"
        "\n"
        "确认后我开始保存：这一步只存名单、不发邮件；保存不可一键撤回。\n"
        "您现在可以：回「确认」，或直接回复卡上家数「%d」；"
        "要改数量或每公司邮箱数回复新数字，我重发新确认卡（旧卡作废）。\n"
        "下一步：确认后开始保存，存完向您报实际存了多少。"
        % (n, tier_text, emails_text, points_text, budget_text, n))
    return {"ok": True, "stage": "present", "card_ref": ref,
            "content_sha256": content_hash, "card_text": readable,
            "card_path": str(card_path(root, ref))}
# confirm
# ---------------------------------------------------------------------------

def binding_hash(plan: Dict[str, Any]) -> str:
    material = {
        "action": "save", "project": plan.get("project"),
        "plan_id": plan.get("plan_id"), "revision": plan.get("revision"),
        "wire_payload_sha256": plan.get("wire_payload_sha256"),
        "dependency_sha256": plan.get("dependency_sha256"),
        "count_hash": plan.get("count_hash"),
    }
    return rule_check.canonical_hash(material)


def _card_numeric_value(quote: str) -> Optional[int]:
    """纯 ASCII 正整数字符串才视为数字授权候选（AC1）。

    拒 0/负/小数/多数字/疑问/否定/中文数字——这些不是保存数量授权，
    交回上层按普通原话处理（大多为歧义拒绝）。
    """
    return rule_check.plain_numeric_save_count(quote)


def _verify_presentation(root: Path, draft: Dict[str, Any], *, quote: str,
                         now: float, verify_hash: bool = True) -> Dict[str, Any]:
    """校验确认引用的保存卡：存在、同计划同 revision、未过期、内容一致。

    返回卡文档；任何不一致拒绝（E_CARD_*）。哈希只证内容一致，
    不证明真人已读，也不防恶意本机篡改（定位声明同 auth_guard）。
    verify_hash=False 时只做轻校验（存在/同计划/过期），
    内容 hash 留给依赖重验之后的 _verify_card_content。
    """
    doc = _load_card(root, str(quote_ref_of(draft)))
    card = doc.get("card") or {}
    for key in ("plan_id", "revision"):
        if str(card.get(key)) != str(draft.get(key)):
            _fail("E_CARD_MISMATCH",
                  "保存卡与计划不一致（%s）：%r != %r，须重新出卡确认"
                  % (key, card.get(key), draft.get(key)))
    if card.get("project") != draft.get("project"):
        _fail("E_CARD_MISMATCH", "保存卡与计划 project 不一致，须重新出卡确认")
    # R2-AC1：卡时间严格校验——presented/expires 必须存在且合法（fail-closed），
    # 顺序有效（expires>presented），未过期；非有限 now 拒。
    if not math.isfinite(float(now)):
        _fail("E_CARD_TIME_INVALID", "now 非有限: %r" % now)
    presented = _parse_utc_strict(doc.get("presented_at"), what="卡 presented_at")
    deadline = _parse_utc_strict(doc.get("expires_at"), what="卡 expires_at")
    if deadline <= presented:
        _fail("E_CARD_TIME_INVALID",
              "卡时间顺序非法：expires(%r) <= presented(%r)"
              % (doc.get("expires_at"), doc.get("presented_at")))
    if float(now) > deadline:
        _fail("E_CARD_EXPIRED", "保存卡已过期，须重新 prepare/present")
    if verify_hash:
        _verify_card_content(draft, doc)
    return doc


def _verify_card_content(draft: Dict[str, Any], doc: Dict[str, Any]) -> None:
    """卡内容一致性：卡文件自 hash 重算 + 与当前计划绑定字段比对。

    卡文件被改而 content_sha256 未同步 → E_CARD_TAMPERED；
    计划字段变了（换计划/换数量/改预算）套旧卡 → E_CARD_TAMPERED。
    """
    stored = doc.get("card") or {}
    if rule_check.canonical_hash(stored) != doc.get("content_sha256"):
        _fail("E_CARD_TAMPERED",
              "保存卡文件内容与其 content_sha256 不一致（卡字段被篡改），须重新出卡")
    # R2：时间元数据在指纹里——改 expires_at/presented_at 而不重算 hash 必拒；
    # 重算了也会因与当前计划重算值不一致而拒。
    expected = card_content_hash(draft, presented_at=stored.get("presented_at"),
                                 expires_at=stored.get("expires_at"))
    if doc.get("content_sha256") != expected:
        _fail("E_CARD_TAMPERED",
              "保存卡内容 hash 与当前计划不一致（字段或时间被改/换卡），须重新出卡")
    # 顶层时间与卡体材料时间必须一致（防只改顶层不改卡体）
    if (str(doc.get("presented_at") or "") != str(stored.get("presented_at") or "")
            or str(doc.get("expires_at") or "") != str(stored.get("expires_at") or "")):
        _fail("E_CARD_TAMPERED",
              "保存卡顶层时间与卡体时间不一致，须重新出卡")


def _quote_ref_from_call(quote_ref: str) -> str:
    return str(quote_ref or "").strip()


def quote_ref_of(draft: Dict[str, Any]) -> str:
    """draft/plan 携带的卡引用（presentation 参数落盘后重读）。"""
    return str(draft.get("card_ref") or "").strip()


def confirm_plan(root: Path, draft: Dict[str, Any], *, quote: str,
                 quote_ref: str, now: Optional[float] = None,
                 presentation: Optional[str] = None) -> Dict[str, Any]:
    """验证依赖/数量/预算，产出同 binding 的 plan+render+ticket 材料。

    auth 票据铸造由调用方（save_company_cli confirm）经 auth_guard.authorize
    执行——本函数只做纯本地验证与 confirmed plan 落盘。
    presentation：确认引用的保存卡 card_ref（prepare 后 present_card 产出）。
    纯确认与纯数字 N 都必须携带有效卡引用；数字 N 还必须等于卡面 N。
    """
    if not isinstance(quote, str) or not quote.strip():
        _fail("E_AUTH_COUNT_AMBIGUOUS", "缺确认原话")
    if not str(quote_ref or "").strip():
        _fail("E_AUTH_COUNT_AMBIGUOUS", "缺 quote_ref（只追溯，不证明真人）")
    card_ref = str(presentation or "").strip()
    if not card_ref:
        _fail("E_CARD_REQUIRED",
              "确认必须携带明确的保存卡引用（present_card 产出的 card_ref）")
    draft = dict(draft)
    draft["card_ref"] = card_ref
    _assert_tier_consistent(draft)
    clock = time.time() if now is None else float(now)
    if not math.isfinite(clock):
        _fail("E_CARD_TIME_INVALID", "confirm now 非有限: %r" % now)
    if draft.get("status") not in ("draft", "confirmed"):
        _fail("E_PLAN_NOT_CONFIRMED", "plan 状态非法")
    # R2：draft 时间严格 fail-closed——缺失/非法不再 deadline=0 放行。
    deadline = _parse_utc_strict(draft.get("expires_at"), what="draft expires_at")
    if clock > deadline:
        _fail("E_PLAN_DEPENDENCY_CHANGED", "draft 已过期，须重新 prepare")
    # 确认前先验卡（轻校验：同计划同 revision、未过期；AC2）。
    card_doc = _verify_presentation(root, draft, quote=quote, now=clock,
                                    verify_hash=False)
    wire = draft.get("wire_payload")
    if not isinstance(wire, dict):
        _fail("E_PLAN_PAYLOAD_MISMATCH", "draft 缺 wire_payload")
    # 铁律7：confirm 再验一次标签，防手改 draft 绕过 prepare。
    validate_offline_tags(Path(root), str(draft.get("project") or ""), draft)
    select_total = rule_check.check_save(wire, {**draft, "status": "confirmed"})
    # 数量必须能从 S4 证据 + 预算重算；confirm 不接受 draft 自报值。
    try:
        count_guard.validate_plan(draft)
    except count_guard.CountError as exc:
        _fail(exc.code, exc.reason)
    # B1：confirm 重读 registry+audit manifest，依赖变化一律拒。
    current_dependencies = build_dependencies(Path(root), draft)
    if rule_check.canonical_hash(current_dependencies) != draft.get("dependency_sha256"):
        _fail("E_PLAN_DEPENDENCY_CHANGED",
              "依赖变化（来源/选择/filters/审计窗口/预算/系数），须重新 prepare")
    # 依赖未变后，卡内容与当前计划一致才算「确认的就是这张卡」（AC2）。
    _verify_card_content(draft, card_doc)
    # B2：原话数量必须可确定；歧义/缺失 → E_AUTH_COUNT_AMBIGUOUS（confirm 无 render.fields 路径）。
    # v3（2026-10-27）：卡面已经写清 N 家时，用户只回「确认/确认保存」也算授权——
    # 但必须整句纯确认（不含数字/别的动作词），N 从 plan 绑定并留痕 count_bound_by=card，
    # 保留“原话说了另一个数 → 拒绝”的防漂移检查。
    quoted = rule_check.extract_save_count(quote)
    numeric = _card_numeric_value(quote)
    if quoted is None and numeric is not None:
        # AC1：纯 ASCII 正整数只在已校验 S5 卡上下文里当数量授权；
        # 数值必须等于卡面 N（上面 _verify_presentation 已校卡与计划一致）。
        # 「1」与其他数字同规则：等于卡面 N 才过，否则是更改请求，不触发菜单白名单。
        quoted = numeric
    if quoted is None:
        if not rule_check.is_plain_save_confirm(quote):
            _fail("E_AUTH_COUNT_AMBIGUOUS",
                  "原话未给出可确定的公司数（歧义/缺失），须明确 N 家或只回「确认」后再确认")
        quoted = int(select_total["selectTotal"])
        count_bound_by = "card"
    elif numeric is not None:
        count_bound_by = "card"
    else:
        count_bound_by = "quote"
    if quoted != select_total["selectTotal"]:
        _fail("E_AUTH_COUNT_MISMATCH",
              "原话 %s 家与 plan/卡面 selectTotal=%d 不一致（这是更改请求，须重新 prepare 并展示新卡）"
              % (quote, select_total["selectTotal"]))
    confirmed = dict(draft)
    confirmed.update({
        # R2-AC2：先落 confirmed_pending（暂存），CLI 侧 render+authorize 全成功后
        # 经 commit_confirmed 才置 confirmed；失败走 rollback_uncommitted_confirm。
        "status": "confirmed_pending", "quote": quote, "quote_ref": quote_ref,
        "confirmed_at": _now_ts(), "binding_sha256": binding_hash(draft),
        "count_bound_by": count_bound_by,
        "count_bound_n": int(select_total["selectTotal"]),
        "card_ref": str(draft.get("card_ref") or ""),
        "card_content_sha256": card_doc.get("content_sha256"),
    })
    target = plan_path(root, confirmed["plan_id"], confirmed["revision"])
    if target.exists():
        existing = json.loads(target.read_text(encoding="utf-8"))
        if existing.get("status") == "confirmed":
            if (existing.get("binding_sha256") != confirmed.get("binding_sha256")
                    or existing.get("card_ref") != confirmed.get("card_ref")
                    or existing.get("card_content_sha256") != confirmed.get("card_content_sha256")):
                _fail("E_PLAN_ALREADY_CONFIRMED", "已有成功计划的绑定或卡不同，须新建 revision")
            return confirmed
    _atomic_write(target, confirmed)
    return confirmed


def commit_confirmed(root: Path, confirmed: Dict[str, Any]) -> Dict[str, Any]:
    """R2-AC2：确认链全部成功后提交 confirmed plan（幂等）。

    confirm_plan 本身改为暂存（pending 落盘），只有 CLI 侧 render+authorize
    都成功后才调用本函数真正置 confirmed。幂等：已是同 binding 的 confirmed
    直接返回，不双写。
    """
    if confirmed.get("status") not in ("confirmed_pending", "confirmed"):
        _fail("E_PLAN_NOT_CONFIRMED", "仅 confirm 产物可提交")
    target = plan_path(root, confirmed["plan_id"], confirmed["revision"])
    if target.exists():
        existing = json.loads(target.read_text(encoding="utf-8"))
        if existing.get("status") == "confirmed":
            if (existing.get("binding_sha256") != confirmed.get("binding_sha256")
                    or existing.get("card_ref") != confirmed.get("card_ref")
                    or existing.get("card_content_sha256") != confirmed.get("card_content_sha256")):
                _fail("E_PLAN_ALREADY_CONFIRMED", "已有成功计划的绑定或卡不同，须新建 revision")
            return {"ok": True, "already": True, "plan_path": str(target)}
    final = dict(confirmed)
    final["status"] = "confirmed"
    _atomic_write(target, final)
    return {"ok": True, "already": False, "plan_path": str(target)}


def rollback_uncommitted_confirm(root: Path, confirmed: Dict[str, Any],
                                 draft_path: Any = None) -> Dict[str, Any]:
    """R2-AC2：render/authorize 失败时回滚未提交的 confirm 落盘为 draft。

    只回滚本次链路自己写的 pending 态；不删除任何既有成功状态/凭证/票据。
    """
    target = plan_path(root, confirmed.get("plan_id"), confirmed.get("revision") or 1)
    rolled_back = False
    if target.exists():
        doc = json.loads(target.read_text(encoding="utf-8"))
        if (doc.get("status") == "confirmed_pending"
                and doc.get("binding_sha256") == confirmed.get("binding_sha256")
                and doc.get("card_ref") == confirmed.get("card_ref")):
            reverted = dict(doc)
            reverted["status"] = "draft"
            reverted["confirm_rolled_back_at"] = _now_ts()
            _atomic_write(target, reverted)
            rolled_back = True
    return {"ok": True, "rolled_back": rolled_back}


def load_confirmed(root: Path, plan_id: str, revision: int) -> Dict[str, Any]:
    path = plan_path(root, plan_id, revision)
    if not path.exists():
        _fail("E_PLAN_NOT_CONFIRMED", "无此 plan/revision: %s" % path)
    plan = load_plan(path)
    if plan.get("status") != "confirmed":
        _fail("E_PLAN_NOT_CONFIRMED", "plan 未确认")
    return plan


def validate_dependencies(root: Path, plan: Dict[str, Any],
                          current_dependencies: Dict[str, Any]) -> None:
    """写路径必经：用重建的依赖快照比对 plan 绑定（不是死代码）。"""
    if plan.get("status") not in ("draft", "confirmed"):
        _fail("E_PLAN_NOT_CONFIRMED", "plan 状态非法")
    if rule_check.canonical_hash(current_dependencies) != plan.get("dependency_sha256"):
        _fail("E_PLAN_DEPENDENCY_CHANGED", "依赖变化，须重新 prepare/confirm")


# ---------------------------------------------------------------------------
# scope 账簿（front prefix）
# ---------------------------------------------------------------------------

def reserve_scope(root: Path, *, query_scope_key: str, plan_id: str,
                  revision: int) -> Dict[str, Any]:
    """O_EXCL 占位；已占用 → E_FRONT_PREFIX_USED。"""
    path = scope_file(root, query_scope_key)
    owner = "owner-" + secrets.token_hex(8)
    attempt_id = "att-" + secrets.token_hex(8)
    doc = {
        "schema_version": SCHEMA_VERSION, "kind": "query_scope",
        "query_scope_key": query_scope_key, "owner": owner,
        "attempt_id": attempt_id, "plan_id": plan_id, "revision": int(revision),
        "state": "reserved", "ts": _now_ts(),
    }
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(str(path), flags, 0o600)
    except FileExistsError:
        current = _read_json(path)
        _fail("E_FRONT_PREFIX_USED",
              "scope 已被占用: plan=%s attempt=%s state=%s" % (
                  current.get("plan_id"), current.get("attempt_id"),
                  current.get("state")),
              scope=current)
    try:
        os.write(fd, (json.dumps(doc, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))
    finally:
        os.close(fd)
    return doc


def _read_json(path: Path) -> Dict[str, Any]:
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
        return doc if isinstance(doc, dict) else {}
    except (OSError, ValueError):
        return {}


def _write_scope(root: Path, query_scope_key: str, updates: Dict[str, Any],
                 owner: str, attempt_id: str) -> Dict[str, Any]:
    path = scope_file(root, query_scope_key)
    current = _read_json(path)
    if current.get("owner") != owner or current.get("attempt_id") != attempt_id:
        _fail("E_FRONT_PREFIX_USED", "scope owner/attempt 不匹配，拒绝更新他人锁")
    merged = dict(current)
    merged.update(updates)
    merged["updated_ts"] = _now_ts()
    _atomic_write(path, merged)
    return merged


def release_scope(root: Path, *, query_scope_key: str, owner: str,
                  attempt_id: str) -> bool:
    """仅明确 transport 未开始的 owner 可释放自己的预占。"""
    path = scope_file(root, query_scope_key)
    current = _read_json(path)
    if current.get("owner") != owner or current.get("attempt_id") != attempt_id:
        return False
    if current.get("transport_started"):
        return False
    if current.get("state") in ("accepted", "uncertain"):
        return False
    try:
        path.unlink()
        return True
    except OSError:
        return False


def mark_attempt(root: Path, *, query_scope_key: str, owner: str,
                 attempt_id: str, plan_id: str, revision: int) -> Dict[str, Any]:
    return _write_scope(root, query_scope_key, {
        "state": "attempted", "transport_started": True,
        "plan_id": plan_id, "revision": int(revision),
    }, owner, attempt_id)


def mark_uncertain(root: Path, *, query_scope_key: str, owner: str,
                   attempt_id: str, reason: str) -> Dict[str, Any]:
    """结果不明：保留 scope/auth 锁；不删锁、不自动重试。"""
    return _write_scope(root, query_scope_key, {
        "state": "uncertain", "uncertain_reason": str(reason)[:500],
        "uncertain_ts": _now_ts(),
    }, owner, attempt_id)


def record_accepted(root: Path, *, query_scope_key: str, owner: str,
                    attempt_id: str, task_id: str,
                    response: Dict[str, Any]) -> Dict[str, Any]:
    return _write_scope(root, query_scope_key, {
        "state": "accepted", "task_id": str(task_id),
        "accepted_response_sha256": rule_check.canonical_hash(response),
        "accepted_ts": _now_ts(),
    }, owner, attempt_id)


def load_scope(root: Path, query_scope_key: str) -> Dict[str, Any]:
    return _read_json(scope_file(root, query_scope_key))


# ---------------------------------------------------------------------------
# status / reconcile 账簿
# ---------------------------------------------------------------------------

def ledger_dir(root: Path) -> Path:
    directory = Path(root) / ".local" / "guard_v2" / "status-ledger"
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def record_status(root: Path, *, record: Dict[str, Any]) -> str:
    record_id = "rec-" + secrets.token_hex(8)
    doc = dict(record)
    doc.update({"schema_version": SCHEMA_VERSION, "kind": "status_record",
                "record_id": record_id, "ts": _now_ts()})
    path = ledger_dir(root) / (record_id + ".json")
    _atomic_write(path, doc)
    return record_id


def find_status_records(root: Path, *, plan_id: str, task_id: Optional[str] = None) -> List[Dict[str, Any]]:
    records = []
    for path in sorted(ledger_dir(root).glob("rec-*.json")):
        doc = _read_json(path)
        if doc.get("kind") != "status_record":
            continue
        if doc.get("plan_id") != plan_id:
            continue
        if task_id is not None and doc.get("task_id") != task_id:
            continue
        records.append(doc)
    return records


def load_attempt_task_id(root: Path, *, plan_id: str, revision: int,
                         query_scope_key: str, attempt_id: str) -> Optional[str]:
    """task_id 只能来自该 attempt 的受理回执（scope 账本）。"""
    scope = load_scope(root, query_scope_key)
    if (scope.get("plan_id") == plan_id and int(scope.get("revision") or 0) == int(revision)
            and scope.get("attempt_id") == attempt_id):
        task = scope.get("task_id")
        return str(task) if task else None
    return None


def find_accepted_scope(root: Path, *, plan_id: str, revision: int,
                        query_scope_key: Optional[str] = None) -> Dict[str, Any]:
    """定位该 plan/revision 已受理的 scope 账本（task_id 唯一合法来源）。

    优先看计划声明的 scope key；找不到时扫描 scope 目录，但仍严格校验
    plan_id + revision + state=accepted，避免跨计划/跨轮次串号。
    """
    wanted = str(plan_id or "")
    if not wanted:
        return {}
    candidates: List[Dict[str, Any]] = []
    if query_scope_key:
        candidates.append(load_scope(root, str(query_scope_key)))
    try:
        for path in sorted(scope_dir(root).glob("scope-*.json")):
            candidates.append(_read_json(path))
    except OSError:
        pass
    for scope in candidates:
        if (scope.get("state") == "accepted"
                and str(scope.get("plan_id") or "") == wanted
                and int(scope.get("revision") or 0) == int(revision)
                and scope.get("task_id")):
            return scope
    return {}


def reconcile(root: Path, *, plan_id: str, revision: int,
              query_scope_key: str, attempt_id: str,
              task_id: Optional[str] = None,
              task_status_json: Optional[Dict[str, Any]] = None,
              status_record_id: Optional[str] = None) -> Dict[str, Any]:
    """只消费本 CLI status 登记记录；外部 JSON/跨 plan task_id → E_RECONCILE_SOURCE。"""
    bound = load_attempt_task_id(root, plan_id=plan_id, revision=revision,
                                 query_scope_key=query_scope_key, attempt_id=attempt_id)
    if bound is None:
        _fail("E_RECONCILE_SOURCE", "该 attempt 无受理回执 task_id（人工处置态）")
    effective_task = task_id or bound
    if effective_task != bound:
        _fail("E_RECONCILE_SOURCE",
              "task_id 属于其他 attempt/plan: %s" % effective_task)
    if status_record_id is not None:
        path = ledger_dir(root) / (status_record_id + ".json")
        record = _read_json(path)
        if (record.get("kind") != "status_record"
                or record.get("plan_id") != plan_id
                or record.get("task_id") != bound):
            _fail("E_RECONCILE_SOURCE", "status 记录与本 plan/attempt 不绑定")
        if task_status_json is not None and rule_check.canonical_hash(task_status_json) != record.get("response_sha256"):
            _fail("E_RECONCILE_SOURCE", "外部 task-status JSON 与登记记录不一致")
        updated = _write_scope(root, query_scope_key, {
            "reconcile_record_id": status_record_id,
            "reconciled_ts": _now_ts(),
        }, attempt_id=attempt_id, owner=load_scope(root, query_scope_key).get("owner", ""))
        return {"ok": True, "scope": updated, "record": record}
    records = find_status_records(root, plan_id=plan_id, task_id=bound)
    if not records:
        _fail("E_RECONCILE_SOURCE", "无本 CLI status 调用记录，不能凭外部 JSON 对账")
    latest = records[-1]
    updated = _write_scope(root, query_scope_key, {
        "reconcile_record_id": latest.get("record_id"),
        "reconciled_ts": _now_ts(),
    }, attempt_id=attempt_id, owner=load_scope(root, query_scope_key).get("owner", ""))
    return {"ok": True, "scope": updated, "record": latest}


def status_payload(task_id: str) -> Dict[str, Any]:
    return {"type": "cluesSave", "id": str(task_id)}
