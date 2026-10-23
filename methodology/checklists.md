---
title: "检查清单（保存前/发信前/计划启动前）"
description: "三个关键节点的 checklist，照着勾选避免翻车"
created: 2026-08-21
updated: 2026-10-21
author: "AI Agent (DeepSeek) + 用户 Tony"
source: "来发信官方文档 + 实战验证"
related: [docs/02-filter-customers, docs/03-save-customers, docs/05-email-marketing]
tags: [方法论, checklist, 检查清单]
status: verified
audience: 人+AI
---

# 检查清单（Checklists）

## ✅ 通用铁律（任何操作前）

- [ ] 操作前查过 lessons/ 先例？（踩过坑没有）
- [ ] 参数语义实测过？（不猜：views:[] / seqId / 标签ID）
- [ ] 真实保存按已确认计划执行，不自行缩量？新增字段/参数在隔离沙箱单条验证（不拿真实账号试水）？
- [ ] 判断标准写死？（用工具/规则表）

## ✅ 保存前（Search → Save）

- [ ] 已抽样查看前 1~5 页 + 末尾页
- [ ] **S3 搜索锚=当前轮 query_en 原文**（逐字，不 trim/改大小写；勿用公司名，同名异司 L-45）；S4 用已选 candidate id → domain/base-info（seed_resolve --id）取域名；S5 保存沿用 S4 同一 keyword/filters/logic/sort（L-46）
- [ ] **连续5页滑动平均 ≥70%** + 逐条语义/客户线 + 独立review（单页低只记抖点；High比例/页1/2/5抽样不算；不按材质/规模二筛）
- [ ] 已确定地域范围（排除中国区 CN/TW/HK/MO）
- [ ] 公司标签已想好（铁律7：客户群体身份 `语言-行业-角色`，不是产品名；实际 id(名称) 成对）
- [ ] 联系人标签与公司标签一致
- [ ] 邮箱类型：有效 + 未知
- [ ] 每客户保存数量（默认 3；存不到数据才按 3→6→9 升阶，ISS-24 用户裁决）
- [ ] 未滥用高级选项（职位/排除词慎用；排除4区 CN/TW/HK/MO 与"选择前N条"为例外必用，见铁律0/L-28/29）
- [ ] N（家）/e（邮箱/家）/p（点/邮箱）/E/P/B/max_points 单位与来源/版本齐全？P≤min(B,max_points)？20000 只是带版本的默认建议，不是硬规则
- [ ] 保存 wire 是 18 字段白名单（selectTotal 正整数家、selectKeys:[]、selectSort:{}、真实 filters、keyword/logic 同审计）？旧 save_first_n 已封停？

## ✅ 发信前（Marketing）

- [ ] 客户标签已打好（可批量加）
- [ ] 邮件模板已备好（AI 开发信生成）
- [ ] 发送渠道：优质发送通道（群发）
- [ ] 发信昵称已设置
- [ ] 计划时间按客户时区

## ✅ 智能跟进计划启动前（Sequence）

- [ ] 邮件追踪已开
- [ ] 发送上限已设（计划24h + 单域名2~10）
- [ ] 公司触发器已配（同公司多联系人策略）
- [ ] 未发送触发器已配（避免无效/黑名单）
- [ ] 模板多选（随机更自然）
- [ ] 后续邮件内容规划（不是只换标题）
- [ ] 计划已激活
- [ ] 已按标签添加客户

## ✅ 保存任务验证（Save 后）

- [ ] 保存任务记录：finished > 0
- [ ] 公司列表出现客户（带标签）
- [ ] 联系人列表出现邮箱（数量=设定值）
- [ ] 标签正确（公司/联系人各自体系）
