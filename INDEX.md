---
title: "来发信知识库·总索引（AI快速查询）"
description: "统一的索引层：md主索引 + tsv数据库索引。标注每个文档/脚本的路径/用途/状态，供AI快速定位（换机/断会话可用）"
created: 2026-08-29
updated: 2026-09-04
author: "AI + 用户对抗"
source: "对抗完善"
related: [RULES.md, specs/data-structure, README]
tags: [索引, 导航, 快速查询, AI定位]
status: verified
audience: 人+AI
---

# 🗂 来发信知识库·总索引

> **★ 用途**：AI/人快速定位文档/脚本。按模块索引。
> **★ 换机**：先读 `RULES.md`（规则总纲）+ 本索引，再定位。

## 📖 文档索引（md 主索引，人机导航）
| 模块 | 文档 | 路径 | 用途 | 状态 |
|------|------|------|------|------|
| **规则总纲** | RULES.md | `RULES.md` | 唯一真源：强制流程+铁律 | ✅ 唯一真源 |
| **入口** | 总索引 | `INDEX.md` | 本文件：快速定位 | ✅ |
| **入口** | README | `README.md` | 百科快速导览 | ✅ |
| **Skill入口** | SKILL.md | `SKILL.md` | ★触发场景路由表+S0-S12一句话判据+铁律摘要（新AI第一读） | ✅ |
| **节点手册** | node-playbook | `specs/node-playbook.md` | ★节点判据×API×脚本对照表（执行照抄） | ✅ |
| **方法-临界** | threshold-method | `specs/threshold-method.md` | AI反思/50页跳/三页平均/找70%临界 | ✅ |
| **判定-适配度** | product-fit | `specs/product-fit.md` | ★S0 前置：强/条件/弱适配三档（买家盘×决策链×周期×渠道层）+各档打法 | ✅ |
| **SOP-环境准备** | environment-setup | `specs/environment-setup.md` | ★零 Python bootstrap：跨平台探测→自动安装→复查 | ✅ |
| **SOP-换机续接** | migration-handoff | `specs/migration-handoff.md` | ★迁移本地状态→项目枚举→从当前节点继续 | ✅ |
| **SOP-运营方档案** | operator-profile-sop | `specs/operator-profile-sop.md` | ★公司级资料主动索取→`.local/operators/<operator_key>.md`→跨产品/换机复用；签名只读昵称 | ✅ |
| **SOP-产品知识档案** | product-profile-sop | `specs/product-profile-sop.md` | ★产品资料主动索取→字段级来源→确认/版本/hash→S2/S4/S7/S9复用 | ✅ |
| **SOP-规模化** | domain-scale-sop | `specs/domain-scale-sop.md` | 域名搜/front保存(前N不翻页) | ✅ |
| **规范-模板/序列** | sequence-config | `specs/sequence-config.md` | code变量/差异30%/冷启动/美国时间 | ✅ |
| **规则-营销** | marketing-rules-2.0 | `specs/marketing-rules-2.0.md` | 70%默认/3邮箱/暖机/contactExcludes | ✅ |
| **SOP-代运营** | operations-sop | `specs/operations-sop.md` | 时区/点数预算/标签/找相似 | ✅ |
| **API参考** | api-reference | `specs/api-reference.md` | 全接口参数（含front保存/验证） | ✅ |
| **教训** | lessons-learned | `lessons/lessons-learned.md` | 问题教训(L-01~L-54) | ✅ |
| **询盘转化** | mass-to-precision | `docs/09-mass-outreach-to-precision-follow-up.md` | 广撒网成本账→询盘背调→A/B/C/D分级→多渠道长期跟进 | ✅ |
| **用户话术** | output-templates | `output-templates/`（总索引+17话术模板，含S0a运营方档案/产品知识档案） | S0-S12+询盘阶段给小白看的固定输出模板 | ✅ |
| **数据结构** | data-structure | `specs/data-structure.md` | md/tsv/jsonl分工/目录规范 | ✅ |
| **运营方档案** | operator-profile | 本地 `.local/operators/<operator_key>.md`（旧单文件兼容，不入 Git） | 多公司隔离；签名只读纯昵称；工具 `operator_profile.py` | ✅ |
| **术语表** | glossary | `glossary/glossary.md` | 系统/业务词人话解释（新手必读） | ✅ |
| **人类教程** | wiki | `wiki/faq.md` + `wiki/guided-tour.md` | 配额/接口空/None 等 FAQ + 界面背景 | 参考 |
| **对抗审查记录** | review-cycle | `review-cycle.md`（机制）；审查记录为本地，不入 Git | 旁观者审查+发布红队结论已并入规则/清单 | ✅ |

> 表格与 `db/docs.tsv` 均列**核心文档/关键模板索引**，不是仓库全部 Markdown 文件清单；新 AI 的必读入口以本表、SKILL 路由和 gate_check 存在性校验为准。
> ⚠️ **docs/ 目录 = 官方教程整理（部分过时）**：docs/03、docs/08 仍教旧 Playwright 界面保存，已被纯 API 取代——以 RULES/specs/SKILL.md 为准，docs/ 仅作界面背景参考。

## 📂 运行档案（runs/：多公司×多产品，★2026-08-30 对抗重构）
> **通用层**（RULES/specs/lessons/tools）不分公司共享；**档案层**（runs/）按 `运营方/产品/` 隔离——新公司/新AI拿到直接用。
```
runs/
  _template/            ← 新公司/新产品先复制这里(operation-record/reflection/evidence/product-profile/模板)
  <operator_key>/           ← 创建项目时固定的运营方标识（不可因补充公司名而改目录）——本地数据，不入 Git
    <product_key>/   operation-record.md + reflection.md + evidence.json + product-profile.md + verify-*.txt + tmap.json + seq-config.json
    _review/  audit-checklist.md        ← 会话级审查工件（本地）
    _archive/ operation-log.md          ← 历史日志归档（本地）
```
- 每个产品目录**自带完整可核查记录**；`operation-record.md` 的标准 status + `product-profile.md` 的版本/hash 是换机与新会话接手真源，详见 `specs/migration-handoff.md`。
- 回落规则：产品跑完 → 写 `runs/<运营方>/<产品>/operation-record.md + reflection.md + evidence.json` → 更新本地运行记录一行（本地数据，不入 Git）

## ⚠️ 问题登记（AI 检查点）
- **问题表**：本地问题登记 `db/issues.tsv`（本地数据，不入 Git；AI 用 awk/pandas 查 `$7=="open"`）
- **每次操作后**：检查本地问题登记 + 本地运行记录，更新状态
- **AI 自查**：`bash tools/check_rules.sh`（检查 token/规则/问题）

## 🔄 AI 快速检查（post-op）
```
1. awk -F'\t' '$7=="open"' db/issues.tsv   # 本地问题登记（不入 Git）
2. tail db/runs.tsv                            # 本地运行记录（不入 Git）
3. bash tools/check_rules.sh --token <TOKEN>   # token/规则校验
```

## 📝 会话回落 + 旁观者审查（★用户强制）
- **会话记录**：本地会话记录（不入 Git；每次会话的用户指令/问题/待办全回落）
- **旁观者审查机制**：`review-cycle.md`（完成阶段→另一AI旁观者审查→结果回落issues/lessons）
- **流程闸门**：`tools/gate_check.sh`（开始前强制通过）

## 📖 关键接口补充（api-reference 已收录）
- **计划时间**：`settings/sequence/schedule-list`（查时区）+ `schedule-default`（设默认）+ sequence-save.schedule_id（引用）——★schedule_id 运行时 `tools/resolve_schedule.py` 按名称/time_zone 解析（★各账号不同,勿硬编码；工具=resolve_schedule.py）
- **序列高级设置**：sequence-save（schedule_id + rules: max_emails_per_day/domain_emails_per_day/notSentTags）

## 🛠 工具脚本索引（工具=规则，优先调用）
| 工具 | 路径 | 用途 | 状态 |
|------|------|------|------|
| **环境准备** | `tools/bootstrap.sh` / `bootstrap.ps1` | 无Python探测/安装/复查（PS1待Windows实机） | ✅/⚠️ |
| **续接扫描** | `tools/onboard_check.py` | 可续接项目/status/profile扫描 | ✅ |
| **公司/产品档案** | `tools/operator_profile.py` / `product_profile.py` / `profile_utils.py` | 分层回落、纯昵称、来源/版本/hash | ✅ |
| **审批/状态** | `tools/approval.py` / `update_run_state.py` | 实际参数hash授权 + 合法状态转换/受控恢复 | ✅ |
| **流程向导** | `tools/flow_orchestrator.py` | 节点交互；参数不全只记pending；S12当前TTY | ⚠️prototype |
| **登录/闸门** | `tools/check_login.py` / `gate_check.sh` / `check_rules.sh` | 登录、必读SOP、profile状态 | ✅ |
| **S2/S3** | `tools/segments_infer.py` / `seed_resolve.py` | 客群生成与结果id取域名 | ✅ |
| **S4审计** | `tools/audit_company.py` / `find_threshold.py` / `find_critical.py` / `finalize_audit.py` | 趋势初筛+语义证据放行收口 | ✅ |
| **S5/S6保存** | `tools/tag_add.py` / `save_first_n.py` / `wait_save_done.py` | 绑定参数保存、任务/标签对账 | ✅ |
| **S7/S8模板** | `tools/gen_templates.py` / `render_preview.py` / `check_template_diff.py` / `rebuild_templates.py` | claims来源、纯昵称、差异、inactive重建 | ✅/⚠️ |
| **S9/S10序列** | `tools/build_sequence.py` / `contact_add.py` | tmap/profile血缘、inactive双回读、views[] | ✅ |
| **S11/S12** | `tools/verify_sequence.py` / `verify_exclude.py` / `finalize_run.py` / `activate_sequence.py` | manifest/合规证据、TTY审批、激活回读 | ✅ |
| **清空产品** | `tools/delete_all_products.py` | 默认dry-run，显式确认才执行 | ✅ |

> 表格列出主流程核心工具；`db/tools.tsv` 为全量工具登记（含未随库分发的 deprecated/research 条目，勿用）。

## 📊 数据库索引（tsv 元数据表，机器可读/分析）
> 用 TSV（结构化表），AI 用 pandas/awk 快速过滤。见 `db/tools.tsv`。
| 表 | 文件 | 字段 |
|----|------|------|
| 文档元数据 | `db/docs.tsv` | path,category,title,status,tags（status值域=**现行/历史/过时/模板/参考**，2026-08-30 完善） |
| **工具全量(权威)** | `db/tools.tsv` | path,name,usage,status |
| **问题登记（本地）** | `db/issues.tsv` | 本地数据，不入 Git |
| 产品运行记录（本地） | `db/runs.tsv` | 本地数据，不入 Git |

## 🔄 流程完善（详见 RULES.md 强制流程）
```
①推演客群→②精准种子→③域名搜→④AI反思70%临界→⑤front保存→⑥差异化模板→⑦序列→⑧contact-add→⑨校验
```
> 每次操作**先读 RULES.md + 本索引**，按流程，禁止跳步。
