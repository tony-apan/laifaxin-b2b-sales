---
title: "运营方档案 SOP（AI 主动索取·跨产品复用·换机迁移）"
description: "用户自己的公司级资料如何由 AI 渐进索取并写入 .local/operators/<operator_key>.md；与产品档案分层；邮件签名只读纯昵称；换机随 .local 迁移。"
created: 2026-09-04
updated: 2026-09-04
author: "AI + 用户对抗完善"
related: [RULES.md, product-profile-sop.md, migration-handoff.md, ../tools/operator_profile.py]
tags: [运营方档案, 主动索取, 公司资料, 签名, 换机]
status: verified
audience: AI优先
---

# 运营方档案 SOP（公司级资料）

> **分层原则**：`.local/operators/<operator_key>.md` 存跨产品复用的公司级资料；`runs/<operator_key>/<product_key>/product-profile.md` 存单个产品的产品事实。两者都不保存 token，也不保存潜在客户/联系人第三方资料。

## 1. 什么时候主动问

开跑仍先按渐进规则只问 token + 纯个人昵称 + 一句话产品。进入 S0a 产品知识档案时，若公司级资料未记录，AI **单独问一次**，不得和 ABCD 方案选择挤在同一轮：

```text
为了以后换电脑或换产品时不用重复问，我可以把您的公司资料存到本机档案（不会上传，也不会进入邮件签名）：
① 公司名 ② 官网/产品目录链接 ③ 您自己的联系邮箱
④ 目标市场/默认语言
有就直接发；没有或不想给可回复“跳过”。认证、产能、MOQ、交期、价格带请放到下一步的产品资料里。
```

用户跳过就继续，不纠缠；没给的字段留空，禁止推断或编造。

## 2. 回落工具

```bash
python3 tools/operator_profile.py init --operator-key <固定标识> --nickname <纯个人昵称>
python3 tools/operator_profile.py update --operator-key <固定标识> --company-name "<公司名>" --website "https://..." --contact-email "..." --target-markets "..." --default-languages "..."
python3 tools/operator_profile.py validate --operator-key <固定标识>
python3 tools/operator_profile.py status --operator-key <固定标识>
```

Windows 使用 bootstrap 输出的 Python 命令（通常为 `py`）。`operator_key` 创建后不可因为补充公司名而改；否则 runs 路径、审批项目键与换机续接会断裂。

## 3. 邮件边界

- **签名区唯一来源**：`nickname`，且必须通过 `profile_utils.validate_nickname`。邮件末尾最后一段只能是该纯昵称。
- `company_name` / `website` / `contact_email`：供 AI 读取官网、辨别公司与产品、建立档案和跨产品复用；**不进入签名区**。
- 产品认证、产能、MOQ、交期、价格带：写入单个产品的 `product-profile.md`；只有用户确认且有字段级来源时，才可作为**正文卖点**，仍不得进入签名区。
- token、客户/潜在联系人邮箱、电话和名单：禁止写入运营方档案。

## 4. 换机与新会话

`.local/operators/<operator_key>.md` 随 `.local/` 一起按 `migration-handoff.md` 迁移。新 AI 先运行 `operator_profile.py validate/status`，再读目标产品的 product-profile；已有非空字段不重复索取。token 不在档案中，新机重新获取。

## 5. 校验清单

- [ ] nickname 是纯个人昵称，未混入公司/职位/网址/邮箱
- [ ] operator_key 与 `runs/<operator_key>/` 一致且未改名
- [ ] 官网为完整 http/https URL；联系邮箱是用户自己的公司联系方式
- [ ] 档案不含 token，不含客户/潜在联系人第三方信息
- [ ] 公司资料与产品资料分层，不把认证/MOQ 等塞进运营方档案
- [ ] 邮件签名生成器只读取 nickname
