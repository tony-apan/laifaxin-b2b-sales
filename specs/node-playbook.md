---
title: "节点判据 × API × 脚本 对照表（Node Playbook）"
description: "S0-S12 每个节点的判据来源/通过条件/API(接口+关键参数+api-reference行号)/脚本命令/产出记录位置——新AI执行时照抄的操作手册"
created: 2026-08-30
updated: 2026-08-30
author: "独立审查agent"
source: "对 RULES.md + specs/* + lessons/lessons-learned.md + tools/* + db/* 的完整性审查"
related: [RULES.md, api-reference, threshold-method, domain-scale-sop, sequence-config, ../lessons/lessons-learned, ../db/tools.tsv]
tags: [操作手册, 节点, 判据, API, 脚本, 对照表]
status: verified
audience: 人+AI
---

# 🧭 节点判据 × API × 脚本 对照表（Node Playbook）

> **★ 用途**：新 AI/新会话接手流程时照抄的操作手册。先读 `../RULES.md`（唯一真源）+ 本表，再动手。
> **★ 引用行号**：`RULES Lx` = `../RULES.md` 第 x 行；`API Lx` = `specs/api-reference.md` 第 x 行（本文件同目录，行号以 2026-08-30 版本为准）；其余按文件名标注。
> **★ 纪律**：只读查询/审计取样/格式整理可自由执行；一切写操作（保存/模板/序列/contact-add/激活）须本节点确认 + 审批凭证，否则禁止。

## 0. 全局闸门与状态转换规则（所有节点通用）

| 规则 | 内容 | 来源 |
|------|------|------|
| **流程闸门** | 流程开始前必须 `bash tools/gate_check.sh --token <TOKEN>` 全绿（token 有效 + 必读文档存在 + 规则 grep 命中）；未通过禁止任何保存/模板/序列/contact-add 操作 | `../RULES.md` L18；脚本 `../tools/gate_check.sh` |
| **节点确认** | 高影响节点必须收到**本节点明确确认**；确认原话、参数 JSON/hash、时间写入 `.local/approvals.tsv`（★审批流水：每账号/每 clone 一份，不入 Git） | `../RULES.md` L40 |
| **审批硬闸门（审批闸门(工具级)）** | 写工具 `save_first_n.py`/`gen_templates.py`/`rebuild_templates.py` 执行前必须带 `--approval <id> --project <产品>`，工具校验 `.local/approvals.tsv`（id+project+state 前缀+status∈confirmed/backfilled），无凭证/不符直接拒绝写入 exit(1)；approval_id 由确认节点用 `tools/approval.py` 的 `record()` 生成或 `flow_orchestrator.py` 输出 | `../RULES.md` L44；`../tools/approval.py` |
| **参数变化回退** | 产品、种子、临界N、标签、模板、配额任一变化 → 原确认失效 → 回到对应状态重新确认 | `../RULES.md` L42 |
| **自由执行范围** | 只读查询、格式整理、读取重试和报告可自由执行 | `../RULES.md` L43 |
| **对抗审查（每产出）** | 四类决策产出（客群分析/种子筛选/模板文案/序列配置）产出后必须空白子代理审查（清单见 RULES「操作对抗审查」）；重操作预审+确认双过；凭证=本地审查记录（不入 Git） | `../RULES.md` 操作对抗审查节 |
| **记录四件套** | 任何客群操作后同步：segments/档状态 → segments.md 索引重生成 → ops-log.tsv 追加（保存行13列必填）→ 本地客群总表重生成 | `../RULES.md` 记录体系节 |
| **ERROR_BLOCKED** | 异常/参数变化/对账不一致/规则冲突时：只读检查，禁止自动写操作 | `../RULES.md` L36 |
| **产出记录位置（统一）** | 确认流水 → `.local/approvals.tsv`；产品全程 → `runs/<运营方>/<产品>/operation-record.md + reflection.md + evidence.json + verify-*.txt + tmap.json + seq-config.json`（模板见 `runs/_template/`）；运行登记 → 本地运行记录一行（不入 Git）；问题 → 本地问题登记（不入 Git） | `../RULES.md` L121-125；`../INDEX.md` L43-57 |

---

## 1. 节点矩阵（S0-S12，每个节点照抄执行）

### S0 INPUT_GATE（闸门 + 必填输入）
- **判据（来源）**：`../RULES.md` L23「昵称 + 基础产品信息必填；缺一只询问，不写入」；`../methodology/decision-trees.md`「Gate 0」：①**昵称** ②**基础产品信息**（产品名/用途/行业/目标市场，可加卖点），缺任一 → 停、先补齐，不猜、不代填。闸门 = `check_login.py` 登录检查通过 + `gate_check.sh` 全绿。
- **通过条件**：昵称非空 + 产品信息非空 + gate_check 通过（token 有效 + `RULES.md/INDEX.md/specs/threshold-method.md/specs/domain-scale-sop.md/specs/sequence-config.md` 存在 + 4区排除/front/时序/code变量 规则 grep 命中）。昵称写入本地运营方档案 `.local/operator-profile.md`（★签名唯一源）。
- **API**：`POST /api/benefits/refine-data {}`（token 校验，返回 dailyLimit/dailyUsed 等）——API L382、L398。
- **脚本**：★第一步 `python3 tools/check_login.py --token '<T>'`（登录检查，只读；org 自动从 token 提取 web.laifaxin.com&<orgId>&<hash>；无/失效→打印官方教程引导 https://www.laifa.xin/share/ai/laifaxin-ai-account-connection ）；然后 `bash tools/gate_check.sh --token <TOKEN> [--org <orgId>]`（--org 可省略=自动提取）；可选 `python3 tools/onboard_check.py`（新会话引导）。
- **产出记录**：`.local/approvals.tsv`（S0 gate_ok 行）；本地运营方档案 `.local/operator-profile.md`。

### S1 PATH_PENDING（路径分支）
- **判据（来源）**：`../RULES.md` L24「有精准网址走快速路径；无网址走标准路径；两者都不能跳过确认」；`../methodology/decision-trees.md` 主逻辑图（A=快速/B=标准）。
- **通过条件**：路径确定 +（快速路径）确认该网址是**客户方**而非用户自己公司、相关产品、非4区（`specs/operations-sop.md`「四、网址找相似」确认原则；网址确认原则）。
- **API**：`POST /api/refine/company-list`（keyword=网址，海量搜相似）——API L54；`POST /api/domain/base-info`（提炼网址行业/NAICS）——API L57；`POST /api/domain/similar-list`（10条相似）——API L56。
- **脚本**：无独立脚本（纯分支决策，对话确认即可；`flow_orchestrator.py` 仅打印分支提示）。
- **产出记录**：对话确认；种子进入 S3。

### S2 SEGMENT_PENDING（标准路径·客群推演）
- **判据（来源）**：`../RULES.md` L25「标准路径推演默认4个；打印全部，判断是否精准潜在客户，给成交周期/询盘速度/量级/邮箱/竞争度/推荐；用户确认或要求更多」；`../RULES.md` L51 输出标准：每个客群必须写「精准潜在客户：是/否/条件成立时是」+ 六维度；`specs/operations-sop.md`「三、AI 推演固化」（选最直接买家客群，Path B 流通与代理优先）。
- **通过条件**：≥1 个客群被用户确认选用（默认4个，要更多 → 再 `inference-segment-generate` 扩到8个重新展示）。
- **API**（API L35 标注 ✅ 全部实测）：`POST /api/profile/inference-product-add`（产品档案，product_name/zh/en/desc_zh/exclusions）——API L40；`POST /api/profile/inference-segment-generate {"product_id":<id>}`——API L44；`POST /api/profile/inference-segment-list {"product_id":<id>}` → segment_name/value_path/ai_reason/query_en/query_total——API L45。
- **脚本**：无独立脚本；`python3 tools/flow_orchestrator.py ...` S2 段调用上述接口并打印（⚠️prototype，写操作须另行执行）。
- **产出记录**：`.local/approvals.tsv`（S2_客群行）；客群固化写入 `runs/<运营方>/<产品>/operation-record.md`。

### S3 SEED_PENDING（种子确认）
- **判据（来源）**：`../RULES.md` L26「展示候选种子及采购可能；用户确认后才搜相似」；`../RULES.md` L100 决策节点②选种子：候选种子+代表客户，按**精准度/邮箱率/是否会采购**展示并给建议。
- **通过条件**：用户确认种子**网址/域名**（或输入新种子）。
- **★双路径（L-45/L-46 修正版）**：① **小批量直存**——客群推演的 query_en 即搜索词，`refine/company-list {keyword:<query_en>}` 首页即高纯度买家，`save_first_n --keyword "<query_en>" --n 30` 直接保存（keyword 可为文本；★禁翻页收集 id 即铁律3，与此不冲突）；② **扩量需域名锚**——`refine/company-list` 返回项**无 domain 字段**且拿公司名搜相似会命中同名异司；但 **`domain/similar-list`（域名找相似，10条/页可翻页）每条结果自带 domain** → 浏览相似列表挑中哪家直接用其 domain 做锚，**无需名字反查**；`seed_resolve.py --company` 仅在手头只有公司名时兜底。
- **API**：`POST /api/search/company-search`（精确找单家拿域名，keyword/keyword_fields/current/pageSize）——API L55；`POST /api/refine/company-list`（展示候选列表）——API L54。
- **脚本**：`python3 tools/seed_resolve.py --company "<候选公司名>"`（反查真实域名，同名多司列出选；只读）——S3 候选确认前必跑；`flow_orchestrator.py` S3 打印候选 + stdin 确认。
- **产出记录**：`.local/approvals.tsv`（S3_种子行）；种子记 `runs/<运营方>/<产品>/operation-record.md`（须含域名）。

### S4 AUDIT_RUNNING（临界审计——★判据核心 = AI 反思）
- **判据（来源）**：`../RULES.md` L27「只读搜客和AI语义审计；50页跳→三页平均→逐页→跌破往前；未完成不能保存」；`specs/threshold-method.md` 全文：**判定标准 = AI 语义反思「这个外贸 B 端客户会不会买我的产品？能买=匹配」**（L19-27，★不是关键词匹配）；50页一跳全局（L30-36）→ 三页滑动平均 ≥70%（L38-44）→ 临界附近逐页精确到1页（L46-48）→ **一旦某页/三页平均跌破70%就【往前找】，不看后面**（L50-53）→ 工具只做趋势初筛、**临界页必须人工逐条读完整10条**（L55-58）；阈值默认 70%（`specs/marketing-rules-2.0.md` L21-27：中等默认70%，严格80/宽松60 需用户指定）。
- **通过条件**：得出临界页 N（=从前往后最后一张≥70%的页；AI 反思 + 人工读两两印证一致）；保存范围 = 前N页 = N×10 条。审计未完成**不能保存**。
- **API**：`POST /api/refine/company-list {"keyword":<种子>,"current":<页>,"pageSize":10,"filters":[],"logic":"and"}`——API L54。
- **脚本**（⚠️全部是词匹配初筛，**只做趋势参考，不可信**，结论必须 AI/人工语义判断，`specs/threshold-method.md` L81-86）：
  - `python3 tools/audit_company.py --query <种子> --pages 1,50,100,...,1000 --token $TOKEN --org <orgId> --mode strict --product <产品> --match-words "<产品词,中英文>"`
  - `python3 tools/find_threshold.py --query <种子> --token $TOKEN --org <orgId> --match-words "..." --start 100 --end 500 --threshold 70`
  - `python3 tools/find_critical.py --query <种子> --token $TOKEN --org <orgId> --match-words "..." --start 1 --end 1000 --threshold 70 --step 50`
  - ★核心判定（AI 反思逐条读描述）无脚本——由 AI 本体/独立 subagent 逐条推理 + 人工读，两两印证（L-26）。
- **产出记录**：`runs/<运营方>/<产品>/operation-record.md`（50页跳/三页平均/逐页精确表格 + 临界页结论）；临界 N 提交 S5 确认。

### S5 SAVE_PENDING（保存参数确认）
- **标签准备（⓪/S5 前置，冷启动审查补）**：`python3 tools/tag_add.py --token <T> --org <orgId> --name "<客户群体中文名>" --type company|contacts --approval <S2/S5凭证> --project <产品>`（同名自动复用不重复建；--list 先查现有）；产出格式 `id(名称)` 直接用于 save_first_n 的 --company-tag/--contact-tag。
- **点数余额**：`python3 tools/check_login.py --token <T>`（输出含 日/月配额已用——无需另查 refine-data）。
- **判据（来源）**：`../RULES.md` L28「展示临界、前N、排除、max、重复保存检查和点数；用户确认后才保存」；**防重复保存** `../RULES.md` L73：保存前查该 (keyword+seed+阈值+selectTotal+排除4区) 是否曾完成保存（用完成标志/最近成功task），已保存则不重存；点数预算 `specs/operations-sop.md`「六、点数预算公式」：可存公司数 = min(点数×60% ÷ (1.5×3), 30000)；max 默认 3（阶梯 3→6→9，`specs/marketing-rules-2.0.md` L60-63）。
- **通过条件**：向用户展示 临界N / 前N条数 / 标签（公司+联系人，★记录一律 id(名称) 成对，`../RULES.md` L66）/ 排除4区 CN,TW,HK,MO / max3 / 点数余额 → 用户明确「确认保存 前N=...」。
- **API**：`POST /api/refine/company-save`（完整 payload：selectKeys:[]、selectTotal:N、**selectOption:"front"**、contactMaxCount:3、filters=4区 exclude schema `{"property":"country_code","operator":"exclude","value":"","values":["CN","TW","HK","MO"],"valueType":"select"}`）——API L96-129；`POST /api/benefits/refine-data`（点数）——API L382；`POST /api/clues/company-save-list`（查保存任务历史/防重）——API L93。
- **脚本**：`python3 tools/save_first_n.py --token $TOKEN --org <orgId> --keyword <种子> --n <前N条数> --company-tag <公司标签id> --contact-tag <联系人标签id> --max 3 --approval <ap-id> --project <产品>`（★内置 `--approval` 硬闸门 + 默认 `--exclude CN,TW,HK,MO`）。
- **⚠️ 缺口**：防重复保存检查**无脚本落地**（RULES 有规则、save_first_n 无已存检查，防重复保存缺口 open）→ 执行前人工查 `company-save-list`/最近成功 task 判断是否已存过。
- **产出记录**：`.local/approvals.tsv`（S5_保存行）；保存返回的 task id 记 `operation-record.md`（供 S6 轮询）。

### S6 SAVE_RUNNING（保存执行 + 时序等待）
- **判据（来源）**：`../RULES.md` L29「front保存；等任务finished；用标签结果对账」；`../RULES.md` L76-82 任务类型对照（保存=查 `operation/backend-task-status` `{"type":"cluesSave","id":<task id>}`，**不是** company-save-list）；邮箱提取异步（`specs/domain-scale-sop.md` L163-167 / L-16）；对账口径=**标签联系人数**，非 contactSaveCount（对账口径差异）。
- **通过条件**：backend-task-status `status:"finished"` + 记录 contactSaveCount/companySaveCount + 标签联系人>0（对账一致）。
- **API**：`POST /api/operation/backend-task-status {"type":"cluesSave","id":<task id>}` → status/finished/total/contactSaveCount——API L131-133、L387；`POST /api/contacts/contacts/show`（标签人数）——API L163、L356。
- **脚本**：`python3 tools/wait_save_done.py --token $TOKEN --org <orgId> --task <保存任务id> --tag <联系人标签id> --timeout 900`（等 finished + 校验标签联系人>0 双闸，失败 exit 1）。
- **产出记录**：`operation-record.md`（task id、contactSaveCount、标签人数）；本地运行记录（不入 Git）一行。

### S7 TEMPLATE_PENDING（模板草稿预览）
- **判据（来源）**：`../RULES.md` L30「只生成本地草稿；展示3-8个跨轮模板（★渲染后的收件人视图效果，非HTML源码——用 tools/render_preview.py）+理由；用户确认后才批量创建」；`../RULES.md` L52 模板展示标准：标题不插变量；正文变量保留编辑器完整 code 样式；有客户实际参数必须照用，无信息才用行业合理值；`specs/sequence-config.md`：变量必须 `<code class="lfxFieldVeriable" contenteditable="false">{联系人:名称}</code>` 包裹（L58-64）、标题纯文案（L66-67）、结合客户实际信息+买者视角（L70-74）。
- **通过条件**：3-8 个**跨轮代表**模板以【渲染后收件人视图】展示 + 每模板理由 → 用户确认。（用户说"不用看"可豁免展示，**不豁免确认**，`../RULES.md` L43。）
- **API**（本节点不创建，只取详情）：`POST /api/mailbox/template-info {"id":<id>}`——API L190。
- **脚本**：`python3 tools/gen_templates.py --token <T> --org <orgId> --product <产品> --prefix "英-<产品>-" --suffix -RT --name <昵称> --preview`（打印 5 个跨轮渲染草稿，不创建）；单封渲染 `python3 tools/render_preview.py --html "<p>Hi <code class=\"lfxFieldVeriable\" contenteditable=\"false\">{联系人:名称}</code>,...</p>" [--name John]`。
- **产出记录**：`.local/approvals.tsv`（S7_模板预览行）；草稿在对话展示。

### S8 TEMPLATE_BUILD（批量创建 + 差异实测）
- **判据（来源）**：`../RULES.md` L31「创建后断言变量样式、标题、正文差异、轮次绑定；失败回S7」；`specs/sequence-config.md` L76-79 ★诚实口径：**"差异≥30%"不得声称达标**——12轮方向互异是硬保证，但同轮变体必须生成后跑 `check_template_diff.py` 实测（Jaccard>0.70=违例）；重建顺序铁律与引用锁（L-43：名称唯一/被序列引用不可删/至少保留1步/step 非空模板）。
- **通过条件**：120 模板全部创建成功 + 每个 id 为完整 24hex（断言失败 exit 1）+ `check_template_diff.py` 实测两两相似度≤0.70 + name→id 映射落盘；任一失败 → 回 S7。
- **API**：`POST /api/mailbox/template-add {"name":...,"foid":"0","subject":...,"html":...}`——API L191、L201-205；`POST /api/mailbox/templates-list`（注意：list 项**不含 html**，只有 subject——取正文必须再调 template-info）——API L189；`POST /api/mailbox/template-info`——API L190；`POST /api/mailbox/template-delete {"id":<id>}`（单删；`templates-delete` 批量 500 勿用）——API L193。
- **脚本**：
  - `python3 tools/gen_templates.py --token <T> --org <orgId> --product <产品> --prefix "英-<产品>-" --suffix -RT --name <昵称> --out <映射路径> --approval <ap-id> --project <产品>`（12轮×10=120；内置 24hex 断言；`--out` 落盘 name→id 映射）
  - `python3 tools/check_template_diff.py --token <T> --org <orgId> --prefix "英-<产品>-" --limit 120`（逐模板 template-info 取真实 html 算 Jaccard，>0.70 列违例对 exit 1）
  - 重建场景 `python3 tools/rebuild_templates.py --token <T> --org <orgId> --product <产品> --prefix ... --suffix -RT --seq <seqId> --name <昵称> --approval <ap-id> --project <产品> [--dry-run]`（⚠️prototype，实操曾失败，正确顺序见 docstring ①-⑧，建议人工分步）
- **产出记录**：name→id 映射（`--out`，建议 `runs/<运营方>/<产品>/tmap.json`）；差异实测 `verify-diff.txt`；`.local/approvals.tsv`（S7/S8 行）。

### S9 SEQUENCE_PENDING（序列配置确认）
- **判据（来源）**：`../RULES.md` L32「展示12步(30分/5/15/30天)、时区(★默认纽约)、单日30000/单家5、notSentTags=[询盘,不发]；用户确认后建序列」；`specs/sequence-config.md`：12轮方向每轮不同（L22-40）、步长 step1=minute/30、step2=day/5、step3=day/15、step4-12=day/30（L46-49）、★纽约 schedule_id **运行时解析**（`tools/resolve_schedule.py --tz "America/New_York"`；各账号不同,勿硬编码——L43-44）、max_emails_per_day:30000 / domain_emails_per_day:5 / notSentTags=[<tagId>(询盘), <tagId>(不发)]（L50-53）、命名 `[产品]-[语言]-[轮数]轮[每轮封数]封-[策略]`（L55-56）、每步 10 个**互不相同**模板（L38-40）。
- **通过条件**：用户确认序列配置（12步+纽约+30000/5+notSentTags+每步10个不同模板 id）。
- **脚本**：`python3 tools/build_sequence.py --token <T> --org <orgId> --name <序列名> --tmap runs/<运营方>/<产品>/tmap.json --from-name <昵称> --tz "America/New_York" --approval <S9凭证> --project <产品>`（★tz/notSentTags 运行时按名解析,各账号id不同;自动12步;实测验证）
- **API**（§10 全部实测）：`POST /api/sequences/sequence-create {"name":...,"channel":"system"}`——API L260；`POST /api/sequences/step-create {"seqId":<id>,"step":<n>,"template_ids":[...],"wait_mode":...,"wait_time":...,"senders":[...]}`——API L273、L279-289；`POST /api/sequences/sequence-save {id,name,schedule_id,others,rules}`——API L261、L291-303；`POST /api/settings/sequence/schedule-list`——API L267；`POST /api/settings/sequence/schedule-default {"id":<schedule_id>}`——API L399（id 运行时解析,勿硬编码）。
- **脚本**：★`python3 tools/build_sequence.py --token <T> --org <orgId> --name <序列名> --tmap runs/<运营方>/<产品>/tmap.json --from-name <昵称> --approval <S9凭证> --project <产品>`（见上 L110——缺脚本旧缺口已闭环, 审批闸门(工具级)/47）。
- **产出记录**：`.local/approvals.tsv`（S9_序列配置行）；`runs/<运营方>/<产品>/seq-config.json`；序列 id 记 `operation-record.md`。

### S10 CONTACT_PENDING（时序守卫 + contact-add）
- **判据（来源）**：`../RULES.md` L33「保存finished、标签联系人>0、序列inactive、人数对账且用户确认后才contact-add」；铁律⑥ `../RULES.md` L65（等 finished+标签联系人>0，否则 add 0）；L-01：`views` 必须传**空数组 `[]`**（传 `["all"]` 会把全部 139 万联系人加入）。
- **通过条件**：`wait_save_done.py` 双校验通过（finished + 标签联系人>0）+ 序列 inactive + 人数对账一致 + 用户确认。
- **API**：`POST /api/sequences/contact-add {"seqId":<id>,"tags":[<联系人标签id>],"views":[]}`——API L309（★views 必须 `[]`）；`POST /api/sequences/contact-list`——API L308；`POST /api/contacts/contacts/show`（标签人数）——API L163、L356。
- **脚本**：★一条龙= `python3 tools/contact_add.py --token <T> --org <orgId> --seq <seqId> --tags <联系人标签id> --task <保存任务id> --approval <S10凭证> --project <产品>`（内置时序守卫 finished+标签>0 + `views:[]` 铁律 + add 数核对；--dry-run 可预演）；单独守卫也可用 `wait_save_done.py`。
- **产出记录**：`.local/approvals.tsv`（S10_加联系人行）；`operation-record.md` 记 add 人数；`evidence.json`（contacts_total）。

### S11 READY_INACTIVE（终检 + 待确认）
- **判据（来源）**：`../RULES.md` L34「输出完整流程和参数；测试保持inactive，等待用户确认」；`../RULES.md` L74 **测试不激活（★用户强制）**：流程跑完→发完整流程待确认，**不激活序列**；`../RULES.md` L53 完成输出标准（完整流程/task id/实际数量/模板序列映射和问题）。
- **通过条件**：`verify_sequence.py` 终检全过（12步+24hex+步长 30分/5/15/30天）+ `verify_exclude.py` 抽验4区 + 向用户输出完整流程与参数；序列保持 **inactive**。
- **API**：`POST /api/sequences/sequence-details {"id":<seqId>}`——API L259；`POST /api/sequences/sequence-count`——API L258；`POST /api/sequences/sequence-list`——API L257。
- **脚本**：
  - `python3 tools/verify_sequence.py --token <T> --org <orgId> --seq <序列id>`（激活前硬闸门，断言 12 步+24hex+步长，失败 exit 1）
  - `python3 tools/verify_exclude.py --token <T> --org <orgId> --keyword <种子> --pages 1,2,3,50,100,200`（4区抽验；⚠️proxy=company-list 非保存结果，见 docstring）
  - ⚠️ **测试不激活约束 open**：测试不激活无技术封锁（可直接调 sequence-active），目前仅规则约束。
- **产出记录**：`.local/approvals.tsv`（S11 ready_inactive 行）；`runs/<运营方>/<产品>/evidence.json + verify-seq.txt + verify-exclude.txt`；本地运行记录 status=inactive/SEQ-READY（不入 Git）。

### S12 ACTIVE（仅用户明确确认 + 发送前检查）
- **判据（来源）**：`../RULES.md` L35「仅明确"确认激活/激活序列<名称>"才激活（★SPF/DKIM/退订等"发送前检查"=禁止项）」；★2026-08-31 用户拍板：SPF/DKIM/DMARC 认证与退订/合规检查**禁止执行**（发信走平台系统通道，域名/IP/认证/退订均属来发信平台职责，运营方不做、不要求、不阻塞激活）；内部整改清单（未随库分发）P0-1/P0-2 作废。激活时仅做：目标序列 id 逐字核对（防误激 legacy）+ notSentTags/上限等序列规则已由 verify 断言。
- **通过条件**：用户明确正向命令（「确认激活」/「激活序列<名称>」）+ （★SPF/DKIM/退订=禁止项，平台职责）+ verify_sequence 已过。禁止自行激活。
- **API**：`POST /api/sequences/sequence-active {"id":<seqId>,"active":true}`——API L262。✅ **已实测恢复**（曾 500，2026-09-02 实证 success+回读 active，见 L-47）；仍须**回读验证**防假成功。
- **脚本**：`tools/activate_sequence.py`（激活+回读 status:active 防假；--status 只读查；须 S12 审批+用户原话含"激活"）。★空序列测完激活后**须回滚 inactive**（防后续加联系人即真发）；激活必须仅用户明确"确认激活"后执行。
- **产出记录**：`.local/approvals.tsv`（激活确认行）；本地运行记录 status→active（不入 Git）。

### ERROR_BLOCKED（异常兜底）
- **判据（来源）**：`../RULES.md` L36「异常、参数变化、对账不一致或规则冲突时，只读检查，禁止自动写操作」；参数变化回退 `../RULES.md` L42。
- **脚本**：`bash tools/check_rules.sh --token <TOKEN>`（AI 自查 token/规则/问题）。
- **产出记录**：本地问题登记（不入 Git）；修复后重跑 `gate_check.sh`。

---

## 2. 易漏判据专项（★这 7 条最容易被 AI 跳过，逐条核对）

| # | 易漏点 | 判据原文要点 | 来源 |
|---|--------|-------------|------|
| 1 | **S0 闸门硬条件** | 昵称+基础产品信息必填，缺一只询问不写入；且必须 `gate_check.sh` 通过（token 有效+必读文档存在+规则命中）才能开始流程 | `../RULES.md` L18/L23；`../methodology/decision-trees.md` Gate0 |
| 2 | **S2 客群推荐维度** | 每个客群写「精准潜在客户：是/否/条件成立时是」并给成交周期/询盘速度/量级/邮箱可得/竞争度/推荐；只打印不代选 | `../RULES.md` L25/L51/L94 |
| 3 | **S4 临界判定** | 判定=AI 反思「会不会买」语义推理，**不是关键词匹配**；工具词匹配只做趋势初筛；50页跳→三页平均→逐页→跌破往前；临界页人工逐条读完整10条 | `specs/threshold-method.md` L19-27/L50-58；L-26 |
| 4 | **S5 保存前重复检查** | 保存前查 (keyword+seed+阈值+selectTotal+排除4区) 是否曾完成保存，已存则不重存（省额度）——★规则有、脚本缺（防重复保存缺口） | `../RULES.md` L73 |
| 5 | **S7 模板草稿预览+差异实测** | 只生成草稿；展示的是**渲染后收件人视图**（render_preview.py），非 HTML 源码；"差异≥30%"**不得声称达标**，生成后必须 check_template_diff.py 实测（>0.70=违例） | `../RULES.md` L30；`specs/sequence-config.md` L76-79；L-43/模板差异实测（工具级） |
| 6 | **S10 时序守卫** | 必须等保存任务 `status:finished` + 标签联系人>0 才 contact-add；且 `views:[]`（永不 `["all"]`）；人数对账+用户确认 | `../RULES.md` L33/L65；L-01/L-32 |
| 7 | **S11/S12 激活判据** | 测试跑完**不激活**（inactive 待确认）；仅用户明确「确认激活/激活序列<名称>」+（★SPF/DKIM/退订=禁止项，平台职责）才激活；禁止自行激活 | `../RULES.md` L34-35/L74；内部整改清单（未随库分发） |

---

## 3. 缺口清单（本次完整性审查结论）

### 判据缺口：无
- S0-S12 全部节点的判据/通过条件在 `RULES.md`（唯一真源）+ specs 中有明确条文，未发现"无判据"节点。S1 分支判定、ERROR_BLOCKED 为规则性节点，判据充分。

### 脚本/工具缺口（按节点）
| 节点 | 缺口 | 依据 | 当前替代 |
|------|------|------|---------|
| S5 | 防重复保存检查无脚本（规则在 RULES L73，save_first_n 无已存检查） | 防重复保存缺口 open | 人工查 `clues/company-save-list`/最近成功 task |
| S9 | ~~建序列无专用脚本~~ ✅ 已补 `tools/build_sequence.py`（tz/notSentTags 运行时按名解析+12步；实测验证 2026-08-30） | 审批闸门(工具级)/新手门槛整改(工具级) | — |
| S10 | ~~contact-add 无专用脚本~~ ✅ 已补 `tools/contact_add.py`（时序守卫+views:[] 铁律+add 数核对） | 审批闸门(工具级)/新手门槛整改(工具级) | — |
| S11/S12 | 测试不激活无技术封锁（可直接调 sequence-active） | 测试不激活约束 open | 仅规则约束 + 人工守 |
| S12 | 激活接口 sequence-active 曾 500 | 已恢复(2026-09-02 实证) | 走 activate_sequence.py(激活+回读防假) |
| 全局 | gate_check.sh 仅 grep 字符串存在性检查，不拦功能缺陷 | 闸门检查局限 open | 人工核验工具真排除 |
| S1/S2/S3 | 无独立脚本（决策/展示节点；flow_orchestrator.py 原型部分覆盖） | `../db/tools.tsv` flow_orchestrator=prototype | 对话确认 + 手工 API |

### API 缺口
- S12 `sequence-active`：✅ 已实测恢复（曾 500，2026-09-02 实证，见 L-47）；激活走 `tools/activate_sequence.py`（回读防假）。其余 S0-S11 所需接口在 api-reference 均有实测说明（见矩阵各节点行号）。

### 已知不一致（供修复参考，本表已按实测为准）
- 时序校验接口：L-32 写 `contacts/contacts-count`，但 `tools/wait_save_done.py` 实际用 `contacts/contacts/show` 的 total（api-reference 收录的也是 show 而非 count）——执行以工具/API 实测为准。
