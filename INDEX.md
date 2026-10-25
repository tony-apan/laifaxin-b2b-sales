---
doc_id: "index"
title: "来发信知识库·总索引（AI快速查询）"
description: "目录索引：全仓文档与数据表的总入口，按模块标注路径与用途，换机或断会话后先看。"
type: "index"
status: "active"
updated: "2026-10-23"
created: 2026-08-29
author: "AI + 用户对抗"
source: "对抗完善"
related: [RULES.md, specs/data-structure, README]
tags: [索引, 导航, 快速查询, AI定位]
audience: 人+AI
---

# 🗂 来发信知识库·总索引

> **★ 用途**：AI/人快速定位文档/脚本。按模块索引。
> **★ 换机**：先读 `RULES.md`（规则总纲）+ 本索引，再定位。
> **🆘 排障**：出错先查 `wiki/faq.md` → `specs/problems-and-fixes-2026-10-23.md` → `lessons/lessons-learned.md`（顺序固定，查不到再开 Issue）。
> **🛡 开工门**：`AGENTS.md`（AI 自动读）→ 读 6 份必读 → `python3 tools/startup_gate.py ack --nickname <昵称> --product <产品>`；未登记时**保存链/执行卡/写票据/16 个写脚本入口**都会被机器拒绝（覆盖缺口已关闭，剩余风险见台账第 25–27 条）。

## 📖 文档索引（md 主索引，人机导航）
| 模块 | 文档 | 路径 | 用途 | 状态 |
|------|------|------|------|------|
| **新手入口** | beginner-flow.md | specs/beginner-flow.md | 一页看懂 6 步 + 开场卡 + 截图参照 + 资料落仓清单（AI 第一屏必读） | 2026-10-23 |
| **踩坑台账** | problems-and-fixes.md | specs/problems-and-fixes-2026-10-23.md | 真实问题：现象/根因/处理/对抗审查/固化位置 | 2026-10-23 |
| **阈值判定** | threshold-probe-spec.md | specs/threshold-probe-spec.md | 70% 达标率与临界页判据 | 现行 |
| **红队审查** | red-team-review.md | specs/red-team-review.md | 对抗审查协议与缺陷清单 | 现行 |
| **规则总纲** | RULES.md | `RULES.md` | 唯一真源：强制流程+铁律 | ✅ 唯一真源 |
| **入口** | 总索引 | `INDEX.md` | 本文件：快速定位 | ✅ |
| **入口** | README | `README.md` | 百科快速导览 | ✅ |
| **Skill入口** | SKILL.md | `SKILL.md` | ★触发场景路由表+S0-S12一句话判据+铁律摘要（新AI第一读） | ✅ |
| **节点手册** | node-playbook | `specs/node-playbook.md` | ★节点判据×API×脚本对照表（执行照抄） | ✅ |
| **方法-临界** | threshold-method | `specs/threshold-method.md` | AI反思/100页跳/连续5页窗口/找70%临界；逐模块逻辑与跳步规则见 step-map | ✅ |
| **执行-临界探测** | threshold-probe-spec | `specs/threshold-probe-spec.md` | S4-A 执行细则 **v3.1**：连续5页滑窗/报告证据分离/四件套契约 | ✅ |
| **逐模块API** | module-api-map | `specs/module-api-map.md` | ★M0–M12 入口脚本×真实API×关键参数×写入门禁×要点（文档=代码核验） | 现行 |
| **判定-适配度** | product-fit | `specs/product-fit.md` | ★S0 前置：强/条件/弱适配三档（买家盘×决策链×周期×渠道层）+各档打法 | ✅ |
| **SOP-环境准备** | environment-setup | `specs/environment-setup.md` | ★零 Python bootstrap：跨平台探测→自动安装→复查 | ✅ |
| **SOP-换机续接** | migration-handoff | `specs/migration-handoff.md` | ★迁移本地状态→项目枚举→从当前节点继续 | ✅ |
| **SOP-运营方档案** | operator-profile-sop | `specs/operator-profile-sop.md` | ★公司级资料主动索取→`.local/operators/<operator_key>.md`→跨产品/换机复用；签名只读昵称 | ✅ |
| **SOP-产品知识档案** | product-profile-sop | `specs/product-profile-sop.md` | ★产品资料主动索取→字段级来源→确认/版本/hash→S2/S4/S7/S9复用 | ✅ |
| **SOP-网站资料增强** | website-profile-sop | `specs/website-profile-sop.md` | ★独立可选：网址角色→六区候选→批准补丁；失败不阻断主线 | ✅ |
| **SOP-规模化** | domain-scale-sop | `specs/domain-scale-sop.md` | 域名搜/front保存(前N不翻页) | ✅ |
| **规范-模板/序列** | sequence-config | `specs/sequence-config.md` | code变量/差异30%/冷启动/美国时间 | ✅ |
| **规则-营销** | marketing-rules-2.0 | `specs/marketing-rules-2.0.md` | 70%默认/3邮箱/暖机/contactExcludes | ✅ |
| **SOP-代运营** | operations-sop | `specs/operations-sop.md` | 时区/点数预算/标签/找相似 | ✅ |
| **API参考** | api-reference | `specs/api-reference.md` | 全接口参数（含front保存/验证） | ✅ |
| **教训** | lessons-learned | `lessons/lessons-learned.md` | 问题教训(L-01~L-61) | ✅ |
| **询盘转化** | mass-to-precision | `docs/09-mass-outreach-to-precision-follow-up.md` | 广撒网成本账→询盘背调→A/B/C/D分级→多渠道长期跟进 | ✅ |
| **用户话术** | output-templates | `output-templates/`（总索引+23话术模板，含S0a运营方/网站资料/产品知识档案） | S0-S12+询盘阶段给小白看的固定输出模板 | ✅ |
| **数据结构（历史参考）** | data-structure | `specs/data-structure.md` | 仅参考 md/tsv/jsonl 格式比较；旧目录未实施，严禁按其保存 token/orgId | 历史 |
| **运营方档案** | operator-profile | 本地 `.local/operators/<operator_key>.md`（旧单文件兼容，不入 Git） | 多公司隔离；签名只读纯昵称；工具 `operator_profile.py` | ✅ |
| **术语表** | glossary | `glossary/glossary.md` | 系统/业务词人话解释（新手必读） | ✅ |
| **人类教程** | wiki | `wiki/faq.md` + `wiki/guided-tour.md` | 配额/接口空/None 等 FAQ + 界面背景 | 参考 |
| **对抗审查记录** | review-cycle | `review-cycle.md`（机制）；审查记录为本地，不入 Git | 旁观者审查+发布红队结论已并入规则/清单 | ✅ |

> 表格与 `db/docs.tsv` 均列**核心文档/关键模板索引**，不是仓库全部 Markdown 文件清单；新 AI 的必读入口以本表、SKILL 路由和 gate_check 存在性校验为准。
> ⚠️ **docs/ 目录 = 官方教程整理（部分过时）**：docs/03、docs/08 仍教旧 Playwright 界面保存，已被纯 API 取代——以 RULES/specs/SKILL.md 为准，docs/ 仅作界面背景参考。

## 📁 目录索引（各目录入口）
> **每个目录都有 INDEX.md**（含数据/测试/运行模板目录；`.git`/`.local` 与 `runs/` 用户项目目录除外），覆盖该目录全部直接子项；新文档落盘后同步更新所属索引。
> 新增或修改文档前先读 [MD-METADATA.md](MD-METADATA.md)，按规范补齐 frontmatter 与链接。

| 目录 | 索引 | 放什么 |
|------|------|--------|
| 根目录 / | [INDEX.md](INDEX.md) | 全仓总导航与本表 |
| db/ | [INDEX.md](db/INDEX.md) | 文档与工具登记数据表 |
| docs/ | [INDEX.md](docs/INDEX.md) | 产品功能与实操教程 |
| glossary/ | [INDEX.md](glossary/INDEX.md) | 术语定义 |
| lessons/ | [INDEX.md](lessons/INDEX.md) | 历史问题库与固化机制 |
| methodology/ | [INDEX.md](methodology/INDEX.md) | 方法论、最佳实践与检查清单 |
| output-templates/ | [INDEX.md](output-templates/INDEX.md) | 各流程节点给用户看的话术模板 |
| runs/ | [INDEX.md](runs/INDEX.md) | 运行档案导航（公开仓只含 _template） |
| runtime/ | [INDEX.md](runtime/INDEX.md) | 运行时执行卡（cards/） |
| specs/ | [INDEX.md](specs/INDEX.md) | 流程规范、SOP、接口与审查记录 |
| tests/ | [INDEX.md](tests/INDEX.md) | 自动化回归测试与运行方式 |
| tools/ | [INDEX.md](tools/INDEX.md) | 工具脚本说明与调用边界 |
| website-profile/ | [INDEX.md](website-profile/INDEX.md) | 网站资料增强模块结构契约 |
| wiki/ | [INDEX.md](wiki/INDEX.md) | 常见问题与新手导览 |

### 根目录文件

| 文件 | 用途 | 什么时候读 |
|------|------|-----------|
| [AGENTS.md](AGENTS.md) | 任何 AI 的强制执行入口与开工顺序 | 接手仓库、开工前 |
| [CHANGELOG.md](CHANGELOG.md) | 公开库版本记录 | 排查版本差异或发布前 |
| [CORE-POINTS.md](CORE-POINTS.md) | 核心要点与实测数值 | 每次开跑前 |
| [LICENSE](LICENSE) | 开源许可证 | 复制/分发前 |
| [MD-METADATA.md](MD-METADATA.md) | Markdown 元数据与引用规范 | 新增/修改文档前 |
| [README.md](README.md) | 项目介绍、安装与阅读顺序 | 第一次了解本 Skill 时 |
| [RULES.md](RULES.md) | 规则唯一真源（确认闸门/安全边界） | 每次操作前 |
| [SKILL-PLAN.md](SKILL-PLAN.md) | 技能化判定与待办规划 | 评估发布条件时 |
| [SKILL.md](SKILL.md) | 技能入口路由与关键文件地图 | 用户提出获客任务时 |
| [requirements.txt](requirements.txt) | Python 依赖清单 | 安装/排障环境时 |
| [review-cycle.md](review-cycle.md) | 旁观者审查机制 | 完成阶段/产品后 |

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
- **AI 自查**：`bash tools/check_rules.sh` 默认只做离线规则/项目检查；需要登录校验时，由主 AI 将聊天框收到的两行凭据通过程序化 stdin 交给 `check_rules.sh --credentials-stdin`

## 🔄 AI 快速检查（post-op）
```
1. awk -F'\t' '$7=="open"' db/issues.tsv   # 本地问题登记（不入 Git）
2. tail db/runs.tsv                            # 本地运行记录（不入 Git）
3. bash tools/check_rules.sh                 # 默认离线检查；不需要凭据
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
| **网站资料增强（可选）** | `tools/website_profile.py` / `website_profile_utils.py` | 公开页候选校验、角色隔离、用户批准后单档案原子导入；失败不阻断主线 | ✅ |
| **审批/状态/证据** | `tools/approval.py` / `update_run_state.py` / `evidence_validation.py` / `compliance_validation.py` | 参数hash授权 + 状态转换 + S4/S11/S12 live-only公共证据校验 | ✅ |
| **流程向导** | `tools/flow_orchestrator.py` | 节点交互；S11 用 `--resume-s12` 当前TTY只签凭证，不联网/不激活 | ⚠️prototype |
| **登录/闸门** | `tools/credential_input.py` / `check_login.py` / `gate_check.sh` / `check_rules.sh` | 聊天框两行凭据→主AI程序化stdin；严格org；urllib内存header；默认离线规则检查 | ✅ |
| **S2/S3** | `tools/segments_infer.py` / `seed_resolve.py` | 客群推演与样板客户结果 id 取域名 | ✅ |
| **S4审计** | `tools/audit_company.py` / `find_threshold.py` / `find_critical.py` / `finalize_audit.py` | 趋势初筛+语义证据；仅evidence_mode=live可正式收口 | ✅ |
| **S5/S6保存** | `tools/save_company_cli.py`（V2 现役）/ `tag_add.py` / `save_budget.py` | plan/confirm/execute 票据链、任务/标签对账 | ✅ |
| **S7/S8模板** | `tools/gen_templates.py` / `render_preview.py` / `check_template_diff.py` / `rebuild_templates.py` | claims来源、纯昵称、差异、inactive重建 | ✅/⚠️ |
| **S9/S10序列** | `tools/build_sequence.py` / `contact_add_authorized.py` | tmap/profile血缘、inactive双回读、views[]、S10 票据 | ✅ |
| **S11/S12** | `tools/verify_sequence.py` / `verify_exclude.py` / `finalize_run.py` / `compliance_validation.py` / `activate_sequence.py` | live证据收口、S11 TTY续接审批、本地闸门先于联网、激活回读 | ✅ |
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
