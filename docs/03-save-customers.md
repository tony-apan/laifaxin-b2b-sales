---
title: "保存客户（精准客户怎么存）"
description: "保存就打标签 + 自动去重 + 保存设置推荐值 + 实测教训（API 直调 0 保存，必须走界面——⚠️旧结论已废止，见正文过时横幅）"
created: 2026-08-21
updated: 2026-08-21
author: "AI Agent + 运营方"
source: "https://www.laifa.xin/zhinan/03-save-customers"
related: [02-filter-customers, 04-tags-views, 08-workflow-ops]
tags: [保存, 标签, Playwright, 踩坑]
status: verified
audience: 人+AI
---
# 03 · 保存客户（精准客户怎么存）

> ⚠️ **过时提示（2026-08-30）**：本篇"直接调 API 会 0 保存、**必须走界面（Playwright）**"的旧结论**已废止**——现行保存 = 纯 API：`selectOption:"front"` + `selectTotal:N` + `selectKeys:[]` + 排除4区（CN/TW/HK/MO) + `contactMaxCount:3`，工具 `tools/save_first_n.py`，验证用 `operation/backend-task-status`（contactSaveCount）。以 `RULES.md`/`specs/api-reference.md` 为准；本篇界面流程描述仅作背景参考。

> 来源：`https://www.laifa.xin/zhinan/03-save-customers` + 实测验证

## 🎯 核心目标：潜在目标精准分类入库

**保存重点**：找准保存界面 → 填好保存设置 → **保存就打标签**

## ✅ 新手定心丸：系统自动去重

不管你分几次保存、用哪种搜索方式，系统**自动去重**——一个邮箱只扣一次点数，删除后重存也不重复扣点。放心大胆操作！

## 一、保存设置（新手推荐值）

| 设置项 | 建议 |
|--------|------|
| 公司标签 | 按客户群体命名，例如"水上运动用品零售商" |
| 联系人标签 | 和公司标签保持一致 |
| 邮箱类型 | 有效、未知 |
| 保存数量 | 3~5（官方建议5，实际按需） |
| 高级选项 | **新手先不调整**（易导致潜在客户流失，慎用） |

## 二、如何保存"N 条"数据（示例：前 194 页）

1. 搜索结果中，先随机勾选**任意 1 个客户**
2. 点击结果列表顶部左侧的「高级」下拉按钮
3. 在「选择前 [200] 条数据」里把 200 改成目标数（如 1940），点击**保存联系人**

> 💡 重要：这里的 200/5000 是**总行数**，不是页码！前 5000 = 第 1~5000 条。

## 三、保存方式（3 种策略）

| 方式 | 适用 |
|------|------|
| 全选一键保存 | 数据精准、数量合适 |
| 自定义分批保存 | 数据量大，分批评分筛选 |
| 手动 + AI 组合 | 前端手动筛最准的，后段 AI 评分 |

## 四、查看保存结果

1. 保存任务提交后，页面右上角看进度
2. 进「客户保存记录」查看所有保存任务
3. 任务完成后，进「联系人界面」按标签筛选已保存的联系人

## 🔬 实测：保存任务的正确打开方式（踩坑总结）

### ⚠️ 直接调 API 保存会 0 保存（关键教训）

调用 `refine/company-save` / `clues/company-save-create` 传 keyword 直接创建任务 → **任务立即 finished:0，validSave:0**。原因：绕过了前端流程的关键环节（勾选上下文、标签选择、弹窗完整提交）。

### ✅ 正确方式：走界面真实流程（Playwright 浏览器自动化）

已验证可成功保存（Blink Cat Food 12邮箱→保存3个，标签打上）：

**界面流程**：
1. AI 数据库搜索 → 结果页勾选客户行（行首 checkbox）
2. 点「保存」→ 弹出「保存公司及联系人」弹窗
3. 填：公司标签（如"猫粮-宠物食品分销商"）、联系人标签同、邮箱验证结果勾「有效邮箱(2点/个)」+「未知邮箱(1点/个)」、**每家公司保存多少个=3**
4. **不碰「高级选项（可选）」**（易导致潜在客户流失）
5. 点「确认保存」→ 公司建档 + 标签 + 邮箱提取

**实测验证结果**：
- 保存任务记录：`contactMaxCount: 3` ✅、`unkownSave: 3` ✅、`finished: 1/1` ✅
- 公司列表：Blink Cat Food 已保存（emails:12）、Cat Food Wellness 已保存
- 联系人列表：<email>×3（正好3个，verify:unkown）

**关键参数**（从真实任务记录获取）：
- `contactVerifyStatus: ["valid","unkown"]`（邮箱类型）
- `contactMaxCount: 3`（每客户保存数量）
- `companyTags`/`contactTags` 用**标签 ID**（不是标签名！公司标签和联系人标签是两个独立体系）
- `contactPositions`（职位，如 owner/ceo/purchasing manager）
- `contactExcludes`（高级设置，禁止使用）

**标签 ID 获取**：
- 公司标签：`POST /api/contacts/tags-list` `{"type":"company"}`
- 联系人标签：`POST /api/contacts/tags-list` `{"type":"contacts"}`

**保存后验证**：
- 公司列表：`POST /api/contacts/companies/show` `{"current":1,"pageSize":10,"filter":{"tags":["标签ID"]}}`
- 联系人列表：`POST /api/contacts/contacts/show` `{"current":1,"pageSize":20,"filter":{"tags":["标签ID"]}}`
- 保存任务：`POST /api/clues/company-save-list`

## 🔗 下一篇

- [04-tags-views.md](04-tags-views.md)

---

> **真实案例演示**：数字与域名为公开仓库作者当时实际运行结果，仅作方法演示，与读者业务无关。
