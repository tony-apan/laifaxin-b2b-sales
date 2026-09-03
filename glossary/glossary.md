---
title: "术语表（Glossary）"
description: "来发信外贸获客全流程术语：中英对照 + 通俗解释，人机通用"
created: 2026-08-21
updated: 2026-08-21
author: "AI Agent + 运营方"
source: "来发信官方文档 + 实战验证"
related: [docs/00-overview, docs/01-customer-search, docs/05-email-marketing]
tags: [术语表, glossary, 中英对照]
status: verified
audience: 人+AI
---

# 术语表（Glossary）

## 🔤 核心概念

| 术语 | 英文 | 解释 |
|------|------|------|
| 金主 | Buyer / Customer | 会买你产品的客户（搜"客户造啥"找到的） |
| 同行 | Competitor / Peer | 生产同类产品的企业（搜"我会做啥"找到的） |
| 服务词 | Service Word | 描述自己能力/产品的词（如 CNC Machining）→ 找同行 |
| 产品词 | Product Word | 描述客户业务/产品的词（如 Drone Frame）→ 找金主 |
| 种子客户 | Seed Customer | 手里已有的精准目标客户（用其网址找相似） |
| 找相似 | Similar Search | 用种子客户找同行（滚雪球裂变） |
| 提纯搜 | Refine Search | 用精准业务描述词/角色词重新搜（替代杂乱关键词） |
| AI 推演 | AI Deduction | 输入产品名→AI 推理目标客群 |
| 客群 | Customer Segment | 目标客户群体（带价值路径/推荐理由/搜索词） |

## 🏷️ 客户管理

| 术语 | 英文 | 解释 |
|------|------|------|
| 标签 | Tag | 客户的静态名片（描述"他是谁"） |
| 视图 | View | 动态筛选器（解决"要找谁"），一次设置永久复用 |
| 黄金公式(★已废,RULES铁律7:标签=客户群体中文名) | Golden Formula | 标签命名：语言-国家-产品-角色 |
| 公司标签 | Company Tag | 描述公司属性（独立标签体系） |
| 联系人标签 | Contact Tag | 描述联系人属性（独立标签体系） |
| 拉黑 | Blacklist | 把不匹配的客户加入黑名单 |
| 意向标签 | Intent Tag | 跟进状态：💬询盘/📦寄样/💰成交 |
| 风险标签 | Risk Tag | 需排除：❌同行/🚫退订/⛔其他 |

## 📧 邮件营销

| 术语 | 英文 | 解释 |
|------|------|------|
| 平台系统通道 | Platform Sending Channel | 平台提供发送基础设施，可减少自有邮箱直接承压，但不保证零封号/零投诉；运营方仍承担名单、内容、退订和目标市场合规责任 |
| 我的邮箱 | Own Mailbox | 自有邮箱，适合少量人工跟进；群发可能影响邮箱和域名信誉 |
| 单次群发 | One-shot Blast | 只发 1 轮的群发（节日问候/测试） |
| 智能跟进计划 | Smart Follow-up Plan | 3~12 轮自动多轮发信（日常开发） |
| 跟进步骤 | Follow-up Step | 计划里的一轮发信（1步=1轮模板） |
| 发送上限 | Send Limit | 计划24h上限/单域名上限（风控） |
| 公司触发器 | Company Trigger | 同公司多联系人，某联系人回复后是否继续触达其他 |
| 未发送触发器 | Unsent Trigger | 避免发给无效/黑名单/不该触达的客户 |
| 回信停发 | Stop After Reply | 当前流程不会自动给回复者打标签；人或AI助手发现回复后须立即打“询盘”标签，标签实际生效后 notSentTags 才停后续邮件 |
| 邮件追踪 | Email Tracking | 实时看打开/点击/附件下载 |
| 退信 | Bounce | 邮件退回（地址无效） |
| 送达率 | Delivery Rate | 成功送达的比例 |
| 阅读率 | Open Rate | 被打开的比例 |

## 🤖 AI 开发信

| 术语 | 英文 | 解释 |
|------|------|------|
| 开发信 | Cold Email | 给潜在客户的开发邮件 |
| 邮件序列 | Email Sequence | 多轮递进的开发信（6~12轮） |
| 5步邮件流 | 5-step Flow | 痛点→桥梁→价值列表→提问→钩子 |
| 钩子 | Hook | CTA 设计（资源/洞察/资格三种原型） |
| KEYWORD 高亮 | Keyword Highlight | 钩子里的回复关键词（Catalog/Data/Yes） |
| 价值主张 | Value Proposition | 产品能解决什么（特性→利益→USP） |
| 独特卖点 | USP | 与众不同的点（最好数字量化） |
| 段落戒律 | Paragraph Discipline | 一段一句（视觉停顿） |
| 零营销感签名 | Clean Signature | 只留英文名，无公司/职位/链接（防垃圾过滤器） |

## ⚙️ 技术/系统

| 术语 | 英文 | 解释 |
|------|------|------|
| 点数 | Credit | 保存邮箱/验证消耗的资源（有效邮箱2点/未知1点） |
| 自动去重 | Auto Dedup | 一个邮箱只扣一次点，不重复建档 |
| 产品档案 | Product Profile | AI 推演的输入（填你的产品，越详细越准） |
| 排除中国区 | Exclude CN | 默认排除 CN/TW/HK/MO |
| 维护期 | Maintenance | 客户搜索/保存引擎维护（2026/3/27 恢复） |
| 精准度 | Accuracy | 本页目标客户占比（教程建议≥80% 保存；★现行底线=70% 临界，见 specs/threshold-method） |
| 临界点 | Threshold | 精准度降到 70% 以下的页（往前翻保存） |
| queryId | 搜索缓存ID | refine 搜索返回的 ID（保存关联用） |
| task_id | 搜索任务ID | 域名/关键词搜索任务（找相似/保存关联） |

## 系统/技术词（新手必读）
| 词 | 人话 |
|----|------|
| token / accesstoken | 你的登录凭证（一长串字符），AI 拿它替你操作；等同密码，只给信任的 AI，换账号要重新取 |
| orgId | 账号/组织标识；已包含在 token 第 2 段里，AI 会自动提取，不用单独找 |
| 闸门（Gate） | 正式开始前的安全自检（防误花点数/误发信），全绿才放行 |
| 状态机 S0-S12 | 流程的 13 个步骤编号（S0 起步检查 → S12 激活），一步步走不跳步 |
| 确认节点 | 需要你拍板的步骤：回复「确认」继续 /「否」终止 / 直接说要改什么 |
| 审批凭证（approval） | 你每次"确认"留下的记录凭证，写操作工具必须凭它才肯执行 |
| 租户 | 一个来发信账号（一个公司）= 一个租户；换租户要换 token |
| 问题/教训编号 | 内部问题登记与教训库（L-xx）的编号，供 AI 溯源；公开版未含内部问题台账明细 |
| undefined / null / None | 编程里的"空/没有"：控制台显示 undefined=复制成功；null=没登录；None=没取到数据，都不是病毒 |
| 点数/配额 | 搜索查看的用量额度（日 500/月 10000），用完次日/次月重置，保存不受影响 |
