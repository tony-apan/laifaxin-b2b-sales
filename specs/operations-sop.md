---
title: "代运营完整 SOP（规则细化）"
description: "代运营全流程规则：时区灵活映射/点数预算公式/单页筛选标准/标签规则/网址找相似确认流程/推演固化"
created: 2026-08-21
updated: 2026-08-21
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
> 现行规则：开局只问 token + 纯个人昵称 + 一句话产品；进入 S0a 后分两轮主动索取（均可跳过、不逼问）：公司名/官网/自己的联系邮箱/默认市场→`.local/operators/<operator_key>.md`；产品线/卖点/认证/产能/MOQ/交期/价格带→当前 `product-profile.md`。潜在买家/联系人第三方资料不索要；邮件末尾签名区只有昵称。详见 `operator-profile-sop.md` 与 `product-profile-sop.md`。
| 资料 | 回落位置/规则 |
|------|-------------|
| 公司名称 / 官网 / 用户自己的联系邮箱 / 默认市场语言 | `.local/operators/<operator_key>.md`；跨产品复用，换机随 `.local/` 迁移 |
| 产品线 / 卖点 / 认证 / 产能 / MOQ / 交期 / 价格带 | `runs/<operator_key>/<product_key>/product-profile.md`；逐字段 source/confidence，确认后版本/hash锁定 |
| 来发信 token / orgId | **只在当前会话命令/环境变量中使用，不落任何文件；换机重新获取** |
| 潜在买家/联系人资料 | 由平台搜索/保存流程产生，不要求用户提供，不写入 operator/product profile |
| 点数预算 | S5 确认材料/operation-record，决定保存规模 |

### 1.2 从用户官网/目录提炼信息（公司级与产品级分层）
用户给了官网或产品目录 → AI 读取并提炼：
- 公司身份/官网/默认市场 → `.local/operators/<operator_key>.md`
- 产品线/卖点/规格/认证/可引用数字 → 当前 `product-profile.md`（字段级来源）
- 产品词/业务描述词 → 仅在用户确认 product-profile 后用于 S2/S3

> ⚠️ **流程**：AI 提炼 → 用 S0a 话术展示 → 用户确认/修改 → 工具回落并生成版本/hash → 才往下走；用户跳过则记录 declined，不静默绕过。

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
   - 现行：`refine/company-list` 以代表买家域名作 keyword 做海量扩量 → 按 S4 70% 名单筛选边界逐页审计
   - ⚠️ `domain/similar-list` 仅属旧接口能力，本流程不使用
   - 需要多个域名任务时，按当前 API 参考与平台状态另行确认，不把历史 `tasks/create` 示例当现行主路径
    ↓
④ 审计精准度（单页标准）→ 找 70/80% 临界点 → 确定保存范围
    ↓
⑤ 记录到 seeds.tsv（已用/待用）
```

> **确认原则**：客户给了网址 → **先展示"我将用它找相似，目标客群是XX"** → 客户确认 → 执行。避免客户提供的是自己公司网址（那是提炼产品，不是找相似！要区分）。

---

## 五、单页筛选标准（★保存前必做）

**抽查"本页"精准度**（不是累计）：

| 本页精准度 | 判定 | 动作 |
|-----------|------|------|
| ≥70%（中等默认）| ✅ 保存 | 红队规则：80%严格/70%中等默认/60%宽松 |
| <70% | ❌ 或换种子 | 用更准种子（企业/品牌/经销）重搜 |

**执行**：
1. 抽查前 1~5 页 + 末尾几页（每页10条，逐条看本页）
2. 用审计工具（audit_company.py 规则表，不主观）
3. 找到**本页降到 70% 以下的临界页** → 往前翻 → 保存范围 = 临界页之前
4. 排除中国区（CN/TW/HK/MO 默认）
5. **记录到 search-log.tsv**（审计页/精准度/临界点）

---

## 六、点数预算公式（★保存规模由预算决定）

### ★ 保存数量默认参考：30000 家（★默认,非硬上限）
> **默认值**：单次保存默认参考 30000 家（★2026-08-30 用户拍板：**30000 是默认，不是硬规则**，可调——除非用户特别说明"多多保存"）。
> 原因：超大批量有风险（邮箱质量/域名信誉/系统限制），分批更稳。

### 公式
```
保存预算 = 用户点数 × 60%（建议 6成用于保存，留 4成验证/评分）
每家公司成本 = 每邮箱均价 × 每公司邮箱数 = 1.5 × 3 = 4.5 点（默认3邮箱，用户可上调）
可保存公司数 = min(保存预算 ÷ 4.5, 30000)   # 默认参考 3 万(非硬上限)
```

### 示例（用户 10万点）
```
10w × 60% = 6w 点用于保存
60000 ÷ 4.5 = 13333 → 保存 13333 家（默认3邮箱/家，用户可上调存更多）
```

### 示例（用户 100万点）
```
100w × 60% = 60w 点
600000 ÷ 4.5 = 133333 → 按默认参考 30000（可调，非硬上限）
剩余预算留后续批次
```

### 参数说明
| 参数 | 值 | 来源 |
|------|-----|------|
| 保存预算比例 | 60% | 建议（留 40% 验证/评分/其他） |
| 每公司邮箱数 | **3**（默认，★每公司邮箱数裁决；存不到数据才按阶梯 3→6→9 升阶） | 用户拍板（marketing-rules-2.0 §3；⚠️旧值"5（下限3）/红队R13"已被覆盖） |
| 每邮箱均价 | 1.5 点 | 有效2点+未知1点 平均 |
| 邮箱类型 | 有效 + 未知 | contactVerifyStatus:["valid","unkown"] |

### 执行
1. 查用户点数（account/current → creditCount）
2. 算可保存公司数 → **展示给客户确认**（"您10万点，按60%预算可保存13333家×3邮箱，确认？"）
3. 确认后按范围保存（选择前 N 条 = 公司数 × 10/页）

---

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
- 每步 ≥10 封（template_ids 10个）

### 序列
- 命名：`[产品]-[语言]-[轮数]轮[每轮封数]封-[策略]`
- 配置按 [sequence-config.md](sequence-config.md) 标准（时区按语言/单日30000/单家5/禁发询盘不发送/每步10封）
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
校验：保存前审计 ≥70%（中等默认；80/60 须用户指定——旧记录"≥80%"为教程线，已被 2.0 拍板覆盖）/ 点数预算 / 加联系人 views:[] / 验证 add 数量
      ↓
留痕：更新 search-log/seeds/customers/inquiries/daily-logs + index.md
      ↓
晚间：汇总当日 → 更新模板分析 → 简报给客户
```

## 🔗 相关

- [data-structure.md](data-structure.md)（数据结构）
- [sequence-config.md](sequence-config.md)（序列配置）
- 操作日志机制：`runs/<运营方>/<产品>/ops-log.tsv`（本地数据，不入 Git）
