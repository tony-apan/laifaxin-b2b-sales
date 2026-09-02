---
title: "API 接口规范（全功能速查）"
description: "来发信全接口按模块分类：认证/推演/搜索/筛选/保存/标签视图/客户管理/邮件营销；含实测结论与注意"
created: 2026-08-21
updated: 2026-08-21
author: "AI Agent + 运营方"
source: "前端 bundle 逆向 + 实测"
related: [docs/01-customer-search, docs/08-workflow-ops]
tags: [API, 规范, 接口]
status: verified
audience: AI优先（人可参考）
---
# API 接口规范（来发信全功能接口速查）

> 来源：前端 bundle 逆向 + 实测验证（✅=已实测可用，⚠️=需界面流程，🚧=维护中）
> 通用约定：`POST`，header `accesstoken: <token>` + query `?uid=<orgId>`，body JSON

## 0. 认证与账户

> ★**token 获取（新手第一步）**：官方教程 https://www.laifa.xin/share/ai/laifaxin-ai-account-connection —— 登录 web.laifaxin.com → 检查→应用程序→本地存储→`accesstoken`（复制"值"**整串**），或控制台 `copy(localStorage.getItem("accesstoken"));`（undefined=已复制；null=未登录→刷新/重登）。**accesstoken 已含账号信息（格式 `web.laifaxin.com&<orgId>&<hash>`），orgId 从中段自动提取，无需单独获取**；登录检查用 `tools/check_login.py --token`（只读，不扣点不写数据）。换账号需重新获取。

| 接口 | 用途 | 备注 |
|------|------|------|
| `POST /api/user/login` | 账号密码登录 | 需 phoneCode（滑块） |
| `POST /api/user/login/by-phone` | 手机号登录 | 需 phoneCode + host |
| `POST /api/user/login/by-email` | 邮箱登录 | |
| `POST /api/account/current` | 当前账户信息 | ✅ userid/uid/email/name/vip/balance/creditCount |
| `POST /api/account/info` | 账户详情 | ✅ 含 phone/wechat/avatar |
| `POST /api/account/logout` | 退出 | |
| `POST /api/account/password-change` | 改密码 | |
| `POST /api/account/permissions` | 权限 | |

> ⚠️ 登录需滑块（AliyunCaptcha）→ 走界面。token 存 localStorage `accesstoken` + `orgId`（uid）。

## 1. AI 推演（客群分析）✅ 全部实测

| 接口 | 用途 | 关键参数 |
|------|------|---------|
| `POST /api/profile/inference-product-list` | 产品档案列表 | {} |
| `POST /api/profile/inference-product-add` | 添加产品档案 | product_name/zh/en/desc_zh/exclusions |
| `POST /api/profile/inference-product-details` | 产品详情 | product_id |
| `POST /api/profile/inference-product-save` | 保存产品 | |
| `POST /api/profile/inference-product-Rename` | 重命名产品 | |
| `POST /api/profile/inference-segment-generate` | 生成客群（AI推演） | product_id |
| `POST /api/profile/inference-segment-list` | 客群列表 | product_id → segment_name/value_path/ai_reason/query_en/query_total |

## 2. 搜索客户 ✅ 实测

> **⭐ 核心确认（2026-08-21）**：**AI 数据库主搜索 = `refine/company-list`**（海量、权威 id、排除国家）；
> `search/company-search` 仅**精确找单家**（拿域名做种子）。

| 接口 | 用途 | 关键参数 |
|------|------|---------|
| **`POST /api/refine/company-list`** | ⭐ **AI 数据库主搜索（海量·域名搜上万）** | keyword(域名或描述句), current, pageSize, filters[], logic → 返回 total + 权威 id |
| `POST /api/search/company-search` | 精确匹配（total:1）· 拿域名 | keyword, keyword_fields, current, pageSize |
| `POST /api/domain/similar-list` | 域名找相似（10条/页） | domain → 每条含 id 等（⚠️流程不依赖此接口——获客统一走 AI 数据库搜索 keyword 路径） |
| `POST /api/domain/base-info` | 公司信息（含★域名） | **入参是 id**（搜索结果项的 32hex id，字段名叫 domain 但值传 id）→ 返回 domain/公司名/NAICS/角色/中英摘要/电话——★取域名的正道：AI数据库搜索第一页每条的 id → 本接口 → domain |
| `POST /api/domain/resolve-domain-name` | 域名解析 | id |
| `POST /api/search/tasks/create` | 创建搜索任务 | type:domain(可用)/keyword(🚧维护中), keyword, language, country |
| `POST /api/search/tasks/show` | 任务详情 | taskId, pageSize, current, filter, sort |
| `POST /api/search/tasks/show-count` | 任务统计 | → total/name/domain/keyword |
| `POST /api/search/preview-companies` | 预览公司 | 🚧维护中 |

> **域名搜（一个网址上万条）**：`refine/company-list` + keyword=域名 → total:9999（权威 id，可直接保存）

### 排除国家筛选（✅ 实测）
```json
"filters": [{"property":"country_code","operator":"exclude","value":"","values":["CN","TW","HK","MO"],"valueType":"select"}]
```
- `operator`: `exclude`(不包含,★已实测) / `include`(包含,★白名单)
- `logic`: `and` / `or`

## 3. 筛选（AI 评分）

| 接口 | 用途 |
|------|------|
| `POST /api/search/company-search-rating` | 公司搜索评分 |
| `POST /api/search/tasks/ai-rating-create` | AI 评分任务创建 |
| `POST /api/search/tasks/ai-rating-chat-info` | 评分详情 |
| `POST /api/refine/company-rating` | 提纯搜评分 |
| `POST /api/search/company-search-save-black` | 拉黑 |

## 4. 保存客户 ✅ 纯 API 可用（真相已摸清）

> **★ 真相（浏览器抓包 + 实测）**：`POST /api/refine/company-save` **可以直接 API 调用**！
> 之前 0 保存的根因：
> 1. **缺 `selectKeys`**（选中客户 ID 数组）——保存的是**勾选的客户**，不是搜索词！
> 2. **系统去重**——重复保存 validSave=0（正常，未重复扣点）

| 接口 | 用途 | 实测参数 |
|------|------|---------|
| `POST /api/refine/company-save` | **保存联系人（纯API）** | ✅ 见下方完整 payload |
| `POST /api/clues/company-save-list` | 保存任务记录（查状态） | ✅ |
| `POST /api/clues/company-save-create/start` | 另一套（clues），保存用 refine | ⚠️ |

**完整 payload（浏览器抓包原样，已验证成功）**：
```json
{   // <tagId>/<tagId>=历史示例标签id(已删); 标签记录须 id+名称 成对(RULES铁律7)
  "companyTags":["<tagId>"], "companyOption":"nothing", "companySave":true,
  "contactTags":["<tagId>"], "contactOption":"nothing",
  "contactVerifyStatus":["valid","unkown"],
  "contactPositions":[], "contactExcludes":[], "contactMaxCount":3,
  "contactSave":true,
  "selectKeys":["<customerId>"],  // ★ 选中客户ID（refine/company-list 的 id）
  "selectSort":{}, "selectTotal":1, "selectOption":"current",
  "filters":[], "filter":{},
  "keyword":"cat food", "logic":"and"
}
```

**selectKeys 获取**：
- ⭐ **域名搜（refine/company-list + 域名 keyword）返回的 id = 权威 id**（validSave 大量 >0 ✅）
- ❌ 泛关键词搜返回的 id 是**搜索会话临时 id**（validSave=0！误判过"valid邮箱不保存"）
- ⚠️ **selectKeys 最多 256 个**！超了报错"必须最多包含 256 个成员"（分批 ≤256）

### ★ 保存"前 N 条"（★正确方式，实测 contactSaveCount>0 提邮箱）
**不收集 id、不分批！** `selectOption:"front"` + `selectTotal:N` + `selectKeys:[]` = **保存前N条并提取邮箱**：
```json
{
  "selectKeys": [],          // 空（选前N）
  "selectTotal": 8000,       // 前8000条
  "selectOption": "front",   // ★ 关键！front=选择前N且提邮箱（current=不提取！）
  "companyTags":["<tagId>"], "contactTags":["<tagId>"], "contactMaxCount":3,  // ★默认3(每公司邮箱数裁决,阶梯3→6→9)（<tagId>/<tagId>=历史示例id已删）
  "keyword":"<seed-domain>", "logic":"and"
}
```
> ⚠️ **★ selectOption 必须是 `"front"`**！我用 `"current"` 全错（邮箱0）。`front` 才提邮箱。
> ⚠️ **contactMaxCount:3**（★每公司邮箱数裁决：默认 3，阶梯 3→6→9；界面默认显示 5 是误导，以 3 为准）。
> ⚠️ 实测：front+selectTotal:8000 → **contactSaveCount 持续增长**（fin 702 → contactSave 1427）＝提邮箱，不翻页。

### ★ 验证邮箱提取：`backend-task-status`（不是 company-save-list！）
```json
POST /api/operation/backend-task-status  { "type":"cluesSave", "id":"<save任务id>" }
→ data.contactSaveCount = 邮箱提取数（>0=提取了）；companySaveCount=公司数
```
> ⚠️ 我之前用 company-save-list 查（它不显示 contactSaveCount，误以为邮箱0）。**正确验证 = backend-task-status**。

**验证结果**（纯 API，2026-08-21）：
- 某宠物食品公司（示例案例，未保存过）→ `<email>` 保存成功 ✅
- 域名搜 240 家（批15）→ validSave:195 + unkownSave:131 = 326 邮箱 ✅
- 重复保存 → validSave:0（去重 ✅）

## 5. 标签与视图 ✅

> ★**标签铁律（RULES 7/8）**：标签=**客户群体中文名**（不写我方产品）；记录 **id(名称) 成对**——只记 id 换会话查不到名；用 `tags-list` 查名称，`tags/tag-save {type,id,name}` 可改名（id 不变、数据不丢，2026-08-30 实测）。
> **当前活跃标签（2026-08-30 tags-list 实测）**：公司 `<tagId>(默认标签)` / `<tagId>(水上运动行业客户)`；联系人 `<tagId>(默认标签)` / `<tagId>(询盘)` / `<tagId>(不发)` / `<tagId>(水上运动行业客户)`。

| 接口 | 用途 | 关键参数 |
|------|------|---------|
| `POST /api/contacts/tags-list` | 标签列表 | type: company/contacts（数量随清空/新建变化，勿信旧计数） |
| `POST /api/contacts/tags-add` | 创建标签 | name, type |
| `POST /api/contacts/tags-save` | 保存标签 | |
| `POST /api/contacts/tags-dirs` | 标签目录 | |
| `POST /api/views/views-list` | 视图列表 | type: dbSearchCompany/contacts |
| `POST /api/views/views-pin` | 视图固定 | |
| `POST /api/views/views-pin-save` | 视图保存 | |

## 6. 客户管理（保存后）

| 接口 | 用途 | 关键参数 |
|------|------|---------|
| `POST /api/contacts/companies/show` | 公司列表 | ★按标签过滤用 filters 数组: `filters:[{property:tags,operator:include,value:<标签ID>,values:[<标签ID>],valueType:select}]`（filter.tags 失效返全库,ISS-52）|
| `POST /api/contacts/contacts/show` | 联系人列表 | ⚠️按标签过滤须用 **filters 数组**(见上,实测精确;filter.tags 返全库 total 假通过 ISS-52)；viewId:all（delete_all_contacts 用）——★见下方「联系人正确参数」节 |
| `POST /api/contacts/contacts/save` | 保存联系人 | |
| `POST /api/contacts/contacts/delete` | **批量删联系人（异步·软删）** | ⚠️ `{selectTotal, selectKeys:[], selectOption:"all", filters:[]}` → 返回backendId；软删入回收站；单任务上限50000(串行)（完整实测payload见文末★联系人正确参数） |
| `POST /api/contacts/contacts/select-count` | 选择计数 | |
| `POST /api/contacts/black/domains-list` | 黑名单域名 | |

## 6.5 标签（独立组 /api/tags/* ✅ 验证）

> 补充发现：`/api/tags/*` 是**标签目录/文件夹管理**（与 `/api/contacts/tags-*` 的标签列表互补）

| 接口 | 用途 | 关键参数 |
|------|------|---------|
| `POST /api/tags/folder-list` | 标签目录列表（含文件夹层级） | type: company/contacts/clues/search |
| `POST /api/tags/folder-add` | 新建标签目录 | type, name |
| `POST /api/tags/tag-add` | 新增标签 | type, name |
| `POST /api/tags/tag-save` | 保存标签 | |
| `POST /api/tags/tag-delete` | 删除标签 | ✅ `{type: company/contacts, id}` |
| `POST /api/tags/tag-info` | 标签详情 | |
| `POST /api/tags/tag-fav-add/delete` | 收藏/取消收藏标签 | |

## 7. 邮件营销（模板/签名/发信）

### 邮件模板 ✅ 全部实测

| 接口 | 用途 | 实测参数 |
|------|------|---------|
| `POST /api/mailbox/templates-list` | 模板列表 | ✅ current/pageSize(≥10)/filter/sort |
| `POST /api/mailbox/template-info` | 模板详情 | ✅ id → name/subject/html/veriables/size |
| `POST /api/mailbox/template-add` | **新建模板** | ✅ **name+subject+html**（foid:"0"）→ 返回 id |
| `POST /api/mailbox/template-save` | **修改模板** | ✅ **id+foid+name+subject+html** |
| `POST /api/mailbox/template-delete` | 删除模板 | ✅ id |
| `POST /api/mailbox/templates-delete` | **批量删模板** | ⚠️ `{ids:[]}`（空ids返回成功，但**批量删正文实测 500 勿用**——L-39；删模板统一用上面 template-delete 单删（清空模板脚本按此参数封装，未随库分发）|
| `POST /api/mailbox/template-score` | 模板评分 | |
| `POST /api/mailbox/templates-folder-list` | 模板文件夹列表 | ✅ {} |
| `POST /api/mailbox/template-folder-add` | **新建分组** | ✅ name |
| `POST /api/mailbox/template-folder-save` | **分组重命名** | ✅ id+name |
| `POST /api/mailbox/template-folder-delete` | **分组删除** | ✅ id |

**模板新建实测**（验证成功）：
```json
POST /api/mailbox/template-add
{"name":"API测试模板","foid":"0","subject":"Hello there","html":"<p>Hi <code class=\"lfxFieldVeriable\" contenteditable=\"false\">{联系人:名称}</code>,</p><p>...</p><p><昵称></p>"}
→ {"success":true,"data":{"id":"..."}}
```

**模板变量**（模板详情 veriables 字段）：
- `{联系人:名称}` → 联系人名称（code: `<code class="lfxFieldVeriable">{联系人:名称}</code>`）
- subject 变量用 `subjectVeriables（★API支持subject变量,但策略禁用=标题纯文案,见sequence-config）`

### 签名/片段/附件
| 接口 | 用途 |
|------|------|
| `POST /api/mailbox/sign-items` | 签名列表 |
| `POST /api/mailbox/sign-add/save/default-set` | 签名管理 |
| `POST /api/mailbox/snippets-list` | 片段列表 |
| `POST /api/mailbox/attachment-options/save` | 附件 |

### 发送
| 接口 | 用途 |
|------|------|
| `POST /api/mails/sendmail-add` | 发送邮件 |
| `POST /api/mails/sendmail-status` | 发送状态 |
| `POST /api/mails/mail-save` | 存草稿 |
| `POST /api/mails/accounts-list` | 邮箱账户 |
| `POST /api/mails/track-info` | 邮件追踪 |
| `POST /api/mails/mail-history-list` | 发送历史 |

## 8. 数据查询（已验证）

| 接口 | 用途 |
|------|------|
| `POST /api/refine/company-list` | 提纯搜（核心！返回 queryId） |
| `POST /api/search/domain-emails` | 域名邮箱（current+pageSize≥10） |
| `POST /api/clues/company-save-list` | 保存任务记录 |
| `POST /api/contacts/companies/show` | 公司列表 |
| `POST /api/contacts/contacts/show` | 联系人列表 |

## 9. 其他（业务模块）

| 接口 | 用途 |
|------|------|
| `POST /api/enterprise/teams/show` | 团队 |
| `POST /api/enterprise/roles-list` | 角色 |
| `POST /api/fields/field-list` | 字段配置 |
| `POST /api/whatsapp/tasks/show` | WhatsApp 任务 |
| `POST /api/clues/search-task-*` | 线索搜索任务 |

## 10. 智能跟进计划（/api/sequences/* ✅ 全部实测）

> 核心！从 `sequence-create-dialog` chunk 抓取 + 实测（用现有序列"静默客户唤醒"验证）

### 序列（计划）管理
| 接口 | 用途 | 实测参数 |
|------|------|---------|
| `POST /api/sequences/sequence-list` | 序列列表 | ✅ current/pageSize/filter/sort → name/channel/rules/active/delivered/reply/stepsCount |
| `POST /api/sequences/sequence-count` | 序列统计 | ✅ → total/active/inactive/poor |
| `POST /api/sequences/sequence-details` | 序列详情 | ✅ id → 完整 rules 结构 |
| `POST /api/sequences/sequence-create` | **新建序列** | ✅ **name+channel**（channel:"system"）→ 返回 id |
| `POST /api/sequences/sequence-save` | **保存序列** | ✅ id+name+**schedule_id**（计划时间）+others+rules |
| `POST /api/sequences/sequence-active` | **激活/暂停** | ✅ id+active:true/false |
| `POST /api/sequences/sequence-copy` | **复制序列** | ✅ id+name → 自动"(副本1)" |
| `POST /api/sequences/sequence-delete` | 删除序列 | ✅ id（**先暂停active**: sequence-active active:false）|
| `POST /api/sequences/sequence-options` | 序列选项 | ✅ {} → 所有序列（下拉用） |
| `POST /api/sequences/sequence-summary` | 序列摘要 | id |
| `POST /api/settings/sequence/schedule-list` | **计划时间模板列表** | ✅ {current,pageSize:100} → 含 name/time_zone/skip_holidays/time_windows/isDefault |

### 步骤管理（1步=1轮）✅ 全部实测
| 接口 | 用途 | 实测参数 |
|------|------|---------|
| `POST /api/sequences/step-list` | 步骤列表 | ✅ **seqId**+current/pageSize → step/type/template_ids/wait_mode/wait_time/senders |
| `POST /api/sequences/step-create` | **新建步骤** | ✅ **seqId+step+template_ids+wait_mode+wait_time+senders** → 返回 id |
| `POST /api/sequences/step-save` | **保存步骤** | ✅ seqId+id+step+template_ids+wait_mode+wait_time（+senders 保留原值，见 rebuild_templates.py） |
| `POST /api/sequences/step-delete` | 删除步骤 | ✅ seqId+id |
| `POST /api/sequences/step-move` | 步骤排序 | seqId+orders |
| `POST /api/sequences/step-move-up/down` | 上移/下移 | seqId+id |

### 步骤实测结构（关键字段）
```json
{
  "step": 1, "type": "auto_email",
  "template_ids": ["模板ID1", "模板ID2"],   // 多选随机
  "wait_mode": "minute", "wait_time": 0,     // 等待模式+时间（第1步立即发）
  "senders": ["发送账号ID"],
  "max_emails_per_day": null, "domain_emails_per_day": null,
  "active": 1473, "delivered": 1107, "opened": 286, "reply": 11
}
```

### 序列规则实测结构（rules）
```json
{
  "finishReply": false,          // 回信不自动停（人工接管）
  "notSentInvalid": true,        // 不发给无效邮箱
  "notSentBlack": true,          // 不发给黑名单
  "aiGuard": true,               // AI 风控
  "max_emails_per_day": 30000,   // 计划24h上限（★用户拍板30000=当前配置值，发送上限拍板记录）
  "domain_emails_per_day": 2,    // 单域名上限（⚠️旧序列"静默客户唤醒"实测值；★当前拍板=5，见 sequence-config）
  "otherReplayDelayDays": 5,     // 其他回复延迟天数
  "notSentTags": ["标签ID"]      // 未发送标签
}
```

### 联系人/邮件/报告（序列内）✅ 部分实测
| 接口 | 用途 | 实测参数 |
|------|------|---------|
| `POST /api/sequences/contact-list` | 序列联系人 | seqId+current+pageSize（⚠️ 需完整参数，500 待确认） |
| `POST /api/sequences/contact-add` | **添加联系人（按标签批量）** | ✅ **`{seqId, tags:[标签ID], views:[]}`** —— ⚠️ **views 必须传空数组 `[]`！传 `["all"]` 会把全部联系人加入！**（实测：views:["all"]→139万全加；views:[]→只加tags的8140/2635） |
| `POST /api/sequences/contacts-status-change` | 联系人状态 | |
| `POST /api/sequences/email-list` | 序列邮件 | seqId+current+pageSize（⚠️ 需完整参数） |
| `POST /api/sequences/email-tags` | 邮件标签 | selectTotal 必填 |
| `POST /api/sequences/report-data` | **序列报告** | ✅ **seqId+beginDate+endDate** → 按天: sended/delivered/bounced/opened/clicked/reply |
| `POST /api/sequences/template-active` | 模板激活 | |
| `POST /api/sequences/template-delete` | 模板删除 | |
| `POST /api/sequences/activity-list` | 活动记录 | |

## 11. 费用/订单（/api/expenses/*）

| 接口 | 用途 |
|------|------|
| `POST /api/expenses/billing/show` | 账单 |
| `POST /api/expenses/orders/show` | 订单 |
| `POST /api/expenses/pay/order-create/cancel/delete/info` | 支付订单 |
| `POST /api/expenses/cdkey/redeem-code` | 兑换码 |
| `POST /api/expenses/packages/show-count` | 套餐 |
| `POST /api/expenses/sell-goods` | 商品 |
| `POST /api/expenses/give-get/status` | 赠送 |

## 📌 全量接口模块分布（对抗审查 · 420 个接口）

| 模块 | 数量 | 说明 |
|------|------|------|
| /contacts | 60 | 客户/联系人/标签/黑名单 |
| /search | 59 | 搜索/任务/预览 |
| /mailbox | 41 | 模板/签名/片段/附件/账户 |
| /clues | 40 | 线索/保存任务/评分 |
| /mails | 40 | 邮件收发/发送/追踪 |
| /enterprise | 24 | 企业/团队/角色/邀请 |
| /user | 23 | 登录/注册/验证码 |
| /account | 21 | 账户/设置 |
| /profile | 15 | 产品档案/AI推演 |
| /expenses | 13 | 费用/订单/充值 |
| /refine | 13 | 提纯搜 |
| /fields | 12 | 字段配置 |
| /tags | 8 | 标签目录/文件夹（独立组） |
| /sequences | 25 | **智能跟进计划**（chunk 抓取） |

## 📌 使用注意

1. **header 格式**：`accesstoken: web.laifaxin.com&<orgId>&<token>`（含 & 原样传）+ `uid: <orgId>`
2. **保存/搜索任务**：保存已**纯 API 可用**（refine/company-save，见 §4）；仅搜索任务 `search/tasks/create` type:keyword 维护中 → 走界面（旧记录"维护期走界面"已被 §4 实测推翻）
3. **标签 ID**：公司/联系人两个独立体系，别混用
4. **排除中国区**：默认 CN/TW/HK/MO

## ★ 联系人正确参数（★用户实测模板，勿猜）
- **查联系人 total** `contacts/contacts/show`：
  `{"viewId":"all","keyword":"","keyword_fields":["name","domain","keywords","seo_description"],"filters":[],"current":1,"pageSize":20,"sort":{"create_time":-1},"logic":"and"}`
  ⚠️ 用 viewId+keyword_fields+filters(空数组)；**不用** filter:{}（旧错）
- **清空联系人** `contacts/contacts/delete`：
  `{"selectAll":false,"selectKeys":[],"selectSort":{"create_time":-1},"selectTotal":N,"selectOption":"all","filters":[],"keyword":"","logic":"and","sort":{"create_time":-1}}`
  ⚠️ **selectOption:"all"**（非"current"）；selectKeys=[]（全部）；带 selectSort/sort
- **删除/任务进度** `operation/backend-progress` `{"id":backendId}`：
  → data.status/total/finished/progress（★这才是进度接口，backend-task-status 只返回id无进度）
- **工具**：清空工具（未随库分发；按上述正确参数封装轮询）
## ★ 产品档案（★两套！别混淆）
- **基础产品档案**（用户"产品档案"页 /settings/product-profile）：`profile/product-list`(查,current/pageSize/filter/sort/keyword) + `profile/product-delete`(删,{"id":<_id>}) + `profile/product-add`(建)
  - delete 参数是 **id**（列表 _id），不是 product_id！
- **AI推演产品**（inference-*）：`profile/inference-product-add/list/delete`（推演客群用，product_id）
- ⚠️ 我误用过 inference-product-delete 删"基础产品档案"——**两套**！用户界面"产品档案"= product-*；推演= inference-product-*

## ★ 清空工具（未随库分发；按本节正确参数自行封装）
- 清空产品：product-list 全量 + product-delete id 逐个
- 清空联系人：contacts/delete selectOption:all + backend-progress
- 清空模板：templates-list 收集 + **template-delete 单删**逐个；templates-delete 批量 500 勿用（L-39 教训）
## ★ 视图接口（★清空易漏项 + 接口名易错）
- 查：`views/views-list` `{"type":"companyDbSearch"}` → data.systemViews(系统默认"所有企业",勿删) / mineViews(用户自建) / othersViews
- 删：**`views/view-delete`** `{"viewId":<id>,"type":"companyDbSearch"}`（⚠️ 不是 views-delete→404）
- 清空清单含视图：mineViews 全删（systemViews 保留）

## ★ 补充核实接口（脚本实际调用）
- `benefits/refine-data`：点数/限额（dailyLimit/monthlyLimit/dailyUsed/monthlyUsed；gate_check 校验 token 用）→ data.isOrg/vip/dailyLimit/monthlyLimit/dailyUsed/monthlyUsed
- `contacts/recycle/show`：回收站联系人查看（清空需先清回收站——`{"current":1,"pageSize":10,"filter":{},"sort":{}}`）
- `tags/folder-delete`：标签文件夹删除（`{"id":<folderId>}`，⚠️不同于 tag-delete 删标签）
- `tags/folder-list`：标签文件夹列表（`{}`）
## ★ 任务/进度/产品/视图/回收站 表格（★关键接口,勿因散文遗漏）
| 接口 | 用途 | 关键参数 | 返回 |
|------|------|---------|------|
| `operation/backend-task-status` | ★保存任务状态 | `{"type":"cluesSave","id":<task id>}` | status/finished/total/contactSaveCount |
| `operation/backend-progress` | ★删除/任务进度 | `{"id":<backendId>}` | status/total/finished/progress |
| `profile/product-list` | 基础产品档案查 | `{"current":1,"pageSize":10,"filter":{},"sort":{"create_time":-1},"keyword":""}` | data.list(_id,product_name,main_business) |
| `profile/product-delete` | 基础产品档案删 | `{"id":<_id>}` | success（⚠️用id非product_id） |
| `profile/product-add` | 基础产品档案建 | product_name/main_business/excluded_customer_types/other_message | data.id |
| `profile/inference-product-delete` | AI推演产品删除 | `{"product_id":<id>}` | success（★用途:删推演档案;勿与product-delete混,L-37） |
| `views/view-delete` | 视图删除 | `{"viewId":<id>,"type":"companyDbSearch"}` | success（⚠️非views-delete→404,L-38） |
| `tags/folder-delete` | 标签文件夹删 | `{"id":<folderId>}` | success |
| `contacts/recycle/show` | 回收站联系人 | `{"current":1,"pageSize":10,"filter":{},"sort":{}}` | list（清空需先清回收站） |
| `benefits/refine-data` | 点数/限额 | `{}` | isOrg/vip/dailyLimit/monthlyLimit/dailyUsed/monthlyUsed |
| `settings/sequence/schedule-default` | 计划时间设默认 | `{"id":<schedule_id>}` | success（★schedule_id 运行时 schedule-list 解析,各账号不同;本租户快照纽约=`<scheduleId>`） |
| `sequences/step-list` | ★序列步骤(500易踩) | `{"seqId":<id>,"current":1,"pageSize":20}` | 12步含template_ids(24hex) |

## ★ 模板变量字段（★真实来源：fields 接口，勿乱编）
- **变量格式**：`{联系人:<title>}` / `{公司:<title>}`（用字段中文标题 title，非 dataIndex；code包裹 lfxFieldVeriable）
- **字段来源接口**：`fields/contacts-fields`（belongTo:"contact"）+ `fields/company-fields`（belongTo:"company"）→ data[].title
- **联系人变量 `{联系人:XX}`**（title值）：名称、邮箱、名字(first_name)、姓氏(last_name)、昵称、职位、公司名称(c_name)、国家、地址、介绍、主页、Linkedin、Facebook、Twitter、邮箱域名
- **公司变量 `{公司:XX}`**（title值）：公司名称(orgName)、域名、官网、国家/地区(countryCode)、员工数、行业、公司电话、公司地址、公司简介、创立时间、Linkedin、Facebook、Twitter
- ★ **发信默认仅 `{联系人:名称}`**；`{联系人:邮箱}`禁用(正文放自己邮箱=荒谬)；`{联系人:职位}`慎用(需确认有值)；`{联系人:公司名称}`/`{公司:公司名称}`/`{公司:域名}`默认禁用(错位+暴露数据源+空值)

---

> **真实案例演示**：数字与域名为公开仓库作者当时实际运行结果，仅作方法演示，与读者业务无关。
