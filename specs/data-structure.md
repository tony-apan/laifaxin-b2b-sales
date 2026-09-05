---
title: "数据结构规范（Data Structure Standard）"
description: "代运营数据存储：md vs tsv vs jsonl 对抗分析 + 目录结构 + 索引规范 + 每文件格式"
created: 2026-08-21
updated: 2026-08-21
author: "AI Agent + 运营方"
source: "对抗分析（代运营场景）"
related: [specs/operations-sop, docs/08-workflow-ops]
tags: [数据结构, 格式对抗, 目录规范, 索引]
status: verified
audience: 人+AI
---

> ⚠️ **布局注记（2026-08-30）**：档案/存储布局以 `runs/<运营方>/<产品>/` + 本地运营方档案（`.local/operators/<operator_key>.md`，不入 Git）为准（RULES「多公司/多产品」）；本文下文的 laifaxin-ops/clients 等目录为**设计参考/未实施**，勿按此建目录。

# 📦 数据结构规范（Data Structure Standard）

> **场景**：代运营（一家公司可能多个产品），每天操作留痕，数据可被 AI 读/写、人可查看。
> **核心问题**：md / tsv / jsonl 用哪个？目录怎么组织？索引怎么做？

## 一、格式对抗分析（md vs tsv vs jsonl）

### 1. 逐维度对比

| 维度 | Markdown (.md) | TSV (.tsv) | JSONL (.jsonl) |
|------|---------------|------------|---------------|
| **AI 读取** | ⭐⭐⭐⭐ 语义清晰，表格/嵌套可解析 | ⭐⭐⭐ 结构简单，但无类型/嵌套 | ⭐⭐⭐⭐⭐ 字段名自带，零歧义 |
| **AI 写入/追加** | ⭐⭐⭐ 追加会破坏结构（表格难续写） | ⭐⭐⭐⭐⭐ 一行一条，append 完美 | ⭐⭐⭐⭐⭐ 一行一个 JSON，append 完美 |
| **人阅读** | ⭐⭐⭐⭐⭐ 最友好（标题/表格/链接） | ⭐⭐ 无排版，靠表头 | ⭐ 需要脑内解析 |
| **Excel 打开** | ❌ | ✅ 直接打开 | ⚠️ 需导入 |
| **字段扩展** | ⭐⭐ 改表头要重写全表 | ⭐⭐⭐ 加列即可 | ⭐⭐⭐⭐⭐ 任意加字段不影响旧行 |
| **大数据量** | ❌ 表格上千行难维护 | ✅ 万行无压力 | ✅ 万行无压力 |
| **版本对比** | ⭐⭐⭐⭐ git diff 友好 | ⭐⭐⭐⭐ | ⭐⭐⭐⭐ |
| **引用/关联** | ✅ 链接/交叉引用 | ❌ | ❌ |

### 2. 结论：**按内容类型分格式，不是一刀切**

| 内容类型 | 推荐格式 | 理由 |
|---------|---------|------|
| **索引/导航**（index.md） | **MD** | 人机导航，链接跳转 |
| **总结/分析/说明**（公司档案、模板分析、客群推演） | **MD** | 语义丰富，人可读 |
| **逐条记录**（搜索日志、种子网址、客户清单、询盘记录、每日操作） | **TSV**（首选）或 JSONL | AI 追加写入最干净，Excel 可查 |
| **模板本体** | **MD**（含 HTML） | 模板=文档，便于 AI 生成/修改 |
| **原始接口数据** | JSONL | 字段多、可扩展 |

> **关键决策**：**结构化的"流水记录"用 TSV**（一行一条，AI append 不破坏结构，人也能 Excel 看）；**语义性的"分析总结"用 MD**。这是"AI 读写效率 + 人可读"的最佳平衡。
>
> ⚠️ TSV 注意：字段值内**禁止含制表符和换行**（用 `\n` 转义），否则列错位。

## 二、代运营目录结构（一家公司一个文件夹）

```
laifaxin-ops/                              # 代运营总根目录
├── clients/                               # 客户公司层
│   └── {company-name}/                    # ⚠️ 一家公司一个文件夹（如 laifaxin-demo）
│       ├── index.md                       # ★ 公司索引（导航：产品/账号/进度/询盘）
│       ├── company-profile.md             # 公司档案（网址/产品/联系人/职位/邮箱/账号token）
│       ├── accounts.tsv                   # 平台账号（来发信token/orgId/点数余额）
│       ├── products/                      # 产品层（一家公司多产品）
│       │   └── {product-key}/             # ⚠️ 一个产品一个子文件夹（如 cat-food）
│       │       ├── index.md               # ★ 产品索引（客群/搜索词/种子/序列/模板/询盘）
│       │       ├── segments.md            # AI推演客群（固化：8客群+价值路径+搜索词）
│       │       ├── search-log.tsv         # 搜索日志（日期/方式/关键词/网址/结果数/审计页）
│       │       ├── seeds.tsv              # 种子网址（已用/待用/来源/找相似结果数）
│       │       ├── customers.tsv          # 已保存客户（邮箱/公司/国家/标签/保存任务ID）
│       │       ├── sequences/
│       │       │   ├── index.md           # 序列索引
│       │       │   └── {seq-name}.md      # 序列配置快照（rules/步骤/模板映射）
│       │       ├── templates/
│       │       │   ├── index.md           # ★ 模板索引（编号/名称/轮次/效果/状态）
│       │       │   └── r01-v01.md         # 模板本体（subject+html，含元信息）
│       │       ├── template-analysis.md   # ★ 模板效果分析（打开率/回复率 对比）
│       │       ├── inquiries.tsv          # ★ 询盘记录（时间/邮箱/公司/内容/状态/跟进）
│       │       └── daily-logs/
│       │           └── 2026-08-21.tsv     # 每日操作日志（时间/动作/对象/结果）
│       └── data/                          # 来发信后台数据快照（只读备份）
│           ├── sequences-snapshot.tsv
│           └── reports-snapshot.tsv
```

### 2.1 每文件用途速查

| 文件 | 格式 | 写入时机 | 内容 |
|------|------|---------|------|
| `index.md` | MD | 每次操作后更新 | 导航+当前进度（人先看这个） |
| `company-profile.md` | MD | 客户签约时 | 公司/产品/职位/姓名/网址（★用户给网址提炼） |
| `segments.md` | MD | AI 推演后 | 客群固化（段名/路径/理由/搜索词/覆盖量） |
| `search-log.tsv` | TSV | 每次搜索后 append | 日期/方式/关键词/网址/结果数/审计精准度 |
| `seeds.tsv` | TSV | 每次找相似后 | 种子网址/状态(已用/待用)/来源/相似结果数 |
| `customers.tsv` | TSV | 每次保存后 | 邮箱/公司/国家/标签/任务ID/邮箱数 |
| `templates/*.md` | MD | 生成模板时 | 模板本体（subject+html+元信息） |
| `template-analysis.md` | MD | 每周分析 | 各模板打开/回复/效果对比 |
| `inquiries.tsv` | TSV | 收到询盘时 | ★询盘单独记录（时间/邮箱/内容/状态/跟进） |
| `daily-logs/*.tsv` | TSV | 每天结束 | 当天所有操作（搜了什么/存了什么/发了什么） |
| `accounts.tsv` | TSV | 配置时 | token/orgId/点数（⚠️注意脱敏） |

## 三、索引规范（每个文件夹一个 index.md）

### index.md 必含字段（人+AI 导航）

```markdown
# {产品名} 索引

## 📌 当前状态（一句话）
客群已推演 / 搜索 5 次 / 保存 13333 家 / 序列 12轮10封(未激活) / 询盘 3 条
（⚠️ 例中旧写"5轮10封"已过时——现行拍板=**12轮10封**，见 sequence-config/步长拍板记录）

## 🔍 关键信息
- 推演客群: 8 个（见 segments.md）
- 种子网址: 5 个（见 seeds.tsv）
- 已保存客户: 13333（见 customers.tsv）
- 序列: 皮筏艇-西班牙语-12轮10封（见 sequences/）（旧例"5轮"已过时，现行=12轮）
- 模板: 10 个（见 templates/，效果见 template-analysis.md）

## 📊 指标
- 发送/送达/打开/回复: ...
- 询盘: 3 条（见 inquiries.tsv）

## 📁 文件导航
| 文件 | 说明 | 最后更新 |
|------|------|---------|
| segments.md | 客群推演 | 2026-08-21 |
| search-log.tsv | 搜索日志 | 2026-08-21 |
| ...
```

> **规则**：index.md 是**人先看、AI 先查**的入口；操作后**必须更新**（哪怕只改"当前状态"一行）。

## 四、TSV 列规范（固定表头，AI 追加不破坏）

### search-log.tsv
```
date	search_type	keyword	seed_url	total	audit_pages	accuracy_threshold	save_range
2026-08-21	refine	cat food manufacturer...	-	10000	1,500,995,1000	995页40%	前990页
```

### seeds.tsv
```
seed_url	status	source	similar_count	date
<seed-domain>	已用	company-search	10	2026-08-21
<seed-domain>	已用	company-search	10	2026-08-21
newdomain.com	待用	客户提供	-	-
```

### customers.tsv
```
email	company	country	tags	save_task_id	emails_count	date
<email>	Blink Cat Food	GB	猫粮-宠物食品分销商	<id>	3	2026-08-21
```

### inquiries.tsv（★询盘单独记录）
```
date	email	company	subject	content	status	follow_up
2026-08-21	buyer@x.com	X Corp	Catalog?	quiere catálogo	待跟进	-
```

### daily-logs/2026-08-21.tsv
```
time	action	object	result
09:00	推演	Cat Food	8客群
10:00	搜索	cat food manufacturer	10000条
14:00	保存	前990页	13333家
```

## 五、模板本地存储（templates/）

### 每模板一个 md 文件（r01-v01.md）
```markdown
---
template_id: <templateId>
name: 西语-皮筏艇-R01-V01-破冰介绍
round: 1
variant: 1
strategy: 价值主张
language: es
created: 2026-08-21
---
# 西语-皮筏艇-R01-V01-破冰介绍
## Subject
Balsas inflables para su empresa 🚣
（⚠️ 旧例原标题含裸变量 `{联系人:名称}` 已删——★标题纯文案不插变量，正文变量必须 code 包裹，见 sequence-config/RULES 铁律2）
## HTML
<p>Hola <code class="lfxFieldVeriable" contenteditable="false">{联系人:名称}</code>,</p>...
## 效果（回填）
opens: 0 | replies: 0 | last_checked: 2026-08-21
```

> ⚠️ **模板本地存储 + 回填效果**：生成时存本地（含 template_id），每周从后台拉数据回填效果 → 分析哪个模板好。

## 六、询盘记录策略

- **单独记录**（inquiries.tsv）：时间/邮箱/公司/内容/状态/跟进
- **状态机**：待跟进 → 已联系 → 已寄样 → 成交 / 无效
- **每个客户一张表？** ❌ 不推荐（碎片化）；✅ **一张表按状态筛**（+ 有深度的询盘在 daily-logs 补详情）
  - 理由：TSV 一张表 AI 查询/聚合快；客户表过多反而难检索

## 🔗 相关

- [operations-sop.md](operations-sop.md)（代运营 SOP）
- 操作日志机制：`runs/<运营方>/<产品>/ops-log.tsv`（本地数据，不入 Git）

---

> **真实案例演示**：数字与域名为公开仓库作者当时实际运行结果，仅作方法演示，与读者业务无关。
