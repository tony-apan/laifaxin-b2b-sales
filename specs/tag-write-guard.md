---
doc_id: "specs-tag-write-guard"
title: "标签危险写统一前置门"
description: "列出仓内活跃发送器、已证标签删除/覆盖契约与统一拒绝边界。"
type: "spec"
status: "active"
updated: "2026-10-29"
---

# 标签危险写统一前置门

## 目标与边界
本门只覆盖本仓已识别的发送 helper：在构造 HTTP/子进程前按同一 path+payload 拒绝已知危险标签/联系人覆盖写。它不是主机防火墙，不能阻止绕过本模块的任意 raw 网络调用；host/重定向/凭据约束沿用各发送器现状。

## 契约来源（specs/api-reference.md）
- `tags/tag-delete`：`{type,id}` 删除标签。
- `tags/folder-delete`：`{id}` 删除标签目录。
- `contacts/contacts/update`、`contacts/contacts/batch-update`：路径存在，但仓内没有字段级契约、保留旧标签与读回验证定义，按未知覆盖写拒绝。
- `tags/tag-save`：仅 `{type,id,name}` 改名；空 id/name、null、额外字段（含 tags/数组/选择器）拒绝。
- `contacts/tags-save`：仓内无字段契约，按未知联系人标签写拒绝；`contacts/tags-list|add|dirs` 保持允许。

## 路径解释
归一与最终发送使用同一原始 path：拒绝自带 `api/` 前缀、查询/片段、百分号编码、反斜杠、重复斜杠、空段与 dot 段；其余去首尾斜杠并小写比较。发送器不得用归一化后的另一个 URL 发送。

## 合法不误杀
`contacts/tags-list|add|dirs`、`tags/tag-add|folder-add|folder-list|tag-info|tag-fav-add|tag-fav-delete`、`sequences/contact-add`（含 `views:[]`）、模板/序列/查询等非标签写保持通过。

## 安全追加：不实现
仓内没有“给已有联系人追加标签且保留旧标签”的接口字段、精确联系人 ID 选择器、前后读回字段或预算绑定契约；因此不实现，也不猜端点。需要该能力时先补真实契约与验收。

## 覆核
新 `tools/tag_write_guard.py` 由 23 个活跃发送 helper 在发送前调用；封条旧脚本 `contact_add.py`、`save_first_n.py`、`delete_all_products.py` 未撤封条，不计入活跃面。
