---
title: "来发信知识库·总索引（AI快速查询）"
description: "统一的索引层：md主索引 + tsv数据库索引。标注每个文档/脚本的路径/用途/状态，供AI快速定位（换机/断会话可用）"
created: 2026-08-29
updated: 2026-08-29
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
| **SOP-规模化** | domain-scale-sop | `specs/domain-scale-sop.md` | 域名搜/front保存(前N不翻页) | ✅ |
| **规范-模板/序列** | sequence-config | `specs/sequence-config.md` | code变量/差异30%/冷启动/美国时间 | ✅ |
| **规则-营销** | marketing-rules-2.0 | `specs/marketing-rules-2.0.md` | 70%默认/3邮箱/暖机/contactExcludes | ✅ |
| **SOP-代运营** | operations-sop | `specs/operations-sop.md` | 时区/点数预算/标签/找相似 | ✅ |
| **API参考** | api-reference | `specs/api-reference.md` | 全接口参数（含front保存/验证） | ✅ |
| **教训** | lessons-learned | `lessons/lessons-learned.md` | 问题教训(L-01~L-52) | ✅ |
| **询盘转化** | mass-to-precision | `docs/09-mass-outreach-to-precision-follow-up.md` | 广撒网成本账→询盘背调→A/B/C/D分级→多渠道长期跟进 | ✅ |
| **用户话术** | output-templates | `output-templates/`（含 S0-连接成功/T-token/S2/S5/S6-数量账/S7/S9/S10/S11/S12/Q1-Q5） | S0-S12+询盘阶段给小白看的固定输出模板 | ✅ |
| **数据结构** | data-structure | `specs/data-structure.md` | md/tsv/jsonl分工/目录规范 | ✅ |
| **运营方档案** | operator-profile | 本地 `.local/operator-profile.md`（不入 Git） | 昵称/公司/官网/联系方式/市场默认（★待用户补公司信息） | ✅ |
| **术语表** | glossary | `glossary/glossary.md` | 系统/业务词人话解释（新手必读） | ✅ |
| **人类教程** | wiki | `wiki/faq.md` + `wiki/guided-tour.md` | 配额/接口空/None 等 FAQ + 界面背景 | 参考 |
| **对抗审查记录** | review-cycle | `review-cycle.md`（机制）；审查记录为本地，不入 Git | 旁观者审查+发布红队结论已并入规则/清单 | ✅ |

> 表格仅列核心文档；**文档全量 = `db/docs.tsv`（status值域=现行/历史/过时/模板/参考）**。
> ⚠️ **docs/ 目录 = 官方教程整理（部分过时）**：docs/03、docs/08 仍教旧 Playwright 界面保存，已被纯 API 取代——以 RULES/specs/SKILL.md 为准，docs/ 仅作界面背景参考。

## 📂 运行档案（runs/：多公司×多产品，★2026-08-30 对抗重构）
> **通用层**（RULES/specs/lessons/tools）不分公司共享；**档案层**（runs/）按 `运营方/产品/` 隔离——新公司/新AI拿到直接用。
```
runs/
  _template/            ← 新公司/新产品先复制这里(operation-record/reflection/evidence/模板)
  <运营方>/             ← 运营方命名空间（昵称；公司名确定后改目录名）——本地数据，不入 Git
    <产品>/   operation-record.md + reflection.md + evidence.json + verify-*.txt + tmap.json + seq-config.json
    _review/  audit-checklist.md        ← 会话级审查工件（本地）
    _archive/ operation-log.md          ← 历史日志归档（本地）
```
- 每个产品目录**自带完整可核查记录**（流程每步+参数+凭证），换人换机只看这一个目录就能接手
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
| **流程编排(向导)** | `tools/flow_orchestrator.py` | 节点确认向导+approvals记账(写操作须人工执行) | ⚠️prototype |
| **保存前N** | `tools/save_first_n.py` | front保存前N(提邮箱) | ✅ |
| **审计** | `tools/audit_company.py` | 50页跳逐页匹配率 | ✅ |
| **找临界** | `tools/find_threshold.py` | 二分找70%临界 | ✅ |
| **找临界细化** | `tools/find_critical.py` | 三页平均找临界 | ✅ |
| **S5前置·建标签** | `tools/tag_add.py` | 建客户群体中文标签+查重复用 | ✅ |
| **S9建序列** | `tools/build_sequence.py` | tz/notSentTags运行时解析+12步(一条龙) | ✅ |
| **S10加联系人** | `tools/contact_add.py` | 时序守卫+views:[]铁律(一条龙) | ✅ |
| **登录检查(第一步)** | `tools/check_login.py` | 只读验证token+无token引导官方教程 | ✅ |
| **流程闸门** | `tools/gate_check.sh` | 开始前强制校验(org自动提取) | ✅ |
| **时序守卫** | `tools/wait_save_done.py` | 等save finished+标签>0 | ✅ |

> 表格仅列随库核心工具（22 个）；`db/tools.tsv` 为全量工具登记（含未随库分发的 deprecated/research 条目，勿用）。

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
