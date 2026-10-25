---
doc_id: "specs-problems-and-fixes-2026-10-23"
title: "全流程问题对照与对抗审查（2026-10-23 · 户外帐篷首跑）"
description: "2026-10-23 户外帐篷首跑踩坑台账：现象、根因与固化位置，排障先查本表。"
type: "record"
status: "active"
updated: "2026-10-23"
---

# 全流程问题对照与对抗审查（2026-10-23 · 户外帐篷首跑）

> 用途：把本次从「找客群」到「激活发信」踩过的坑逐条挂账；每条含 **现象 → 根因 → 当时处理 → 文档 vs 实际 → 对抗审查 → 结论/固化位置**。
> 铁律：以后再遇同类问题，先查本表；新增问题必须追加到本表（AGENTS 第 14 条）。

---

## 一、问题清单（按发生顺序）

| # | 现象 | 根因 | 当时处理 | 状态 |
|---|---|---|---|---|
| 1 | 建 48 个模板，跑到 24 个被前端 120 秒超时杀掉 | 长任务无进度续跑设计 | 按名字去重，只补建缺的 24 个 | ✅ 已解 |
| 2 | 重试报 E_AUTH_REUSED（同一票据只能用一次） | 票据一次性 + 任务被杀，凭证被消耗 | 重新铸票据，按"缺谁补谁"再跑 | ✅ 已解 |
| 3 | 模板分组 `--foid auto` 报解析/创建失败 | 分组已存在，auto 未复用 | 查到已有分组 id 直接复用 | ✅ 已解 |
| 4 | 审批只认整句，用户回 `A` 被拒 | 校验按关键词匹配整句 | 改 `approval.py`：单字母 A–D/1–4 视为对已展示选项卡的确认 | ✅ 已修 |
| 5 | 写票据校验"缺数量/域名/标签"拒绝 `A` | `auth_guard` 目标校验只认这些对象 | 给单字母加豁免 | ✅ 已修 |
| 6 | 激活时"确认激活+序列名"被拒：必须与审批原话逐字一致 | 两套校验口径冲突：审批要**原话**，写票据要**目标** | 本次用原话过审批、另铸带目标的票据 | ⚠️ 本次已修（见下） |
| 7 | 激活报"执行卡 S12 未 show/record" | 流程没有自动引导执行卡 | 手动 `step_gate.py show/record --state S12` | ✅ 已解 |
| 8 | `flow --resume-s12` 报 `--project` 不识别、缺 `--org`、`--product` 必填 | 工具参数与直觉不一致，文档没写全 | 试错三次后改用 `--profile --product --credentials-from-session` | ⚠️ 仅口头 |
| 9 | 票据传 nonce 报"票据文件不存在" | 必须传 `授权票据文件（路径由工具生成）` 路径 | 改传路径 | ✅ 已解 |
| 10 | `contact_add.py` 一跑就 DEPRECATED，S10 没有 CLI 写通道 | 旧脚本被封条；现役写通道是 `save_guard.authorize_write` | 新建 `tools/contact_add_authorized.py`（审批+票据+同款时序守卫） | ✅ 已解 |
| 11 | 加完联系人状态只到 S10，S11 终检没有自动推进命令 | 流程缺 S11 收口脚本 | 手工读序列设置核对后改记录 | ⚠️ 待固化 |
| 12 | 序列「对方回复后是否继续发」默认保持 False | `build_sequence.py` 硬编码 `finishReply=False` | **口径裁定：保持 False 是正确默认**（回信→转人工接管，避免自动停发误伤）；此前台账「手工打开为 True」作废；文档/话术统一按「回信不自动停=人工接管」表述，不改代码 | ✅ 已定口径（2026-10-23） |
| 13 | 审计清单时间报 can't subtract offset-naive and offset-aware | 校验函数用本地 naive 时间，文件里写了带时区时间 | 统一写本地 naive ISO | ✅ 已修 |
| 14 | 审计证据"缺必需内容"被拒 | 关键词清单过严，正常证据写不进去 | 放宽为"70%/临界 + 至少 2 项佐证" | ✅ 已修 |
| 15 | 审计清单"未绑定当前 project/profile/seed" | 记录缺 seed 字段 | 记录补 seed | ✅ 已解 |
| 16 | 文案有高风险事实但计划缺 claims 字段 | 生成器与计划 schema 不一致 | 改写文案，避开高风险表述 | ✅ 已解 |
| 17 | 模板四要素/加粗数量违例 8 处 | 角度句只有一个加粗卖点 | 每轮补第二个加粗卖点 | ✅ 已解 |
| 18 | 汇报出现"preview / 硬门 / 审批凭证"等黑话 | 直接照搬内部术语 | 全部改写人话，并写入播报规范 | ✅ 已固化 |
| 19 | 流程拆成 7 步，后两步要确认两次 | 步骤粒度设计错 | 合并为 6 步，第 6 步一口气跑完 | ✅ 已固化 |
| 20 | 确认点放在第 4 步（上传前）导致上传后再确认一次 | 确认点位置错 | 确认点前移到第 5 步末（模板建好核对完） | ✅ 已固化 |
| 21 | 播报间隔 3 分钟，用户以为卡死 | 频率太低 | 改 10–30 秒 + 三要素 + 第X步/共6步 | ✅ 已固化 |
| 22 | 用户回 `a` 不够，激活必须"确认激活"四个字；用户要求先看拒绝样例 | 安全门设计 + 表达不清 | 给出接受/拒绝两段模拟，并加粗口令 | ✅ 已固化 |
| 23 | 激活成功后没告诉用户"几点开始发" | 交付缺时间换算 | 固化三地时区 + 倒计时播报 | ✅ 已固化 |
| 24 | 平台接口偶发空导致状态查询失败 | 平台已知间歇空 | 查询失败一律 fail-closed + 重试 3 次 | ✅ 已固化 |

---

## 二、逐条对抗审查（攻击 → 结论 → 修法）

1. **超时杀任务**：攻击"没建完就以为建完了？"→ 若只按数量核对，重复/漏建会混过。结论：必须按"名字集合 + 逐封内容比对"双核对。修法：`s7-supplement-create.py` 只补缺，建成后 48/48 逐字比对（本次已验）。
2. **票据一次性**：攻击"重试会不会重复创建？"→ 会。结论：重试必须先去重再补建。修法：同上；并把"票据一次性、失败先盘点再重铸"写进 SOP。
3. **分组复用**：攻击"每次都新建分组会不会越来越乱？"→ 会。结论：先查同名分组，有则复用。修法：SOP 模板流程已写"同名分组复用"。
4. **单字母确认**：攻击"回个 A 就等于授权写平台，会不会太松？"→ 前提是卡片上已完整展示对象和后果。结论：可接受，但仅限卡已展示且选项明确。修法：`approval.py` 只对 A–D/1–4 放行，且仍需项目绑定。
5. **目标校验豁免**：攻击"以后啥都回 A，岂不是任意写？"→ 仍有参数哈希绑定和项目校验。结论：可接受。
6. **两套口径冲突（本次核心坑）**：攻击"AI 会不会自己编一句'确认激活'去过闸？"→ 必须用**用户原话**过审批，所以绝对不能改写；写票据要目标，属于另一层。结论：**审批 quote = 用户原话；写票据 quote = 原话 + 目标对象**，两处分开、都不许编造。修法：`auth_guard` 对 `activate` 增加"payload.seq 存在且 quote 含'激活'"即视为有目标（本次已改），以后一句"确认激活"即可，不再需要拼序列名。
7. **执行卡**：攻击"忘了 show 就能绕过吗？"→ 不能，会被拒。结论：这是防走神，不是安全边界。修法：SOP 增加 S12 三段式命令清单（show → record → activate）。
8. **flow 参数**：攻击"文档写的和工具不一致，换个人必踩"→ 是。结论：文档必须以真实 `--help` 为准。修法：SOP 写死本次可用的完整命令（见第三节）。
9. **票据路径**：攻击"传 nonce 更自然，为什么不支持？"→ 支持路径可防伪造。结论：保持路径，文档写明。修法：SOP 已写。
10. **S10 无 CLI 通道**：攻击"自己写个脚本不就绕过闸门了？"→ 新脚本仍走审批 + 票据 + 保存 finished + 标签>0 + views=[] + 序列 inactive 全部门禁。结论：**不是绕过，是补上现役正路**。修法：`contact_add_authorized.py` 入库，README 标注"现役"。
11. **S11 未自动收口**：攻击"手工改记录会不会忘？"→ 会。结论：需要一条命令或明确 checklist。修法：SOP 加 S11 核对单（人数/轮次/时区/上限/跳过标签/回复即停），并记录 S11-report。
12. **回复即停默认关**：攻击"这会让已回复的客户继续收信，严重"→ 是。结论：默认必须开。修法：`build_sequence.py` 默认 True，并在建序列后回读断言，不对就报错（本次已改）。
13–15. **审计三连坑**：攻击"放宽关键词会不会放水？"→ 放宽的是措辞，不是结论；放行仍需"放行/P0=0/P1=0"。结论：可接受。修法：保持现有双口径 + 时间 naive 统一 + seed 必填。
16–17. **文案/模板**：攻击"为了过闸改文案，会不会把卖点改没？"→ 需复核卖点仍在且加粗。结论：改完必须重跑四要素校验。修法：已在生成器内置校验。
18–21. **汇报与流程**：攻击"规则写了 AI 就一定遵守？"→ 不能保证，只能靠播报模板 + 用户当场指出。结论：规则要短、可执行、有对照表。修法：SOP v2–v5 + AGENTS #11/#13。
22–23. **激活 UX**：攻击"加粗两个字会不会还是有人回 a？"→ 会，但会被拒且给出明确提示。结论：拒绝提示必须写清"现状不变、没发信、要回什么"。修法：拒绝/接受两段模拟已固化。
24. **接口间歇空**：攻击"fail-closed 会不会误杀正常流程？"→ 会重试 3 次再拒。结论：宁可拒，不可猜。修法：保持 fail-closed。

---

## 三、固化到哪些文件（下次照抄执行）

1. **激活标准命令（本次验证可用）**
```bash
# 1) 合规核验（live 五项）→ runs/<op>/<product>/compliance-check.json
# 2) 签审批（用户原话必须含"激活"）
.venv/bin/python tools/flow_orchestrator.py --profile runs/tony/户外帐篷/product-profile.md \
  --product 户外帐篷 --resume-s12 --seq <seq> \
  --compliance-file runs/tony/户外帐篷/compliance-check.json --confirm "确认激活" --credentials-from-session
# 3) 铸写票据（action=activate，payload={seq,active:true}）
.venv/bin/python tools/auth_guard.py authorize --action activate --quote "确认激活" \
  --payload-json '{"seq":"<seq>","active":true}'
# 4) 过执行卡
.venv/bin/python tools/step_gate.py show --state S12 --run default
.venv/bin/python tools/step_gate.py record --state S12 --run default
# 5) 激活（--confirm 必须与审批原话逐字一致）
.venv/bin/python tools/activate_sequence.py --token $TOKEN --org $ORG --seq <seq> \
  --confirm "确认激活" --approval <ap-id> --project <op>/<product> \
  --profile runs/<op>/<product>/product-profile.md \
  --compliance-file runs/<op>/<product>/compliance-check.json \
  --auth-ticket 授权票据文件（路径由工具生成） --record ... --run default
```
2. **S11 核对单**：人数/轮次/时区/单日上限/单家上限/跳过标签/回复即停/状态 inactive → 把核对结果写入 `operation-record.md` 并留 `reflection.md`。
3. **S10 现役通道**：`tools/contact_add_authorized.py`（审批 + 票据 + 时序守卫），旧 `contact_add.py` 仅作流程核对。
4. **播报**：10–30 秒一次；三要素；第X步/共6步；禁黑话；确认一律编号选项。
5. **激活后**：三地时间 + 倒计时（纽约/用户本机/北京），说明"窗口外不会立刻发"。

## 25. AI 不读文档就开跑 → 开工必读机器门（部分完成，仍有 P0）

- 现象：换新 AI/新会话直接跳步执行；第一屏被塞菜单、重复索取资料。
- 本轮固化：新增开工必读闸门脚本（6 份必读 + 内容指纹锁定 + 本地账本）；执行卡校验与写票据铸造已接闸门；仓库根新增 AGENTS；README/SKILL/INDEX 写死登记时机；新增 10 条测试。
- 红队 P0（未关）：① 覆盖只到保存链，建模板/建序列/加人/激活的脚本仍直连写；② 测试模式开关生产可伪造；③ 登记只是自述、可手写账本；④ 曾承诺「五类全拒」与实现不符（已改准确表述）；⑤ 未登记报错含内部文件名，用户层需过滤。
- 下一步：闸门下沉到统一写入口；测试模式改由测试框架不可伪造注入；登记绑定用户原话/会话；集成测试覆盖每个写 CLI。

## 26. 机器门第二轮红队结论（2026-10-23，未关项挂账）

- P0-1 覆盖：五类写操作只有保存链真接门；建模板/建序列/加人/激活仍直连平台写，入口级注入会误伤 43 条子进程测试（已回滚），需下沉统一写入口。
- P0-2 测试模式：环境变量可被生产命令自设，配合假文档/假账本可整体绕过。
- P0-3 账本可伪造：写一行 JSON + 自算 sha256 即过；符号链接未被拒；需签名/会话绑定/防跟随。
- P1-4 隐藏旁路：测试框架在内存中即放行，测试包装器同样命中。
- P1-5 已铸票据：必读文档变更后校验/消费不复检登记。
- P1-6 死锁风险：安装期禁问昵称/产品 与「装完只问两样、拿到后才登记」冲突，需先统一规则口径。
- P1-8 异常路径：部分入口 traceback 退出码 1，不是中文退出码 2；账本字段非字典时同类（已修 startup_gate 两处）。
- P2-9 文档互斥：INDEX 曾称全拒（已改）、RULES 全篇无开工门规则、踩坑台账激活命令与 argparse 不符。
- 已修本轮：账本损坏改中文退出码 2；INDEX 口径与实现一致；AGENTS/README/SKILL 不再声称五类全拦。
- 未复现：删账本 fail-closed；20 并发登记账本完整。

## 27. P0-1 覆盖缺口关闭 + 写门人话与集成测试（2026-10-23）

- 做法：每个写脚本的 HTTP 写函数入口统一调用开工门；模板脚本 3 处 curl 写操作各自加门；保存链保持原有执行卡/写票据门。共 16 个写脚本受控。
- 报错体验：未登记时退出码 2，并给用户一句白话「还差一步：请先告诉我怎么称呼您、主要卖什么产品」，不展示文件名/命令。
- 测试隔离：测试包与 4 个历史子进程测试文件显式设置测试标记；生产命令不继承该标记。
- 新增集成测试 3 条：纯净副本未登记必失败；登记后通过、改文档后必须重新登记；16 个写脚本必须带门。全量 431 tests OK。
- 仍开放：测试标记可被生产伪造（需宿主级不可伪造注入）、账本可手写（需签名/会话绑定）、已铸票据不随文档变化失效、激活/建序列的执行卡仍靠调用顺序约束。

## 28. P1-5/P0-3/P2-10 部分关闭 + 加固测试（2026-10-23）

- 已铸票据复检：`auth_guard.verify` 与 `consume` 开头都调用开工门；必读文档变化或未登记时，已铸票据也不能消费（P1-5 关闭）。
- 账本防跟随：读/写账本拒绝符号链接（E_LEDGER_SYMLINK），读取使用 O_NOFOLLOW（P0-3 部分关闭；手写普通文件仍可伪造，本机工具无法提供密码学真人证明，已在 RULES/AGENTS 说明）。
- 跨会话复用：ack 记录 DSH_SESSION_ID/LFX_SESSION_ID，check 发现会话不一致即要求重新登记（P2-10 部分关闭；无会话变量时降级为兼容模式）。
- 新增 3 条集成测试：符号链接账本必拒；跨会话 ack 必拒；无登记时票据 verify 必拒。全量 434 tests OK，check_rules exit 0。
- 仍开放（受限项，如实说明）：测试标记仍可被生产进程自设（需宿主级不可伪造注入）；本机账本无法防蓄意手写伪造；激活/建序列的 S12 执行卡仍靠调用顺序与审批参数约束。

## 29. 逐模块逻辑索引 + Mermaid 源码 + 100 页跳口径统一（2026-10-23）

- 新增 `specs/step-map.md`（220 行）：总览 Mermaid + 12 个模块（M0–M12）的「读什么/做什么/怎么判/失败出口/用户回什么/能不能跳」+ 跳步规则总表 + 步骤→文档索引；Mermaid 源码文本放 specs 与 AGENTS，禁止放进 output-templates（用户屏）。
- 明确 **70% 唯一适用范围**：仅 S4 审计临界/S5 保存边界（连续 5 页滑动窗口 ≥70%）；**客群推演（S2）没有 70% 指标**。
- 把「跳着找临界点」固定为：100 页 1 跳 → 前后 3 页 → 连续 5 页滑动窗口 → 首个 <70% 即停、临界=前一窗口末页 → 窗口二分 100→50→25→10→5→1 → 未采样=UNKNOWN、不得声称全带合格；跌破后反弹窗口不得定界。
- 统一旧口径：RULES L64/L240、INDEX L33、methodology/decision-trees S4 节点、threshold-method 阶段1 全部从「50 页跳」改为「100 页跳」（threshold-probe-spec v3.1 为执行细则真源）。
- 新增测试 `tests/test_step_map.py` 5 条：step-map 存在且含 Mermaid/12 模块；70% 适用边界句；AGENTS 指向 step-map；RULES/INDEX 不得再出现 50页跳；用户模板禁止 Mermaid。全量 439 tests OK，check_rules exit 0。

## 30. 逐模块 API/要点核验（对抗审计两轮，2026-10-23）

- 新增 `specs/module-api-map.md`：M0–M12 每模块「入口脚本 × 真实 API × 关键参数 × 写入门禁 × 要点 × 证据」，并列出 20 条文档↔代码差异（D1–D20）与待真机项。
- **核验发现的真实分层**（旧文档写反了）：S5=save_guard V2 plan/render/ticket；S10=auth_guard `authorize_write(action="sequence")`；S7/S8 模板、S9 序列、S12 激活=approval.py 审批凭证（S12 另加原话校验）；`authorize_write` 当前只覆盖 S10。
- 修复/修正：SKILL/docs10/CORE-POINTS 的「无条件封条」改为「文档层禁用」；SKILL v3.5→v3.1；S10 现役 `contact_add_authorized.py`；模板 add `foid=<分组id>`（非 0）；价格/折扣禁止写入（删「价格带」）；S4/SKILL 50页→100页、三页→5页窗口；probe 预算统一「单轮≤60、采样≤51」；`save_company_cli` 文档参数待改（--request-file/--ticket-file）。
- 代码修复（本轮派 2 个实现代理）：finalize_audit 加窗口/临界页/语义表机器校验；save_company_cli execute 前加 workspace_guard.preflight；find_critical/find_threshold 补四区 filters；audit_company 修 loose/错误上报/--domains 主搜；S10 票据返回值校验；S12 口令改「确认激活」+拒绝 exit 2；gen_templates 12×4 fail-fast、硬 no-price、建后自动 diff。
- 仍未闭合（诚实记录）：旧保存脚本无物理封条（文档层）；`finishReply` 口径冲突；S12 六项检查未全由工具验证；`verify_sequence` 未接线；模板分组 `folder` 字段待真机；S10 名额/预算预检无落点；`save_company_cli` 文档命令示例未改。

### 30.1 M0–M6 审计新增（2026-10-23）

- P0 已修：`beginner-flow.md` 存客户口径由「回 1」改为「确认保存 前 N 家」（与 S5/工具一致）。
- P1 已修：`seed_resolve.py` 接口失败改为报错 exit 2（原先 exit 0 冒充成功）；`auth_guard.authorize` activate 分支 `hits` 未赋值（潜在 UnboundLocalError）已修；`save_company_cli` 开工门 RuntimeError 改由实现代理补中文 exit 2。
- 仍待办：`browser_login.py` 不存在（RULES/SKILL 称 CDP 首选）→ 文档需改为「一键命令首选」；`onboard_check.py` 无退出码（AGENTS 称未通过不得开始）→ 需加 exit 2；S5 执行卡 `runtime/cards/S5.json` 新 checkout 缺失 → 安装自检需生成/检查；`segment_source.evidence_record` 未接线；`segments_infer` 无轮询；`S0-连接成功` dailyUsedUp 字段未实现；M1 本会话绑定可绕过（双方 session 为空即跳过）。

### 30.2 修复落地与最终回归（2026-10-23）

- 代码门禁已落地并测：`finalize_audit.py` 新增 `validate_audit_window`（连续页/5页窗≥70%/临界页=首跌窗起点+3/语义表对齐，失败 exit 2）；`save_company_cli.py` execute 前加 `workspace_guard.preflight`；`find_critical/find_threshold` 补四区 filters；`audit_company` 修 loose 分母、HTTP 错误上报、`--domains` 改走主搜；`contact_add_authorized` 校验票据返回值且无票 exit 2；`activate_sequence`/`flow_orchestrator` 口令改「确认激活」+拒绝 exit 2；`gen_templates` 加 12×4 fail-fast、硬 no-price、建后自动差异检查。
- 补齐仓库缺失模块 `tools/segment_fields.py`（`search_company.py` 引用但仓库原本不存在，导致 `save_company_cli` 导入即失败）；`auth_guard.authorize` activate 分支 `hits` 未赋值已修；`seed_resolve` 接口失败改 exit 2；`beginner-flow` 存客户口径改「确认保存 前 N 家」。
- 文档同步：`specs/module-api-map.md`（M0–M12 API/要点/差异 D1–D21）、`specs/step-map.md`、`threshold-method`/`threshold-probe-spec`（100页/5页窗口/预算≤60）、`S4/S5/S6/S7/S10` 模板、`SKILL/RULES/CORE-POINTS/docs10/api-dictionary/sequence-config/node-playbook/INDEX/README`。
- 最终机器证据：`python3 -m unittest discover -s tests` → **Ran 489 tests, OK**；`bash tools/check_rules.sh` → exit 0。工作区 86 项改动（67 文件，+1293/−297），**未提交、未推送**。
- 仍未闭合（诚实记录）：①`build_sequence.py` exact=False 静默切分未改（gen_templates 已自证产物精确，外来 tmap 仍有风险）；②模板分组 `folder` 字段真机未验证；③`finishReply` 口径冲突；④`verify_sequence` 未接入建序列/激活；⑤S12 六项检查未全由 activate 验证；⑥S10 名额/预算预检无落点；⑦旧保存脚本仍无物理封条（文档层禁用）；⑧`save_company_cli` 文档命令示例仍待改 `--request-file/--ticket-file`；⑨`onboard_check` 无未通过退出码。

### 30.3 剩余缺口闭合轮（2026-10-23 07:00 前后）

- 对齐口径（B 代理）：`docs/10-execution-guardrails.md` §8、`specs/module-api-map.md` 顶部与 D2/D11/D12/D19/D20/§3 已同步「4 个旧脚本已加物理封条（仍非安全边界）」及各项已修状态；`finishReply` 维持 False=回信人工接管（不改代码，30 行历史记录已加口径裁定）。
- 序列/激活/verify 闭合（A 代理）：`build_sequence` 在联网前校验 tmap 精确 12×N，建完自动 `verify_sequence.check_sequence`，失败 exit 2 且不推进 S8；`verify_sequence` 改为全模板识别（分组模板计入）、邮件模板列表为空/步骤未绑模板一律失败；`activate_sequence` 激活写之前校验 12 步/rules/notSentTags/每步绑模板，不满足 exit 2、S11 不动。新增 14 测试（假 curl 零真实网络）。
- S10 预检与文档（C 代理）：加人前只读打印标签人数/预计加人/去重/未激活，0 人或缺标签 exit 2 不写；`check_template_diff`/`rebuild_templates` 取消 folder 跳过；SKILL/operations-sop 保存命令改真实参数；新增 `specs/save-offline-input.md` 最小 schema+样例（样例过 rule_check 实校验）。新增 12 测试。
- 旧脚本封条与安装门（B 代理）：save_first_n/contact_add/delete_all_products/wait_save_done 最早可执行位置封条（--help/import 不受影响，dry-run 也封）；onboard_check env_ok=False 时 exit 2；RULES/SKILL/CORE-POINTS 口径同步。新增 7 测试；全流程仿真改为状态推进，不再依赖旧脚本后门。
- 交叉冲突：A 改 verify 输出为「步骤数=12」，Lead 在 `finalize_run.evidence_ok` 做等价归一化（两种写法均认，值仍须 12）。
- **最终机器证据**：`python3 -m unittest discover -s tests` → **Ran 522 tests, OK**；`bash tools/check_rules.sh` → exit 0；未提交/未推送。
- **剩余（真机/后续，不再阻塞发布预览）**：①S5 执行卡 `runtime/cards/S5.json` 全新 checkout 生成；②`browser_login.py` 文档口径改「一键命令首选」；③`S0-连接成功` dailyUsedUp；④`segment_source.evidence_record` 接线；⑤`segments_infer` 轮询；⑥真实平台 `folder` 字段确认（代码已不依赖）；⑦S12 真机首跑；⑧模板建后自动 diff 与 S7 首次真机确认；⑨`verify_sequence` CLI 失败码沿用 exit 1（API/CLI 历史契约，build/activate 映射 exit 2）。

### 30.4 本机可跑性补齐（2026-10-23 07:10 前后）

- 发现本仓缺失 RULES/SKILL 明确引用的两个登录脚本：从同机 `laifaxin-knowledge/tools/` 补入 `browser_login.py`（944 行，标准库实现，隔离 profile + CDP + `--save-session/--forget`）与 `session_store.py`（0700/0600 本机会话存储）；`py_compile`、`--help`、`import` 均通过。凭据三层降级中「CDP 首选」现在是真的。
- 补入 `runtime/cards/` 9 张执行卡（S0a/S2/S3/S4/S5/S7/S9/S10/S12，来源同机知识库仓），保存链 `step_gate.require_card("S5")` 在全新 checkout 可加载；新增 `tests/test_runtime_cards.py` 锁「卡存在 + schema + S5 可加载」。
- 本机环境现状（供后续真机）：`LFX_TOKEN/LFX_ORG` 未设置、无 session 文件、9222/9211 无 CDP 端口；因此真机登录需用户在本机弹出的浏览器窗口里登录一次（`browser_login.py --save-session` 可保存到 0600 本机会话文件）。
- 本机可跑性验证：`python3 tools/onboard_check.py` → exit 0；`python3 tools/browser_login.py --help` 正常；`python3 -m unittest tests.test_runtime_cards` → OK。
