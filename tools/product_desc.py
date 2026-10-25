#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""S0 用途 → 平台推演描述（product_desc_zh）唯一拼装器（v3）。

固定一行、字段顺序固定、可审计：
    产品：<产品名>；已确认用途：<...|无>；待验证用途：<...|无>；排除条件：<...|无>

硬约束（用户裁决 + 第二席 P0）：
- 只接受**白名单字段**内容：档案 ①定位 ②产品线 ③卖点；④目标客群一律不进 payload（客群由平台推演）。
- 禁止整段档案原文（frontmatter/标题/source/confidence）、内部术语、第三方公司名/域名/邮箱/电话。
- 用途只写**应用场景**（终端用途/行业场景），禁止出现买家角色词（批发商/采购商/代理商/经销商/贸易商/店主等）。
- 不含昵称、联系方式、凭据、种子公司细节；未知一律写「无」。
- 用途不得写入 product-profile 的 8 个事实字段（本模块不读写任何档案）。
"""
import re

EMPTY = "无"
FORMAT = "产品：{}；已确认用途：{}；待验证用途：{}；排除条件：{}"
SEPARATOR = "、"
DIGEST_SEPARATOR = "，"

# 档案白名单字段（只允许 ①-③ 的内容行；④目标客群不参与平台推演）
PROFILE_FACTS = {"1": "定位", "2": "产品线", "3": "卖点"}
PROFILE_FACT_ORDER = ("1", "2", "3")
# ④ 存在只做本地档案/备注，不进 product_desc_zh
EXCLUDED_PROFILE_FACTS = {"4": "目标客群"}
FIELD4_EXCLUSION_REASON = "客群由平台推演"

# 用途只写应用场景；出现买家角色词=把「用途」写成了买家类型（本地编客群），一律拒绝
BUYER_ROLE_WORDS = (
    "批发商", "采购商", "代理商", "经销商", "贸易商", "店主",
    "分销商", "进口商", "零售商", "渠道商", "中间商",
)

# 内部术语/开发信息：一旦出现在任何字段就拒绝拼装（防泄漏给平台并回流给用户）
_INTERNAL_RE = re.compile(
    r"\bS(?:0a|1[0-2]|[0-9])\b|status|profile|pid|sha256|token|orgId|approval|query_en|segment|"
    r"source|confidence|hash",
    re.I,
)
# 第三方联系方式/域名/URL——不属于本产品档案可提交内容
_CONTACT_RE = re.compile(
    r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"
    r"|https?://|www\."
    r"|\+?\d[\d\s\-()]{6,}"
    r"|\b[A-Za-z0-9-]+\.(?:com|net|org|cn|io|co|biz|de|uk)\b",
    re.I,
)
# 整段档案原文的痕迹（frontmatter/标题/字段行）
_BULK_RE = re.compile(r"^\s*---|^\s*##\s|^\s*-\s*(?:内容|source|confidence)\s*[:：]", re.M | re.I)

_FORMAT_BREAKERS = ("；", ";", "\n", "\r")
_MAX_FIELD = 400


def _items(value):
    if value is None:
        return []
    if isinstance(value, str):
        raw = re.split(r"[,，、|/]+", value)
    else:
        raw = list(value)
    out = []
    for item in raw:
        text = str(item).strip()
        if text and text not in out:
            out.append(text)
    return out


FIELD_LABEL_WORDS = ("目标客群", "客群", "买家类型", "采购商画像", "客户画像")


def _clean(value, label, banned_terms):
    text = str(value).strip()
    if not text:
        return ""
    if any(token in text for token in _FORMAT_BREAKERS):
        raise ValueError("{} 含分隔符/换行，会破坏固定格式：{!r}".format(label, text))
    if any(word in text for word in FIELD_LABEL_WORDS):
        raise ValueError("{} 含客群类字段名 {!r}——客群只能由平台推演，禁止以任何形式写进推演描述：{!r}".format(label, next(w for w in FIELD_LABEL_WORDS if w in text), text))
    if _INTERNAL_RE.search(text):
        raise ValueError("{} 含内部术语，禁止进入推演描述：{!r}".format(label, text))
    if _CONTACT_RE.search(text):
        raise ValueError("{} 含 URL/域名/邮箱/电话，禁止进入推演描述：{!r}".format(label, text))
    if _BULK_RE.search(text):
        raise ValueError("{} 疑似整段档案原文（标题/frontmatter/字段行），禁止提交：{!r}".format(label, text))
    for term in banned_terms:
        term = str(term or "").strip()
        if term and term.lower() in text.lower():
            raise ValueError("{} 含昵称/敏感词 {!r}：{!r}".format(label, term, text))
    if len(text) > _MAX_FIELD:
        raise ValueError("{} 过长（>{} 字）".format(label, _MAX_FIELD))
    return text


def _join(values, label, banned_terms):
    cleaned = [_clean(v, label, banned_terms) for v in _items(values)]
    cleaned = [c for c in cleaned if c]
    return SEPARATOR.join(cleaned) if cleaned else EMPTY


def _clean_uses(values, label, banned_terms):
    """用途必须是应用场景；出现买家角色词即拒绝（防止本地编买家类型）。"""
    cleaned = _join(values, label, banned_terms)
    if cleaned == EMPTY:
        return cleaned
    for word in BUYER_ROLE_WORDS:
        if word in cleaned:
            raise ValueError(
                "{} 出现买家角色词 {!r}——用途只写应用场景（谁拿它做什么），不写买家类型".format(label, word))
    return cleaned


def _iter_profile_facts(profile_facts):
    """归一输入形态，逐条产出 (key, content)；不校验来源、不判归属。"""
    for item in profile_facts or []:
        if isinstance(item, dict):
            key = str(item.get("field") or item.get("no") or "").strip().strip("①②③④⑤⑥⑦⑧")
            content = item.get("content") or item.get("text") or ""
        elif isinstance(item, (list, tuple)) and len(item) == 2:
            key, content = str(item[0]).strip().strip("①②③④⑤⑥⑦⑧"), item[1]
        else:
            continue
        yield key.strip(), str(content or "").strip()


def normalize_profile_facts(profile_facts):
    """只归一 ①-③（定位/产品线/卖点）；④及⑤-⑧一律忽略，不进 payload。"""
    out = []
    seen = set()
    for key, text in _iter_profile_facts(profile_facts):
        if key not in PROFILE_FACTS or key in seen or not text:
            continue
        seen.add(key)
        out.append({"key": key, "label": PROFILE_FACTS[key], "content": text})
    out.sort(key=lambda item: PROFILE_FACT_ORDER.index(item["key"]))
    return out


def excluded_profile_facts(profile_facts):
    """④有内容时返回排除说明，供 operation-record 留痕（不进 payload）。"""
    for key, text in _iter_profile_facts(profile_facts):
        if key == "4" and text:
            return [{"key": "4", "label": EXCLUDED_PROFILE_FACTS["4"],
                     "reason": FIELD4_EXCLUSION_REASON}]
    return []


def build_profile_digest(profile_facts, banned_terms=()):
    """只拼 ①-③ 的内容行；空则返回空串（payload 保持纯产品名）。"""
    parts = []
    for item in normalize_profile_facts(profile_facts):
        parts.append("{}：{}".format(item["label"],
                                     _clean(item["content"], "档案" + item["label"], banned_terms)))
    return DIGEST_SEPARATOR.join(parts)


def build_product_desc_zh(product, confirmed_uses=(), pending_uses=(), exclusions=(),
                          banned_terms=(), profile_facts=()):
    """拼出唯一合法的 product_desc_zh 一行（严格四段、字段顺序不可变）。"""
    name = _clean(product, "产品", banned_terms)
    if not name:
        raise ValueError("产品名不能为空")
    digest = build_profile_digest(profile_facts, banned_terms)
    if digest:
        name = "{}（{}）".format(name, digest)
    confirmed = _clean_uses(confirmed_uses, "已确认用途", banned_terms)
    pending = _clean_uses(pending_uses, "待验证用途", banned_terms)
    excluded = _join(exclusions, "排除条件", banned_terms)
    return FORMAT.format(name, confirmed, pending, excluded)


def build_from_answers(product, answer="", confirmed_uses=(), pending_uses=(),
                       exclusions=(), banned_terms=(), profile_facts=()):
    """便捷入口：answer 是用户的用途选择（可多选，如"12"或"1,3"）。

    选择结果仍由用户在对话里确认；本函数不做任何推断、不补条。
    """
    chosen = []
    picks = re.findall(r"\d+", str(answer or ""))
    if picks:
        option_map = {str(i + 1): item for i, item in enumerate(_items(confirmed_uses))}
        chosen = [option_map[p] for p in picks if p in option_map]
    confirmed = chosen or list(confirmed_uses)
    return build_product_desc_zh(product, confirmed, pending_uses, exclusions,
                                 banned_terms, profile_facts)


def has_forbidden(text, banned_terms=()):
    """审计用：返回命中的禁用项（空列表=干净）。"""
    hits = []
    text = str(text or "")
    for rx in (_INTERNAL_RE, _CONTACT_RE, _BULK_RE):
        match = rx.search(text)
        if match:
            hits.append(match.group(0))
    for term in banned_terms:
        term = str(term or "").strip()
        if term and term.lower() in text.lower():
            hits.append(term)
    return hits
