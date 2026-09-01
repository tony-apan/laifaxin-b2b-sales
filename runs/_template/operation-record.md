---
title: "「产品」客户开发·流程核查记录"
description: "完整跑一遍「产品」获客，每步记录（可核查）"
created: "YYYY-MM-DD"
updated: "YYYY-MM-DD"
author: "AI Agent + 用户"
status: inprogress
related: [../../../specs/threshold-method, ../../../specs/domain-scale-sop, ../../../specs/sequence-config, ../../../specs/api-reference]
---

# 🛶「产品」客户开发·流程核查记录

> 每步记录关键参数/结果，供核查。**判断标准 = AI语义反思"会不会买"**（非关键词）→ 见 [threshold-method.md](../../../specs/threshold-method.md)。

## ✅ 本轮最终记录（唯一当前真相）
| 环节 | 本轮真实值 |
|------|-----------|
| 种子 | |
| 客群 | |
| 临界 | |
| 保存 | |
| 邮箱 | |
| 标签 | 公司 xxx(客户群体中文名) / 联系人 xxx(客户群体中文名) |
| 模板 | |
| 序列 | |
| 步长 | step1=minute/30、step2=day/5、step3=day/15、step4-12=day/30 |
| contact-add | |
| 状态 | inactive（测试不激活，待确认）|

- 证据：`evidence.json`（seq_id/active/rules/templates/steps/contacts_total/tags）
- 抽验：`verify-seq.txt`、`verify-exclude.txt`、`verify-diff.txt`
- 审批：`.local/approvals.tsv`（每个决策节点一行，id+state；本地凭证，不入 Git）

## 基础信息
- 产品：
- 种子网址：
- 网址搜 total：
- 70%临界：
- 保存范围：

## 步骤① 选种子 + 网址搜
## 步骤② AI反思判断找临界
## 步骤③ 保存客户
## 步骤④ 建标签（★客户群体中文名）
## 步骤⑤ 建模板（gen_templates.py，跑 check_template_diff 实测差异）
## 步骤⑥ 建序列（12步 30分/5/15/30、纽约、30000/5、notSentTags）
## 步骤⑦ 时序守卫 + contact-add（views:[] 铁律）
## 步骤⑧ 终检（verify_sequence + verify_exclude + check_template_diff）→ inactive 待确认
