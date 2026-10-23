---
title: "固化机制（如何防止问题再犯）"
description: "把踩坑经验固化成可执行机制：规则进工具/清单/规范/自动化校验，防止再犯"
created: 2026-08-21
updated: 2026-10-21
author: "AI Agent (DeepSeek) + 用户 Tony"
source: "基于 lessons-learned.md 的固化设计"
related: [lessons/lessons-learned, methodology/checklists, specs/api-reference, tools/README]
tags: [固化, 机制, 防再犯, 工程化]
status: verified
audience: 人+AI
---

# 🔒 固化机制（Fixation Mechanism）

> **目标**：把"踩坑经验"变成"默认行为"——不是靠记性，而是靠**机制**。
> **原则**：能写进工具的写进工具，能写进清单的写进清单，能自动校验的绝不手动。

## 四层固化（由深到浅）

### 第 1 层：工具层（最硬 · 自动执行）

把规则**内置到脚本**，违规直接拦截或强制默认：

| 规则 | 固化方式 | 状态 |
|------|---------|------|
| contact-add 必须 `views:[]` | 工具函数默认 `views:[]` + **add 数量确认**（>10000 警告） | ✅ 已设计 |
| 标签传 ID 不传名 | 工具封装 `get_tag_id(name, type)`（查/建） | ✅ 已设计 |
| 排除中国区 CN/TW/HK/MO | audit_company.py 默认 exclude | ✅ 已实现 |
| 审计用规则表 | audit_company.py（MATCH/REJECT/MARGINAL 硬编码） | ✅ 已实现 |
| pageSize≥10 | 工具统一 pageSize=20 | ✅ 已设计 |
| 保存计划链 | `save_company_cli.py prepare/confirm/execute` + front/selectTotal + confirmed plan | V2 实施中；文档作者未实测；旧 save_first_n 封停 |
| 真实数量/单位 | `rule_check.py`：selectTotal 严格正整数（家）、count 只相等性、18 字段 wire | V2 实施中；未验收前不宣称闭环 |
| front/unknown | `save_plan.py` scope O_EXCL + `status/reconcile` 本账簿绑定 | V2 实施中；不明结果保留锁，不盲重试 |

### 第 2 层：规范层（文档 · 有据可查）

**api-reference.md 标注规则**：
- 🔴 = 必须界面流程 / 有严重踩坑
- ⚠️ = 参数有坑（views:[] / seqId / 标签ID）
- ✅ = 已实测
- 🚧 = 维护中

**checklists.md 加硬性检查项**（保存前/加联系人前/激活前）。

### 第 3 层：流程层（方法论 · 行为准则）

**四条铁律**（写进 methodology/best-practices.md 顶部）：
1. **先实测再下结论**：任何参数空 body 试探 → 补全 → 验证结果数字（不是只看 success）
2. **判断标准写死**：可复现，不主观漂移
3. **新字段先在隔离沙箱单条验证；真实保存按 confirmed plan 的 N**，不自行缩量；先 1 个看 add 数量（add:8140 ✅ / add:1398445 ❌）只适用于新参数验证，不适用于缩小用户已确认的保存规模
4. **接口逆向跟踪懒加载 chunk**：不全量 dump 主 bundle

### 第 4 层：记忆层（AI 辅助 · 每次会话自动带）

**AI 代理记忆规范**（每次操作前自查）：
```
[操作前必查]
□ 这个操作有没有先例？（查 lessons/）
□ 参数语义实测过吗？（不猜）
□ 批量操作验证过数量吗？
□ 判断标准写死了吗？
```

## 具体固化落地清单

### 1. 工具函数（tools/）
- [x] `audit_company.py`（审计规则表）✅
- [x] `create_es_templates.py`（模板批量）✅（⚠️ 现 deprecated：已由统一生成器 gen_templates.py 替代，见 L-39 / db/tools.tsv）
- [ ] `contact_add.py`（内置 views:[] + 数量确认——**尚未创建此工具**，现靠人工 curl + wait_save_done 时序守卫）
- [ ] `get_tag_id.py`（按名称查/建标签 ID）
- [ ] ~~`save_flow.py`（Playwright 界面保存）~~ —— **已废不建**（L-29 纯 API 破解：front+selectTotal 通路保留；V2 保存入口为 `save_company_cli.py` 计划链，旧 save_first_n 封停）

### 2. 文档更新
- [x] api-reference 标注（views:[] 🔴 / seqId ⚠️ / 标签ID ⚠️）✅
- [x] checklists 加检查项 ✅
- [x] best-practices 顶部加四条铁律 ✅（已加，见 methodology/best-practices.md 顶部"🚨 四条铁律"）
- [ ] runs/tony/_archive/operation-log.md 加"操作前自查"步骤

### 3. 自动化校验（进阶）
- [ ] 工具脚本对 contact-add 的 add>10000 自动警告/暂停
- [ ] 保存任务后按 `save_company_cli.py status` 本 plan/attempt 的 task_id 回读 contactSaveCount/companySaveCount，并用 `reconcile` 只消费本 CLI 记录（不是只看 success）

## 如何持续积累（记忆系统）

```
每次操作/踩坑 → 记录到 lessons/lessons-learned.md（问题/根因/修复/教训/预防）
            → 更新索引（README lessons 表）
            → 固化到工具/清单/规范（对应层）
            → 下次操作前查 lessons + checklists
```

**闭环**：踩坑 → 记录 → 反思 → 固化 → 防再犯 → （新坑）→ 循环

## 📁 索引入口

- 问题库：[lessons/lessons-learned.md](lessons-learned.md)
- 固化机制：[lessons/fixation.md](fixation.md)（本文）
- 检查清单：[methodology/checklists.md](../methodology/checklists.md)
- API 规范：[specs/api-reference.md](../specs/api-reference.md)
- 工具：[tools/README.md](../tools/README.md)
