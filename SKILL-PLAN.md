---
title: "Skill 化现状与差距清单（对抗判定 · 2026-08-30）"
description: "判定本库现在算不算 skill、离可发布还差什么；旧过时原则（Playwright 保存等）逐条用现行机制替换；待办按现状重列（已做/未做）。"
created: 2026-08-21
updated: 2026-08-30
author: "独立审查 agent（对抗判定后重写）"
source: "2026-08-21 旧 SKILL-PLAN + 2026-08-30 全库对抗审查"
related: [SKILL.md, RULES.md, INDEX.md]
tags: [Skill, 判定, 差距清单, 发布]
status: draft
audience: 人（开发者）
---

# Skill 化现状与差距清单（对抗判定）

## 🎯 判定结论

**现在算不算 skill？——"准 skill"：机制内核已齐（判据/工具/回流甚至超过多数已发布 skill），但缺发布外壳，尚不能原样发布。**

按主流 skill 五要素对照：

| 要素 | 现状 | 判定 |
|------|------|------|
| 触发词 | SKILL.md 已建触发路由表（本次落地）；但未与任何 skill 注册机制（auto-trigger 的 name+description）对接 | ⚠️ 半 |
| 路由 | 路由逻辑成熟：GATE0→A/B 路径→S0-S12；`methodology/decision-trees.md` + SKILL.md §1 | ✅ 有 |
| 判据 | 强：每节点一句话判据 + 70% 临界方法论 + verify 系列断言 + gate_check 硬闸门 | ✅ 有 |
| 工具 | 强：tools/ 下 22 个核心工具随库分发、工具=规则、`--approval` 审批硬闸门、时序守卫 | ✅ 有 |
| 回流 | 强：CHECKPOINT/approvals/runs 档案/issues/lessons/旁观者审查，全链路留痕 | ✅ 有 |

**差距一句话**：差在"入口清单化 + 触发词可注册 + 租户/遗留内容净化 + P0 服务端闭环"，不差在方法本身。

## ✅ 当前状态（现行机制，逐条替换旧 SKILL-PLAN 的过时原则）

1. **保存不再走 Playwright**。旧原则"保存必须走界面流程（API 直调 0 保存）"已作废——L-02 的根因是参数错，不是必须浏览器。现行：**纯 API** `save_first_n.py`（`selectOption:"front"` + `selectTotal=前N条数` + `contactMaxCount:3` + 排除4区正确 schema），实测有效（皮筏艇 6500 保存/10211 联系人）。
2. **审计不再靠规则表硬判**。现行：`audit_company.py` 词匹配**只做趋势初筛**（会把船只/海洋/风筝冲浪漏判），临界判据 = **AI 语义反思**（"会不会买我的品"），见 `specs/threshold-method.md`；底线 70% 用户拍板，80% 是教程更稳值、须与用户确认（旧原则把 80% 当默认，已修正）。
3. **标签 = 客户群体中文名**（不是我的产品）——铁律 7；内部命名一律中文、邮件正文按目标市场（默认全球英语）——铁律 8；标签记录一律 `id(名称)` 成对。
4. **模板差异可度量**：`check_template_diff.py` 逐模板 template-info 取真实 html，Jaccard≤0.70（差异≥30%）；模板差异实测（工具级） 实测闭环：旧批次最大 0.82 → 重建 RT2 批次最大 0.61。
5. **审批硬闸门**：`approval.py` + 写工具（`save_first_n.py`/`gen_templates.py`/`rebuild_templates.py`）必须 `--approval <id> --project <产品>`，无凭证拒绝写入 exit(1)；凭证落 `.local/approvals.tsv`（本地流水，不入 Git）。
6. **多公司多产品**：通用层（RULES/specs/lessons/tools）共享；档案层 `runs/<运营方>/<产品>/` 每产品一份完整可核查记录 + `runs/_template/`；运营方唯一源 = 本地 `.local/operator-profile.md`（不入 Git）。
7. 其他新增机制：S0-S12 状态机 + 铁律 0-8（RULES 唯一真源）、`gate_check.sh` 硬闸门、`onboard_check.py` 三步引导、`wait_save_done.py` 时序守卫、`verify_exclude.py`/`verify_sequence.py`、`gen_templates.py` 统一模板生成器（create_en_*_12rounds 系列已 deprecated）、`rebuild_templates.py` 重建顺序铁律（L-43）、旁观者审查 `review-cycle.md`、会话回落（本地记录，不入 Git）。

## 📋 旧"待办（做 Skill 前）"清单对照（按现状重列）

- [x] **测试完整流程（换产品端到端）**：电动自行车/金属粉末/步进电机/玻璃瓶/皮筏艇已多产品跑通；⚠️ 半完成——S12 激活被激活接口未就绪（sequence-active 接口 500）阻塞，"端到端含真实发信"最后一棒未闭环。
- [x] **邮件模板结构 Prompt（单封优化）**：官方教程原文（未随库分发；整理版见 `docs/07`）。
- [~] **审计规则表完善（audit-rules.md）**：未建独立文件；规则已固化进 `audit_company.py`（硬编码规则表）+ `specs/threshold-method.md`（AI 反思判据）。判定：独立文件可省，保持工具+spec 双固化即可。
- [ ] **产品档案描述模板**：仍未建；现由本地运营方档案（`.local/operator-profile.md`）+ 产品档案接口 + S2 推演客群覆盖。发布前可补一份独立模板，也可维持现状。
- [ ] **客户画像 Prompt（AI 推演输入）**：仍未建。
- [x] **SKILL.md 入口**：本次落地（触发路由/前置/状态机判据/铁律/三步走/文件地图）。

> 旧 SKILL-PLAN 的目录建议（docs/ 00-08 复制 + Playwright 界面保存脚本）**整体作废**，以现行 RULES/specs/tools 体系为准。

## 🚧 差距清单（发布前）

**P0（发布阻塞）**
1. **发布外壳未定**：skill 注册层需要 SKILL.md 的 name+description 触发词供 auto-trigger 匹配；本库 SKILL.md 只是仓内入口，尚未按目标平台（Claude/其他）的 skill 目录规范定发布包。
2. **双源风险未清**：遗留 `docs/00-08` 仍含过时规则（`docs/03-save-customers.md`、`docs/08-workflow-ops.md` 仍在讲 Playwright 界面保存，与现行纯 API front 保存矛盾——已加"过时横幅"）；第三方教程原文未随库分发；`glossary/`、`wiki/` 已并入现行体系——新 AI 需以 RULES/specs 为准。
3. **编排器名实不符**：`flow_orchestrator.py` 是**向导原型**（docstring 明言写操作须人工执行），README"一键跑全流程"表述过强；发布前要么升级为真编排（自动传递 approval_id 串接写工具），要么在入口如实改口径。
4. **租户耦合**：工具默认 `--org <orgId>`、本地状态文件混入当前租户状态、`.local/approvals.tsv` 与 `runs/<运营方>/` 是单租户数据；发布给第二个客户需"通用层/租户层"分离方案（目录机制已有，工具默认值与本地状态未分离）。
5. **P0 服务端阻塞未闭环**：激活接口未就绪（sequence-active 实测 500）/ 发信认证未配（SPF/DKIM/DMARC，平台侧）/ 合规退订缺口（平台侧）——S12 激活与真实发信无法兑现，发布文档必须如实声明。

**P1（发布前建议）**
6. `gate_check.sh` 用 grep 文本断言（改 RULES 措辞会误报）→ 改结构校验或固定锚点。
7. SKILL.md 触发路由表是首版，需按真实用户话术校准（哪些说法会漏路由）。
8. operator-profile 待填项无工具级挡板：RULES 写"不得编造"，但 `gen_templates.py` 未校验 → 可加断言。
9. 发布元数据缺失：版本/许可/维护人 manifest。

## 📦 发布形态建议（二选一）

- **方案 A（推荐）· 桥接壳**：与 `maozhishi-ui-delivery`、`allincms-bulk-content-upload` 同构（ADR-131）——发布目录只放一份 SKILL.md 指路到本仓单一源，本库继续 git 同步作唯一真源，避免双源漂移。
- **方案 B · 自包含**：净化后把通用层（RULES/specs/tools/lessons/SKILL.md）拷入 skill 目录，租户层（运行档案与本地数据表）留在客户侧。
- 无论 A/B：description 必须含触发词（找客户/获客/开发信/保存客户/建序列/来发信）；token 策略注明"每次会话用户提供，绝不入库"。

## 📋 待办（做 Skill 前，按现状重列）

**已做 ✅**：状态机+铁律、纯 API front 保存、审批硬闸门、verify 断言三件套、runs 多公司多产品目录、CHECKPOINT 续接、SKILL.md 入口（本次）。
**未做 ⬜**：
- [ ] 发布外壳选定（方案 A/B）+ name/description 触发词注册对接
- [x] 目录净化：docs/ 旧规则已标注作废；db/docs.tsv 状态已补全；第三方原文（prompts/raw）不随库分发
- [ ] flow_orchestrator 升级真编排（或改口径）
- [ ] 租户分离：工具默认 org 参数化、CHECKPOINT 拆"通用续接点+租户状态"
- [ ] P0 闭环：平台接口未就绪(激活接口500)/04/05 解决或发布文档如实声明
- [ ] 可选：产品档案描述模板、客户画像 Prompt、gate_check 结构校验、运营方档案断言

---

> **真实案例演示**：数字与域名为公开仓库作者当时实际运行结果，仅作方法演示，与读者业务无关。
