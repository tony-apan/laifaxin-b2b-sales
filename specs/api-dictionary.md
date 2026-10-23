---
doc_id: "lfx-api-dictionary"
title: "来发信接口字典（排障速查）"
description: "按用途列接口、要点、常见报错与替代路径；出问题先查本表再下结论。"
created: "2026-10-22"
updated: "2026-10-22"
type: "spec"
status: "normative"
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

## 5. 待补

- 保存/序列/联系人的接口要点（待实测后补入本表）。