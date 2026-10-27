---
doc_id: "tools-index"
title: "tools 索引"
description: "目录索引：tools 下脚本与说明的导航，找现役工具或确认用途时读。"
type: "index"
status: "active"
updated: "2026-10-26"
---

# tools 索引
> 一句话：这里放工具脚本与调用边界的说明入口；找脚本、确认用途或排查行为时读。

## 子目录

| 子目录 | 说明 | 什么时候进 |
|---|---|---|
| （无） | 本目录没有子目录 | - |

## 文件

| 文件 | 说明 | 什么时候读 |
|---|---|---|
| README.md | 工具目录说明与随库核心工具清单 | 找脚本或确认工具清单时 |
| s11_closure.py | S11 收口证明校验库：缺字段/格式错/超 24 小时/来自未来一律拒绝（供签发/激活复用）。 | 改 S11 收口校验或签发/激活前校验时 |
| activate_sequence.py | profile+合规证据+绑定审批+回读active+状态推进 | 第 7 关激活序列前 |
| api_base_url.py | 只读 base-url 配置（Guard V2）。 | 排查接口地址配置 |
| approval.py | 写工具require_approval硬闸门;.local/approvals.tsv id列+gen_id/record | 五道确认闸门审批与审计时 |
| audit_company.py | 词匹配初筛(⚠️仅趋势,临界须AI反思) | 第 2 步审计初筛（仅趋势） |
| auth_guard.py | 执行护栏 · auth 授权票据（v3）。 | 写操作前排查授权票据 |
| bootstrap.ps1 | 零Python探测/winget安装Python+Git/复查(Windows;待实机动态验) | 新电脑首次准备环境（Windows） |
| bootstrap.sh | 零Python探测/自动安装/复查(macOS/Linux/WSL/Git Bash) | 新电脑首次准备环境（macOS/Linux） |
| browser_login.py | Isolated Chromium login connector. Standard library only, Python 3.9+. | 浏览器登录连接器调试 |
| build_sequence.py | 校验纯昵称+profile+tmap.meta hash/status+稳定项目键;运行时解析tz/notSentTags;12步 | 第 6 步建序列前 |
| check_login.py | 用户聊天框直贴两行;主AI经--credentials-stdin;orgId独立必填不回退;urllib内存header;失效给教程 | 连平台或登录校验前 |
| check_rules.sh | 默认离线检查规则/项目/问题;在线登录校验由主AI经--credentials-stdin传两行凭据 | 交付前离线规则检查 / 排障 |
| check_template_diff.py | Jaccard相似度≤0.70(差异≥30%);★逐模板template-info取真实html(templates-list不含html) | 第 4/5 步模板差异检查 |
| compliance_validation.py | live-only;五项72h真实source/detail;模拟离线桩占位fail-closed;flow/activate共用 | 第 7 关激活/合规证据校验 |
| contact_add.py | ⛔已封条（save_guard.require，运行时即 DEPRECATED）：仅作流程核对，禁止调用 | 只读核对旧链路时 |
| contact_add_authorized.py | ★S10 加联系人入序列（一条龙缺口#2）：时序守卫(保存finished+标签>0) → contact-add(views:[]铁律) → 核对 add 数 | 第 6 步加联系人入序列前 |
| count_guard.py | S5 保存数量推导闸门：只认 S4 收口证据 + 预算上界；50/手工缩量/末页/预算超限全拒。 | 第 3 步保存数量推导前 |
| credential_input.py | 严格解析聊天框两行凭据;LF/CRLF/CR;缺org/重复/控制符/超限fail-closed | 连平台贴凭据后 / 凭据解析失败时 |
| delete_all_products.py | product-list+product-delete id | 清空测试产品（危险，显式确认） |
| evidence_validation.py | S4/S11/S12共用simulation/mock/stub/离线网络桩占位识别 | S4/S11/S12 证据模式识别 |
| finalize_audit.py | 70%临界证据+独立放行review后推进S4 | 第 2 步审计收口前 |
| finalize_run.py | 聚合序列/排除/差异证据与核实面板;仅S10可推进S11 | 第 7 关激活前收口 |
| find_critical.py | 三页平均(词匹配,历史) | ⛔ S4 禁用；仅历史参考 |
| find_threshold.py | 二分找70%临界(词匹配,历史) | ⛔ S4 禁用；仅历史参考 |
| flow_orchestrator.py | ⚠️原型:仅节点确认向导+approvals记账(输出approval_id);写操作须人工执行 | 需要节点确认向导时（原型） |
| gate_check.sh | 主AI经程序化stdin运行--credentials-stdin;缺token/orgId阻断;legacy参数仅内部兼容 | 开工前闸门检查 / 登录失败排障 |
| gen_templates.py | 必须plan+profile;纯昵称签名;profile hash;claims字段/source/evidence_text;--out含meta | 第 4 步生成模板前 |
| onboard_check.py | Python就绪后环境复查+可续接项目/status/profile扫描;敏感字段不输出 | 安装后/换机后自检，开工前 |
| opening_gate.py | ADVISORY/仅测试：生产开场由 SKILL 路由及文案卡驱动，本模块不参与生产。 | 仅测试咨询，不用于生产 |
| operator_profile.py | 公司级资料init/update/validate/status;签名只读nickname | 第 1 步运营方档案 |
| install_hooks.sh | 安装提交前/推送前自检钩子（core.hooksPath=.githooks），每个 clone 跑一次。 | 克隆仓库后 / 想启用提交与推送前必检时 |
| preflight.py | 跨平台自检（Windows/macOS 通用）：文档引用+全量测试+规则检查；Windows 用 py 跑。 | 交付/合并/发布前（Windows 首选） |
| preflight.sh | 发布前一条命令自检：文档引用+全量测试+规则检查，全绿才交付（Unix）。 | 交付/合并/发布前（macOS/Linux） |
| product_desc.py | S0 用途 → 平台推演描述（product_desc_zh）唯一拼装器（v3）。 | 第 1 步拼装平台推演描述 |
| product_profile.py | init/confirm/validate/status;状态/版本/hash/operation-record推进 | 第 1 步产品知识档案 |
| profile_utils.py | 纯昵称/第三方信息/source值域/profile哈希/事实字段解析 | 档案字段/哈希工具，排查档案问题时 |
| project_lock.py | 同项目高风险写操作互斥;活PID阻断;死PID陈旧锁清理 | 同项目高风险写操作前 |
| rebuild_templates.py | ⚠️半自动:实操两次失败(重名/引用锁/≥1步)——正确顺序见docstring+L-43,需人工分步 | 模板重建（半自动，需人工分步） |
| render_guard.py | 执行护栏 · render 渲染留痕校验（v3）。 | 渲染留痕校验前 |
| render_html_preview.py | ★模板 HTML 预览（收件人视角）：把 plan 渲染成可在浏览器打开的邮件预览页。 | 第 4 步浏览器预览模板 |
| render_preview.py | HTML→收件人视图(非源码) | 第 4 步预览收件人视图 |
| resolve_schedule.py | schedule-list按--tz/--name解析schedule_id(--list列全部);★schedule_id各账号不同,禁止硬编码,建序列前必跑 | 第 6 步建序列前解析 schedule_id |
| rule_check.py | S5 真实 payload / plan / 预算的纯函数严格校验（Guard V2 C 组）。 | 第 3 步保存 payload/预算校验 |
| save_budget.py | 保存预算自动校准（Auto-Cal v11 定稿口径）。 | 第 3 步保存预算校准 |
| save_company_cli.py | 现役唯一真实保存通道（Guard V2：prepare → confirm → execute → status/reconcile）。 | 第 3 步保存（唯一真实通道） |
| save_first_n.py | front+exclude4区+max3(selectTotal=前N条数;★--approval闸门S5) | 第 3 步 front 保存前 N 条 |
| save_guard.py | 执行护栏 · save 唯一写入口（v3）。 | 保存链写操作前 |
| save_plan.py | S5 保存计划与账簿（Guard V2 C 组核心）。 | 第 3 步保存计划与账簿 |
| save_progress.py | 保存进度播报一行话术（已存/总数/已用点/预计剩余），不联网不写盘。 | 第 3 步保存期间每 5–10 秒播报 |
| search_company.py | 只读搜索 prepare/execute（Guard V2 B 组）。 | 第 2/3 步只读搜索公司 |
| seed_resolve.py | --id结果id→base-info取域名;只读 | 第 2 步解析样板客户域名 |
| segment_fields.py | S3/S4 搜索字段守卫（此前被 search_company.py 引用但仓库缺失，2026-10-23 补齐）。 | 第 2/3 步搜索字段守卫 |
| segment_registry.py | 当前产品/轮次来源登记（Guard V2 A 组）。 | 第 2 步登记产品/轮次来源 |
| segment_select.py | ★S2 客群落档（铁律 7d）：把用户选中的客群写进 operation-record 的「客群」行。 | 第 2 步落档用户选中的客群 |
| segment_source.py | S2 客群来源闸门（v3）：客群只能逐条来自本次平台返回。 | 第 2 步核对客群来源 |
| segments_infer.py | inference-generate×N+segment-list拉全量含query_en/query_total;--approval S2 | 第 2 步推演客群前 |
| session_store.py | Local session persistence. Digests detect accidental damage, not hostile edits. | 排查会话持久化 |
| startup_gate.py | 开工必读闸门 L1（机器强制）：没登记就先读文档，写操作一律拒绝。 | 开工前登记必读 / 写操作被拒时 |
| step_gate.py | 执行卡闸门（L2 加载留痕 / L3 写操作前拒绝）。 | 执行卡加载与写操作前 |
| tag_add.py | contacts/tags-add建标签+同名查重复用+铁律7中文提醒;--list免审批;--approval S2/S5闸门 | 第 3 步建标签 / 查重 |
| tag_check.py | 只读检查联系人标签存量；>0 默认拒绝，防复用共享标签把全库老联系人带进 S10。 | 保存前 / 加人前核对标签是否新 |
| template_batch.py | 模板批次选取单一真源：按前缀收集、排除同名分组容器（分组/未分组模板都计入）。 | 改模板差异/重建模板的收集口径时 |
| tmap_grid.py | tmap 网格解析（★单一真源）：从 gen_templates 产出的 name→id 映射，解析"12 轮 × N 变体"并分组。 | 第 5 步解析 12 轮×N 变体分组 |
| update_run_state.py | 安全更新operation-record并按合法转换图/恢复证据防跳步 | 推进状态 / 换机续接 |
| usage_record.py | 把「用途 + 推演来源」写进 operation-record，保证换会话/重跑可复现（v3 K6）。 | 写运行记录 / 换会话续接 |
| verify_exclude.py | 4区排除列表内容校验(L-33) | 第 6/7 关核验四区排除 |
| verify_sequence.py | 断言12步+template_ids 24hex+wait(30分/5/15/30天) | 第 6/7 关核验序列 |
| version_check.py | 版本检查（轻量·零依赖·永不阻塞主流程）： | 启动时版本自检 |
| wait_save_done.py | ⛔ 已禁用（save_guard 封条）；保存对账用 `save_company_cli.py status/reconcile` | 勿调用 |
| website_profile.py | 无网络:角色分类+六区候选校验+批准补丁+单档案原子导入;失败不阻断主线 | 第 1 步可选网站资料增强 |
| website_profile_utils.py | stdlib schema/来源host/第三方联系/patch hash/原子写 | 网站资料增强工具函数 |
| workspace_guard.py | ★工作空间落点校验（fail-closed）——防"给了企业 orgId 却写进个人空间"。 | 保存/建模板/加人前核对落点 |
| check_doc_links.py | 文档引用与目录索引核验脚本：Markdown 链接、反引号 .md 路径、代码内 .md 名、INDEX 覆盖。 | 改文档/索引后或交付前 |
| email_style_gate.py | email-style.md 机器闸门：只允许称呼/开场/段落/CTA/签名五项；价格/联系方式/认证/承诺出现即拒（生成模板前强制）。 | 第 4 步旧开发信提炼后 |
