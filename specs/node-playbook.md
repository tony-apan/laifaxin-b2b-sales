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
| **审批硬闸门（工具级）** | 新项目稳定键=`<operator_key>/<product_key>`，确认参数同时绑定当前 product-profile path/version/hash；legacy 项目可暂用旧产品名但不得跨运营方复用。写工具无有效 approval 或项目键不符直接 exit 1；换机历史 approvals 只作审计，未执行写节点与 S12 必须当前对话重新确认 | `../RULES.md` 状态转换与确认；`../tools/approval.py` |
| **参数变化回退** | 产品、种子、临界N、标签、模板、配额任一变化 → 原确认失效 → 回到对应状态重新确认 | `../RULES.md` L42 |
| **自由执行范围** | 只读查询、格式整理、读取重试和报告可自由执行 | `../RULES.md` L43 |
| **对抗审查（每产出）** | 四类决策产出（客群分析/种子筛选/模板文案/序列配置）产出后必须空白子代理审查（清单见 RULES「操作对抗审查」）；重操作预审+确认双过；凭证=本地审查记录（不入 Git） | `../RULES.md` 操作对抗审查节 |
| **记录四件套** | 任何客群操作后同步：segments/档状态 → segments.md 索引重生成 → ops-log.tsv 追加（保存行13列必填）→ 本地客群总表重生成 | `../RULES.md` 记录体系节 |
| **ERROR_BLOCKED** | 异常/参数变化/对账不一致/规则冲突时：只读检查，禁止自动写操作 | `../RULES.md` L36 |
| **产出记录位置（统一）** | 确认流水 → `.local/approvals.tsv`；产品全程 → `runs/<运营方>/<产品>/operation-record.md + reflection.md + evidence.json + verify-*.txt + tmap.json + seq-config.json`（模板见 `runs/_template/`）；运行登记 → 本地运行记录一行（不入 Git）；问题 → 本地问题登记（不入 Git） | `../RULES.md` L121-125；`../INDEX.md` L43-57 |

---

## 1. 节点矩阵（S0-S12，每个节点照抄执行）

### S0 INPUT_GATE + S0a PRODUCT_PROFILE（闸门 + 必填输入 + 产品知识档案）
- **判据（来源）**：`../RULES.md` S0「开跑只问 token + 纯个人昵称 + 一句话产品；禁止开局列清单」。之后进入 S0a：按 `product-profile-sop.md`，用户给官网/目录/卖点就由 AI 读取提炼；没给则 AI 主动要一次（给填空模板、可跳过、不逼问）。公司名/官网/邮箱/认证/产能/MOQ/交期/价格带等**用户自己的商业资产可以主动要**；潜在买家/客户/联系人联系方式等第三方信息不索要。
- **签名与正文边界**：邮件末尾签名区**只能是纯个人昵称**；公司身份/官网/联系邮箱不进入签名。`product-profile.md` 中经用户确认且有字段级来源的认证、产能、MOQ、交期、价格带可用于正文卖点；无来源或仅为推断的具体事实不得写进正文。
- **通过条件**：①环境 bootstrap check 全绿 ②昵称通过 `profile_utils.validate_nickname` ③token 登录检查 + gate_check 通过 ④项目目录 `runs/<operator_key>/<product_key>/` 已固定 ⑤product-profile 存在且状态为 `confirmed` 或 `declined`（draft 禁止进入 S2）；confirmed 记录 path+content hash，declined 仅允许通用无具体事实文案。
- **脚本顺序**：无 Python 时先 `bash tools/bootstrap.sh --install`（macOS/Linux/Git Bash/WSL）或 `powershell -ExecutionPolicy Bypass -File tools/bootstrap.ps1 -Install`（Windows PowerShell）→ `python3|py tools/onboard_check.py` → `python3|py tools/product_profile.py init ...` → AI 按模板/SOP 填档 → `python3|py tools/product_profile.py confirm --profile ... --by <纯昵称> --quote '<用户确认原话>'` → `python3|py tools/check_login.py --token '<T>'` → `bash tools/gate_check.sh --token '<T>' --product <项目键>` → `python3|py tools/flow_orchestrator.py --profile <档案路径> ...`。
- **产出记录**：`.local/operators/<operator_key>.md`（nickname/operator_key，不含 token）；`runs/<operator_key>/<product_key>/product-profile.md`（状态/版本/hash/字段级来源/变更记录）；`.local/approvals.tsv`（S0 gate_ok + profile hash）。

### S1 PATH_PENDING（路径分支）
- **判据（来源）**：`../RULES.md` L24「有精准网址走快速路径；无网址走标准路径；两者都不能跳过确认」；`../methodology/decision-trees.md` 主逻辑图（A=快速/B=标准）。
- **通过条件**：路径确定 +（快速路径）确认该网址是**客户方**而非用户自己公司、相关产品、非4区（`specs/operations-sop.md`「四、网址找相似」确认原则；网址确认原则）。
- **API**：`POST /api/refine/company-list`（keyword=网址，海量搜相似）——API L54；`POST /api/domain/base-info`（提炼网址行业/NAICS）——API L57；`POST /api/domain/similar-list`（⚠️已弃用——统一走 refine/company-list keyword=域名）——API L56。
- **脚本**：无独立脚本（纯分支决策，对话确认即可；`flow_orchestrator.py` 仅打印分支提示）。
- **产出记录**：对话确认；种子进入 S3。

### S2 SEGMENT_PENDING（标准路径·客群推演）
- **判据（来源）**：`../RULES.md` L25「标准路径推演默认4个；打印全部，判断是否精准潜在客户，给成交周期/询盘速度/量级/邮箱/竞争度/推荐；用户确认或要求更多」；`../RULES.md` L51 输出标准：每个客群必须写「精准潜在客户：是/否/条件成立时是」+ 六维度；`specs/operations-sop.md`「三、AI 推演固化」（选最直接买家客群，Path B 流通与代理优先）。
- **通过条件**：≥1 个客群被用户确认选用（默认4个，要更多 → 再 `inference-segment-generate` 扩到8个重新展示）。
- **API**（API L35 标注 ✅ 全部实测）：`POST /api/profile/inference-product-add`（产品档案，product_name/zh/en/desc_zh/exclusions）——API L40；`POST /api/profile/inference-segment-generate {"product_id":<id>}`——API L44；`POST /api/profile/inference-segment-list {"product_id":<id>}` → segment_name/value_path/ai_reason/query_en/query_total——API L45。
- **脚本**：无独立脚本；`python3 tools/flow_orchestrator.py ...` S2 段调用上述接口并打印（⚠️prototype，写操作须另行执行）。
- **产出记录**：`.local/approvals.tsv`（S2_客群行）；客群固化写入 `runs/<运营方>/<产品>/operation-record.md`。

> ★S0 产品画像交互：AI 先出 A/B/C/D 客群/画像方案（每项含组合内容/买家纯度/邮箱可达/推荐与淘汰理由），用户回复字母或组合，或自由填写覆盖——**方案化优先于开放式提问**（新手常说不清画像）。

### S3 SEED_PENDING（种子确认）
- **判据（来源）**：`../RULES.md` L26「展示候选种子及采购可能；用户确认后才搜相似」；`../RULES.md` L100 决策节点②选种子：候选种子+代表客户，按**精准度/邮箱率/是否会采购**展示并给建议。
- **通过条件**：用户确认种子**网址/域名**（或输入新种子）。
- **★AI 数据库搜索链（3步，2026-09-03 用户拍板；禁用 domain/similar-list 作为主流程）**：
  1) **预览**：客群 query_en 作关键词 → `refine/company-list {keyword:<query_en>}` 默认第一页 10 条（含 id/公司名/国家/角色/NAICS/客户类型/置信度/邮箱数/电话/社媒/摘要/匹配分；列表项无 domain）。若首页质量差 → 改关键词或换客群。
  2) **取域名**：挑代表买家 → 结果 `id` 调 `domain/base-info {"domain":<id>}` → 真实域名+详情（`tools/seed_resolve.py --id`；`--company` 仅兜底）。
  3) **扩量**：域名作 keyword 继续走 `refine/company-list` 主搜索 → 用户确认锚点后进入 S4 审计。
  随后由 S4 找名单筛选边界；S5/S6 按审计所用 keyword 保存前 N（域名/长文本 keyword 均已实测：保存与列表同批）。勿拿公司名当锚；禁翻页收集 id（铁律3）。
- **API**：`POST /api/refine/company-list`（预览/扩量）+ `POST /api/domain/base-info`（id→真实域名/详情）；`search/company-search` 仅兜底精确查单家。
- **脚本**：`tools/seed_resolve.py --id <结果id>`（主）/ `--keyword "<query_en>"`（全览）/ `--company`（仅兜底）；`flow_orchestrator.py` S3 打印候选 + stdin 确认。
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
- **产出记录**：审计证据 + 独立 review 均落项目目录；`audit-manifest.json` 绑定 project/profile_sha256/seed/generated_at 与两文件path+sha256+pass；运行 `finalize_audit.py --record ... --profile ... --project <key> --manifest .../audit-manifest.json` 推进S4。

### S5 SAVE_PENDING（保存参数确认）
- **标签准备**：先 `tag_add.py --list` 只读查重；创建时须 `--profile .../product-profile.md --project <operator_key>/<product_key>`，用 `approval.py grant` 按 `{project,profile,tag{name,type}}` 实际参数签发绑定凭证。
- **点数余额**：`check_login.py --token <T>`（只读）。
- **通过条件**：展示临界N/前N/公司与联系人标签id(名称)/排除4区/max/点数 → 用户当前对话明确确认；flow只记录pending，标签和保存实际参数齐后分别grant。
- **保存脚本**：`save_first_n.py --keyword <种子> --n <N> --company-tag <id> --contact-tag <id> --max 3 --profile runs/<operator_key>/<product_key>/product-profile.md --record .../operation-record.md --approval <绑定凭证> --project <operator_key>/<product_key>`；工具按完整实际参数重算hash，成功推进S5。
- **⚠️ 缺口**：防重复保存检查**无脚本落地**（RULES 有规则、save_first_n 无已存检查，防重复保存缺口 open）→ 执行前人工查 `company-save-list`/最近成功 task 判断是否已存过。
- **产出记录**：`.local/approvals.tsv`（S5_保存行）；保存返回的 task id 记 `operation-record.md`（供 S6 轮询）。

### S6 SAVE_RUNNING（保存执行 + 时序等待）
- **判据（来源）**：`../RULES.md` L29「front保存；等任务finished；用标签结果对账」；`../RULES.md` L76-82 任务类型对照（保存=查 `operation/backend-task-status` `{"type":"cluesSave","id":<task id>}`，**不是** company-save-list）；邮箱提取异步（`specs/domain-scale-sop.md` L163-167 / L-16）；对账口径=**标签联系人数**，非 contactSaveCount（对账口径差异）。
- **通过条件**：backend-task-status `status:"finished"` + 记录 contactSaveCount/companySaveCount + 标签联系人>0（对账一致）。
- **API**：`POST /api/operation/backend-task-status {"type":"cluesSave","id":<task id>}` → status/finished/total/contactSaveCount——API L131-133、L387；`POST /api/contacts/contacts/show`（标签人数）——API L163、L356。
- **脚本**：`wait_save_done.py --task <id> --tag <联系人标签id> --record runs/<operator_key>/<product_key>/operation-record.md --timeout 900`；finished+标签>0 后自动推进S6，否则保持S5。
- **产出记录**：`operation-record.md`（task id、contactSaveCount、标签人数）；本地运行记录（不入 Git）一行。

### S7 TEMPLATE_PENDING（模板草稿预览）
- **判据（来源）**：`../RULES.md` S7 + `product-profile-sop.md`：只生成本地草稿；展示3-8个跨轮模板的渲染后收件人视图+理由；用户确认后才批量创建。邮件末尾签名区只含纯个人昵称。正文具体事实必须来自当前已确认 product-profile 的字段级来源；declined 档案只允许不含数字/认证/交期/价格承诺的通用表达。
- **通过条件**：3-8 个**跨轮代表**模板以【渲染后收件人视图】展示 + 每模板理由 → 用户确认。（用户说"不用看"可豁免展示，**不豁免确认**，`../RULES.md` L43。）
- **API**（本节点不创建，只取详情）：`POST /api/mailbox/template-info {"id":<id>}`——API L190。
- **脚本**：`gen_templates.py --token <T> --org <org> --product <产品> --profile .../product-profile.md --plan <计划JSON> --prefix "英-<产品>-" --suffix -RT --name <纯昵称> --record .../operation-record.md --project <operator_key>/<product_key> --preview`；预览成功推进S7但不写平台。
- **产出记录**：`.local/approvals.tsv`（S7_模板预览行）；草稿在对话展示。

### S8 TEMPLATE_BUILD（批量创建 + 差异实测）
- **判据（来源）**：`../RULES.md` L31「创建后断言变量样式、标题、正文差异、轮次绑定；失败回S7」；`specs/sequence-config.md` L76-79 ★诚实口径：**"差异≥30%"不得声称达标**——12轮方向互异是硬保证，但同轮变体必须生成后跑 `check_template_diff.py` 实测（Jaccard>0.70=违例）；重建顺序铁律与引用锁（L-43：名称唯一/被序列引用不可删/至少保留1步/step 非空模板）。
- **通过条件**：120 模板全部创建成功 + 每个 id 为完整 24hex（断言失败 exit 1）+ `check_template_diff.py` 实测两两相似度≤0.70 + name→id 映射落盘；任一失败 → 回 S7。
- **API**：`POST /api/mailbox/template-add {"name":...,"foid":"0","subject":...,"html":...}`——API L191、L201-205；`POST /api/mailbox/templates-list`（注意：list 项**不含 html**，只有 subject——取正文必须再调 template-info）——API L189；`POST /api/mailbox/template-info`——API L190；`POST /api/mailbox/template-delete {"id":<id>}`（单删；`templates-delete` 批量 500 勿用）——API L193。
- **脚本**：
  - `python3|py tools/gen_templates.py --token <T> --org <orgId> --product <产品> --profile runs/<operator_key>/<product_key>/product-profile.md --plan <计划JSON> --prefix "英-<产品>-" --suffix -RT --name <纯昵称> --out runs/<operator_key>/<product_key>/tmap.json --record runs/<operator_key>/<product_key>/operation-record.md --approval <ap-id> --project <项目键>`（全部成功后自动推进S8；签名/profile/claims/id硬校验）
  - `python3 tools/check_template_diff.py --token <T> --org <orgId> --prefix "英-<产品>-" --limit 120`（逐模板 template-info 取真实 html 算 Jaccard，>0.70 列违例对 exit 1）
  - 重建场景：按 `rebuild_templates.py` docstring 分别铸造“建新模板”与“重建序列步骤”两份绑定凭证，命令必带 `--profile --plan --record --gen-approval --approval --project <operator_key>/<product_key>`；仅inactive序列可重建，12步回读全指向新模板后才删旧模板。
- **产出记录**：name→id 映射（`--out`，建议 `runs/<运营方>/<产品>/tmap.json`）；差异实测 `verify-diff.txt`；`.local/approvals.tsv`（S7/S8 行）。

### S9 SEQUENCE_PENDING（序列配置确认）
- **判据（来源）**：`../RULES.md` L32「展示12步(30分/5/15/30天)、时区(★默认纽约)、单日30000/单家5、notSentTags=[询盘,不发]；用户确认后建序列」；`specs/sequence-config.md`：12轮方向每轮不同（L22-40）、步长 step1=minute/30、step2=day/5、step3=day/15、step4-12=day/30（L46-49）、★纽约 schedule_id **运行时解析**（`tools/resolve_schedule.py --tz "America/New_York"`；各账号不同,勿硬编码——L43-44）、max_emails_per_day:30000 / domain_emails_per_day:5 / notSentTags=[<tagId>(询盘), <tagId>(不发)]（L50-53）、命名 `[产品]-[语言]-[轮数]轮[每轮封数]封-[策略]`（L55-56）、每步 10 个**互不相同**模板（L38-40）。
- **通过条件**：用户确认序列配置（12步+纽约+30000/5+notSentTags+每步10个不同模板 id）。
- **脚本**：`python3|py tools/build_sequence.py --token <T> --org <orgId> --name <序列名> --tmap runs/<operator_key>/<product_key>/tmap.json --profile .../product-profile.md --record .../operation-record.md --from-name <纯昵称> --tz "America/New_York" --approval <S9凭证> --project <operator_key>/<product_key>`。
- **API**（§10 全部实测）：`POST /api/sequences/sequence-create {"name":...,"channel":"system"}`——API L260；`POST /api/sequences/step-create {"seqId":<id>,"step":<n>,"template_ids":[...],"wait_mode":...,"wait_time":...,"senders":[...]}`——API L273、L279-289；`POST /api/sequences/sequence-save {id,name,schedule_id,others,rules}`——API L261、L291-303；`POST /api/settings/sequence/schedule-list`——API L267；`POST /api/settings/sequence/schedule-default {"id":<schedule_id>}`——API L399（id 运行时解析,勿硬编码）。
- **脚本入口唯一**：使用上一行带 `--profile`、tmap.meta 校验与稳定项目键的 `build_sequence.py`；缺任一项即拒绝，禁止用旧命令绕过档案绑定。
- **产出记录**：`.local/approvals.tsv`（S9_序列配置行）；`runs/<运营方>/<产品>/seq-config.json`；序列 id 记 `operation-record.md`。

### S10 CONTACT_PENDING（时序守卫 + contact-add）
- **判据（来源）**：`../RULES.md` L34「保存finished、标签联系人>0、序列inactive、人数对账且用户确认后才contact-add」；铁律⑥ `../RULES.md` L66（等 finished+标签联系人>0，否则 add 0）；L-01：`views` 必须传**空数组 `[]`**（传 `["all"]` 会把全部 139 万联系人加入）。
- **通过条件**：`wait_save_done.py` 双校验通过（finished + 标签联系人>0）+ 序列 inactive + 人数对账一致 + 用户确认。
- **API**：`POST /api/sequences/contact-add {"seqId":<id>,"tags":[<联系人标签id>],"views":[]}`——API L309（★views 必须 `[]`）；`POST /api/sequences/contact-list`——API L308；`POST /api/contacts/contacts/show`（标签人数）——API L163、L356。
- **脚本**：`contact_add.py --seq <id> --tags <联系人标签id> --task <保存任务id> --record runs/<operator_key>/<product_key>/operation-record.md --approval <绑定S10凭证> --project <operator_key>/<product_key>`；工具查询失败/active序列 fail-closed、views固定[]、add对账成功后推进S10。
- **产出记录**：`.local/approvals.tsv`（S10_加联系人行）；`operation-record.md` 记 add 人数；`evidence.json`（contacts_total）。

### S11 READY_INACTIVE（终检 + 待确认）
- **判据（来源）**：`../RULES.md` L35「输出完整流程和参数；测试保持inactive，等待用户确认」；`../RULES.md` L129 **测试不激活（★用户强制）**：流程跑完→发完整流程待确认，**不激活序列**；`../RULES.md` L54 完成输出标准（完整流程/task id/实际数量/模板序列映射和问题）。
- **通过条件**：verification-manifest绑定project/org_sha256/seq/profile_sha256/72小时内generated_at及4份不同的项目内证据path+sha256+pass；`finalize_run.py --record ... --profile ... --project <key> --org <org> --seq <id> --manifest ...` 推进S11。
- **API**：`POST /api/sequences/sequence-details {"id":<seqId>}`——API L259；`POST /api/sequences/sequence-count`——API L258；`POST /api/sequences/sequence-list`——API L257。
- **脚本**：
  - `python3 tools/verify_sequence.py --token <T> --org <orgId> --seq <序列id>`（激活前硬闸门，断言 12 步+24hex+步长，失败 exit 1）
  - `python3 tools/verify_exclude.py --token <T> --org <orgId> --keyword <种子> --pages 1,2,3,50,100,200`（4区抽验；⚠️proxy=company-list 非保存结果，见 docstring）
  - ✅ **测试不激活工具闸门**：activate_sequence.py 必须当前 S12 confirm/confirmed绑定凭证 + profile + 五项合规文件，并禁止自签；直接手工 curl 绕过属于恶意操作，审批机制防呆不防恶。
- **产出记录**：项目目录 `evidence.json + verify-seq.txt + verify-exclude.txt + verify-diff.txt + verification-panel.md + verification-manifest.json`；manifest逐文件hash绑定后 `finalize_run.py` 才推进S11。

### S12 ACTIVE（仅用户明确确认 + 技术可用性与运营合规核验）
- **判据（来源）**：`../RULES.md` L36「仅明确确认激活才激活；平台负责发送技术与退订呈现，运营方仍核验目标市场规则、名单来源、发送主体、实际退订入口、拒收名单与数据处理要求」+ 铁律5 L65。激活前逐字核对目标序列 id，并验证 notSentTags/上限/步骤。
- **通过条件**：verify_sequence已过；compliance-check顶层绑定project/seq/profile/checked_at，五项均status=pass且evidence含source/checked_at/detail；补齐flow的seq/compliance参数，在当前TTY由用户现场确认签发S12凭证。S12禁止approval.py grant，历史/backfilled/工具自签无效。
- **API**：`POST /api/sequences/sequence-active {"id":<seqId>,"active":true}`；工具必须回读 active 防假成功。
- **脚本**：`activate_sequence.py --seq <id> --project <key> --profile <product-profile> --compliance-file <compliance-check.json> --record <operation-record> --confirm '<与凭证一致的用户原话>' --approval <S12凭证>`。
- **产出记录**：`.local/approvals.tsv`（激活确认行）；本地运行记录 status→active（不入 Git）。

### ERROR_BLOCKED（异常兜底）
- **判据（来源）**：`../RULES.md` L37「异常、参数变化、对账不一致或规则冲突时，只读检查，禁止自动写操作」；参数变化回退 `../RULES.md` L42。
- **脚本**：`bash tools/check_rules.sh --token <TOKEN>`（AI 自查 token/规则/问题）。
- **产出记录**：本地问题登记（不入 Git）；修复后重跑 `gate_check.sh`。

---

## 2. 易漏判据专项（★这 7 条最容易被 AI 跳过，逐条核对）

| # | 易漏点 | 判据原文要点 | 来源 |
|---|--------|-------------|------|
| 1 | **S0 闸门硬条件** | 昵称+一句话产品必填（中英皆可），缺一只问这一项；渐进索取，禁开局列清单；且必须 `gate_check.sh` 通过（token 有效+必读文档存在+规则命中）才能开始流程 | `../RULES.md` S0；`../methodology/decision-trees.md` Gate0 |
| 2 | **S2 客群推荐维度** | 每个客群写「精准潜在客户：是/否/条件成立时是」并给成交周期/询盘速度/量级/邮箱可得/竞争度/推荐；只打印不代选 | `../RULES.md` L25/L51/L94 |
| 3 | **S4 临界判定** | 判定=AI 反思「会不会买」语义推理，**不是关键词匹配**；工具词匹配只做趋势初筛；50页跳→三页平均→逐页→跌破往前；临界页人工逐条读完整10条 | `specs/threshold-method.md` L19-27/L50-58；L-26 |
| 4 | **S5 保存前重复检查** | 保存前查 (keyword+seed+阈值+selectTotal+排除4区) 是否曾完成保存，已存则不重存（省额度）——★规则有、脚本缺（防重复保存缺口） | `../RULES.md` L73 |
| 5 | **S7 模板草稿预览+差异实测** | 只生成草稿；展示的是**渲染后收件人视图**（render_preview.py），非 HTML 源码；"差异≥30%"**不得声称达标**，生成后必须 check_template_diff.py 实测（>0.70=违例） | `../RULES.md` L30；`specs/sequence-config.md` L76-79；L-43/模板差异实测（工具级） |
| 6 | **S10 时序守卫** | 必须等保存任务 `status:finished` + 标签联系人>0 才 contact-add；且 `views:[]`（永不 `["all"]`）；人数对账+用户确认 | `../RULES.md` L34/L65；L-01/L-32 |
| 7 | **S11/S12 激活判据** | 测试跑完保持 inactive；仅用户明确确认 + 序列验证 + 运营方完成市场/名单/主体/退订入口/拒收核验后才激活 | `../RULES.md` L35-36/L65 |

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
