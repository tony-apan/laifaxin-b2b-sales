---
title: "「产品」全流程·反思提炼"
description: "本次「产品」获客全程的反思：做对的、犯的错、可优化点（供旁观者对抗分析）"
created: "YYYY-MM-DD"
updated: "YYYY-MM-DD"
author: "AI + 用户对抗"
status: inprogress
related: [../../../specs/threshold-method, ../../../specs/sequence-config, ../../../lessons/lessons-learned]
tags: [反思, 流程复盘, 对抗分析]
---

# 🛶「产品」全流程·反思提炼

## ✅ 做对的
1. **保存**：`selectOption:"front"` + selectTotal:N + max3（提邮箱，不翻页防封号）
2. **模板**：12轮方向×10变体正文句互异（生成后跑 check_template_diff 实测≤0.70，不声称达标）
3. **标签**：客户群体中文名 + 记录 id(名称) 成对
4. **序列**：12步/纽约/30000/5/notSentTags + contact-add views:[] 铁律
5. **验证**：backend-task-status（contactSaveCount）

## ❌ 犯的错（反复踩坑）
1.
2.

## 🔍 可优化/存疑点（供旁观者分析）
- **平台数据质量**：邮箱率（邮箱数/家数）是否合理？
- **模板差异度**：实测最大 Jaccard 多少？
- **序列激活**：多少人×12轮，新列表节奏验证如何安排（★非域名保温——保温问题不存在,2026-08-30裁决③）？
- **边界**：临界页数据质量 vs 其他产品对比？
