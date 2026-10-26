---
doc_id: "tests-index"
title: "tests 索引"
description: "目录索引：测试用例分组、运行方式与文档回归测试入口，跑回归前读。"
type: "index"
status: "active"
updated: "2026-10-25"
---

# tests 索引
> 一句话：这里放全仓自动化回归测试与运行入口；改代码、改文档或跑验收前读。

运行方式：python3 -m unittest discover -s tests

## 子目录

| 子目录 | 说明 | 什么时候进 |
|---|---|---|
| （无） | 本目录没有子目录 | - |

## 文件

| 文件 | 说明 | 什么时候读 |
|---|---|---|
| __init__.py | 测试包初始化文件（一次性票据注入） | 无需读；仅测试包初始化 |
| gate_env.py | 测试放行一次性票据：生产入口只认票据，不认裸 LFX_GATE_TEST_MODE | 改测试放行/门禁隔离后 |
| test_approval_numeric_quotes.py | 确认卡回数字的审批回归：S7/S9/S10 放行「1」，S5/S12 仍要求原话。 | 改审批确认词判定时 |
| test_audit_tools_fixes.py | 探针/审计工具的 P1 回归：四区 filters、--domains 走 refine、loose 匹配率、错误上抛（P1-3/P1-4） | 改 S2/S3/S4 搜索与审计工具后 |
| test_beginner_flow_links.py | 新手入口链接纪律测试（2026-10-23）。 | 改 specs/beginner-flow.md 或新手入口链接后 |
| test_compliance_evidence_mode.py | S7/S8/S11/S12 合规证据模式：live-only 与 fail-closed 契约 | 改 S7/S8/S11/S12 合规证据校验后 |
| test_confirm_numbering.py | 确认点一律回数字（2026-10-23 用户要求：只回数字就能继续）。 | 改确认点话术或确认闸门后 |
| test_contact_add_ticket_gate.py | P0-A S10 票据门回归测试（静态红队：票据门曾经失效）。 | 改 S10 加人票据门后 |
| test_count_guard.py | S5 数量推导闸门回归：50 绕过、末页、预算、样本、五处一致、哈希篡改。 | 改保存数量/预算/证据推导后 |
| test_credential_input.py | 聊天框两行凭据解析（LF/CRLF/缺 org/超限 fail-closed） | 改凭据输入/传输方式后 |
| test_cross_platform.py | 跨平台一致性：preflight.py 存在且用当前解释器、.gitattributes 行尾、Windows/macOS 文案齐全。 | 改自检入口、行尾规则或安装话术后 |
| test_cta_keyword_gate.py | CTA 回复关键词闸门测试：引导对方回一个短词，且该短词必须加粗。 | 改模板 CTA 关键词或渲染文案后 |
| test_doc_naming.py | 文档命名与目录索引防回归（2026-10-23 文档重命名与索引重构）。 | 重命名文档或改目录/INDEX 后 |
| test_evidence_mode.py | evidence_mode 判定：仅 live 可正式收口 | 改 evidence_mode 判定后 |
| test_finalize_audit_window.py | S4 finalize_audit 的审计窗口机器校验（P0-1 回归测试）。 | 改 S4 审计窗口/finalize 逻辑后 |
| test_flow_credential_transport.py | 主流程凭据传递：程序化 stdin、不落盘 | 改流程内凭据传递后 |
| test_full_flow_simulation.py | 全流程模拟：S0→S12 编排与状态推进联调 | 改主流程编排或全流程联调前 |
| test_gate_hardening.py | 闸门加固回归：写操作前拒绝与票据 | 改闸门加固/写入口后 |
| test_gate_integration.py | 闸门与写脚本集成：开工门/执行卡/审批链 | 改闸门与各写脚本集成后 |
| test_install_first_screen.py | 安装首屏口径（2026-10-23 用户裁决）：刚装好直接问昵称+产品，不出菜单、不要数字。 | 改安装首屏话术或开场流程后 |
| test_legacy_seals.py | 旧脚本物理封条 + 安装自检退出码回归（2026-10-23）。 | 改旧脚本封条或安装自检后 |
| test_module_api_map.py | 锁定逐模块 API 核验表与「文档=代码」口径，防止回退到旧说法。 | 改逐模块 API 对照表后 |
| test_multi_segment_batching.py | 多客群分批铁律测试（RULES 7d / 2026-09-09 用户拍板：允许分批、接受成本翻倍）。 | 改多客群分批规则后 |
| test_nickname_hardening.py | 纯昵称硬约束：签名与正文不含公司名/电话/邮箱 | 改纯昵称/签名规则后 |
| test_spam_trigger_words.py | 垃圾词清单/生成器硬门/S7 写作避开/S12 看数据五问话术。 | 改垃圾词或看数据话术 |
| test_email_format_doctrine.py | 邮件格式口径：HTML 载体/CTA 加粗/emoji 限制/120 词；docs07 旧高亮已纠偏。 | 改 S7 或 docs07 后 |
| test_novice_late_stage_edges.py | 第 5–7 屏边界：重跑不重复建/试跑停发/不能部分加人/提前激活/回1不等于激活。 | 改第 5–7 屏卡片后 |
| test_novice_edge_cases.py | 新手首测边界：只答一半/回数字/Safari/拒绝连接/单一候选/审计时长/产品照片。 | 改首测卡片或边界话术后 |
| test_novice_flow_contract.py | 新手流程契约测试（specs/novice-flow-contract.md v1.0）。 | 改新手契约/回复次数后 |
| test_product_profile_hardening.py | 产品档案硬约束：字段校验/版本/hash/回落 | 改产品档案校验/回落后 |
| test_registration_facts.py | 注册/开通事实口径测试（2026-09-09 对抗审查）。 | 改注册/开通事实口径后 |
| test_release_consistency.py | 发布一致性：SKILL 版本 = CHANGELOG 最新条目；README/总索引挂演示稿；模板改名有映射记录。 | 发版、改版本号或新手入口后 |
| test_render_html_preview.py | HTML 预览渲染测试：加粗标记不泄漏、CTA 段独立标注、变量替换正确。 | 改 HTML 预览渲染后 |
| test_repo_layout.py | 仓库目录布局纪律测试（防「影子副本」回退）。 | 改仓库目录布局后 |
| test_repo_references.py | 仓库自洽性：文档引用的工具/模板必须真实存在（2026-10-23 新手实测暴露）。 | 改文档引用/模板位置后 |
| test_runtime_cards.py | 执行卡就位测试：全新 checkout 必须自带 runtime/cards，保存链才可用。 | 改执行卡或 runtime/cards 后 |
| test_s10_precheck.py | S10 加人前只读预检回归（任务C）：人数为 0 / 标签缺失 → 中文 exit 2 且不写平台。 | 改 S10 加人前预检后 |
| test_s12_adversarial.py | S12 激活凭证链 · 对抗模拟测试（2026-09-17 用户要求"模拟对抗"后固化）。 | 改 S12 激活凭证链后 |
| test_s12_resume.py | S12 续接激活：当前 TTY 续接凭证与回读 | 改 S12 续接激活流程后 |
| test_save_company_cli_preflight.py | save_company_cli.execute 的 workspace_guard 预检回归（P0-2）。 | 改保存链 workspace 预检后 |
| test_save_offline_input_doc.py | 保存命令文档回归（任务C）：SKILL/operations-sop 示例参数与代码一致 + offline-input schema 文档 | 改保存命令示例或 offline-input 文档后 |
| test_s7_numeric_confirm.py | S7 数字确认端到端回归（2026-10-23）：S7 回「1」可铸凭证；S2/S5/S9/S10 裸「1」一律拒绝 | 改审批口令或 S7 卡确认方式后 |
| test_s12_activation_gates.py | 第 7 关激活前结构闸门：上限实读/标签身份/模板库归属/凭证一次性 + --check-structure 端到端。 | 改激活结构闸门或 S12 凭证消费后 |
| test_s11_closure_gate.py | S11 收口证明闸门：只认 finalize_run 写的收口字段，手写/过期/坏 sha 一律拒绝。 | 改 S11 收口字段或 S12 签发/激活前校验后 |
| test_workspace_verified_gate.py | 工作空间未判定必须 fail-closed（exit 5），仅测试进程放行。 | 改 workspace_guard.preflight 后 |
| test_sequence_closure_hardening.py | 任务A 回归测试：闭合序列 / 激活 / verify 三处加固（2026-10-23）。 | 改序列闭合/激活/verify 加固后 |
| test_startup_gate.py | 开工必读闸门：6 文档 sha256+会话+ack 机器强制 | 改开工必读/6 文档哈希登记后 |
| test_step_map.py | 锁定「逐模块逻辑 + 流程图」索引的存在与关键口径，防止以后被删/被改回旧口径。 | 改 step-map/流程图索引后 |
| test_subject_per_variant.py | 标题逐变体差异化测试（2026-09-18 用户实测后立）。 | 改邮件主题逐变体规则后 |
| test_template_batch_filter.py | 批次选取回归：分组容器排除、组内/未分组模板计入、顺序与上限。 | 改模板差异收集口径时 |
| test_template_folder_scope.py | 模板分组（folder）不得把已分组模板排除（任务C）。 | 改模板分组 folder 规则后 |
| test_template_generation_gates.py | S8 模板生成三道门的回归测试（P0-C 价格硬门 / P0-D 12轮×4 断言 / P1-E 自动差异检查）。 | 改 S8 模板三道门后 |
| test_tmap_grid.py | tmap 网格分组测试（2026-09-11 每轮变体数 10→4 后立）。 | 改 tmap 网格/每轮变体数后 |
| test_troubleshooting_paths.py | 排障路径：faq→踩坑台账→lessons 链路可达 | 改排障路径文档后 |
| test_user_visible_jargon.py | 用户可见话术黑话闸门（对抗审查加固）：output-templates 代码块内不得出现客群/序列/硬门/审批凭证/S 编号等内部词。 | 改 output-templates 话术或术语对照后 |
| test_user_facing_copy.py | 用户可见文案纪律测试（2026-09-09 用户拍板：小白要能看懂，不许用黑话）。 | 改用户可见文案后 |
| test_website_profile.py | 网站资料增强：角色分类/候选校验/批准补丁/失败不阻断 | 改网站资料增强模块后 |
| test_workspace_guard.py | 工作空间落点校验的对抗性测试：确凿误路由必须阻断，探测不到必须"未校验"而非"已通过"。 | 改工作空间落点校验后 |
| test_workspace_transport.py | 工作空间传输方式测试（2026-09-09 真实双空间对照实测）。 | 改双空间传输方式后 |
| test_doc_frontmatter.py | 文档 frontmatter 回归：必填字段、description 长度、doc_id 唯一、type 枚举、MD-METADATA 自身完整性。 | 改元数据规范/文档 frontmatter 后 |
| test_doc_links.py | 文档引用回归：Markdown 链接、反引号 .md 路径、INDEX 覆盖，坏链必须为 0。 | 改文档链接或 INDEX 后 |
| test_email_style_gate.py | email-style.md 闸门回归：结构五项必填，价格/邮箱/电话/认证/承诺必须拒绝。 | 改旧开发信提炼/模板生成前闸门后 |
