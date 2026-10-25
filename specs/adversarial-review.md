---
doc_id: "specs-adversarial-review"
title: "对抗审查报告（Adversarial Review）"
description: "全量接口重抓对比已有记录：发现遗漏（sequences/tags/expenses）+ 验证模板/序列接口 + 结论"
type: "spec"
status: "active"
updated: "2026-10-23"
created: 2026-08-21
author: "AI Agent (DeepSeek) + 用户 Tony"
source: "全量接口 dump + 实测"
related: [specs/api-reference, docs/03-save-customers, docs/05-email-marketing]
tags: [审查, 验证, 接口完整性]
audience: 人+AI
---

# 对抗审查报告（Adversarial Review）

> **目的**：回答"相关接口都抓了和验证了吗？"——用全量 dump 对比已有记录，用实测验证，找遗漏和错误。

## 方法

1. 全量 dump 前端 bundle 的 `/api/*` 接口（420 个）
2. 对比 `specs/api-reference.md` 已有记录（68 个）
3. 针对遗漏的关键模块**实测**（模板/序列/标签目录）
4. 记录结论

## 审查发现

### ✅ 已正确记录（实测验证无误）

| 模块 | 状态 |
|------|------|
| AI 推演（profile/inference-*） | ✅ 实测全通过 |
| 搜索（refine/company-list、domain/similar-list） | ✅ 实测 |
| 保存（clues/company-save-*） | ⚠️ 结论：必须走界面（API 直调 0 保存）——**★已被推翻（2026-08-21 后续实测）**：保存=纯 API `refine/company-save` 可用，0保存根因=缺 selectKeys/selectOption 误用 current，见 api-reference §4 / RULES 铁律1 |
| 标签（contacts/tags-*） | ✅ 实测（公司/联系人两体系） |
| 客户管理（contacts/companies|contacts/show） | ✅ 实测 |

### ❌ 遗漏（本次补充）

| 模块 | 遗漏内容 | 已补 |
|------|---------|------|
| **/api/sequences/*** | **智能跟进计划全套 25 个接口**（主 bundle 未含，在懒加载 chunk） | ✅ api-reference 第 10 节 |
| **/api/tags/*** | **标签目录/文件夹管理 8 个接口**（与 contacts/tags-* 互补） | ✅ api-reference 第 6.5 节 |
| **/api/expenses/*** | 费用/订单/充值 13 个接口 | ✅ api-reference 第 11 节 |
| /api/enterprise/* | 企业/团队/角色 24 个（只记了 3 个） | ✅ 模块清单 |

### ⚠️ 参数纠正（实测发现的坑）

| 接口 | 错误认知 | 正确 |
|------|---------|------|
| `sequences/step-list` | 以为传 id | **必须传 `seqId`** |
| `mailbox/template-add` | 以为只需 name | 需 **name+subject**（html 建议） |
| `mailbox/templates-list` | 任意 pageSize | **pageSize≥10** |
| `search/domain-emails` | 任意 pageSize | **pageSize≥10** |
| `search/tasks/show` | 传 task_id | **传 taskId + pageSize/current/filter/sort** |
| 保存标签 | 传标签名 | **传标签 ID**（公司/联系人两体系） |

## 实测关键证据

### 邮件模板（新建成功）
```
POST /api/mailbox/template-add
{"name":"API测试模板","foid":"0","subject":"Hello {联系人:名称}","html":"<p>...</p>"}
→ {"success":true,"data":{"id":"6a8842c0eab0f07f0a98e7c8"}}
```

### 智能跟进计划（序列+步骤真实数据）
```
序列：静默客户唤醒 (英语-皮筏艇-经销商)  [channel:system, stepsCount:4]
  rules: {finishReply:false, max_emails_per_day:30000, domain_emails_per_day:2, aiGuard:true, notSentInvalid:true}
步骤1: {step:1, type:auto_email, template_ids:[2个], wait_mode:minute, wait_time:0, senders:[账号]}
```

### 序列新建（实测 + 完整验证）
```
POST /api/sequences/sequence-create
{"name":"API审查-临时序列","channel":"system"}
→ {"success":true,"data":{"id":"6a8843cba69a56777e624fde"}}  （已删除测试）
```

### 保温杯序列 12 步（完整步骤验证）
> ⚠️ 下为**旧序列实测步长**（step1=5天起）；★现行拍板步长=step1 minute/30、step2 day/5、step3 day/15、step4-12 day/30（L-41 用户纠正；sequence-config §步长）
```
保温杯-礼品经销商-多轮开发（stepsCount:12, channel:system）
  step1:  wait_mode:day, wait_time:5   （5天后发第1轮）
  step2:  wait_mode:day, wait_time:15  （15天后第2轮）
  step3-12: wait_mode:day, wait_time:30（每30天一轮，覆盖1年）
  每步 template_ids: 10个（多选随机）
```

### 序列列表/选项
- `sequence-list`（分页）→ 所有序列含数据统计
- `sequence-options` → 序列下拉选项（含全部序列名/状态）
- `sequence-count` → total/active/inactive/poor

## 结论

1. **核心链路接口全部验证**（搜/筛/存/模板/序列），但**保存必须走界面**（不是接口问题，是前端流程）——**★此条已推翻**：同日后续抓包实测 `refine/company-save` 纯 API 可存（front+selectTotal 提邮箱），见 api-reference §4
2. **sequences 是之前最大的遗漏**——智能跟进计划的完整接口在懒加载 chunk，主 bundle 抓不到
3. **建议**：以后做接口清单，不能只抓主 bundle，要**跟踪懒加载 chunk**（sequence-create-dialog 等）

## 待办（下次审查）

- [ ] 跟踪更多懒加载 chunk（contactsDrawer、filters-drawer、task-create-dialog）
- [x] 验证 /api/sequences/sequence-create 完整参数（✅已完成：name+channel，rules 实测结构——见 api-reference §10）
- [x] 验证 /api/sequences/contact-add（✅已完成：tags+views:[] 铁律，views:["all"]=139万全加——api-reference §10/L-01）
- [x] 验证 /api/sequences/report-data（✅已完成：seqId+beginDate/endDate 按天报告——api-reference §10）

---

## 🆕 追加审查（2026-08-22 · 写真机/电动自行车实操后）

### ① 数字靠照搬（严重）
- **问题**：我口头说"写真机9500家"，实际是 **9820**（TARGET=9999 收集到9820）——**照抄了电动自行车的 TARGET=9500**，未核实
- **教训**：⚠️ **每个产品独立核实真实数据**（save-list 按标签过滤统计 total），不凭"同类假设"

### ② 判产品匹配率方法（反复被纠正）
- **问题**：大量靠工具 % + 抽查1页，**没逐页完整读描述**
- **纠正**：**50页粒度 + 每页完整读10条**，逐条问"是否产品行业客户"（中等：印刷/设备/耗材商算，媒体/目录不算）
- **实测写真机**：第1/500/900/1000页逐条读 → **全程100%**（全印刷/超大设备/耗材）
- **教训**：⚠️ **判定必须逐条读描述，数出比例**（10/10、8/10），不要工具% + 抽查就定论

### ③ 教程标准 vs 用户要求（需记录）
- 教程 02：保存前**本页精准度 ≥80%**（更严格）/ 建议不低于70%
- 用户要求：**≥70%**（更宽松）
- **实际执行**：按用户 70%（写真机/电动自行车）
- **注意**：70% 是用户底线，**教程 80% 是更稳**——**跟用户确认用哪个**（默认按用户）

### ④ 数据质量对比（写真机 vs 电动自行车）
| | 保存家数 | 邮箱 | 匹配率 |
|--|--------|------|--------|
| 写真机 | 9820 | 16872(valid 8400) | 100% |
| 电动自行车 | 9500 | 332(valid 220) | 90-100% |

- **写真机远好于电动自行车**：种子方向准 + 印刷行业邮箱全
- **电动自行车邮箱少**（332）——可能种子/行业邮箱完备度问题，**值得复查**

### ✅ 做对了
- 排除中国区 CN/TW/HK/MO ✅
- 保存前N条 = selectTotal+selectKeys空 ✅（见 save_first_n.py）
- contact-add views:[] 铁律 ✅
- 序列标准（美国时间/30000/5/禁发询盘/12轮10封）✅
- save 用 refine/company-save + 权威 id ✅
