---
doc_id: "specs-module-api-map"
title: "逐模块 API 与要点核验表（文档≠代码，全部对过）"
description: "M0–M12 每模块：入口脚本、真实 API、关键参数、写入门禁、要点、证据；附文档与代码差异清单（已修/待办）。"
type: "spec"
status: "active"
updated: "2026-10-23"
created: 2026-10-23
audience: 人+AI
---

# 🔍 逐模块 API 与要点核验表

> **用途**：AI 执行到某模块前，先看本表这一行，就知道「调哪个脚本、真正打哪些接口、带什么参数、谁卡门禁、用户要回什么」。
> **核验方式**：端点以 `tools/*.py` 实际调用为准（grep 命中）；参数以 `specs/api-reference.md`（实测记录）为准；门禁以代码实际 import/调用为准。
> **图例**：✅=文档与代码一致；⚠️=文档已修正或仍有差异；ℹ️=仅文档层约束（无代码物理拦截）。

## 0. 写入门禁的真实分层（2026-10-23 核验）

| 层 | 代码位置 | 真实作用 | 覆盖 |
|---|---|---|---|
| 开工门 L1 | `tools/startup_gate.py` `enforce_cli_startup()` | 未 ack 昵称+产品 → 写脚本 exit 2；6 份必读 sha256 + 会话绑定 | 16 个写脚本 + 保存链 |
| 执行卡 L2/L3 | `tools/step_gate.py` | 状态推进前先 show/record 卡 | 保存链（`save_company_cli.py` 依赖 `runtime/cards/S5.json`） |
| 审批凭证 | `tools/approval.py` `require_approval()` | 用户确认行 + 参数哈希绑定，`confirm+confirmed` 才可用 | S2 推演写、S5 标签、S7/S8 模板、S9 序列、S10 加人、S12 激活 |
| 保存计划链 V2 | `tools/save_guard.py` `save_company_v2()` + `auth_guard.authorize_save_plan` | plan/scope/render/ticket 同 binding，一次提交 | **仅 S5 保存** |
| 写票据 | `tools/auth_guard.py` `authorize_write()` | action+payload_hash 绑定、一次性消费 | **仅 S10 加人**（`contact_add_authorized.py`） |
| 原话门 | `approval.confirm_quote_ok` | 激活原话必须含「确认激活」 | **仅 S12** |

> ⚠️ 重要纠正：**模板（S7/S8）、序列（S9）、激活（S12）目前用的是 `approval.py` 审批凭证，不是 `auth_guard.authorize_write()` 票据**。
> 旧文档写「模板/序列/激活必须持 auth_guard 票据」= 与代码不符，已按实际修正（见 §2 差异清单 D1）。
> 旧写脚本中本仓现存的 4 个（save_first_n / contact_add / delete_all_products / wait_save_done）已在最早可执行位置加 `save_guard.require()` **物理封条**（dry-run 也封）；其余旧脚本仍为「文档层禁用」+ 开工门 + 审批。封条仅防误触，不是安全边界（RULES L235/L237 已如实声明）。

## 1. 逐模块 API 卡

| 模块 | 入口脚本 | 真实 API（方法 路径） | 关键参数 | 写? | 门禁 | 要点（AI 必守） |
|---|---|---|---|---|---|---|
| M0 安装/第0屏 | `onboard_check.py` | 无 | — | 否 | — | 只问昵称+产品；不菜单/不数字/不要 token |
| M1 开工门 | `startup_gate.py ack` | 无 | `--nickname --product` | 本地写 | — | 6 份必读 sha256 + 本会话；文档变/换会话要重 ack |
| M2 第1屏 | 无 | 无 | — | 否 | — | 「进度 1/6」+ 6 步全景 + 该回什么 |
| M3 连平台 | `check_login.py`、`workspace_guard.py` | `POST benefits/refine-data`（只读空间/配额）；`account/current` 仅 `save_budget.py` 使用（M8） | `{}`；读 uid/额度 | 否 | — | 首次平台调用前必检；token/orgId 缺一即停；不让用户排查 |
| M4 产品档案 | `product_profile.py`（本地档案）/ `flow_orchestrator.py`（推演档案）；`website_profile.py` 无平台 API | `POST profile/inference-product-add`、`profile/inference-product-list`、`profile/product-list` | add: product_name/product_zh/product_en/product_desc_zh/product_exclusions；list: `{}`（ID 字段=`_id`） | 是（推演档案） | startup + S2 审批 | 8 项核对用户确认；无来源事实不得进邮件 |
| M5 客群推演 S2 | `segments_infer.py`、`segment_source.py` | `POST profile/inference-segment-generate`、`profile/inference-segment-list` | generate: `product_id`（=_id）；list: `product_id` → segment_name/query_en/ai_reason/_id | 是（推演） | startup + S2 审批 | 类型逐条来自平台返回；无 70% 指标；不本地生成；≥2 类提示分开做 |
| M6 种子 S3 | `seed_resolve.py`、`search_company.py` | `POST refine/company-list`、`search/company-search`、`domain/base-info` | **代码实际**：company-list keyword+current+pageSize=10+logic=and+**filters:[]（尚未排四区、无 sort，见 D21）**；company-search keyword/current/pageSize；base-info 传 id 或 domain | 否 | — | 先 query_en 第一页→代表买家 id→base-info 取域名→域名再搜；禁 similar-list 扩量 |
| M7 审计/临界 S4 | `audit_company.py`、`finalize_audit.py` | `POST refine/company-list`、`domain/base-info` | 同上 + 每页 current/queryId/matched/total/emails 记录 | 否 | 证据 live + 独立审查 | 100 页跳→前后 3 页→5 页滑窗；临界=首跌前一窗口末页；未采样=UNKNOWN；工具只做趋势初筛 |
| M8 保存 S5 | `save_company_cli.py`（V2）、`tag_add.py`、`save_budget.py`、`wait_save_done.py` | `POST refine/company-save`、`operation/backend-task-status`、`contacts/tags-add`、`contacts/tags-list`、`account/current`、`benefits/refine-data` | save: 见 api-reference §4 payload（selectTotal/selectKeys 等）；status: `{type:"cluesSave", id}`；tags-add: name,type | 是（唯一保存通道） | startup + 执行卡 S5 + plan/confirm/execute + render/ticket | 无 confirmed plan 不写；用户回数字=选类型≠保存授权；保存后对账 |
| M9 模板 S7/S8 | `gen_templates.py`、`check_template_diff.py`、`rebuild_templates.py` | `POST mailbox/templates-list`、`template-info`、`template-add`、`template-delete`、`templates-folder-list`、`template-folder-add` | list: current/pageSize≥10；add: name+subject+html+foid=<自动分组id>（不是 0）；folder-add: name | 是 | startup + S7/S8 审批 | 先本地 3–8 样稿→用户确认→48 封=12轮×4变体；每封主题/正文不同；自动归同名分组 |
| M10 序列 S9 | `build_sequence.py`、`resolve_schedule.py`、`verify_sequence.py` | `POST sequences/sequence-create`、`sequence-save`、`sequence-details`、`sequence-list`、`step-create`、`step-list`、`step-save`、`settings/sequence/schedule-list` | create: name+channel:"system"；save: id+name+schedule_id+rules；step-create: seqId+step+template_ids+wait_mode+wait_time+senders；schedule-list: current/pageSize:100 | 是 | startup + S9 审批 | 12 步；时区/计划时间运行时解析；建后 verify 步骤数+绑定 |
| M11 加人 S10 | `contact_add_authorized.py`（现役） | `POST sequences/contact-add`、`contact-list`、`contacts/contacts/show`、`contacts/tags-list`、`sequence-list`、`operation/backend-task-status` | contact-add: `{seqId, tags:[标签ID], views:[]}` ★views 必须空数组；contact-list: seqId+current+pageSize | 是 | startup + S10 审批 + `auth_guard` sequence 票据 + 时序守卫 | 保存 finished + 标签联系人>0 + 序列 inactive + 对账一致才加；`contact_add.py` 仅流程核对 |
| M11b 激活 S12（并入 M11 的同一用户步） | `activate_sequence.py`、`flow_orchestrator --resume-s12` | `POST sequences/sequence-list`、`sequence-active` | sequence-active: id+active:true/false | 是（不可回退） | startup + S12 审批 + `confirm_quote_ok` 原话「确认激活」 | 两条路：AI 执行（原话）/用户平台手开+`--sync-manual` 只读同步；含糊应答拒绝 |
| M12 出错/续接 | `onboard_check.py`、`update_run_state.py` | 无 | — | 否 | — | 三行话术；不让用户排查；续接不回 S0 但要重 ack |

## 2. 文档↔代码差异清单（本轮核验）

| # | 差异 | 证据 | 处理 |
|---|---|---|---|
| D1 | 文档称「模板/序列/激活必须持 auth_guard 票据 authorize_write」；实际三者用 `approval.py` 审批，只有 S10 用 `auth_guard.authorize_write` | `tools/gen_templates.py:677`、`build_sequence.py:108`、`activate_sequence.py:277` 均 `require_approval`；`auth_guard` 仅被 `save_company_cli.py`/`contact_add_authorized.py` 引用 | ✅ 已改 SKILL.md 写入口纪律 + docs/10 L99 |
| D2 | 文档称旧写脚本「已被 save_guard.require() 无条件封条」；原先无任何脚本调用 | 4 个旧脚本现已在最早可执行位置调用 require；其余仍无 | ✅ **已修**：4 个脚本物理封条 + 文档改为「部分封条、仍非安全边界」 |
| D3 | SKILL 称 `threshold-probe-spec` v3.5；实际文件 v3.1 | `specs/threshold-probe-spec.md:3` | ✅ 已改 SKILL L82 |
| D4 | SKILL 称 S10「无 CLI 写通道 / contact_add 已 DEPRECATED」；实际现役 `contact_add_authorized.py`（票据+时序守卫） | `tools/contact_add_authorized.py:4,226` | ✅ 已改 SKILL L176 + novice-flow-contract + node-playbook + tools/README |
| D5 | `api-dictionary.md` §5「保存/序列/联系人要点 待补」 | `specs/api-dictionary.md:50-52` | ✅ 已补全 §5 |
| D6 | `docs/11-replay-script.md` 仍写 authorize_write(action="sequence"/"activate") | `docs/11-replay-script.md:281,284` | ⚠️ 历史演练脚本，保留原文；以本表 §0 为准 |
| D7 | `version_check.py` 57 个脚本中唯一未被任何文档引用 | `ls tools/*.py` | ✅ 已补进 tools/README |
| D8 | `step-map.md` 未把各模块「真实 API」写进每节 | `specs/step-map.md` | ⚠️ 仅 M11 节有「API 见 module-api-map」；其余节待补（2026-10-23 复核） |
| D9 | `finalize_audit.py` 不校验 window/5页窗口/临界页；RULES/probe-sop 门禁描述被夸大 | `tools/finalize_audit.py:validate_audit_window` | ✅ **已修并测**：连续页/5页窗≥70%/临界页=首跌窗起点+3/语义表对齐，失败 exit 2 |
| D10 | `save_company_cli` 缺 `workspace_guard.preflight`（RULES:203 声称内置） | 旧版无 import | ✅ **已修并测**：execute 在 save_company_v2 之前 preflight，阻断 exit 2 且写入 0 次 |
| D11 | 旧保存脚本无物理封条，但文档称「无条件封条」 | save_first_n/contact_add/delete_all_products/wait_save_done 已调用 | ✅ **已修并测**：4 脚本最早可执行位置封条（含 dry-run），--help/import 不受影响；README/RULES 口径同步 |
| D12 | `save_company_cli` 文档命令参数（--project/--audit-manifest/--ticket）不存在 | 实际 argparse `--request-file/--ticket-file` | ✅ **已修**：SKILL/operations-sop 改真实参数；新增 `specs/save-offline-input.md` 最小 schema 与样例 |
| D13 | `find_critical/find_threshold` filters=[]，不排四区 | `find_critical.py:19`、`find_threshold.py:19` | ✅ **已修并测**：两工具统一四区 filters |
| D14 | `audit_company` loose 恒 100%、吞 HTTP 异常、`--domains` 走 similar-list | `audit_company.py:224,248,96-100,122` | ✅ **已修并测**：loose 按总条数算、401/403/422 立即报错 exit 2、5xx 重试≤2、--domains 走 company-list |
| D15 | 判据三套并存（50页+三页 / 100页+三页 / 100页+5页）；预算 51/60/50 三值 | threshold-method 旧段落、probe §7、S4 模板旧句 | ✅ 已统一（100页/5页窗口；method 加历史注记；预算「单轮≤60，采样≤51」） |
| D16 | 模板 48=12×4 无断言；价格禁令缺 cheap/FOB/CIF；`check_template_diff` 未接入 | `gen_templates.py:106-118,209-213,684` 等 | ✅ **已修并测**：12×4 fail-fast（含生成后复核）、NO_PRICE_RE 硬门（claims 不得放行）、建后自动 diff fail-closed |
| D17 | S10 票据门失效（`authorize_write` 返回值被丢弃，无票仍写） | `contact_add_authorized.py:226-227`；`save_guard.py:243-244` | ✅ **已修并测**：无票/坏票 exit 2 且写调用 0 次；好票恰好 1 次写；`--auth-ticket` 非 dry-run 必填 |
| D18 | 激活口令代码只认「激活」；flow 拒绝时 return 0 | `activate_sequence.py:114-141`；`flow_orchestrator.py:154-156` | ✅ **已修并测**：两处必须含「确认激活」；拒绝 exit 2；仅说激活→零联网拒绝 |
| D19 | `finishReply` 台账 vs 代码/话术冲突；S12 六项未由 activate 验证；`verify_sequence` 未接线；`folder` 过滤待真机 | `build_sequence.py`；`activate_sequence.py`；`verify_sequence.py` | ✅ **已闭合**：finishReply 定「False=回信人工接管」不改代码；build 建后自动 verify 且失败 exit 2；activate 激活前校验 12 步/每步绑模板/rules/notSentTags；三处 folder 过滤删除（分组模板计入） |
| D20 | S10 名额/去重/预算无代码落点；用户话术含「序列/任务数/unkown」 | S10/S6 模板 | ✅ **已修并测**：加人前只读预检打印标签人数/预计加人/去重/未激活；0 人或缺标签 exit 2 不写；话术已改 |
| D21 | M0–M6 审计发现：`browser_login.py` 不存在但 RULES/SKILL 称首选；onboard_check 无退出码；S5 执行卡 `runtime/cards/S5.json` 仓库缺失；`segment_source.evidence_record` 未接线；`segments_infer` 无轮询；`seed_resolve` 失败曾 exit 0；`S0-连接成功` dailyUsedUp 未实现 | 详见 specs/problems-and-fixes-2026-10-23.md §30 与三份只读审计 | ✅ 已修：`browser_login.py`/`session_store.py` 已补进仓库、9 张执行卡已随仓库分发（`runtime/cards/`）、onboard 未通过 exit 2、seed_resolve 失败 exit 2、auth_guard hits 修复；剩下 dailyUsedUp/证据接线/推演轮询归 §3 真机项 |

## 3. 未核验 / 待办（不虚构）

- **live 实测**：本表端点来自代码 grep + 仓库实测记录（api-reference），本轮**未**再连真实账号逐接口打；真实跑项目时以工具 `--dry-run` / 回读为准。
- **step_gate 覆盖**：目前仅保存链依赖 `runtime/cards/S5.json`；其他写节点是否要卡，见 RULES/novice-flow-contract 的节点定义，未在代码强制。
- **D6 历史演练脚本**：docs/11 是 2026-10 的复盘记录，按「历史记录不改写」原则保留；新执行以 RULES + 本表为准。
- **M11 两条路**：contact_add_authorized（AI 执行）与用户平台手加（AI 只回读）都可；选择哪条需在 S10 卡里写清，不能事后补。
- **待真机核验（剩余）**：`S0-连接成功` dailyUsedUp 字段；`segment_source.evidence_record` 接线；`segments_infer` 轮询；真实平台上的 `folder` 字段确认（代码已不依赖它）；S12/模板自动差异首次真机跑。
- **本轮补齐**：`tools/segment_fields.py`、`tools/browser_login.py`、`tools/session_store.py`（原缺失，RULES/SKILL 引用的脚本已随仓库分发）；`runtime/cards/` 9 张执行卡（含 S5，全新 checkout 保存链可用）；`finalize_run` 兼容两种「步骤数」写法。
- **最终机器证据**：`python3 -m unittest discover -s tests` → 489 tests OK；`bash tools/check_rules.sh` → exit 0（2026-10-23 06:41）。
