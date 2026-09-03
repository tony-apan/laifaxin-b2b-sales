---
title: "实操链路（搜筛存发全流程·实战验证版）"
description: "猫粮案例端到端跑通：AI推演→搜索/找相似→审计70%临界点→界面保存（⚠️已改纯API，见正文过时横幅）→智能跟进→发信；含已验证接口速查"
created: 2026-08-21
updated: 2026-08-21
author: "AI Agent + 运营方"
source: "实战验证（本会话）"
related: [01-customer-search, 03-save-customers, 05-email-marketing, specs/api-reference]
tags: [实操, 流程, 接口速查]
status: verified
audience: 人+AI
---
# 08 · 实操链路：搜筛存发全流程（实战验证版）

> ⚠️ **过时提示（2026-08-30）**：本篇"第四步：保存必须走界面（Playwright）、API 直调 0 保存"的旧结论**已废止**——现行保存 = 纯 API：`selectOption:"front"` + `selectTotal:N` + 排除4区 + `contactMaxCount:3`（`tools/save_first_n.py`，验证用 `backend-task-status`）。以 `RULES.md`/`specs/api-reference.md` 为准；猫粮案例的其余步骤记录为历史快照，仅作背景参考。

> 本项目实测跑通的完整链路（以"猫粮"为例），含已验证 API + 浏览器操作

## 🗺️ 完整链路

```
① AI推演客群 → ② 搜客户（关键词/域名找相似）→ ③ 审计找70%临界点 → ④ 保存（标签+每客户3个）→ ⑤ 建智能跟进计划 → ⑥ AI开发信模板 → ⑦ 发信跟回信
```

## 第一步：AI 推演客群（从产品推理买家）

**操作**：AI 数据库 → AI推演 → 输入产品（如"猫粮"）→ 智能生成 → 得到 8 个客群（每个带英文搜索词 query_en + 推荐理由 + 覆盖量）

**API**：
```bash
# 添加产品档案（详细描述 → 推演更准）
POST /api/profile/inference-product-add {"product_name":"Cat Food","product_zh":"猫粮及宠物食品","product_en":"...","product_desc_zh":"详细描述...","product_exclusions":"排除... "}

# 生成客群
POST /api/profile/inference-segment-generate {"product_id":"..."}

# 查看客群（核心！）
POST /api/profile/inference-segment-list {"product_id":"..."}
# → segment_name / value_path / ai_reason / query_en / query_total
```

**客群价值路径**：
- Path A: 转化与创造（生产端）
- Path B: 流通与代理（分销/零售/品牌方 ← **最直接买家**）
- Path C: 运营与赋能（场景应用方）
- Path D: 职能与使命（政府/机构）

## 第二步：搜客户（两种主力打法）

### 打法A：关键词/提纯搜（海量）
用客群的英文搜索词 → `POST /api/refine/company-list`（可排除国家）

### 打法B：域名找相似（⭐ 精准同行）
1. 用关键词搜到最准客户（带域名）
2. 用其域名 `POST /api/domain/similar-list` → 10 个同行（带 _score 相似度）
3. 或用 `tasks/create type=domain` 建域名搜索任务（换行拼多域名）

**核心心法**：搜客户的产品词/业务描述词（金主），不搜自己服务词（同行）

## 第三步：审计找 70% 临界点（用工具不靠主观）

```bash
python3 audit_company.py --query "英文描述句" --pages 1,500,990,995,1000 --token $TOKEN --org <orgId> --mode strict --product "猫粮"
```

- 逐页看"本页"精准度，找到降到 70% 以下的临界页
- 往前翻：保存范围 = 临界页之前的页数
- 判定标准写死在规则表（MATCH/REJECT/MARGINAL + 杂货一票否决），可复现

**实测（猫粮提纯搜）**：1~950页 80-100%，995页 40% → 保存范围前 990 页

## 第四步：保存（走界面流程！API 直接调会 0 保存）

**⚠️ 关键教训**：API 直接调 `refine/company-save` 传 keyword → 任务立即 finished:0。**必须走界面**（Playwright 浏览器自动化）：

1. AI 数据库搜索 → 勾选客户行（行首 checkbox）
2. 点「保存」→ 弹窗
3. 填：公司标签 + 联系人标签（同一名称）+ 邮箱验证勾「有效(2点)+未知(1点)」+ **每客户 3 个**
4. **不碰高级选项**（易导致潜在客户流失）
5. 确认保存 → 验证：公司建档 + 标签 + 邮箱提取（Blink Cat Food 12邮箱→保存3个，邮箱以 <email> 占位）

**标签 ID 注意**：companyTags 用公司标签 ID（type=company），contactTags 用联系人标签 ID（type=contacts），是两个独立体系！

## 第五步：建智能跟进计划（先模板后计划）

**先准备**：邮件模板（AI 开发信生成，见 07）→ 设置-邮件模板

**计划配置**：
1. 创建计划：名称（客户群体）+ 时间（客户时区）+ 优质发送通道
2. 添加步骤：第1轮立即发，30天未回复→第2轮...（3~12轮）
3. 高级规则：发信昵称 + 发送上限（计划24h上限、单域名2~10）+ 公司触发器 + 未发送触发器
4. 激活计划 → 按标签批量添加客户

## 第六步：AI 开发信模板（多轮序列）

用 AI 开发信 Prompt 方法（见 docs/07）生成 6~12 轮序列，每轮 3~6 封模板：
- 一段一句、≤100词、禁 Dear、签名零营销感
- 5步流程（痛点→桥梁→价值列表→提问→钩子）
- 钩子 KEYWORD 高亮（资源/洞察/资格三种原型）
- 策略递进：痛点破冰 → 价值展示 → 建立信任

## 第七步：发信 + 跟回信

- 系统自动多轮发送（跨时区/控频/控量）
- 邮件追踪（打开/点击/下载）
- 客户回信 → 人工 1-on-1 接管（用自有邮箱）

## 📌 已验证的接口速查表

| 功能 | 接口 | 关键参数 |
|------|------|---------|
| 提纯搜 | POST /api/refine/company-list | keyword, current, pageSize, filters, logic |
| 排除国家 | filters | [{"property":"country_code","operator":"exclude","value":"","values":["CN","TW","HK","MO"],"valueType":"select"}] |
| 域名找相似 | POST /api/domain/similar-list | domain |
| 产品档案 | POST /api/profile/inference-product-add | product_name/zh/en/desc_zh/exclusions |
| 生成客群 | POST /api/profile/inference-segment-generate | product_id |
| 客群列表 | POST /api/profile/inference-segment-list | product_id |
| 保存任务 | ~~界面流程（Playwright）~~（已废）| 现行=纯 API：`tools/save_first_n.py`（front+selectTotal+contactMaxCount:3+valid+unkown）|
| 标签列表 | POST /api/contacts/tags-list | type: company/contacts |
| 公司列表 | POST /api/contacts/companies/show | filter.tags |
| 联系人列表 | POST /api/contacts/contacts/show | filter.tags |
| 保存任务记录 | POST /api/clues/company-save-list | filter/sort |

## 🔧 本项目工具

- `audit_company.py` — 客户精准度审计（关键词搜 + 域名找相似双模式）
- 旧版界面保存脚本（未随库分发）→ 现行 `tools/save_first_n.py`（纯API front+selectTotal）

---

> **真实案例演示**：数字与域名为公开仓库作者当时实际运行结果，仅作方法演示，与读者业务无关。
