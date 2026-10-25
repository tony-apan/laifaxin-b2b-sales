---
doc_id: "specs-save-offline-input"
title: "S5 保存 offline-input 最小 JSON schema"
description: "S5 保存输入 JSON schema：字段、最小样例与校验要求，调用保存脚本前读。"
type: "spec"
status: "active"
updated: "2026-10-23"
created: 2026-10-23
author: "AI Agent"
source: "按 tools/save_company_cli.py 与 tools/save_plan.py 代码实读整理"
related: [specs/operations-sop, specs/module-api-map, RULES]
tags: [S5, 保存, offline-input, schema, V2]
audience: 人+AI
---

# S5 保存 offline-input 最小 JSON schema

> 本文件是 `tools/save_company_cli.py prepare --request-file <offline-input.json>` 的输入契约，
> 字段以 `tools/save_company_cli.py::_cmd_prepare` 与 `tools/save_plan.py::prepare_save` 的**代码实读**为准。
> 只描述 prepare 消费的输入；draft/confirmed plan 的结构由 prepare/confirm 生成，不在这里手写。

## 一、链路位置

```
offline-input.json ──prepare（纯本地：零凭据/零 transport/零 auth）──▶ draft plan
draft plan ──confirm（用户原话+确认）──▶ confirmed plan + 唯一票据 + S5V2 render
confirmed plan + render + ticket ──execute（工作空间预检→重验 binding）──▶ 一次保存
```

- `--request-file <path>` 与 `--request-json '<JSON文本>'` **二选一**，同时给会报 `E_BAD_INPUT`。
- 其余 prepare 参数：`--root <仓库根>`（缺省=仓库根）、`--out <draft路径>`（缺省写账簿默认路径）、`--run <执行卡运行标识>`。
- `prepare` 不取凭据、不构造写 transport、不签发票据；产出 draft 后，`confirm` 才绑定 plan/render/ticket。

## 二、顶层字段

| 字段 | 必填 | 类型 | 说明 |
|---|---|---|---|
| `project` | ✅ | string | 稳定项目键 `<operator_key>/<product_key>`，同时用作 query_scope 的 workspace_ref |
| `source` | ✅ | object | 本次保存的来源（见 §三）；缺 `platform_product_id/generation_id/segment_id/keyword` 任一 → `E_PLAN_REQUIRED` |
| `wire_payload` | ✅（真保存） | object | 平台保存 payload，严格 18 字段（见 §五）；prepare 时可缺省，但 confirm/execute 必须有 |
| `audit_manifest` | ✅（confirm 前） | string(path) | 审计证据文件路径（仓库根相对或绝对）；confirm 时不存在 → `E_AUDIT_SCOPE` |
| `budget` | ✅（真保存） | object | `budget_points` / `max_points`（见 §四）；缺来源/缺失 → `E_BUDGET_UNRESOLVED` |
| `coefficients` | ✅（真保存） | object | `estimated_emails_per_company` / `estimated_points_per_email`（见 §四） |
| `selectTotal` | ✅（真保存） | int | 本次保存家数，严格 int 且 >0；缺失 → `E_SELECT_TOTAL_REQUIRED` |
| `count` | 可选 | int | 旧字段别名；若给必须等于 `selectTotal`，否则 `E_COUNT_MISMATCH` |
| `companyTags` | ✅ | array[string] | 公司标签**名称**（铁律7：语言-行业-角色）；与 wire 的标签 ID 必须成对 |
| `contactTags` | ✅ | array[string] | 联系人标签名称；同上 |
| `contactMaxCount` | 可选 | int | 联系人提取档位，只允许 `3/6/9`（缺省 3） |
| `contactVerifyStatus` | 可选 | array[string] | 缺省 `["valid","unkown"]`（平台原拼写） |
| `plan_id` | 可选 | string | 缺省自动生成 `plan-<随机>` |
| `revision` | 可选 | int | 缺省 1 |
| `profile_sha256` | 可选 | string | 产品档案哈希留痕 |
| `audit` | 可选 | object | 审计元数据；通常只填 `audit_manifest` 即可 |

## 三、source 子字段

| 字段 | 必填 | 说明 |
|---|---|---|
| `platform_product_id` | ✅ | 平台产品 id（当前轮来源） |
| `generation_id` | ✅ | 当前生成批次 id；旧 generation/跨产品 → `E_SOURCE_STALE` |
| `segment_id` | ✅ | 客群 id（已登记，如 S01） |
| `keyword` | ✅ | 本次检索原句/已选域名（与 wire_payload.keyword 一致） |
| `selection_id` | 可选 | 已选域名/种子选择记录 id；给了会校验登记存在 |
| `query_scope_key` | 可选 | 已算好的 query_scope 键；缺省由 project+product+generation+selection+keyword+filters+logic+selectSort 计算 |
| `query_scope` | 可选 | 已存 query_scope 对象；缺省自动生成 |
| `filters` / `logic` / `selectSort` | 可选 | 仅在计算 query_scope 时兜底读取；真实保存 schema 以 `wire_payload` 为准 |

## 四、budget / coefficients 子字段

```json
"budget": {
  "budget_points": {"points": 10000, "source_ref": "用户本轮明确预算", "version": "2026-10-23"},
  "max_points":    {"points": 18000, "source_ref": "账户可用点数上限", "version": "2026-10-23"}
},
"coefficients": {
  "estimated_emails_per_company": {"value": 1.5, "source_ref": "历史均值", "version": "CORE-POINTS"},
  "estimated_points_per_email":   {"value": 1.5, "source_ref": "平台点数规则", "version": "2026-10"}
}
```

- 估算：`E = selectTotal × e`（邮箱），`P = ceil(selectTotal × e × p)`（点数）。
- `P > max_points` → `E_MAX_POINTS_EXCEEDED`；`P > budget_points` → `E_BUDGET_EXCEEDED`；预算/系数缺 `source_ref`/`version` → `E_BUDGET_UNRESOLVED`/`E_ESTIMATE_SOURCE`。
- 数字型预算（如 `"budget_points": 10000`）代码也接受，但不留来源，**不推荐**。

## 五、wire_payload 的 18 字段（严格白名单）

| 字段 | 要求 |
|---|---|
| `companyTags` | 非空数组，plan 实际公司标签 ID |
| `companyOption` | 固定 `"nothing"` |
| `companySave` | 固定 `true`（严格 bool） |
| `contactTags` | 非空数组，plan 实际联系人标签 ID |
| `contactOption` | 固定 `"nothing"` |
| `contactVerifyStatus` | 非空字符串数组 |
| `contactPositions` | 固定 `[]` |
| `contactExcludes` | 固定 `[]` |
| `contactMaxCount` | `3/6/9` 之一 |
| `contactSave` | 固定 `true` |
| `selectKeys` | 固定 `[]` |
| `selectSort` | 固定 `{}` |
| `selectTotal` | 严格 int 且 >0 |
| `selectOption` | 固定 `"front"` |
| `filters` | 数组；每项 `{property:"country_code", operator:"include|exclude", value, values, valueType:"select"}`，include/exclude 不可混用，logic=or 时禁用 exclude |
| `filter` | 固定 `{}` |
| `keyword` | 非空字符串（当前来源原句/已选域名） |
| `logic` | `"and"` 或 `"or"` |

白名单外字段（含顶层 `exclude`/`sort`）→ `E_PLAN_PAYLOAD_MISMATCH`；filters 结构不符 → `E_FILTER_SCHEMA`。

## 六、最小样例（可直接作为 --request-file 内容改数据）

```json
{
  "project": "tony/demo",
  "source": {
    "platform_product_id": "prod-123",
    "generation_id": "gen-456",
    "segment_id": "S01",
    "keyword": "caps manufacturer"
  },
  "selectTotal": 300,
  "companyTags": ["英语-客户"],
  "contactTags": ["英语-联系人"],
  "contactMaxCount": 3,
  "contactVerifyStatus": ["valid", "unkown"],
  "audit_manifest": "runs/tony/demo/evidence/audit-manifest.json",
  "budget": {
    "budget_points": {"points": 10000, "source_ref": "用户本轮明确预算", "version": "2026-10-23"},
    "max_points": {"points": 18000, "source_ref": "账户可用点数上限", "version": "2026-10-23"}
  },
  "coefficients": {
    "estimated_emails_per_company": {"value": 1.5, "source_ref": "历史均值", "version": "CORE-POINTS"},
    "estimated_points_per_email": {"value": 1.5, "source_ref": "平台点数规则", "version": "2026-10"}
  },
  "wire_payload": {
    "companyTags": ["tag-company-1"],
    "companyOption": "nothing",
    "companySave": true,
    "contactTags": ["tag-contact-1"],
    "contactOption": "nothing",
    "contactVerifyStatus": ["valid", "unkown"],
    "contactPositions": [],
    "contactExcludes": [],
    "contactMaxCount": 3,
    "contactSave": true,
    "selectKeys": [],
    "selectSort": {},
    "selectTotal": 300,
    "selectOption": "front",
    "filters": [
      {"property": "country_code", "operator": "exclude", "value": "",
       "values": ["CN", "TW", "HK", "MO"], "valueType": "select"}
    ],
    "filter": {},
    "keyword": "caps manufacturer",
    "logic": "and"
  }
}
```

样例自检：`wire_payload` 恰为 18 字段、`validate_wire` 通过；`selectTotal=300`、e=1.5、p=1.5 → E=450 邮箱、P=675 点，低于 budget/max_points。

## 七、常见错误码（prepare 阶段，均为中文报错、exit 2）

| 错误码 | 触发 |
|---|---|
| `E_BAD_INPUT` | `--request-file` 与 `--request-json` 同时给/都没给；JSON 解析失败 |
| `E_PLAN_REQUIRED` | source 缺 `platform_product_id/generation_id/segment_id/keyword` |
| `E_SOURCE_STALE` | generation/segment 不是当前登记来源（旧批次/跨产品/未登记） |
| `E_TAG_RULE` | 标签不合格（客群名/产品名、语言-行业-角色缺项、名称与 ID 不成对） |
| `E_SELECT_TOTAL_REQUIRED` / `E_SELECT_TOTAL_INVALID` | 缺 `selectTotal` / 非严格 int 或 ≤0 |
| `E_COUNT_MISMATCH` | `count` 与 `selectTotal` 不一致 |
| `E_PLAN_PAYLOAD_MISMATCH` | wire 字段缺/多/固定值不符 |
| `E_FILTER_SCHEMA` | filters 结构不符或 include/exclude 冲突 |
| `E_BUDGET_UNRESOLVED` / `E_MAX_POINTS_EXCEEDED` / `E_BUDGET_EXCEEDED` | 预算缺失/超上限/超本次预算 |
| `E_ESTIMATE_SOURCE` | 系数缺值/缺来源/非正数 |
| `E_AUDIT_SCOPE` | confirm 时 `audit_manifest` 不存在 |
| `E_PLAN_DEPENDENCY_CHANGED` | draft 过期或依赖（来源/审计/预算/系数）变化，须重新 prepare |

## 八、相关

- 保存链用法与确认闸门：`SKILL.md`、`specs/operations-sop.md` 的"保存入口"。
- 真实 API/票据分层：`specs/module-api-map.md`。
- 数量对账：`RULES.md` S6 与去重机制。
