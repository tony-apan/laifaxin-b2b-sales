---
title: "代运营完整 SOP（规则细化）"
description: "代运营全流程规则：时区灵活映射/点数预算公式/单页筛选标准/标签规则/网址找相似确认流程/推演固化"
created: 2026-08-21
updated: 2026-10-21
author: "AI Agent + 运营方"
source: "对抗分析 + 用户要求细化"
related: [specs/data-structure, specs/sequence-config, docs/08-workflow-ops]
tags: [SOP, 代运营, 规则, 预算, 时区]
status: verified
audience: 人+AI
---

> ⚠️ **布局注记（2026-08-30）**：档案/存储布局以 `runs/<运营方>/<产品>/` + 本地运营方档案（`.local/operators/<operator_key>.md`，不入 Git）为准（RULES「多公司/多产品」）；本文下文的 laifaxin-ops/clients 等目录为**设计参考/未实施**，勿按此建目录。

# 🏭 代运营完整 SOP（Operations Standard Operating Procedure）

> **目标**：把代运营的每个决策点写成**可执行的规则**（不靠临场判断），数据全程留痕。
> **原则**：规则写死 + 灵活点留白（时区按客户语言） + 预算公式化 + 操作先确认。

---

## 一、项目初始化（签约客户）

### 1.1 渐进收集并分层回落客户资料
> 现行规则：开局只问纯个人昵称 + 一句话产品（目标市场可选），不要催 token；进入 S0a 后分两轮主动索取（均可跳过、不逼问）：公司名/官网/默认市场→`.local/operators/<operator_key>.md`（不索取邮箱）；产品线/卖点/认证/产能/MOQ/交期/价格带→当前 `product-profile.md`。完成产品了解与适配判断、首次调用来发信平台前，再一键双取 token + 当前工作空间 orgId；token 中段用户 UID 不得当企业 orgId。潜在买家/联系人第三方资料不索要；邮箱不索取（平台不支持绑定自有邮箱）；邮件末尾签名区只有昵称。详见 `operator-profile-sop.md` 与 `product-profile-sop.md`。
| 资料 | 回落位置/规则 |
|------|-------------|
| 公司名称 / 官网 / 默认市场语言 | `.local/operators/<operator_key>.md`；跨产品复用，换机随 `.local/` 迁移 |
| 产品线 / 卖点 / 认证 / 产能 / MOQ / 交期 / 价格带 | `runs/<operator_key>/<product_key>/product-profile.md`；逐字段 source/confidence，确认后版本/hash锁定 |
| 来发信 token / orgId | 用户在浏览器一键复制后，把带字段名的两行整段直接粘贴到当前主 AI 聊天框；仓库工具不主动回显原始凭据，不写 `.env`/持久环境变量/工具日志，不向子代理扩散；用户明示授权后，仅允许本机 `.local/session-credential.json` 保存会话凭证（目录 0700、文件 0600、用 `--forget` 清除、备份与迁移必须排除）。该文件不是安全边界，真正防线是远端校验：每进程首次复用须通过 `check_login` 与 `workspace_guard --require-verified`。主 AI 通过程序化 stdin 检查。聊天服务留存取决于宿主隐私政策 |
| 潜在买家/联系人资料 | 由平台搜索/保存流程产生，不要求用户提供，不写入 operator/product profile |
| 点数预算 | S5 确认材料/operation-record，决定保存规模 |

### 1.2 用户网址走独立可选增强模块
用户提供网址时，先按 `website-profile-sop.md` 确认角色：
- 自己的公司官网/产品页/目录 → AI 只读公开页，生成六区候选；用户批准补丁后才分别导入公司或产品正式档案
- 买家/老客户/询盘方网址 → 转 S3 种子，不进入用户档案
- 竞品、平台页、行业文章 → 只做分析，不成为用户公司事实
- 无法确认 → 只问一次用途，未确认前不导入

> ⚠️ **独立边界**：网站模块失败、网页打不开或用户跳过，不修改正式档案和 operation-record，不阻断原 S0/S0a；不自动修改线上网站。成功导入产品补丁后回到 draft，仍须按现有 product-profile 确认流程生成版本/hash，才往下走。

---

## 二、时区规则（★按客户语言灵活映射）

**默认时间 = 客户目标市场语言对应时区**（不是死板美国时间）：

| 目标语言 | 时区 | schedule 建议 |
|---------|------|--------------|
| 俄语 | **莫斯科（Europe/Moscow UTC+3）** | 自定义或找对应模板 |
| 西班牙语 | 马德里（Europe/Madrid UTC+1）/ 拉美可问 | 马德里/洛杉矶 |
| 英语（美国客户） | 美国纽约（America/New_York） | 运行时 `tools/resolve_schedule.py --tz "America/New_York"` 解析（本租户快照 `<scheduleId>`） |
| 德语 | 柏林（Europe/Berlin UTC+1） | 系统创建 |
| 法语 | 巴黎（Europe/Paris UTC+1） | 运行时 `--tz "Europe/Paris"` 解析（本租户快照 `<scheduleId>`,2026-08-30 实测） |
| 葡语 | 巴西圣保罗 | 运行时 `--tz "America/Sao_Paulo"` 解析（本租户快照 `<scheduleId>`,2026-08-30 实测） |
| 日语 | 东京（Asia/Tokyo UTC+9） | 自定义 |

> **规则**：语言→时区映射表 + 客户确认（拉美西语用马德里还是墨西哥？）。
> **执行**：查 `schedule-list` 选模板，或创建自定义 schedule（time_zone + time_windows + skip_holidays）。
> ⚠️ **schedule_id 各账号不同，禁止硬编码**——建序列前必须 `tools/resolve_schedule.py` 运行时解析；下表仅为**本租户(<orgId>)快照**：
> **★ 2026-08-30 实测 schedule-list 共 7 个**：纽约 `<scheduleId>`(isDefault✅) / 巴黎 `<scheduleId>` / 伦敦 `<scheduleId>` / 洛杉矶 `<scheduleId>` / 巴西圣保罗 `<scheduleId>` / 美国Denver `<scheduleId>`(废弃) / Asia/Shanghai `<scheduleId>`。

---

## 三、AI 推演固化（segments.md）

1. 用产品词/业务描述词建产品档案（product profile 越详细越准）
2. `inference-segment-generate` 推演客群
3. **固化到 segments.md**：每个客群的 `segment_name / value_path / ai_reason / query_en(英文搜索词) / query_total(覆盖量)`
4. 选**最直接的买家客群**（Path B 流通与代理优先）
5. 客群不准 → 编辑产品方案 → 重新推演

**固化字段**：
```markdown
## 客群 1：宠物食品与用品专业分销商
- 价值路径: Path B 流通与代理
- 推荐理由: ...
- 英文搜索词: Pet supplies distributor supplying wholesale...
- 覆盖量: 10000
- 是否选用: ✅（最直接买家）
```

### 3.1 ★多客群分批执行 SOP（2026-09-09 用户拍板：允许分批、接受成本翻倍）

**铁律（`RULES.md` 7d）**：每个被选中的客群**独立成档**——独立一对标签、独立一套模板、独立一条序列；**禁止合并**。

**为什么必须分开**：
- 不同客群采购需求与痛点不同，共用一套话术必然打偏（保温杯混存案例：3 客群共用 1 个标签 `英语-咖啡器具与保温杯-渠道商` + 1 套模板）。
- `threshold-method` 要求直采/OEM/拓品**分线计数**，OEM/拓品线索不进本池匹配率与保存范围——合并标签等于废掉这条防线，制造商会被打进经销商池收错话术。

**正确样例（皮筏艇，3 客群 3 档）**：

| 客群 | 标签 | 模板批次 | 序列 |
|---|---|---|---|
| <客群A：如 景区运营商> | `<tagA(名称)>` | <批次前缀A>（48，运营商角度） | `-S04` |
| <客群B：如 装备批发商> | `<tagB(名称)>` | <批次前缀B>（48，经销利润/MOQ/条款） | `-S05` |
| <客群C：如 装备零售商> | `<tagC(名称)>` | <批次前缀C>（48，零售上架/动销/小单） | `-S06` |

**执行顺序（严格串行）**：

```
对每个选中客群，按用户确认的顺序依次走完整条链：
  S3 选起点 → S4 审计（该客群客户线）→ S5 保存（该客群专属标签）
  → S7/S8 生成该客群整批模板(默认48) → S9 建该客群序列 → S10 加该客群联系人
一个客群全部走完，再做下一个；不得并行铺开、不得合并写操作。
```

**确认节点必答项**：
- S2 选中 ≥2 个客群 → **必须**提示"建议分开做"并给出"先做 1 个 / 都做（分 K 批）"；如实告知成本 K×48 模板 + K 条序列（默认每套48=12轮×4）。
- S5/S7/S9 每张确认卡标题必须写「<客群名>（第 i/K 批）」。
- 标签名必须带该客群自身角色；禁止把多个客群拼成一个标签名。
- 序列名带客群档位后缀（`-S04`/`-S05`…），与标签、模板前缀三方呼应。

**落档**：用 `python3 tools/segment_select.py --record <record> --segments "S04:客群名,S05:客群名"` 写入 `operation-record.md` 的「客群」行（只允许 S1/S2/S3 状态；`--dry-run` 可预览），并在 `segments/<ID>-<客群名>.md` 各档登记（含 标签/保存/序列 三列），禁止只在对话里记。

**例外**：用户明确说"这几个客群本质是一类买家"并书面确认 → 允许合并，但必须在 record 里写明合并理由与合并范围（默认仍禁止）。

---

## 四、网址找相似（★用户给了精准网址）

### 流程（含确认步骤）
```
客户提供精准客户网址
    ↓
① 我提炼网址信息（domain/base-info → 行业/产品/NAICS）
    ↓
② ★与用户确认："用这个网址找相似？目标客群是这样吗？"（用户要求确认！）
    ↓
③ 确认后执行：
   - S3 先用当前轮 query_en **逐字**找候选；代表买家 id → `domain/base-info` 取真实域名并落选择记录
   - S4 用**已选域名**作 keyword 走 `refine/company-list` 海量扩量；用户自带网址走“原始来源→规范化域名→同客群关联→确认”分支，不捏造平台 candidate id
   - ⚠️ `domain/similar-list` 仅属旧接口能力，本流程不使用；需要多个域名任务时另行确认，不把历史 `tasks/create` 示例当现行主路径
    ↓
④ 审计精准度（连续5页窗口）→ 找 70% 边界 → 确定保存范围；S5 沿用同一 keyword/filters/logic/sort
    ↓
⑤ 记录到 seeds.tsv（已用/待用）
```

> **确认原则**：客户给了网址 → **先展示"我将用它找相似，目标客群是XX"** → 客户确认 → 执行。避免客户提供的是自己公司网址（那是提炼产品，不是找相似！要区分）。

---

## 五、连续5页窗口标准（★保存前必做；2026-10-21 V2）

**按连续5页滑动平均判定，不是单页也不是累计**：

| 连续5页均值 | 判定 | 动作 |
|-----------|------|------|
| ≥70% 且逐条语义/独立review完整 | ✅ 可保存 | 不再按材质/规模二筛 |
| <70% | ❌ 往前收 | 单页跌破只记抖点；不换“更准种子”来掩盖窗口 |

**执行**：
1. 抽查前 1~5 页 + 末尾几页（每页10条，逐条看本页语义/客户线）
2. 用审计工具（audit_company.py 规则表）做趋势初筛；工具 confidence/High 比例不是精准度
3. 用连续5页窗口找边界：窗口均值跌破70% → 往前精确；页1/2/5抽样不能宣称边界已到
4. 排除中国区（CN/TW/HK/MO 默认；filters 完整 schema）
5. **记录到 search-log.tsv**（窗口页/均值/判定/边界）

### 保存入口（V2 预期；实施中，文档作者未实测）
```bash
python3 tools/save_company_cli.py prepare --project <项目键> --segment-id <Sxx> --generation-id <id> \
  --selection-id <id> --audit-manifest <manifest> --request <offline-input.json>
python3 tools/save_company_cli.py confirm --plan <draft.json> --quote "<用户原话>" --quote-ref <来源>
python3 tools/save_company_cli.py execute --plan <confirmed.json> --render <render> --ticket <ticket>
python3 tools/save_company_cli.py status --plan <confirmed.json>
```
- `prepare` 只读本地、不取凭据/不构造 transport；`confirm` 唯一铸票；`execute` 重验同一 binding 后才写。
- 无 confirmed plan 不写；旧 `save_first_n.py` 继续封停；数字/字母选择不是保存授权。

---

## 六、点数预算公式（★保存规模由预算决定）

### 默认参考：单次建议上限 2 万点（不是硬上限）
> **默认建议**：单次保存建议不超过 2 万点（必须带 source_ref/version，例：当前计划明确上限或用户本轮明确上限）。它是建议上限，不是硬规则；经用户明确预算确认可调整。历史“30000 家/60% 比例”不再作为默认公式。

### 公式（单位必须分开）
```
N=selectTotal（家）；e=邮箱/家；p=点/邮箱；B=本次确认预算（点）
E = N × e                 [邮箱]
P = ceil(N × e × p)       [点]
建议 N = floor(B ÷ (e × p))  [家]
```
- B/max_points 缺失或无来源 → E_BUDGET_UNRESOLVED；P>max_points → E_MAX_POINTS_EXCEEDED；P>B → E_BUDGET_EXCEEDED。
- 既有“余额×50%”只在本次计划明确采用时使用；不得再乘第二个50%。

### 示例（仅示意，系数须有来源）
```
B=10000点，e=1.5邮箱/家，p=1.5点/邮箱
建议 N=floor(10000 ÷ 2.25)=4444 家；E≈6666 邮箱；P≈9999 点
```
### 示例（用户明确小规模）
```
用户说“就存20家”，且来源/审计/预算/标签/filters 成立：N=20，e=1.5 → E=30，P=45（系数仅示意）
允许，但必须如实说明量级影响；AI 不得把已确认的6200擅自缩成20
```

### 参数说明
| 参数 | 值 | 来源 |
|------|-----|------|
| 预算 B / max_points | 本次确认的具体点数 | plan 的 source_ref+version；20000 只是默认建议来源，不是硬编码 |
| 每公司邮箱数 | **3**（提取上限，不是保证；存不到才按 3→6→9 升阶） | 用户拍板（marketing-rules-2.0 §3） |
| 每邮箱点数 p | 估算 **1.5**（历史观测 1.81 仅作 Batch C 观测） | 用户 seq7141 建议，model_version=user-estimate-20261021-v1；不是平台费率 |
| 每公司邮箱 e | 估算 **1.5**（历史观测 1.53 仅作 Batch C 观测） | 有出处版本；不能把3当e |
| 邮箱类型 | 有效 + 未知 | contactVerifyStatus:["valid","unkown"] |

### 执行
1. 查用户可用点数（只读；余额≠可写预算）
2. 把 N/e/p/B/max_points 及来源写进 plan，展示 E/P 与“够不够发一批”
3. 用户原话确认后才 `confirm`；`execute` 才写；无 confirmed plan 不写
4. 不擅自缩量/扩量；用户明确20家按同一计划校验，弱适配只解释不默认500

---

### 6.5 自动校准流程（Auto-Cal：余额 → 样本 → 两次确认 → 结转 → 区间）

保存接口不返回消耗点数（已核实），唯一真实成本 = **同一 org、同一 token、同一任务窗口、已结转的余额差**。命令：`python3 tools/save_budget.py probe|begin|settle|carry|plan|status`。

1. **probe（只读）**：读 benefits/refine-data 的 monthlyLimit/monthlyUsed，`B_avail=limit−used`；字段缺失或 limit<=0 → `E_BALANCE_UNAVAILABLE`；`used>limit` → `E_BALANCE_OVER_LIMIT`（不截断为 0）；`used==limit` → `B_avail=0` 并报 `E_BUDGET_EXHAUSTED`。读数超过 10 分钟 → `E_BALANCE_STALE`。
2. **样本前告知 + 递增探针阶梯（v14）**：无历史时固定 **1 家探针**（不再一次 20 家）；阶梯 `1 → 10 → 50 → 按上限`，**每级单独确认**；同一 `round_id` 内探针批合计 **≤3 批**，超限仍无可靠上限 → `E_CALIB_INCONCLUSIVE`（停止交用户）。探针批的 `sample_ack` 账簿记录必须**早于**该批 `batch_begin`（严格小于时间戳），否则该批 `void` 并报 `E_LEDGER_REPLAY`。`per_company_upper` **只用最新一级**（固定费纠正，ROUND_CEILING 到 6 位），不得用 1 家级外推大批量。有历史干净批次时 `N0=min(100,max(1,min(20,floor(B_plan/历史上限))))`；可负担 <20 时取可负担量并硬提示、单独确认，禁止硬顶 20。用户估值只标 `kind=user_estimate`，不得用于 N_cons/可负担量。样本风险告知原文：“首批 N0 家为成本实测样本，实际扣点未知；样本本身可能耗掉本轮预算的大部分甚至全部余额。”未确认 → `E_SAMPLE_ACK_REQUIRED`。
3. **begin（执行前）**：写 `batch_begin`（exec_ack、B0）；同一 batch_id 重复 begin → `E_LEDGER_REPLAY`。
4. **settle（取样点）**：任务 finished 后每秒轮询余额，连续两次读数相等且稳定 ≥10s 得 `B_settle`；120s 不稳定 → `E_BALANCE_NOT_SETTLED`，该批保持 preliminary 并停止推进。取样点 `batch_cost_lo=B0−B_settle`，此时 `cost_lo==0` 属正常中间态，不报错。settle 必须对应已存在的 begin；重复 settle → `E_LEDGER_REPLAY`。
5. **carry（结转）**：读 `B_after`；`late=max(0,B_settle−B_after)`，`batch_cost=max(0,B0−B_settle)+late`；写 `carry`（state=settled、late、external_risk）。**两次确认**（执行前 exec_ack + 结转后 settle_ack）都齐才 `external_risk=confirmed`；任一缺失 → `unprovable`（计入 spent_all、不进校准账）。结转后 `batch_cost==0` 且公司数>0 → `E_CALIB_COST_ZERO`；重复 carry → `E_LEDGER_REPLAY`。
6. **plan（区间）**：仅当无 preliminary、且校准账（settled 且 confirmed）非空时才给数量；否则 `E_CALIB_NOT_READY`（禁止 0/0、禁止用 unprovable 批次）。`spent_all=Σ 全部 settled`，`budget_left=B_plan−spent_all`，`N_cons=floor(budget_left/per_company_upper)`、`N_est=floor(budget_left/per_company_est)`，输出区间 `[N_cons,N_est]`（estimate）。用户确认数量不得超过 N_cons；超过须显式冒险记账，且不得超过 N_est（`E_QUANTITY_EXCEEDS_CONS`/`E_QUANTITY_EXCEEDS_EST`）。`budget_left < per_company_upper` → `E_BUDGET_EXHAUSTED`；建议上限 20000 点只提示（cap 确认后放行）。
6.1 **未结清批次（v14）**：`spent_all` = Σ settled `batch_cost` + Σ preliminary/void 的 `unresolved_upper`（**按该批自身窗口**：`max(0, B0_该批 − B_该批当前读数)`，不得用全局余额差）。只要存在未清零 unresolved → **冻结后续批次**并报 `E_UNRESOLVED_BATCH`。三条清除路径都写账簿：① 结转完成（settle→carry）；② `audit_clear` 核销（记录 `batch_id/cleared_value/evidence`）；③ 确认未扣点记 0（`audit_clear` value=0）。
6.2 **轮次互斥与跨轮上限（v14）**：`budget.lock` 以 O_EXCL 抢锁，已存在 → `E_ROUND_CONFLICT`（零网络请求）。账簿每条含 `round_id`；`spent_cumulative_all_rounds` = 全部 settled + 当前 unresolved 上界；达 `cumulative_cap` → `E_ROUND_CAP_EXHAUSTED`。`B_plan` 与首轮冻结值恒等，跨轮重算被拒。
7. **预算冻结**：`B_plan` 在本轮首次 plan 时冻结写入账簿（`kind=plan,state=budget_frozen`），其后只做减法，不按新余额重算 50%。
8. **账簿（append-only）**：`.local/budget-ledger.jsonl`；kind 固定 7 个 `probe/sample_ack/batch_begin/settle/carry/plan/audit_clear`；org_hash=`sha256(orgId)[:16]`；必需字段 `at/org_hash/project/kind/batch_id/state/source_ref/late/external_risk/sample_ack_at/round_id`；`audit_clear` 另含 `cleared_value/evidence`；禁存 token/明文凭据。
9. **展示（带单位）**：余额（点）、本轮预算（点）、已花（点，含全部 settled）、校准样本（家/个邮箱）、实测单位成本（点/家、点/邮箱、邮箱/家）、保守/估算可存（家，区间 estimate）、执行后预计余额（点）、风险（约占余额 xx%；实际单位成本更高时可能提前耗尽）。
10. **错误码顺序**：计数非 int/bool → `E_CALIB_BAD_COUNT`；int 负数 → `E_CALIB_BAD_COUNT`；零 → `E_CALIB_NO_COMPANIES`/`E_CALIB_NO_EMAILS`；status 与 finished 矛盾或回读超时 → `E_TASK_STATE_INCONSISTENT`。

```bash
# 只读余额 → 执行前登记 → 取样 → 结转 → 区间（离线测试用 loopback 桩）
python3 tools/save_budget.py probe  --project acme/widget --org "$ORG" --token "$TOKEN" --out .local/b0.json
python3 tools/save_budget.py begin  --project acme/widget --org "$ORG" --task-id <saveTaskId> --b0-file .local/b0.json
python3 tools/save_budget.py settle --project acme/widget --org "$ORG" --token "$TOKEN" --task-id <saveTaskId>
python3 tools/save_budget.py carry  --project acme/widget --org "$ORG" --batch-id <batchId> --b-after 99000 \
  --settle-quote "<用户确认无外部操作>" --settle-quote-ref <seq>
python3 tools/save_budget.py plan   --project acme/widget --org "$ORG" --b-plan 50000 --b-avail 100000 --target 1000 --saved 100
```

## 七、标签规则（★固化）

### 7.1 客户标签（黄金公式）
> ⚠️ **过时标注（2026-08-30，RULES 铁律7 推翻）**：下述"语言-国家-产品-角色"公式**已废弃**——标签=**客户群体中文名**（不写我方产品，购买者不一定是卖同产品的人；如 `水上运动行业客户`，反例 `english-raft-dealer`）；**记录一律 id(名称) 成对**（tags-list 可查名）；内部命名一律中文。现行活跃标签见 api-reference §5。
```
语言-国家-产品-角色
例：俄语-俄罗斯-皮筏艇-经销商
```
- 语言最前（按语种筛模板）→ 国家（时区/节日）→ 产品/角色（客群细分）

### 7.2 固定标签（所有项目通用）
> ★ 现行活跃实例（2026-08-30，记录 id+名称成对）：**询盘**=`<tagId>`、**不发**=`<tagId>`（即下表"禁发"的现行名称）——见 api-reference §5 活跃标签。
| 标签 | 用途 | 设到 |
|------|------|------|
| **禁发** | 骂人/退订 → 不再打扰 | 序列 notSentTags |
| **询盘** | 有明确意向 → 转人工 | 序列 notSentTags |
| 💬 询盘 / 📦 寄样 / 💰 成交 | 意向状态 | 意向排除视图 |
| ❌ 同行 / 🚫 退订 / ⛔ 其他 | 风险排除 | 风险排除视图 |

### 7.3 标签 ID 规则
- 公司标签（type=company）和联系人标签（type=contacts）**两个体系**
- 保存任务 companyTags/contactTags 用**标签 ID**（先查/建）
- 序列 notSentTags 用**联系人标签 ID**

---

## 八、模板与序列（★本地存储+效果分析）

### 模板
- 本地存储 `templates/rXX-vYY.md`（含 template_id + subject + html + 元信息）
- **模板效果分析**（template-analysis.md）：每周从后台拉数据回填 opens/replies → 对比哪个模板好 → 迭代
- 每步 4 封（template_ids 4 个，互不相同）

### 序列
- 命名：`[产品]-[语言]-[轮数]轮[每轮封数]封-[策略]`（★名字里的「N轮M封」必须与实际一致——当前 12轮4封；不符则 build_sequence 拒绝建序列）
- 配置按 [sequence-config.md](sequence-config.md) 标准（时区按语言/每日30000(全账号)/每公司每日5/禁发询盘不发送/每步4封）
- 序列配置**快照**存 `sequences/{seq-name}.md`（rules/步骤/模板映射）——便于复盘

---

## 九、每日操作日志（★留痕）

### 记录内容
- 搜了什么客户（关键词/网址/结果数）
- 保存了什么（范围/数量/标签）
- 发了什么（序列/步骤/数量）
- 收到什么（询盘/回复）
- 模板效果（打开/回复）

### 存储
- `daily-logs/2026-08-21.tsv`（结构化，AI append）
- 重要决策补充到 `index.md`（人看）

### 读来发信后台数据（快照）
- `sequences/sequence-list`（序列数据）→ sequences-snapshot.tsv
- `sequences/report-data`（报告）→ reports-snapshot.tsv
- 询盘（邮件/回复）→ inquiries.tsv（★单独记录）

---

## 十、完整流程总览（代运营每日）

```
晨间：读来发信后台数据（序列/报告/询盘）→ 更新快照 → 分析模板效果
      ↓
操作：按当日计划（新搜索/新保存/建序列/改模板）
      ↓
校验：保存前**连续5页均值 ≥70%** + 逐条语义/独立review（单页低不是终点；不得按材质/规模二筛；High比例不算证据）/ N/e/p/B 单位与来源 / 加联系人 views:[] / 验证 add 数量
      ↓
留痕：更新 search-log/seeds/customers/inquiries/daily-logs + index.md
      ↓
晚间：汇总当日 → 更新模板分析 → 简报给客户
```

## 🔗 相关

- [data-structure.md](data-structure.md)（数据结构）
- [sequence-config.md](sequence-config.md)（序列配置）
- 操作日志机制：`runs/<运营方>/<产品>/ops-log.tsv`（本地数据，不入 Git）

## ★S5 保存前必读要点（2026-10-23 实战教训固化）

### 必须满足的三件事（缺一则工具会拒绝）
1. **原话含数量**：用户授权原话必须能被解析出公司数，例如「确认，保存 9400 家」；只说「确认」→ `E_AUTH_COUNT_AMBIGUOUS`。
2. **显式点数预算**：`budget_points` 与 `max_points` 取用户明示值（如「点数预算 3 万」）。不足 → `E_BUDGET_EXCEEDED` / `E_MAX_POINTS_EXCEEDED`。
3. **探针确认**：auto-cal 首轮要求 1 家样本单独确认（`sample_needs_ack`）；上一轮未结清须先 `audit-clear`（0=确认未扣点），否则冻结额成锚。

### 保存期间的操作要求
- **每 10–30 秒查一次任务状态**；禁止重复 execute。**必须滚动向用户报进度**（见下「汇报纪律」）。
- 任务 finished 后立刻对账：`companySaveCount` / `contactSaveCount` / 实际扣点 / 任务 id。
- 结果不明时保留锁、走 `status`/`reconcile`，不得盲目重试。

### 预算口径（2026-10-23 已修，务必按此执行）
- **保存点数真源 = `POST /api/account/current` 的 `data.creditCount`**（量级数百万）。
- `benefits/refine-data` 的 `monthlyLimit/monthlyUsed` 是**查看配额**，不是保存点数；仅在点数接口不可用时降级，且 probe 账簿标 `source_kind=view_quota` 并写入降级原因。
- `save_budget.py probe` 现为点数优先并记录 `source=account/current.creditCount`；`plan` 在非点数来源且无显式预算时 **fail-closed**（`E_BUDGET_UNRESOLVED`），有显式预算则放开 2 万建议上限。
- 实测（2026-10-23）：9400 家 → 实际邮箱 11,370 封 → 消耗 **19,676 点**（4,634,069 → 4,614,393）。

### 汇报纪律（2026-10-23 用户纠正）
- 保存进行中**必须滚动汇报进度**：每 10–30 秒查一次状态，把「当前步骤 + 是否已写入 + 任务状态」告诉用户。
- 不得「闷头跑、结束才回话」；也不得刷屏——每次一句进度即可。
- **播报三要素（用户 2026-10-23 明确要求）**：①明确说「正在跑」；②告诉用户「不用操作，等我」；③给出**预计等待时间**（如「约 5 分钟」）。缺一项视为无效播报。
- **有真实进度源的任务**（平台保存任务、批量接口）：每 10–30 秒报真实百分比/计数。
- **没有真实进度源的本地任务**（写模板、写计划、本地校验）：每 15–30 秒报**阶段节点**（如「计划写完 → 正在写第 N 轮 → 正在预览」）+ 心跳；**禁止编造百分比**，只说节点和「仍在跑」。
- 最终账（公司/邮箱/扣点）在 finished 后给；中间可报阶段性计数。

## ★S4 双口径与连续窗口（2026-10-23 固化，防卡死）
- 两套口径必须显式声明，不得混用：
  - 宽松口径：企业业务与户外/露营/营地接待/帐篷住宿租赁相关即算“潜在购买方”，可发信尝试（用户 2026-10-23 决策：严谨过少时用宽松）。
  - 严谨口径：以“是否真会采购该产品”判定，供应商/制造商/零售商/信息站/OTA/环保/宗教/纯房车租赁等判否。
- 临界页判定用连续 5 页滑动平均 ≥70%；窗口必须给连续页码 + 逐页 matched/total（manifest.window.page_rows），且窗口内所有 5 页滑窗 ≥70%。
- 边界带必须诚实披露（如内侧某窗口 68%），不得隐藏；边界页取“达标带末页”，与已保存量按 10 家/页 核对，允许 ≤0.1% 噪声偏差不重存。
- 审计证据文件须含关键词：70%、临界、逐页、敏感性（50页/三页平均 建议保留）；对抗审查须含 P0=0、P1=0、放行。

## ★S7 批量创建防卡死（2026-10-23 固化）
- 必须后台执行（nohup/后台 job）并写滚动日志（每 10–30 秒一行「已建 X/N + 下次时间」）；前台命令 >120s 会被外层杀，留下“票已消费、只建一半”的状态。
- 票据：auth_guard.py authorize 输出 JSON 的 nonce → --auth-ticket .local/auth/ticket-<nonce>.json（传文件路径，不传 nonce）。
- E_AUTH_REUSED 处置：先只读核对平台已有数量；0 条才可清 .local/auth 的 payload/ticket .ok 重授权；已有部分则按 name 去重只补缺，禁止重跑全量。
- 分组：templates-folder-list 返回 _id 才是分组 id；template-folder-add 报“名称重复”即分组已存在，复用 _id。
- 完成后必须核对：分组内数量=预期、名称/ID 唯一、template-map.json 条数与平台一致、meta 的 tmap_sha256 匹配、内容逐字匹配。

- **交互确认格式**：给用户的选择一律用编号（A/B/C 或 1/2/3），每项写「做什么 + 代价/耗时」，推荐项排第一并标注；不要用“回我一句话”这种自由文本确认。

## ★对用户的播报规范 v2（2026-10-23 用户反馈固化）
- **禁止黑话**：不许出现「preview / 硬门 / 审批凭证 / 指纹 / 哈希 / 载荷 / 消费票据 / 归档 / 状态机 / S 编号」等内部词。一律翻译成用户能懂的话：
  - preview → 「先在电脑上看样子，还没上传」
  - 硬门通过 → 「检查通过」
  - 审批凭证/票据 → 「您刚才的确认」
  - 状态 S9 → 「第 4 步 / 共 6 步」
- **每次播报必须有「三步曲」**：①已完成什么 ②现在在做什么 ③接下来做什么 + 大概还要多久。
- **阶段面板**：播报里给一行「第 X 步 / 共 N 步」，N 固定为 7：1 找客群→2 划边界→3 存客户→4 写邮件→5 建模板→6 建序列→7 加人激活。
- **节奏**：长任务每 **10–30 秒**必须有一条进度（有真实计数就报计数，没有就报阶段节点+心跳）；「3 分钟后再报」不合格。

## ★邮件模板流程 v2（对抗审查后修正，2026-10-23）
- **旧流程缺陷**：本地一次写 48 封 → 只给用户看 3 封 → 直接上传 48 封。用户实际没看过其余 45 封，确认节点形同虚设。
- **新流程（固定顺序）**：
  1. 本地先写 **4 封样稿**（覆盖 4 个角度，不是随机 3 封）
  2. 把 4 封样稿原文给用户看（主题+正文+落款），一句话说明「其余按同样规则生成」
  3. 用户回复确认（编号选项 A 确认 / B 改哪里）
  4. 确认后一次批量生成 48 封并**归入同名分组**（分组名=前缀）
  5. 上传后核对：分组内数量、名称唯一、内容逐字一致
  6. 核对通过才推进「第 5 步建模板」为已完成，进入建序列
- **一次性确认**：用户只确认 1 次（4 封样稿），不允许逐封打扰；改稿也只改被指出的那几封，再一次性重传未建部分。

## ★一次确认跑完（2026-10-23 用户要求：一气呵成）
- 用户回一个 **A**，即视为同意把「建序列 → 加联系人 → 设置/终检」连续做完，**中途不再问第二次**。
- 允许的连续链：S9 建序列 → S10 加联系人 → S11 设置/终检（时区、单日/单家上限、标签、公司触发动作、序列与模板对齐）。
- **唯一例外：S12 激活发信**。激活会真发 9,400 封邮件、不可撤回，必须用户单独明确说「确认激活」；不得把 A 解释成同意激活。
- 连续链执行时：每 10–30 秒播报一次「第 X 步 / 共 6 步 + 已加 X / 9,400 家 + 大概还要多久」，不得长时间静默。
- 任一步失败：停下并用人话报「哪一步失败、影响什么、下一步选什么」，保留原文留证。

## ★流程合并 v3（2026-10-23 用户拍板：6 步 + 2 个确认点）
- 旧 7 步拆太碎：**「建序列」和「加人+设置」必须合并成同一步**，由用户一次选择（A）后一口气跑完。
- 固定 6 步：
  1. 找客群 → 2. 划边界 → 3. 存客户 → 4. 写邮件（本地 4 封样稿）→ 5. 建模板（分组+核对）→ 6. 建序列+加人+设置（一口气）→ 之后单独确认是否激活发信
- **只有 2 个确认点**：
  - 确认点 1（第 4 步末）：看 4 封样稿，回 A 确认 / B 指出改哪里。
  - 确认点 2（第 5 步末）：模板建好并核对完，给一个合并选项 **A = 建序列 + 加人 + 设置一次做完**（不再拆开问）。
- 第 6 步内部顺序固定：建序列 → 核对 12 轮 × 每轮 4 封 → 加联系人并计数 → 设置（时区/单日上限/单家上限/跳过标签/公司触发）→ 终检 → 报「共 X 家已就绪」。
- 激活发信是**第 6 步之后**的单独硬门，必须用户明确说「确认激活」。

## 流程 v4（2026-10-23 用户拍板：只在第 5 步确认一次，第 6 步一气呵成）
- 固定顺序：1 找客群 -> 2 划边界 -> 3 存客户 -> 4 本地写邮件（4 封样稿贴出来给用户看，不打断）-> 5 上传 48 封到同名分组并核对 -> 请用户确认一次「模板没问题」-> 回 A 后第 6 步一气呵成（建序列 + 加人 + 设置 + 终检）。
- 全流程只有 1 个中途确认点（第 5 步末）；第 6 步内部不再向用户提问。
- 第 6 步完成后，单独问一次「是否开始发信（激活）」，这是另一个硬门。
- 第 6 步执行时每 10-30 秒播报：已加 X / 9400 家，预计还剩 Y 分钟。

## 交付播报格式 v5（2026-10-23 用户要求：短、①②③、可核对）
1) 每次播报不超过 6 行；工作项一律用 ①②③ 编号，不写表格堆砌。
2) 第 6 步做完后必须输出「设置清单 + 数量 + 链接」：
   - 模板：多少封、分组名
   - 联系人：加了多少家、几个邮箱
   - 邮件序列：几轮、每轮几封、间隔多久
   - 设置：时区、每天最多几封、同一家最多几封、跳过哪些标签
   - 登录看：https://app.laifaxin.com （用户核对）
3) 用户核对后：回 a = 开始发信（激活）；有问题直接说，AI 改完再请用户确认。
4) 激活前必须再确认一次，且激活不是 a 能默认包含的（独立硬门）。

## ★激活后必须报「什么时候开始发」（2026-10-23 用户要求）
- 激活成功后立刻回读平台状态，确认 active，再报首发时间。
- 必须同时给**三地时间 + 倒计时**：对方当地（如纽约）、用户本机时区、北京时间；并说明「现在不在发送窗口内，所以不会立刻发」。
- 格式固定：
  1. 已启动（平台状态=active）
  2. 第一批：纽约 X 月 X 日 08:00 = 你这边 0X:00 = 北京 20:00；还有 X 小时 X 分
  3. 之后每 30 分钟一轮，首日走完第 1 轮 4 封
- 发送窗口来自序列 schedule：周一至周五 08:00–17:00（序列时区）。

## 问题台账(开工必看)
- 踩坑与对抗审查: specs/problems-and-fixes-2026-10-23.md
- 同类问题先查该表; 新增问题直接追加.
- 激活/S11/S10 命令与核对单见其第三节.

## ★新手开场卡与截图参照（2026-10-23 用户要求）
- 第一次回复按 specs/beginner-flow.md 第一节输出「6 步全景 + 当前步 + 接下来 + 只需回数字」。
- 所有确认用 1/2/3（1=同意继续放第一）；只有发信激活要求「确认激活」四个字。
- 第 4 步写邮件前主动邀请：有以前效果好的开发信可以截图发我（1-5 张），我只学结构/语气；提炼结果写 runs/<运营方>/<产品>/email-style.md，不得照抄价格/承诺/公司名/联系方式。
- 用户可只用截图和数字走完全程；AI 负责把每个决定落成仓库文件。
