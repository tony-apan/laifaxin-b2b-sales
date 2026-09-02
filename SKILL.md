---
title: "来发信 B2B 获客 · Skill 入口（新 AI/新会话第一份加载）"
description: "外贸获客技能入口：触发路由、必备前置、状态机判据、铁律摘要、新会话三步走、文件地图。用户说找客户/获客/开发信/保存客户/建序列/来发信即走本入口；细节一律指向 RULES.md 与 specs/，禁止凭本摘要跳步。"
created: 2026-08-30
updated: 2026-08-30
author: "独立审查 agent（对抗判定后落地）"
related: [RULES.md, INDEX.md, methodology/decision-trees.md]
tags: [skill入口, 触发路由, 状态机, 入驻, 获客]
status: active
audience: AI优先
---

# 🧭 来发信 B2B 获客 · Skill 入口

> **一句话定位**：把"产品 → 推演客群/找种子 → 域名搜相似 → AI 反思 70% 临界 → 纯 API 保存前 N → 差异化模板 120 → 12 步序列 → contact-add → 不激活待确认"整条外贸获客流水线，做成**判据明确 + 工具硬闸门 + 全程留痕**的可执行流程。
> **本文件只做路由与判据摘要**；执行任何步骤前先读 `RULES.md`（唯一真源）及指向的 specs，禁止凭记忆跳步。

## 1️⃣ 触发场景路由表（用户说什么 → 去哪）

| 用户说（触发词） | 路由到 |
|------------------|--------|
| 新会话 / 换机 / 接手 / "接着上次" | `python3 tools/onboard_check.py`（自检+读本地状态）→ 本文件 → `RULES.md` |
| "帮我找 X 产品的客户" / 开新项目 | §2 前置检查 → ① `python3 tools/check_login.py --token <T>`（登录检查）→ ② `bash tools/gate_check.sh --token <T>`（闸门）→ ③ `python3 tools/flow_orchestrator.py`（S0→S12 向导）|
| "这客户/这批准不准" / "临界在哪" | 状态机 S4 → `specs/threshold-method.md`（AI 反思 70% 判据）+ `tools/audit_company.py`（⚠️仅趋势初筛）|
| "保存这批 / 前 N 条" | 状态机 S5/S6 → `tools/save_first_n.py`（★必须带 S5 的 `--approval`）|
| "写开发信 / 模板 / 预览" | 状态机 S7 → `tools/gen_templates.py --preview`；S8 生成后必跑 `tools/check_template_diff.py` |
| "建序列 / 跟进计划" | 状态机 S9 → `python3 tools/build_sequence.py --tmap runs/<运营方>/<产品>/tmap.json --approval <S9凭证>`（tz/notSentTags 运行时解析+12 步；规范 `specs/sequence-config.md`）|
| "加联系人 / 进序列" | 状态机 S10 → `python3 tools/contact_add.py --seq <id> --tags <标签id> --task <任务id> --approval <S10凭证>`（内置时序守卫+views:[] 铁律）|
| "激活 / 发信" | S12：仅用户明确"确认激活" → **`python3 tools/activate_sequence.py --seq <id> --confirm "<用户原话>" --approval <S12凭证> --project <产品>`**（激活+回读 status:active 防假成功）；★**空序列测完激活后须回滚 inactive**（防后续加联系人即真发）；发信前核铁律 5（SPF/DKIM/退订=禁止项，平台职责）|
| "验证这批对不对" | `tools/verify_exclude.py`（排除4区）/ `tools/verify_sequence.py`（12步）/ `tools/check_template_diff.py`（差异≥30%）|
| "模板重建 / 换模板" | `tools/rebuild_templates.py`（⚠️半自动，顺序铁律见 L-43，需人工分步）|
| "清空重来" | 危险操作，先用户确认 → 按 `specs/api-reference.md` 清空工具节执行（清空脚本未随库分发）|
| "出问题了 / 记教训" | 本地问题登记（`db/issues.tsv`，本地数据不入 Git）+ `lessons/lessons-learned.md` |
| **"对抗审查 / 这个准不准 / 审一下"** | **RULES.md「🛡 操作对抗审查」（★用户强制：决策/产出必经空白子代理对抗）→ 按四类固定清单/执行前反思矩阵审 → 产出 `dialogue/reviews/rev-<日期>-<时分>-<操作>.md`（只放行/整改P0P1P2）→ 写操作三凭证：用户确认(approvals)+对抗审查(reviews)+操作流水(ops-log)** |
| "查当前数据 / 最近跑批" | 本地运行记录（`db/runs.tsv`，本地数据不入 Git）+ 本地状态（`.local/`）|

## 2️⃣ 必备前置（硬条件，缺一停）

- **★第一步=登录检查**：`python3 tools/check_login.py --token '<T>'`（只读；org 自动从 token 提取）。无 token/失效 → **引导用户**按官方教程获取后发来：https://www.laifa.xin/share/ai/laifaxin-ai-account-connection
  - 方法一(小白)：登录 web.laifaxin.com → 右键"检查"→"应用程序"→本地存储→web.laifaxin.com→accesstoken→复制"值"整串
  - 方法二(更快)：检查→控制台→`copy(localStorage.getItem("accesstoken"));`→undefined=已复制；null=未登录→刷新/重登
  - ★请用 Chrome 或 Edge 打开 web.laifaxin.com（其他浏览器界面可能不同）
  - 粘贴时浏览器可能提示 "Don't paste code"（防骗保护，正常现象）——核对命令一致后按提示输入 allow pasting 再粘贴
  - 安全边界：token 等同登录凭证，只发给你信任的 AI（本流程仅用于你会话、不写文件）；不要发群聊/工单/公开文档
  - 首次连接只做只读检查（不搜客/不保存/不扣点/不发信）；换账号需重新获取
- **必须向用户要**：① **token**（accesstoken 整串，org 从中段自动提取）② **昵称** ③ **基础产品信息**（产品名/用途/行业/目标市场/卖点）；可选 ④ 精准客户网址（有→快速路径 A，无→标准路径 B）。
- **闸门硬条件**：`bash tools/gate_check.sh --token <TOKEN>` 全部通过 = 开始流程的**唯一通行证**；未通过**禁止任何保存/模板/序列/contact-add**。
- 缺 ① 或 ② → **停，向用户要，不猜不代填**。
- token 只放命令/环境变量，**绝不写入任何文件**。
- 本地运营方档案（`.local/operator-profile.md`，首次运行自动生成）待填项（公司名/官网/联系方式）补齐前，模板正文**不得编造**。

## 3️⃣ 状态机 S0-S12（每节点一句话判据，细节见 RULES.md）

| 节点 | 一句话判据 |
|------|-----------|
| S0 INPUT_GATE | 昵称+产品信息齐了才准动，缺一停 |
| S1 PATH_PENDING | 有精准网址→快速路径 A；无→标准路径 B；两条都要用户确认 |
| S2 SEGMENT_PENDING | 推演 4 客群，逐个判"会不会采购"+周期/询盘/量级/邮箱/竞争度，给推荐，用户确认（★档案=**推理档案** inference-product-add，非 product-add，否则 generate 500；generate 后轮询 list 至非空）|
| S3 SEED_PENDING | 展示候选种子+采购可能+邮箱率，用户确认后才搜相似 |
| S4 AUDIT_RUNNING | 只读+AI 语义反思找 70% 临界（50页跳→三页平均→逐页→跌破往前）；**★按 v2 三条客户线(直采/OEM/拓品)逐条判定+判定表留痕+边界敏感性检查**；未完成不能保存 |
| S5 SAVE_PENDING | 展示临界 N/标签/排除4区/max/点数，用户确认后才保存（→输出 approval_id）|
| S6 SAVE_RUNNING | front 保存；等任务 status:finished；用标签结果对账 |
| S7 TEMPLATE_PENDING | 只生草稿，展示 3-8 个**渲染后视图**（render_preview.py）+理由，确认后才批量创建 |
| S8 TEMPLATE_BUILD | 生成 120 模板，断言变量样式/标题/差异（Jaccard≤0.70），失败回 S7 |
| S9 SEQUENCE_PENDING | 12 步(30分/5/15/30天)+纽约时区+单日30000/单家5+notSentTags，确认后建 |
| S10 CONTACT_PENDING | finished+标签联系人>0+序列 inactive+对账+确认后 contact-add(views:[]) |
| S11 READY_INACTIVE | 输出完整流程与参数，测试不激活，发"流程待确认" |
| S12 ACTIVE | 仅用户明确"确认激活/激活序列<名称>"才激活（SPF/DKIM/退订检查=禁止项）|
| ERROR_BLOCKED | 异常/参数变/对账不一致 → 只读检查，禁写 |

## 4️⃣ 铁律摘要（0-8，违反即错，详见 RULES.md）

0. **排除中国 4 区** CN/TW/HK/MO——保存与 S4 扩量搜排除；S3 文本搜不排除（schema：`values:[]` + `value:""` + `valueType:"select"`）
1. 保存 `selectOption:"front"`（≠current，current 邮箱 0）+ `contactMaxCount:3`（不足才 3→6→9 升阶）
2. 模板变量 `<code class="lfxFieldVeriable" contenteditable="false">{联系人:名称}</code>`；标题纯文案；差异≥30%（实测 Jaccard≤0.70）
3. 不翻页收集 id（封号）——保存前 N 用 `selectTotal=前N条数`
4. 验证用 `backend-task-status`（contactSaveCount）；删除进度用 `backend-progress`
5. 发信前 去重（★SPF/DKIM/DMARC 认证与退订链接/合规检查=禁止执行：平台系统通道职责）；单日 30000/单家 5；notSentTags=[询盘,不发]
6. **时序**：等保存 `status:finished` + 标签联系人>0 后才 contact-add
7. **标签=客户群体身份 `语言-行业-角色`**（不是你的产品）；记录一律 `id(名称)` 成对
8. 内部命名（标签/视图/序列/模板分组）一律中文；邮件正文=目标市场语言（默认全球英语）

## 5️⃣ 新会话三步走

1. `python3 tools/onboard_check.py`（自动打印读什么/当前状态/下一步）
2. 读 `.local/` 本地状态（当前状态+下一步，勿重头；首次运行自动生成）
3. 读 `RULES.md`（唯一真源）→ 向用户要 token+昵称+产品信息 → ①`tools/check_login.py`(登录检查) → ②`tools/gate_check.sh`(闸门) → ③按状态机逐节点跑

## 6️⃣ 关键文件地图

| 类别 | 文件 |
|------|------|
| 规则（唯一真源） | `RULES.md` → `specs/api-reference.md`（接口模板）/ `specs/threshold-method.md`（70%临界）/ `specs/domain-scale-sop.md`（域名搜+保存）/ `specs/sequence-config.md`（模板+序列）/ `specs/operations-sop.md` |
| 流程逻辑 | `methodology/decision-trees.md`（A/B 路径图）/ `INDEX.md`（导航）|
| 当前状态 | `.local/`（本地状态+运营方档案+审批凭证；首次运行自动生成，每账号/每 clone 一份，不入 Git）|
| 工具（工具=规则） | `tools/gate_check.sh`、`onboard_check.py`、`check_login.py`、`flow_orchestrator.py`、`approval.py`、`tag_add.py`（S5 前置建标签）、`save_first_n.py`、`wait_save_done.py`、`gen_templates.py`、`check_template_diff.py`、`build_sequence.py`（S9）、`contact_add.py`（S10）、`resolve_schedule.py`、`verify_exclude.py`、`verify_sequence.py`、`rebuild_templates.py`、`audit_company.py`、`render_preview.py`、`check_rules.sh`（★一条龙=check_login→gate→orchestrator→save→wait→gen→diff→build→add→verify）|
| 档案（多公司多产品） | `runs/<运营方>/<产品>/`（operation-record/reflection/evidence/verify-*）+ `runs/_template/` + 本地运行记录（不入 Git）|
| 问题与教训 | 本地问题登记（`db/issues.tsv`，本地数据不入 Git，open 即待办）/ `lessons/lessons-learned.md`（L-01~L-43）/ `review-cycle.md`（旁观者审查）|

> ⚠️ **执行纪律**：写操作工具必须带 `--approval <id> --project <产品>`（审批硬闸门·工具级，凭证在 `.local/approvals.tsv`）；每次操作前先读 RULES+对应 spec；本 SKILL.md 只是入口，与 RULES/specs 冲突时以后者为准。
> 🆘 新手黑话/常见疑惑：`glossary/glossary.md`（系统词人话表）· `wiki/faq.md`（配额/接口空/None 等FAQ）
> ⚠️ **审批闸门边界（防呆不防恶）**：`--approval` 校验的是本地 `.local/approvals.tsv`（每账号/每 clone 一份，不入 Git），该文件对本机 AI 可写——**自证行 ≠ 用户授权**。高风险操作（保存/建序列/加联系人/激活）仍必须在对话中出示用户原话；AI 自行 append 的凭证视为无效（审批补记·内部教训）。
> 🔑 **凭证出口**：`flow_orchestrator.py` 确认节点是 approval 凭证的**唯一合法出口**；审批补记（内部）的 backfilled 行不构成写授权。新 AI 给新产品写开发信文案前，先按「新产品文案军规」执行（数字可举证/标准写到底/禁假前提假稀缺/环保具体化/CTA 轮换——见 docs/07 与 specs/sequence-config.md）。
