---
profile_version: 1
status: ${STATUS}
operator_key: ${OPERATOR_KEY}
product_key: ${PRODUCT_KEY}
created_at: ${CREATED_AT}
updated_at: ${UPDATED_AT}
confirmed_at:
confirmed_by:
confirm_quote:
content_sha256:
sources_status: ${SOURCES_STATUS}
sources_present: no
---

# 📇 产品知识档案（product-profile·机读）

> **作用**：把用户自己的产品/公司商业资产（官网 / 目录 / 卖点 / 认证 / 产能 / MOQ / 交期 / 价格带）提炼成本档案，供 **S2 客群推演 / S4 客户线判定 / S7 开发信卖点 / S9 序列钩子** 复用；零上下文 AI 断点续接先读它。
> **怎么建**（product_profile.py）：`init` 建档（draft）→ AI 填 8 字段 → 用户拍板 `confirm --by <纯昵称> --quote <原话>` → status=confirmed；用户明确不给资料 → `init --declined`，仍建档（status=declined，只能用无具体事实的通用口径）。
> **硬边界（2026-09-04 用户拍板）**：
> - 邮件正文签名=**纯个人昵称**（如 Tony/Iris）。公司名/官网/邮箱/职位/电话/认证等**绝不进签名**，只可写进本档案供建档/背调。
> - 用户自己的公司名/官网/邮箱/认证/产能/MOQ/交期/价格带：用户没给时 **AI 主动要一次**（给模板可跳过、不逼问）；拒绝则 status=declined 仍保留本档案。
> - **第三方信息禁止**：客户/潜在联系人的任何第三方联系方式（email、电话、名单、清单）一律不得写入本档案。
> - 状态机：status=draft/confirmed/declined；资料请求 sources_status=requested/provided/partial/declined；确认事实 sources_present=yes/partial/no。
> - 字段来源：`用户` / `URL:https://完整来源地址` / `推断` / `none`；推断须标⚠️。数字/认证等具体事实只有“用户”或完整URL来源才可用于正文。
> - 变更记录 append-only：只追加不改写历史行。

## ① 产品定位（卖给谁/解决什么）
- 内容：（待补）
- source: none
- confidence: low

## ② 产品线（品类/子品类/SKU/成分配比）
- 内容：（待补）
- source: none
- confidence: low

## ③ 核心卖点（≤5 条，每条一句：为什么买你）
- 内容：（待补）
- source: none
- confidence: low

## ④ 目标客群+市场（国家/语言/渠道角色）
- 内容：（待补）
- source: none
- confidence: low

## ⑤ 规格/认证（型号/标准号/证书/参数——有来源才写）
- 内容：（待补）
- source: none
- confidence: low

## ⑥ 差异化（vs 竞品强在哪）
- 内容：（待补）
- source: none
- confidence: low

## ⑦ 合规/禁忌（禁运区/受管制品类/环保声明——有依据才写）
- 内容：（待补）
- source: none
- confidence: low

## ⑧ 可引用数字（产能/MOQ/交期/价格带——用户给或官网可查才写，没有不编）
- 内容：（待补）
- source: none
- confidence: low

> source 取值：none / 用户 / `URL:https://完整来源地址` / 推断（⚠️须核对）；confidence：low / medium / high。
> 正文卖点引用规则：仅 status=confirmed 且本档案有来源的字段可进邮件正文卖点；declined 只能用无具体数字/认证的通用口径。签名永远是纯昵称。

## 变更记录（append-only·只追加不改写）
| 时间 | 操作 | 摘要 |
|------|------|------|
| ${CREATED_AT} | init | 建档（${STATUS}）——AI 主动要一次产品资料：给了→填8字段+confirm；拒绝→保持 declined |
