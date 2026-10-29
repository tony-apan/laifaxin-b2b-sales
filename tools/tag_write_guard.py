#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""标签危险写统一前置门（B 2026-10-29）。

只封本仓已识别、契约明确的标签删除/目录删除/联系人覆盖更新路径。
不声称主机防火墙；不阻止绕过本模块的任意 raw 网络调用。
路径按最终发送 URL 的同一解释归一；有歧义（编码/dot段/重复斜杠/查询）直接拒绝。
"""

DANGEROUS_PATHS = frozenset({
    "tags/tag-delete",
    "tags/folder-delete",
    "contacts/contacts/update",
    "contacts/contacts/batch-update",
})

# 只列本仓已有契约的标签读/建/改名/收藏路径；tag-save 另按精确字段校验。
_SAFE_TAG_PATHS = frozenset({
    "tags/folder-list", "tags/folder-add",
    "tags/tag-add", "tags/tag-save", "tags/tag-info",
    "tags/tag-fav-add", "tags/tag-fav-delete",
})
_SAFE_CONTACT_TAG_PATHS = frozenset({
    "contacts/tags-list", "contacts/tags-add", "contacts/tags-dirs",
})
# contacts/contacts/* 仅放行仓内实际读取/新建路径；delete/update/replace 等未知写默认拒。
_SAFE_CONTACT_PATHS = frozenset({
    "contacts/contacts/show", "contacts/contacts/save", "contacts/contacts/select-count",
})


def normalize_path(path):
    raw = str(path or "").strip()
    if any(ch in raw for ch in ("?", "#", "%", "\\")):
        raise ValueError("路径含查询/编码/反斜杠，含义有歧义，拒绝发送")
    if raw.startswith(("api/", "/api/")):
        raise ValueError("路径自带 api 前缀，含义有歧义，拒绝发送")
    raw = raw.strip("/")
    if "//" in raw:
        raise ValueError("路径含重复斜杠，含义有歧义，拒绝发送")
    parts = raw.split("/") if raw else []
    if any(p in ("", ".", "..") for p in parts):
        raise ValueError("路径含空段/dot 段，含义有歧义，拒绝发送")
    return "/".join(parts).lower()


def _check_tag_save(payload):
    """tags/tag-save 只允许已证改名 {type,id,name}；其他字段或空值拒绝。"""
    if not isinstance(payload, dict) or set(payload) != {"type", "id", "name"}:
        raise ValueError("tags/tag-save 只允许改名字段 type/id/name，拒绝覆盖/清空标签")
    if payload.get("type") not in ("company", "contacts"):
        raise ValueError("tags/tag-save type 非法")
    for key in ("id", "name"):
        value = payload.get(key)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"tags/tag-save {key} 为空，拒绝覆盖")


def check_send(path, payload=None):
    """危险标签/联系人覆盖写禁止发送；返回 None，拒绝时抛 ValueError。"""
    value = normalize_path(path)
    if value in DANGEROUS_PATHS:
        raise ValueError("标签删除或联系人批量更新接口未授权，拒绝发送")
    if value == "tags/tag-save":
        _check_tag_save(payload)
        return None
    if value.startswith("tags/") and value not in _SAFE_TAG_PATHS:
        raise ValueError("未知标签路径默认拒绝")
    if value.startswith("contacts/tags-") and value not in _SAFE_CONTACT_TAG_PATHS:
        raise ValueError("未知联系人标签路径默认拒绝")
    if value.startswith("contacts/contacts/") and value not in _SAFE_CONTACT_PATHS:
        raise ValueError("未知联系人写路径默认拒绝")
    return None
