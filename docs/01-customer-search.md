---
title: "客户搜索（AI 数据库）"
description: "4 种搜索方式（搜域名/AI推演/提纯搜/找相似）+ 服务词vs产品词心法 + 实测 API 参数"
created: 2026-08-21
updated: 2026-09-03
author: "AI Agent + 运营方"
source: "https://www.laifa.xin/zhinan/refine-search-all"
related: [02-filter-customers, 08-workflow-ops, specs/api-reference]
tags: [搜索, AI数据库, API, 找相似]
status: verified
audience: 人+AI
---
# 01 · 客户搜索（AI 数据库）

> 来源：`https://www.laifa.xin/zhinan/refine-search-all` + 实测 API 验证

## 🎯 核心目标：找对人

通过不同搜索策略，把茫茫人海中的线索提纯为目标客群。

## 🚨 开始搜之前：先想清楚"找同行 还是 找金主？"

新手最常翻车的地方——**用错了产品词**：

| 词类型 | 例子 | 搜出来是谁 | 用途 |
|--------|------|-----------|------|
| 自己的服务词 | CNC Machining | 同行（其他 CNC 工厂） | ❌ 不是客户 |
| 客户的产品词 | Drone Frame | 金主（无人机品牌方） | ✅ 是客户 |

> 💡 **一句话记住**：搜"我会做啥"找的是同行；搜"客户造啥"才找到金主。

## 四种搜索方式

### ① 搜域名（⭐⭐ 强烈推荐）：用精准客户网站搜

**适用**：手里有目标客户/老客户/发过询盘的客户网址

**操作**：AI 数据库顶部搜索框 → 输入客户网址 → 搜索 → 匹配大量相似企业

> ⚠️ 数据同步中：输入域名后如果结果空/少，表示数据正在同步，换其他网站搜，过几天再试。

**历史 API 能力（当前 S3 主流程不使用）**：
- `POST /api/domain/similar-list` 可返回固定 10 条相似结果，但现行流程统一使用 `refine/company-list`：query_en 搜第一页 → id 取真实域名 → 域名作为 keyword 海量扩量。
- 域名任务类接口属于历史/补充能力，执行前须按当前 `specs/api-reference.md` 与平台状态复核。

### ② AI 推演：让系统帮你想客群

**适用**：只了解自己产品、没有目标客户网址、不会定关键词

**操作**：
1. AI 数据库 → 顶部搜索框右侧「AI 推演」按钮（或方案库→新建方案）
2. 弹窗输入产品名称 → AI 智能生成
3. 选择匹配客群 → 立即查看

**客群不精准时**：编辑产品方案（方案库标签），越详细越好，修改后**重新推演**。

**API（实测验证）**：
- 产品档案：`POST /api/profile/inference-product-add` `{"product_name","product_zh","product_en","product_desc_zh","product_exclusions"}`
- 产品列表：`POST /api/profile/inference-product-list`
- 推演客群：`POST /api/profile/inference-segment-generate` `{"product_id"}`
- 客群列表：`POST /api/profile/inference-segment-list` `{"product_id"}` → 每个客群带 `segment_name`/`value_path`/`ai_reason`/`query_en`(英文搜索词)/`query_total`(覆盖企业数)

### ③ 提纯搜：用精准词重新搜

**适用**：常规词搜出来太杂乱

**两种提纯方法**：
1. **用业务描述词**：搜目标客户网站 → 复制结果页公司描述里的**业务介绍** → 去掉不相关的 → 翻译成英文 → 再搜
2. **用客户角色词**：完全不知道客户是谁时，先用「客户的产品词」探路 → 收集客户角色词（distributor / wholesaler / importer / OEM）→ 翻译成英文 → 按优先级单个搜索

**API（实测验证，可用）**：
- 提纯搜：`POST /api/refine/company-list`
  ```
  {"keyword":"英文业务描述句","current":1,"pageSize":20,"filters":[],"logic":"and"}
  ```
  → 返回 `total`、`list[]`（含 `company_name`、`country_code`、`client_focus`、`confidence`、`operational_role`、`naics_label`、`emailsCount`、`summary_zh`）
- **排除国家筛选**（实测验证）：filters 传
  ```
  {"property":"country_code","operator":"exclude","value":"","values":["CN","TW","HK","MO"],"valueType":"select"}
  ```
  排除中国/台湾/香港/澳门 → total 会减少，结果无 CN/TW/HK/MO

### ④ 找相似：滚雪球裂变（🔥 小妙招）

**适用**：结果里发现 1 个极准客户

**现行操作**：从 AI 数据库搜索结果中挑代表买家 → 用该条 id 查询真实域名 → 把域名作为 keyword 继续走 `refine/company-list` 海量扩量。不要调用 `domain/similar-list` 作为现行 S3 主路径。

**历史能力说明**：平台界面的“找相似”与旧 `domain/similar-list` 仍可能存在，但本仓库的现行规则以 `RULES.md`、`SKILL.md` 和 `specs/node-playbook.md` 为准。

## ⚙️ 搜索词构造技巧（金玉良言）

- **从精准客户的业务描述里提炼英文描述词**（AI 翻译）→ 这是最准的提纯词
- **收集客户角色词**（distributor/wholesaler/importer/OEM/retailer/brand）→ 单个词搜索，便于打标签区分
- **服务词 vs 产品词**：永远搜客户的产品/业务，不搜自己的

## 🔗 下一篇

- [02-filter-customers.md](02-filter-customers.md)
