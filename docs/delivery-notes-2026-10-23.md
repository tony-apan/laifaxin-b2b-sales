---
doc_id: "docs-delivery-notes-2026-10-23"
title: "交付清单：文档核验、跨平台兜底与双审修复"
description: "交付清单：文档链接/锚点/抽检、自检脚本与钩子、Windows/macOS 兜底、新手话术与双审修复证据。"
type: "record"
status: "active"
updated: "2026-10-23"
---

# 交付清单：文档核验、跨平台兜底与双审修复

> 一句话：这份清单记录本轮为「文档基建 + 交付前自检」做的全部改动与验收证据，复盘本轮工作或核对交付时读。
> 状态：全部改动**未提交、未推送**，分支 `novice-onboarding`。

## 1. 新增/修改的工具与钩子

| 交付物 | 文件 | 作用 |
|---|---|---|
| 参考式链接核验 | [check_doc_links.py](../tools/check_doc_links.py) | 支持 `[文字][标签]` + `[标签]: 目标`，坏链可检出 |
| 锚点核验 | 同上 | 标题 slug（含同名标题 `-1/-2` 后缀）与 `<a id>`；同文件/跨文件都查 |
| INDEX 描述抽检 | 同上 | `--sample-index 20` 随机抽 20 行，seed 可复现，供人工核对真实性 |
| title/H1 一致性 | [test_doc_frontmatter.py](../tests/test_doc_frontmatter.py) | title 与 H1 去符号后最长公共子串 ≥4，防标题跑偏 |
| 锚点回归测试 | [test_doc_links.py](../tests/test_doc_links.py) | 好锚点不误报、坏锚点必报、同名标题后缀正确 |
| 一条命令自检 | [preflight.sh](../tools/preflight.sh) | 文档引用 → 全量测试 → 规则检查；失败退出 1 |
| CI 工作流 | [preflight.yml](../.github/workflows/preflight.yml) | push/PR 自动跑同一命令（未推送，尚未触发） |
| 提交前钩子 | [pre-commit](../.githooks/pre-commit) | `git commit` 前跑 preflight，失败阻止提交 |
| 推送前钩子 | [pre-push](../.githooks/pre-push) | `git push` 前再跑一遍，失败阻止推送 |
| 钩子安装 | [install_hooks.sh](../tools/install_hooks.sh) | 每个 clone 跑一次；本机已安装 |

## 2. 内容与索引类改动

| 改动 | 位置 |
|---|---|
| tests/INDEX 45 行「什么时候读」逐文件重写，13 条空说明补实 | [tests/INDEX.md](../tests/INDEX.md) |
| tools/INDEX 66 行按流程阶段重写，并新增 3 个工具行 | [tools/INDEX.md](../tools/INDEX.md) |
| 修 1 处含糊描述（S2/S3 行） | [INDEX.md](../INDEX.md) |
| 修 1 处 title/H1 跑偏（decision-trees 的 H1） | [decision-trees.md](../methodology/decision-trees.md) |
| 规范同步：preflight、锚点、抽检、钩子写法 | [MD-METADATA.md](../MD-METADATA.md)、[AGENTS.md](../AGENTS.md) |

## 3. 测试证据（最近一次全量）

| 项目 | 结果 |
|---|---|
| 文档引用核验 | 坏链 0 · 坏引用 0 · 缺失同名 0 · TOTAL_BAD 0 |
| 全量测试 | Ran 576 tests / OK（正常环境；无 bash 环境 6 项 skip） |
| 规则检查 | PASS |
| 一条命令自检 | PREFLIGHT PASS（正常环境与无 bash 环境均退出 0） |
| 钩子实测 | 正常路径 PASS；`SKIP_PREFLIGHT=1` 退出 0 |
| 目录索引 | 17/17 目录有 INDEX；未覆盖直接子项 0 |

## 4. 复现方式

```bash
bash tools/preflight.sh                          # 发布前全量自检
python3 tools/check_doc_links.py --sample-index 20  # INDEX 描述人工抽检
bash tools/install_hooks.sh                      # 安装提交/推送前钩子（每个 clone 一次）
```

## 6. 第二轮：跨平台兜底 + 新手话术 + 双审修复（2026-10-23）

| 类别 | 改动 | 证据 |
|---|---|---|
| 跨平台 | 新增 [preflight.py](../tools/preflight.py)（用当前解释器、UTF-8 输出、无 bash 时 Python 兜底）；[.gitattributes](../.gitattributes) 统一行尾 | 无 bash 环境（PATH 仅含 python3）跑 `preflight.py` → PASS，558 tests OK（skip 6） |
| 自检可靠性 | `check_rules.sh` 缺规则文件改为 exit 2；`preflight.py` 即使 rc=0 也把 `[FAIL]` 判失败；`preflight.sh` 自动探测 python3/py/python | 临时目录缺规则文件 → RC=2；行为测试 2 条固化 |
| 新手话术 | 第 1 屏重排：先核对产品资料再连账号、48 个模板≠发 48 封、12 轮跟进、您/你统一、次数说明；README 去开发徽章、加费用说明与「给 AI 看」标注 | 契约测试 12 条 + 文档测试全绿 |
| 黑话闸门 | 新增 [test_user_visible_jargon.py](../tests/test_user_visible_jargon.py)：output-templates 代码块禁客群/序列/硬门/审批凭证/S 编号；顺手修 12 处用户可见措辞 | 36 个话术块扫描，0 命中 |
| 双审修复 | 一审 14 条 + 二审 9 条逐条仲裁：采纳 20 条、修正表述 3 条（如「还要回 8 次」为测试锁定短语，保留并补注）、驳回/降级其余 | 两审均「需改」→ 修复后两路自检 PASS |
| 契约同步 | 第 1 屏原型与现文案一致；「5 个硬闸门」改「4 个」；`确认激活` 口径与工具 required_phrase 对齐 | `test_novice_flow_contract` / `test_confirm_numbering` 全绿 |
| 全新电脑清单 | 新增 [docs/fresh-computer-checklist.md](fresh-computer-checklist.md)：Windows/macOS 两路逐步自检、失败对表、证据留存 | `test_cross_platform` 断言文件/README/INDEX 三处就位 |
| 第 3/6 步话术 | S5/S6/S9/S10/S11 去「审计/数量账/总账/锚点」等内部词；「未激活」补白话「发信开关没开」；48 封改「48 个邮件模板（12 轮×4 种写法）」 | 定向 21 项测试 OK；全量 558 tests OK |
| 三审 A·可读性 | S5 加「只存名单，一封邮件都不会发」；S5 分钟占位符改「保存时长」；S6 去「800+/验真/未知邮箱」；S9 去「30000/全账号/纽约/固定标签」，改「12 封邮件（12 轮）」+ 买家当地时间；S10/S11 去「总账」；黑话闸门补 3 个词 | 定向 119 tests OK；黑话扫描 0 命中 |
| 三审 B·契约回归 | 清单删「无 bash 跳过 onboard_check」，写明 AGENTS 硬门不可跳；wait_save_done 在 tools/README、tools/INDEX、onboard_check 三处标禁用；check_rules 空转测试改真实临时目录行为测试；[FAIL] 行为测试改 ASCII 并断言输出含标记；S5/S3 锁定加严；交付数字 556→557 | test_cross_platform 10 项 OK；全量 558 tests OK |
| 三审 C·跨平台边界 | 加「只有浏览器/不能跑命令 → 停」硬门；Windows 命令统一正斜杠；PYTHONUTF8 改 py -X utf8 / PowerShell / export 三种写法；WSL 的 bash 排除、走 Python 兜底；安装统一 bootstrap.ps1 -ExecutionPolicy Bypass；AGENTS 补 py；S12 两条激活路径口径拆分、时区改「按您确认的时区（默认纽约）」；模板索引改「回 1」；CI 加 python 入口 + Windows 非阻断冒烟 | test_cross_platform 断言清单无 tools 反斜杠；全量 558 tests OK |
| 全新电脑演练 | 完整仓库副本（含 runs/、重建 .git）跑 python3 tools/preflight.py → TOTAL_BAD 0 / PREFLIGHT PASS / 558 tests（本机 macOS，非实机 Windows） | 结果：EXIT=0；证据边界见 §7 |
| 首屏三审 D·可读性 | 第0屏：回复机制纠错（平台只给回复总数，您看到告诉我→我打「询盘」标记）、加「不用装任何东西」「平台额度」「一条消息回两样」、去「平台帮您找」；第1屏删「第 7 关」、授权信息=钥匙、顺利时 8 次、4 类买家；产品资料卡加来源列、术语统一「产品资料」、询盘引导改「只收公开网址」；公司资料卡改按需、不默认多占一轮；S11 不再二次索要激活 | 首屏定向 131 tests OK |
| 首屏三审 E·契约回归 | 黑话闸门加「档案/推演」；startup_gate 出口改白话并加测试（还差一步+昵称产品、不泄文件名）；onboard_check 旧中文卡名改英文现役；公司资料卡尾行补行动指引；契约测试加第0屏新口径、S11 单次激活断言 | 全量 558 tests OK |
| 首屏三审 F·边界 | 连接耗时统一 3–5 分钟；token 卡「只读检查」改「只做连接检查」；cross-platform 的 winget/Add-to-PATH 旧说法改 bootstrap.ps1 唯一入口；Windows 命令统一正斜杠；清单目录建议 C:/laifaxin | test_cross_platform 10 项 OK |
| 首屏三审证据 | 三审 D/E/F 均判「需改」→ 采纳约 35 条（含 5 条 S0 级事实/安全/费用：回复机制、存客户扣点闸门、账号钥匙等同密码、连接耗时、"8 项都填好了"不实） | 全量 558 tests / PREFLIGHT PASS；Windows 仍非实机 |
| 三审 G·第2/4步可读性 | S3 缺闭合围栏、S2 主块围栏错配（黑话扫描对两段失明）→ 补围栏并加「围栏必须成对」回归测试；S2 裸编号兼作选类型与看详情 → 看详情改「详情 2」；S3 缺 # 列 → 补；S4「抽样页面」改「看平台公司资料，不打开对方网站」、去 70% 改「像买家够多就继续翻」；S7 30 分钟锚点改「确认激活后」、签名给理由、旧信说明、分组名=语言-产品-买家类型、4 封样稿口径统一；S8 去「机器检查/逐对比较」 | 三审 G 判「需改」→ 全部 S1/S2 采纳；定向 130 tests OK |
| 三审 H·契约/工具一致 | finalize_audit.py 旧词（50页/三页平均）仍作必需项 → 只留 70%/逐页（窗口由 validate_audit_window 校验）；gen_templates.py 不识别已分组模板 → 去 folder 条件（S8 重跑可续）；S7 回「1」但审批工具拒纯数字 → 按 --state S7 接受「1」；契约引用 :653→:753；弱适配明示不建 48 模板；语言-产品-客群口径同步 RULES；4 封样稿口径同步 contract/beginner/S7 | 定向 130 tests OK；全量 561 tests OK |
| 三审 I·安全边界 | S7 价格红线写反（有来源即可写）→ 改「价格折扣一律不写，等对方回 PRICE 人工报价」；S2 把 AI 判断说成会买/回复快 → 表头「像不像买家（我的判断）」+免责；S2 补推不得改说法；S8 检查失败必须先停下并重新给样稿确认；S7「同一家公司最多12封」改「同一联系人」 | 三审 I 判「需改」→ 1 条 S0 + 10 条 S1 全部采纳；全量 561 tests / PREFLIGHT PASS |
| 余项清理 | 三审 H 余项闭环：find_critical/find_threshold/onboard_check 注释标注「历史参考、不作定界依据」；segments_infer --rounds 说明改为「4 轮推演请求，候选数以平台返回为准」 | 全量 569 tests OK |
| 缺口①人数硬对账 | [contact_add_authorized.py](../tools/contact_add_authorized.py)：S10 加人前强制 `contactSaveCount == 标签人数`，不等/缺字段一律 fail-closed exit 2 且不写平台；仅 `--allow-count-mismatch` 人工放行并留痕。新增 2 条回归（不等/缺字段都 0 写调用） | 三审 K/L 缺口闭环；定向 6 tests OK |
| 缺口②标签自动创建 | [build_sequence.py](../tools/build_sequence.py)：缺「询盘/不发」联系人标签时按 RULES 自动 `contacts/tags-add` 创建再重查，失败 exit 2 不建序列；dry-run 不写平台。新增 2 条回归（自动创建成功/创建失败阻断） | 三审 K 缺口闭环；定向 16 tests OK |
| 缺口③S7 数字确认 e2e | 新增 [test_s7_numeric_confirm.py](../tests/test_s7_numeric_confirm.py)：S7 回「1」可铸凭证；S2/S5/S9/S10 裸「1」一律拒绝 | 三审 K 余项闭环；3 tests OK |
| 旧信机器闸门 | 新增 [email_style_gate.py](../tools/email_style_gate.py)：样式文件只允许称呼/开场/段落/CTA/签名五项，价格/联系方式/认证/承诺即拒；gen_templates 生成前强制校验，**「旧开发信只学结构语气」由文档约定升级为机器闸门** | 新增 8 条测试；全量 569 tests / PREFLIGHT PASS |
| 三审 J·第③/⑥步可读性 | S9 同一张卡「加人」/「不加人」自相矛盾 → 改为「先建计划，一个人都不加，下一屏确认才加」；S9 暗示自动打「询盘」标 → 明写「平台只给回复总数，您告诉我谁回了，我打标；打标前邮件照发」；S9「慢周期只建少量几轮」与工具固定 12 轮矛盾 → 改为固定 12 轮、建议先不激活；S9「买家当地时间」与账号级单时区不符 → 明写默认美国东部时间、周一至周五；S5 补预计邮箱 E/预计扣点 P/预算上限 B 三行；S5 明示保存不可逆、只能用户手动删；S6「全部入库」改「确认 N→实存 X」；S10 补公司数→联系人数桥接与三个实际数字核对；S11 补设置核对五行、动态模板数、项目文件夹路径；“12 封/12 轮/12 步/第 7 关”统一为「12 轮（共 12 封）」+「发信开关」 | 三审 J 判「需改」→ 18 条全部采纳/改写；定向 116 tests OK；全量 569 tests / PREFLIGHT PASS |
| 三审 K·契约/工具一致 | S5 点数额度名实不符（computed.estimated_points ≠ budget_points）→ 卡片拆「预计扣点 P」与「预算上限 B」并标不确定性；S6 companySaveCount 是任务进度计数、非去重新增 → 改「确认 N→实存 X」并用 contactSaveCount 对账；S10 预印 ✅ 但工具未断言 contactSaveCount==标签人数 → 卡片改实际三数，AI 必须亲自核对（缺口入 §7）；flow_orchestrator 仍指向已封存的 save_first_n.py → 改 save_company_cli.py；S4 旧阈值提示 → 100页跳/连续5页窗口；S5 向导提示「前N=2000」解析不了 → 提示改「确认保存 前 2000 家」并兼容空格 | 三审 K 判「需改」→ 8 条 S1 全部采纳/3 条 S2 采纳；全量 569 tests / PREFLIGHT PASS |
| 三审 L·安全边界/费用不可逆 | S9 时区与「买家当地时间」冲突（S0）→ 改账号级时区+先确认再建；S9 慢周期承诺与固定 12 轮冲突（S0）→ 删承诺；S5 费用只写「约点数」→ 补「首批实测可能和估算有差、以平台为准」+预算上限 B；S5 保存不可逆未告知 → 已加；S6 部分成功无对照 → 已加 N/X 差额；S10 假 ✅ → 已改实际数字；S11 缺时区/上限/标签核对 → 已加五行；S6 1.4~2.1 无出处 → 改「约 1.5/家（历史批次，仅供参考）」；S6「用户问时才发」违背 S5 承诺 → 改「保存完成即发」 | 三审 L 判「需改」→ 2 条 S0 + 6 条 S1 全部采纳；全量 569 tests / PREFLIGHT PASS |

## 7. 已知边界（第二轮补充）

- Windows **未在全新实机跑完整业务流程**：CI 在 ubuntu 跑 bash/python 两个入口，windows-latest 仅有非阻断冒烟 job（continue-on-error，用于积累证据，不作验收门）；Windows 侧为静态适配 + 对表排障，首次实机安装需反馈 py tools/preflight.py 输出。
- 「全新电脑演练」是在本机 macOS 上用完整副本模拟（非 Windows 实机），只能证明干净副本 + 自检脚本可跑通，不能替代 Windows 实机验收。
- 第 0/1 屏本轮只做了话术 + 契约 + 机器断言验证，**未在真机对新用户首次对话做完整实测**（需真人回昵称/产品、按真实浏览器操作）；Windows 亦未完成实机验收。
- 三审 J/K/L 余项已闭环：①S10 人数硬对账已进 `contact_add_authorized.py`（fail-closed + 2 测试）；②`build_sequence.py` 已按 RULES 自动创建缺失「询盘/不发」标签（失败阻断 + 2 测试）；③S7 数字确认「1」已有端到端测试（3 tests）。
- 仍须知：S5 卡里的 E/P/B 由 `save_plan.py` 的 estimation 提供；计划文件缺字段时 AI 必须停下补算，不得填假数。
- 本轮新增文件（`.gitattributes`、`tools/preflight.py`、`tests/test_user_visible_jargon.py` 等）仍是未跟踪状态，提交时须 `git add`，不能只用 `git commit -a`。

## 5. 已知边界

- 锚点：GitHub 同名标题去重后缀已覆盖；自定义 HTML 锚点仅支持 `id`/`name`。
- INDEX 描述语义真实性：机器只查格式、重复、覆盖；真实性靠 `--sample-index` 人工抽检。
- CI：工作流文件已就绪，推送后才会真正运行。
- 提交/推送钩子每次约 65–70 秒；应急用 `SKIP_PREFLIGHT=1`，发布前必须完整跑一次。

## 8. 第三轮：第 7 关「发信开关」三审（2026-10-23 下午）

三路独立对抗审查（新手可读性 / 契约-测试-工具一致 / 安全边界-费用-不可逆）均判「需改」；本轮先修可立即闭环项，其余登记为 §9 边界。

### 已采纳并落地
- **S12 卡重写**（可读性 S0/S1）：第一屏先给「一句话结论 + 激活后果」，再给「这次发多少（本批人数 M、每人 12 封、最多 M×12 封、首封约 30 分钟、窗口 8:00–17:00 + 北京时间换算）」；删「放心/推荐/别为难自己/效果一样」，两种方式并列；方式二只让用户开开关、不让用户数 12 轮；定义「回 2 = 先不发（计划保持关闭，一封不发）」；补失败路径「计划保持关闭，一封不发」；去 inactive/回滚/额度/发送主体/拒收机制等内部词；产品资料按 confirmed/跳过分别表述。
- **确认口令误杀（可读性 S0 / 契约 S0）**：[approval.py](../tools/approval.py) 去掉「不/考虑」整句子串黑名单，改为明确否定/拖延短语；「确认激活 不锈钢-S04」「我考虑清楚了，确认激活」放行，「先别激活/再考虑一下/取消激活/确认激活吗」拒绝；新增 [test_confirm_numbering.py](../tests/test_confirm_numbering.py) 3 条真实词组回归。
- **注意：本 S0 在真实业务里会把「不锈钢」类产品卡死；已复现并修复。**
- **resume-s12 与 activate 口径统一（契约 S1-3/S1-4）**：[flow_orchestrator.py](../tools/flow_orchestrator.py) 拒绝「确认激活，但先别」等保留句；record 缺 sequence_id 不再短路放行，与 activate 一样视为不一致。
- **激活写后回读三态（安全 S0-1）**：[activate_sequence.py](../tools/activate_sequence.py) 不再用「接口 success=false」直接断言未激活；写后强制回读，active=成功 / inactive=明确未激活 / 未知=标记「异常阻断」并提示先停发。
- **停发不再被状态锁死（安全 S0-3/S2-3）**：--deactivate 允许 S11/S12/异常阻断状态，执行前补 workspace_guard（落点校验）。
- **回归测试**：[test_user_facing_copy.py](../tests/test_user_facing_copy.py) 新增 S12 卡 7 条（真实后果/时区/12 轮/两条路径/回 2 解释/回复不自动停/围栏成对）与 48 模板≠48 封、S7/S8 主题正文、围栏成对；三审 A/B/C/J/K/L 既有测试保持全绿。
- **证据**：python3 tools/preflight.py → TOTAL_BAD 0 / 587 tests OK / PREFLIGHT PASS（2026-10-23）。

### 三审提出、本轮未闭环（见 §9）
- 发送上限 30000/5 仍只写平台规则、未从 rules 实读断言；标签只验形状不验「询盘/不发」身份；12 步模板只验 id 形状不验模板库归属；方式二 sync-manual 只补话术未跑完整只读闸门；审批凭证未消费/未过期；核实面板仍只验关键词；S11 仅认状态字符串不验 manifest；激活路径 workspace_guard 未判定时仍 fail-open。

## 9. 已知边界（第三轮补充，交付必须带）

- **上限/标签/模板归属未闭环**：激活前 check_sequence_structure 只验 rules 非空、notSentTags 形状、12 步 template_ids 形状；未读 max_emails_per_day/domain_emails_per_day、未解析标签名、未比对模板库归属。因此 S12 卡面不能把这三项说成「工具已核验」；当前卡面已改「平台规则」，AI 要点仍要求人数对账。
- **方式二仍少一道自动检查**：--sync-manual 只做 record 状态、seq 一致、workspace 落点、平台 active 回读；未跑 compliance/profile/12 步/标签/上限。卡面已改为「方式二少一道自动检查」，但工具侧完整只读闸门留待下一轮。
- **审批凭证可复用**：activation 成功后未消费 approval，deactivate 后 72h 内理论上可用旧凭证重开；需 next round 加 used_at/TTL。
- **S11 状态仍是字面量**：resume-s12 只认 record.status=="S11"，不校验 live manifest 收口字段；正常工具链仅 finalize_run 能写 S11，属纵深防御缺口。
- **Windows 实机未验收**：三轮所有测试均在本机 macOS 跑；Windows 为静态适配 + CI 非阻断冒烟，首次实机仍需用户反馈。
- **第 0/1/2/3/4/6 屏真人首测未做**：本轮为话术/Bot 契约/机器断言验证，不等于真实新手首次对话验收。
- 未提交/未推送：分支 novice-onboarding，所有改动保持工作区未跟踪/未提交状态。


## 10. 第三轮收尾：第 7 关工具闸门已闭环（2026-10-23 下午）

§9 中「上限/标签/模板归属未闭环」「方式二少一道自动检查」「审批凭证可复用」三项已在本轮补齐，其余边界仍有效。

- **结构闸门实读**：[activate_sequence.py](../tools/activate_sequence.py) 的 check_sequence_structure 现在：①读 rules 断言 max_emails_per_day==30000、domain_emails_per_day==5；②拉 contacts/tags-list 解析 notSentTags 名称必须是「询盘」「不发」；③拉 step-list 与 mailbox/templates-list，断言 12 步模板都在模板库、步长 30分/5天/15天/30天；任一读失败/不符一律 exit 2，不写平台。
- **方式二同闸门**：--sync-manual 回读 active 后先跑同一结构闸门，不通过标异常阻断并提示先停发，不写 S12。
- **凭证一次性**：[approval.py](../tools/approval.py) 新增 approvals-used 账本，激活成功后登记；复用旧凭证再次激活 exit 2。
- **只读预检入口**：新增 activate_sequence.py --check-structure（只读、不激活、不写状态），可单独做激活前预检。
- **回归**：新增 [test_s12_activation_gates.py](../tests/test_s12_activation_gates.py) 6 条（上限错/标签身份错/模板不在库/标签读取失败/通过/凭证一次性）；全量 593 tests OK / PREFLIGHT PASS。
- 仍有效边界：Windows 实机未验收、真人新手首测未做、S11 只认状态字符串、激活路径 workspace 未判定时 fail-open、S5 的 E/P/B 依赖 save_plan estimation；这些不影响本轮闸门闭环，但交付时必须继续标注。


## 11. 第四轮：S11 收口证明与落点 fail-closed 已机械化（2026-10-23 晚）

§10 末尾「S11 只认状态字符串」「激活路径 workspace 未判定时 fail-open」两项已在本轮补齐。

- **收口证明**：[finalize_run.py](../tools/finalize_run.py) 成功收口时写入 s11_finalized_at（ISO 时间）与 s11_manifest_sha256（verification manifest 文件字节 sha256）；新增 [s11_closure.py](../tools/s11_closure.py) 统一校验（缺字段/格式错/超 24 小时/来自未来一律拒绝）。
- **签发与激活都校验**：[flow_orchestrator.py](../tools/flow_orchestrator.py) 的 --resume-s12 与 [activate_sequence.py](../tools/activate_sequence.py) 的激活/方式二同步都先校验收口证明；手写 status: S11 不能签发、不能激活（exit 4）。
- **落点 fail-closed**：[workspace_guard.py](../tools/workspace_guard.py) 的 preflight(require_verified=True) 在平台未返回判定时直接拒绝（exit 5），激活/同步/停发三处均启用；仅测试进程（unittest 或显式测试标记）放行，生产不可继承。
- **回归**：新增 [test_s11_closure_gate.py](../tests/test_s11_closure_gate.py) 5 条 + [test_workspace_verified_gate.py](../tests/test_workspace_verified_gate.py) 4 条 + [test_s12_activation_gates.py](../tests/test_s12_activation_gates.py) 追加 2 条（手写 S11 两种形态拒绝）。
- 仍有效边界：Windows 实机未验收、真人新手首测未做、S5 的 E/P/B 依赖 save_plan 估算；这些不影响本轮收口/落点闭环，交付时必须继续标注。

## 12. 第五轮：真人首测（第 0–4 屏）与边界话术补齐（2026-10-23 晚）

以零技术外贸老板视角走第 0→4 屏，按真实回复模拟（只答一半、回数字、只有 Safari、拒绝连接、平台只给一家样板、产品照片代替文字），发现 5 个会让人卡住或让 AI 空转的缺口，已补话术并用测试锁死：

- **第 0 屏只答一半/回「1」**：新增 C1c 分支（只补缺的那一样；数字/问候不算昵称，不得登记成昵称）；beginner-flow 第 0 屏后同步说明。
- **只有 Safari 的 Mac**：连接平台卡补 Safari 兼容路径（装 Chrome 最省事，或开 Safari 开发者功能），不再默认用户一定有 Chrome/Edge。
- **用户说「先不连 / 不想连」**：连接卡补明确分支（说明为什么必须连 + 1=现在连 / 2=先看流程，停下等，不跳过推演、不反复催）。
- **平台只返回一家样板客户**：S3 之前只写「回 2 换一个」，只有一家时用户无路可走；补「回 1 用它 / 说『再找一轮』/ 发我网址」分支，禁止空转。
- **审计时长空口承诺**：S4 补规则——没跑完第一批前不说总时长，先给第一批 1–2 分钟，再按实测速度报区间。
- **产品照片/链接代替文字**：产品资料卡补「先复述产品请用户确认，不要求改发文字；看不清的参数标暂无」。

回归：[test_novice_edge_cases.py](../tests/test_novice_edge_cases.py) 6 条；全量自检 PREFLIGHT PASS。
仍有效边界：本次是 AI 按文档模拟，不等于真人首次对话验收；Windows 实机、真人首测仍待做。

## 13. 第六轮：真人首测（第 5–7 屏）与边界话术补齐（2026-10-23 晚）

继续以零技术老板视角走第 5→7 屏，重点模拟「模板建一半失败」「嫌 12 轮长」「想只加一部分人」「提前说确认激活」「最后屏回 1」五个真实场景，发现并修复：

- **S8 失败重跑会不会重复建**：用户最怕「建一半失败再建一遍会不会多出一堆模板」。卡片补「已建成功的复用、重跑不重复建、只补失败的那几个」（工具本来就幂等，之前没敢跟用户说）。
- **S9 想先小范围试**：原话只写「12 轮固定、改不了，建议别激活」，等于死胡同。补真实路径：照 12 轮建，激活后跑完第 1 轮就让我停发；停发只停后续，已发追不回。
- **S10 想只加一部分人**：加人工具没有部分加入参数。卡片补「只能整批加入本批名单；想少加请在存客户那步少存，或先别加、按标签拆开」，避免口头答应后照旧全加。
- **提前说「确认激活」**：在第 5/6 步说这句话时，原文档没规定怎么回，AI 可能被带跑。流程补固定回应「还没到发信那一步，开关不会开；完成设置我再问」，不跳过、不提前激活、不催。
- **S11 回「1/好的」不等于激活**：用户前面一路回 1，最后屏很可能习惯性回 1。卡片补「回 1 或好的也不会开开关；真要发请回确认激活四个字」，AI 也要明说。

回归：[test_novice_late_stage_edges.py](../tests/test_novice_late_stage_edges.py) 5 条；全量自检 PREFLIGHT PASS。
仍有效边界：仍是 AI 按文档模拟，不等于真人首次对话验收；Windows 实机、真人首测仍待做。

## 14. 邮件格式口径统一：HTML 是载体，不是「营销式 HTML」（2026-10-23 晚）

用户追问「邮件不是 HTML 吗？CTA 不该显眼吗？不需要 emoji 吗？」——此前把「禁营销式 HTML」压缩成「禁 HTML」是错话，已统一口径并锁进测试：

- **S7 卡新增「邮件格式白话口径」AI 备注**：邮件本身是 HTML，但只保留普通文字+加粗；不放产品大图/彩色按钮/背景色/外链/追踪图；CTA 显眼靠独立成段+放最后+关键词加粗；emoji 0–1 个且仅品类适配；正文 ≤120 词，关键数字必须真实有来源并加粗 2–4 处；用户要求加图/附件/链接/花哨排版时按固定话术回「等对方回信再发」。
- **澄清 preview.html 的黄色高亮/蓝线只是本地预览标注**，不会随邮件发出；真实模板只有加粗。
- **docs/07 旧教程置顶纠偏**：明确「格式口径以 specs/sequence-config.md 为准」，列出已作废的旧做法（HTML 列表、彩色 span 高亮 CTA、每封 emoji、8 轮×4=32、6~12 轮随机），并把彩色 span 高亮段落直接改写为现行加粗口径，避免 AI 照旧教程生成高风险邮件。

回归：新增 tests/test_email_format_doctrine.py 3 条；全量自检 PREFLIGHT PASS。
边界：这是规则/文档口径统一，不是投递率保证；真实送达仍受平台通道与收件方策略影响。

## 15. 垃圾邮件触发词清单 + 看数据五问话术（2026-10-23 晚）

用户要求「结合之前遇到的问题和用户问题截图继续对抗完善，触发词清单可以完善下」，本轮落地：

- **sequence-config 新增「★垃圾邮件触发词清单」三级**：
  - A 类硬禁（free sample / free trial / act now / limited time / click here / buy now / !!! 等 21 条），生成器扫描标题+正文+轮次句，命中列出词并 exit 2；
  - B 类慎用（guarantee / best price / 促销 / 免费 等，不进硬门，AI 写作主动避开）；
  - C 类已有规则覆盖（价格、全大写、emoji、首封链接、彩色 HTML）。
- **tools/gen_templates.py 新增独立 check_spam_words() 预检**：放在四要素预检之前，避免垃圾词报错被其他违例的「只显示前 10 条」截断（首个实现踩过这个坑，已改）。
- **S7 AI 备注新增「写作时直接避开垃圾词」**，不让 AI 写完才被生成器打回。
- **S12 新增「用户看数据时最常问的 5 句」**：对方说没收到（先翻垃圾箱/点不是垃圾邮件；先查地址是否失效，不直接拉黑）、是不是进垃圾箱、退信多是不是域名坏了（20% 以内正常、超过 30% 才查内容、发信环境平台负责）、打开率低是不是发失败（看回复，48 小时再判断）、硬退回能不能重发（标不发，重发须换主题和内容）。
- **统一退信口径冲突**：S12 原来「>10% 就关开关」与 SKILL「20% 正常」矛盾，最终改为「>10% 跟我说；20% 以内正常；20–30% 先查内容、暂不停发；超过 30% 先停发（只停后续）再查内容，关前告知」。

回归：tests/test_spam_trigger_words.py 4 条静态断言 + test_template_generation_gates.py 新增 SpamWordGateTest 5 条真跑 e2e（标题/正文/!!! 命中 exit 2、clean 不误伤）；全量自检 PREFLIGHT PASS。
边界：清单是启发式，不保证投递率；A 类只做短语匹配，避免误伤 100% cotton 这类正常产品词。
## 16. 多轮对抗审查：垃圾词门 4 缺陷 + 话术 7 发现（2026-10-23 晚）

用户要求「上边的问题对抗审查完善，要多审」。本轮做了三遍：作者自攻 + 两名异厂独立审查（gpt-6.1-sol 审生成器、GLM-5.3 审话术），全部只读；作者逐条复现、修复、补回归。

**生成器 4 项（均已修 + 回归）**：
1. ⚡ 无词边界误伤：contract now 被 act now 硬拦 → 改为前后不得紧邻字母/数字的词边界匹配；紧凑匹配只要求前边界，兼顾 clickhere 连写与误伤。
2. ⚡ 实体/Unicode 绕过：click 实体、cl 实体、全角、U+2060、Unicode 连字符 → 归一化顺序改为 HTML 实体解码 → NFKC → 去标签/零宽 → 连字符转空格；补 5 条 e2e。
3. ⚡ 签名漏扫：昵称可填 Congratulations 且直出渲染 → check_spam_words 增加 SIGN 扫描；补 e2e。
4. ⚡ 报错被遮蔽：事实门/去重门先退出，垃圾词不报 → 垃圾词预检提前到事实/去重之前；价格测试与 clean 用例全部回归。

**话术 7 项（均已修）**：
- SKILL 与 S12 退信阈值「超过 30%」vs「连续超过 30%」不一致 → S12 去掉「连续」，与用户拍板口径对齐；
- 「对方说没收到」直接打「不发」会误杀线索 → 改为先查地址是否失效，失效才标不发，只是没看到先不标；
- 「连续 >30% 我关开关」补「关之前我会立刻告诉您一声」；
- 「>10% 说一声、20% 以内正常」拆分表述；
- 补第 5 问「退回去的还能再发吗 / 换标题行不行」；
- docs/09 诊断漏斗「名单/通道问题」改为「名单质量问题（通道由平台负责）」；
- sequence-config A 类旁补「R12 别直译 last chance，用 closing note / final follow-up」。

证据：生成器 e2e 34 条、静态口径 4 条；全量 PREFLIGHT PASS（TOTAL_BAD 0）。
边界：审查为静态 + 本地 e2e，不含真实平台发送；投递率仍不作保证。

## 17. 第二轮对抗审查（S7-S12 话术/跨文件一致性）：1 项严重 + 7 项一般 + 2 项建议全修（2026-10-23 更晚）

两轮独立审查（GLM-5.3 新手视角、gpt-6.1-sol 跨文件一致性）+ 作者自审；审查期间文件并行修改，以下均按修后现态复核。

- 严重：S12 激活失败不再保证「计划关闭、一封不发」；改为三态——只有回读 inactive 才说没发，回读 active 先停发并核对，状态不明先按停发处理、确认后回报。
- 一般：48 小时止损口径统一为「≥3 扩量、1-2 方向成立继续、连续两轮 0 才止损」，S12/docs09/SKILL 一致。
- 一般：docs09 诊断表删掉「通道信誉」类平台技术动作、打开率仅作参考；补「单批 ≥3000 封再看打开率/回复率，量不足先加量、不先换行业」。
- 一般：「调低轮次」旧建议全部清除（SKILL/docs09/RULES/README/output-templates README 统一为固定 12 轮、不承诺改轮次；先不激活或人工低频）。
- 一般：S12 时区改占位符、不硬编码纽约；30 分钟承诺限定「发送窗口内」；S9 写明时区是账号级统一设置、改前先确认。
- 一般：回信与打标口径统一「平台不自动识别回复人 → 您告诉我名字 → 我代打『询盘』并核对生效」，去掉「我做不到」误导。
- 一般：用户出口去技术词——SKILL 退信短答删「域名和 IP」，S12 自查行改「已确认/已核对」白话；S7 补用户问图片/按钮/链接时的白话答法，不出现 HTML/CTA/标签词。
- 一般：R12 旧正例「Last chance」改 closing note / final follow-up；样稿数量统一默认 4 封、用户主动要看最多 8 封。
- 建议：docs07 第三～六部分标为历史参考，可复制指令以 sequence-config 为准；旧加粗/轮数示例加注。
- 建议：delivery-notes 与 tests/INDEX 的「四问」改「五问」。

回归：定向 128 条通过；全量 PREFLIGHT PASS（TOTAL_BAD 0）。边界：静态+本地审查，不含真实平台发送，投递率不作保证。

## 18. 修后冻结版本核验（两名独立审查员 + 机器门禁，2026-10-23 晚）

**流程**：修复完成后冻结文件，再请两名非作者独立审查员对冻结点复核；作者在此期间不再改用户可见文案，只补测试与交付记录。

**第一轮复核（发现残留后修复）**：两人共指出 6 项部分关闭 + 1 项新矛盾——
- S12 失败三态仍未区分「当前已关」与「历史是否发过」→ 改为回读没开只说明当前已关，是否发过另查发送记录，查不到说暂不能确认；
- README/FAQ 入口仍按「连续两轮不达标」止损 → 统一为「1–2 个方向成立继续、只有连续两轮 0 个才止损」；
- docs09 诊断表仍越过唯一诊断顺序 → 重写为退信分级（20% 内正常、20–30 先查内容、>30% 先停发）、发送量 ≥3000 前提、打开率仅参考、不直接换行业；
- 30 分钟承诺只在 S12 有限定 → S7/S9 同步改为「允许发送窗口内，窗口外/节假日顺延」，并删「最长等到下周一」；
- S7 内部格式说明与用户白话答句并存 → 标注「仅 AI 内部理解，禁止照抄」；
- 样稿数量口径 SkILL/node-playbook 未完全统一 → 统一「默认 4、最多 8」；
- docs07 第七部分未纳入历史区、旧加粗示例无作废注 → 整段标历史并逐条加注；
- S12 新增 20–30 区间后与另一处两区间矛盾 → 两处统一三区间（25% 退信同动作：先查内容、暂不停发）；
- 数据可见与上限表述软化为「以平台实际更新为准」「这是上限，按本批人数排程发」。

**第二轮冻结版复核结论**：两位审查员均明确「修后冻结版本可交付」；S12 逐条 5/5 无回退，跨文件指定项全部关闭，本轮范围内无可复现反例。

**机器结果**：全量 PREFLIGHT PASS，641 条测试，TOTAL_BAD 0；新增 4 条回归（失败三态、退信三区间、30 分钟窗口条件、入口止损统一）。

**边界**：审查为静态 + 本地测试，不含真实平台发送；投递率/进箱率不作保证；改动未提交、未推送。

## 19. 2026-10-24 · docs/14 三轮复核与修订记录

对象：docs/14-novice-walkthrough-demo.md（新手全流程模拟演示）。

### 19.1 独立审查（只读，均未改文件）

| 视角 | 角色 | 首轮结论 | 复核结论 |
|---|---|---|---|
| 老板/新手可读性 | 独立审查员 A | 4🔴 + 9⚡ + 5💡 | 4🔴 全关；修掉重写引入的转义反引号后可交付 |
| 跨文件一致性 | 独立审查员 B | P1–P7 需修 | P1/P4–P7 关闭；P2/P3 必展项与 5 处小修 |
| 红队/攻击 | 独立审查员 C | 4🔴 + 13⚡ | 2/3/4 关闭；#1 残留状态窗口；A–G 最小关单集 |

### 19.2 本轮修复（对应意见）

1. 重写引入的 154 处「反斜杠+反引号」全部还原为反引号（代码块/mermaid 正常渲染）。
2. 激活双路径口径：方式一「确认激活 + 计划名」；方式二「我已在网页激活 + 计划名」；用户只说「已开/激活」先回读再补计划名；删除「确认激活四个字」兜底。
3. 连接三层降级补粘贴位置（终端/PowerShell）、Safari 路径、allow pasting；「保证任何电脑」改「覆盖常见 Windows/Mac，走不通换方式或找客服」。
4. 0 屏承诺改为「装的时候不用您动手；连账号、开发信开关两步要您点一下」。
5. S5 补：本批买家类型、临界来源（审计页）、3600 点为估算上限、2600→2480/3210 落差话术。
6. S10 三数对账改为用户可见一行；S11 补项目文件夹、下一屏激活口令指引。
7. S7/S12 用户卡补 12 轮×4=48 模板、同人每轮 1 封最多 12 封、38520 分 12 轮约 9 个月发完；术语白话（发送时间段/5 项检查都过了/加量）。
8. 环节 8 补卡首行；3000（判退信样本线）与 5000（当天看趋势）按用途分开写；退信 10–20% 档前移；小范围试标注 <3000 不能判断回复率。
9. 第 1 屏补六步文字样张；总规则「花钱/真发信只认原话」前移；多客群成本去乘法；6B/6C 数字清理（2480/3210）。
10. 跨文件：S7-template-confirm.md:16「30 分钟后」→「30 分钟内」；SKILL.md:232 保存授权须含「确认保存」四字 + 家数。

### 19.3 机器门禁

python3 tools/preflight.py：645 tests，TOTAL_BAD 0，PREFLIGHT PASS（2026-10-24）。新增回归：演示稿禁转义反引号、禁旧数字、S7/S9/S12「30 分钟内」一致、SKILL 保存原话、演示稿双激活口令。

### 19.3.1 附：测试时间炸弹修复

推送前发现 5 个测试文件把 S11 收口时间硬编码为 2026-10-23T10:00:00，超过 24h 窗口后会让 bash tools/preflight.sh 在任意电脑上失败（pre-commit/pre-push 钩子会拦）。已改为运行时生成 NOW_ISO（test_compliance_evidence_mode / test_sequence_closure_hardening / test_s12_adversarial / test_s12_resume），并重跑全量 647 测试通过。

### 19.4 边界

本轮为文档/话术/契约与测试层验证，未上真实平台发送、未在 Windows 真机执行；平台发信环境（SPF/DKIM/DMARC、域名/IP、预热）由平台负责，效果不承诺。所有改动未提交、未推送。
