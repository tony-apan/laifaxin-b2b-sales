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
        "contactMaxCount": offline_input.get("contactMaxCount", 3),
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


def confirm_plan(root: Path, draft: Dict[str, Any], *, quote: str,
                 quote_ref: str, now: Optional[float] = None) -> Dict[str, Any]:
    """验证依赖/数量/预算，产出同 binding 的 plan+render+ticket 材料。

    auth 票据铸造由调用方（save_company_cli confirm）经 auth_guard.authorize
    执行——本函数只做纯本地验证与 confirmed plan 落盘。
    """
    if not isinstance(quote, str) or not quote.strip():
        _fail("E_AUTH_COUNT_AMBIGUOUS", "缺确认原话")
    if not str(quote_ref or "").strip():
        _fail("E_AUTH_COUNT_AMBIGUOUS", "缺 quote_ref（只追溯，不证明真人）")
    if draft.get("status") not in ("draft", "confirmed"):
        _fail("E_PLAN_NOT_CONFIRMED", "plan 状态非法")
    expires = str(draft.get("expires_at") or "")
    try:
        # expires_at 是 UTC；time.mktime 按本地时区解析，Windows/UTC+8 会误判已过期。
        deadline = calendar.timegm(time.strptime(expires, "%Y-%m-%dT%H:%M:%SZ"))
    except ValueError:
        deadline = 0
    if deadline and (now if now is not None else time.time()) > deadline:
        _fail("E_PLAN_DEPENDENCY_CHANGED", "draft 已过期，须重新 prepare")
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
    # B2：原话数量必须可确定；歧义/缺失 → E_AUTH_COUNT_AMBIGUOUS（confirm 无 render.fields 路径）。
    quoted = rule_check.extract_save_count(quote)
    if quoted is None:
        _fail("E_AUTH_COUNT_AMBIGUOUS",
              "原话未给出可确定的公司数（歧义/缺失），须明确 N 家后再确认")
    if quoted != select_total["selectTotal"]:
        _fail("E_AUTH_COUNT_MISMATCH",
              "原话 %d 家与 plan selectTotal=%d 不一致" % (quoted, select_total["selectTotal"]))
    confirmed = dict(draft)
    confirmed.update({
        "status": "confirmed", "quote": quote, "quote_ref": quote_ref,
        "confirmed_at": _now_ts(), "binding_sha256": binding_hash(draft),
    })
    _atomic_write(plan_path(root, confirmed["plan_id"], confirmed["revision"]), confirmed)
    return confirmed


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
