---
doc_id: "md-metadata"
title: "Markdown 元数据规范（MD-METADATA）"
description: "全仓 md 的 frontmatter 与引用规则：新增或修改文档前必读，校验元数据时按此执行。"
type: "spec"
status: "active"
updated: "2026-10-23"
---

# Markdown 元数据规范（MD-METADATA）

一句话定位：本仓库所有 Markdown 文档的 frontmatter 与引用写法唯一标准。写新文档、改旧文档、加目录索引前先读本文，再动手。

## 1. 适用对象

- 本仓库所有 .md 文件。
- 排除：.git/、.local/、runs/<运营方>/<产品>/ 下的用户运行数据。
- 包含：runs/_template/（随库分发的模板）。
- 每个目录必须有 INDEX.md（含 db/、runtime/、tests/ 等代码/数据目录）；新增目录先建 INDEX，再登记到父索引。
- 例外：`.git`、`.local` 等本地目录不纳入（本地数据不入库）；`runs/` 下用户项目目录（`runs/<运营方>/<产品>/`）为本地运行数据，不要求 INDEX。

## 2. 字段表

| 字段 | 必填 | 格式 | 示例 | 常见错误 |
|---|---|---|---|---|
| doc_id | 必填 | 稳定英文 slug：目录名+文件名，小写短横线，全局唯一 | "specs-api-dictionary" | 中文/大写/随标题改名/重复 |
| title | 必填 | 短标题（列表展示用），与正文 H1 同主题；可精简 emoji/编号，不得与 H1 含义矛盾 | "来发信接口字典（排障速查）" | 留空、与 H1 含义矛盾 |
| description | 必填 | 一句具体中文用途，15–80 字（优先 ≤60），双引号包裹 | "按用途列接口与常见报错；出问题先查本表。" | 「本文档介绍……」空话、超长、含未转义引号 |
| type | 必填 | 8 类枚举之一，见第 4 节 | "spec" | 自定义类型、大小写混用 |
| status | 必填 | 统一 active；机器种子保留自身状态 | "active" | 继续写 verified/normative/draft |
| updated | 必填 | YYYY-MM-DD，本次实际修改日期 | "2026-10-23" | 伪造成 created、未来日期 |
| related | 选填 | YAML 数组，只写正文明确引用且真实存在的相对路径 | ["specs/api-dictionary.md"] | 写不存在的路径、外部 URL、凭猜测补 |
| created | 选填 | 仅当能确证首次创建日才写，不伪造 | "2026-08-29" | 把迁移日当创建日 |

## 3. description 写作标准

- 回答两个问题：这份文档解决什么问题？什么时候该读？
- 15–80 字（优先 ≤60），一句中文，具体到场景；宁短勿空。
- 禁止「本文档介绍……」「主要用于……」这类没有信息量的开头。
- 统一双引号包裹，避免冒号、井号破坏 YAML。
- INDEX.md 与索引型 README.md 以「目录索引：」开头。
- 机器种子文件（runs/_template/product-profile.md、runs/_template/operation-record.md）保留自身状态值，不强行写 active。

好例子："按用途列接口、要点、常见报错与替代路径；出问题先查本表再下结论。"

坏例子："本文档介绍来发信接口相关内容。"（没有说清何时读、解决什么）

## 4. type 枚举

| type | 何时用 | 本仓示例 |
|---|---|---|
| rule | 强制规则、铁律、唯一真源 | RULES.md |
| entry | 入口路由、开工必读的索引页 | AGENTS.md、SKILL.md |
| spec | 规格、SOP、契约、设计说明 | specs/operations-sop.md、MD-METADATA.md |
| template | 用户话术卡、随库分发的产物模板 | output-templates/S5-save-confirm.md 与 runs/_template/product-profile.md |
| guide | 教程、操作指引、排障向导 | docs/00-overview.md、specs/beginner-flow.md |
| index | 目录导航 | INDEX.md、specs/INDEX.md |
| record | 历史记录、踩坑台账、复盘、变更日志 | lessons/lessons-learned.md、CHANGELOG.md |
| readme | 面向人的项目或目录说明 | README.md、tools/README.md |

## 5. 完整 frontmatter 模板

~~~yaml
---
doc_id: "specs-example-topic"
title: "示例主题"
description: "一句具体中文用途：解决什么问题、什么时候该读。"
type: "spec"
status: "active"
updated: "2026-10-23"
related: ["../INDEX.md"]
---
~~~

注意：frontmatter 必须在文件最上方，先删 BOM；三横线包裹；冒号后留空格；中文 description 用双引号。

## 6. 三个真实示例

### 6.1 根规则 RULES.md

~~~yaml
---
doc_id: "rules"
title: "来发信获客·规则总纲（唯一真源）"
description: "所有规则的唯一入口：无论会话长短/换电脑，先读本文件再执行。强制流程+校验清单。"
type: "rule"
status: "active"
updated: "2026-10-23"
created: 2026-08-29
---
~~~

### 6.2 话术模板 output-templates/S5-save-confirm.md

~~~yaml
---
doc_id: "output-templates-s5-save-confirm"
title: "S5 保存参数展示（确认后才执行）"
description: "保存方案确认话术：列明保存前 N 家、点数与标签，用户回「确认保存」才执行。"
type: "template"
status: "active"
updated: "2026-10-23"
---
~~~

### 6.3 目录索引 specs/INDEX.md

~~~yaml
---
doc_id: "specs-index"
title: "specs 索引"
description: "目录索引：specs 下规格、SOP 与踩坑台账入口，按主题定位执行细则时读。"
type: "index"
status: "active"
updated: "2026-10-23"
---
~~~

## 7. 新增/修改检查清单

- [ ] 文件首行是 ---，无 BOM，frontmatter 用三横线闭合。
- [ ] doc_id 全局唯一、小写短横线，不随标题频繁改名。
- [ ] title 与正文 H1 同主题（可精简 emoji/编号），无 H1 时用文件名。
- [ ] description 写清问题与阅读时机，15–80 字（优先 ≤60），双引号包裹。
- [ ] type 在枚举内；status 按第 2 节规则；updated 为本次实际修改日。
- [ ] 相对链接按当前文件所在目录可解析；反引号里的 .md 路径存在。
- [ ] 所属目录 INDEX.md 已登记本文档；新增目录已建 INDEX.md 并登记父索引。
- [ ] 跑 bash tools/preflight.sh（文档引用 + 全量测试 + 规则检查），全绿再交付。

## 8. 校验方式

- tests/test_doc_frontmatter.py：检查 6 个必填字段、description 长度（10–80 字）、doc_id 唯一与 slug、type 枚举、status=active（机器种子例外）、updated 真实日期且非未来、description 不重复，并检查本文存在且包含字段名与 type 枚举。
- tests/test_doc_links.py：检查 Markdown 相对链接、反引号 .md 路径、INDEX 覆盖。
- tests/test_doc_naming.py：检查每个目录有 INDEX.md 且覆盖直接子项、文件名 ASCII、旧中文名零残留。
- tools/check_doc_links.py：可单独运行的引用核验脚本，输出坏引用清单；支持标题锚点（含同名标题 `-1/-2` 后缀）与 `<a id>` 锚点。
- tools/check_doc_links.py --sample-index 20：随机抽检 20 行 INDEX 描述（seed 固定可复现），供人工核对描述与目标文件是否一致；语义真实性无法全自动判定，按 20 行/次抽检。
- 已知未机器覆盖（人工检查）：语义级“title/H1 是否同主题”的细腻判断、INDEX 描述与目标文件内容是否一致（用 `--sample-index` 抽检）。

## 9. 参考来源

借鉴 DSH 文档规范（~/.dsh/AGENTS.md、~/.dsh/rules/documentation.md）的元信息、索引与链接原则；字段集合、type 枚举与校验以本仓库本文为准。
