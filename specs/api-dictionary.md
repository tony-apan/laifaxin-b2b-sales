---
doc_id: "lfx-api-dictionary"
title: "来发信接口字典（排障速查）"
description: "按用途列接口、要点、常见报错与替代路径；出问题先查本表再下结论。"
type: "spec"
status: "active"
updated: "2026-10-23"
created: "2026-10-22"
---

# 来发信接口字典（出问题先查这张表）

> 铁律：**接口报错 ≠ 平台不可用**。先查本表有没有替代接口，再考虑降级。

## 1. 搜索客户

| 用途 | 接口 | 关键参数 | 要点 |
|---|---|---|---|
| **主搜索（行业/描述句，海量）** | `refine/company-list` | keyword（可传完整描述句）、current、pageSize、filters、logic | ★行业发现只用这个；返回 total（实测 9993）与权威 id；列表项**无 domain**，要再调 `domain/base-info` 取域名 |
| 精确找单家 | `search/company-search` | keyword、keyword_fields、current、pageSize | 只适合"公司名/域名精确匹配"；用它做行业发现会命中同名垃圾（实测 tent → thisistent.com / tent.eu） |
| **找相似/扩量** | `refine/company-list` | **keyword = 客户域名** | ★用户 2026-10-22 纠正：扩量也走 company-list、传域名（total 可达 9999），**不要用** `domain/similar-list` |
| 公司详情（含域名/邮箱数） | `domain/base-info` | id 或 domain | ★取域名正道；返回 name/country/emailCount/email_size |

## 2. 客群推演（产品 → 买家类型）

| 用途 | 接口 | 要点 |
|---|---|---|
| 建推理产品档案 | `profile/inference-product-add` | 字段 product_name/product_zh/product_en/product_desc_zh/product_exclusions；desc 不得含买家角色词 |
| 产品档案列表 | `profile/inference-product-list` | 列表项 ID 字段是 **`_id`** |
| 生成客群 | `profile/inference-segment-generate` | 入参 `product_id`（值取 `_id`）；异步，需轮询 |
| 客群列表 | `profile/inference-segment-list` | 返回 segment_name / query_en / ai_reason / _id |

## 3. 常见报错 → 先查这里

| 现象 | 最可能原因 | 正确做法 |
|---|---|---|
| `company-search` total=0 | 用错接口（它是精确匹配） | 换 `refine/company-list` |
| `company-search` 命中一堆同名公司 | 用单词搜索 | 换描述句 + 主搜索接口 |
| `search/tasks/create` 422 | 该接口非主搜索，参数也不合 | **不要用它**；用 `refine/company-list` |
| 搜索 total=0 | 描述句太长/太窄 | 缩短到 15–25 词的核心品类+角色，再搜 |
| 取不到域名 | 直接拿列表项当域名 | 用 `domain/base-info` 传 id 换域名 |
| emailCount=0 | 该公司暂无邮箱 | 换样板；样板必须有邮箱才算可用 |

## 4. 判定顺序（写死在流程里）

1. 先问：这是"行业发现"还是"精确找单家"？→ 决定接口。
2. 报错先查第 3 节，不要直接说"平台维护/不可用"。
3. 只有**换完本表所有同用途接口**仍失败，才允许报阻断，并附接口名+原文报错。

## 5. 保存 / 模板 / 序列 / 联系人（按模块）

| 模块 | 接口 | 关键参数 | 要点 |
|---|---|---|---|
| S5 保存 | `refine/company-save` | 见 `specs/api-reference.md` §4 完整 payload；`selectTotal`+`selectKeys:[]` | 唯一保存通道是 `save_company_cli.py` prepare→confirm→execute；无 confirmed plan 不写；保存后必须 `operation/backend-task-status` 查 finished |
| S5 保存状态 | `operation/backend-task-status` | `{type:"cluesSave", id:<任务id>}` | 不能只看 company-save 返回；finished 才允许加人 |
| S5 标签 | `contacts/tags-list` / `contacts/tags-add` | list: type=company/contacts；add: name+type | 同名复用，新建后记录标签 id |
| S7/S8 模板 | `mailbox/templates-list` / `template-info` / `template-add` / `template-delete` / `templates-folder-list` / `template-folder-add` | list: current+pageSize≥10；add: name+subject+html+foid=<自动分组id>（**不是 "0"**）；folder-add: name | 模板自动归同名分组；每封主题/正文不同；批量删用 template-delete 单删（批量删正文 500 勿用） |
| S9 序列 | `sequences/sequence-create` / `sequence-save` / `sequence-details` / `step-create` / `step-save` / `step-list` | create: name+channel:"system"；save: id+name+schedule_id+rules；step-create: seqId+step+template_ids+wait_mode+wait_time+senders | 12 步；计划时间用 `settings/sequence/schedule-list` 运行时解析，禁硬编码 |
| S10 加人 | `sequences/contact-add` | `{seqId, tags:[标签ID], views:[]}` | ★`views` 必须 `[]`；传 `["all"]` 会把全库联系人加入；现役脚本 `contact_add_authorized.py` |
| S10 对账 | `sequences/contact-list` / `contacts/contacts/show` | seqId+current+pageSize；contacts/show 用 filters 数组 | 加完回读人数，与保存任务标签人数对账 |
| S12 激活 | `sequences/sequence-list` / `sequence-active` | active: `{id, active:true/false}` | 只有用户原话含「确认激活」才可激活；`--sync-manual` 只读同步 |

> 逐模块完整表（含门禁/要点/证据）见 `specs/module-api-map.md`。