# 📂 runs/ 模板（新公司/新产品从这里复制）

**用法**：以创建时确定且不再改名的 `operator_key/product_key` 建目录：复制 `runs/_template/` 到 `runs/<operator_key>/<product_key>/` → 先按 `specs/product-profile-sop.md` 初始化并确认/decline `product-profile.md` → 按 RULES 状态机 S0→S12 跑 → 每步更新 operation-record 标准状态与证据。

> 📌 **两点说明**：
> 1. 模板内的相对链接（`../../../specs/...`）按**复制后位置**书写——从 `runs/<运营方>/<产品>/` 出发 `../../../` = 仓库根目录，复制后即可解析（模板原位 `_template/` 深度浅一层，原位解析不到属正常）；审批凭证等本地文件在 `.local/`，不入 Git。
> 2. 模板**不含** `verify-*.txt` 空桩——它们是抽验输出，跑完 S12 终检（verify_sequence / verify_exclude / check_template_diff）后生成。

**目录规则**（INDEX「运行档案」+ RULES「多公司/多产品」）：
- 通用层（RULES/specs/lessons/tools）不分公司共享，**不要**往根目录散放产品记录
- 每个产品一个目录：`operation-record.md` + `product-profile.md` + `audit-manifest.json`（S4审计/review绑定）+ `verification-manifest.json`（S11四证据绑定）+ `compliance-check.json`（S12五项结构化证据）+ `recovery-manifest.json`（ERROR受控恢复）+ `reflection/evidence/verify-*`
- **product-profile 是必经档案**：用户没给资料时 AI 主动要一次；拒绝/跳过也要记录 `status: declined`，draft 不得进入 S2；后续 S2/S4/S7/S9 绑定档案 path/hash
- 跑完更新本地运行记录 `db/runs.tsv` 一行（product/seed/…/status/nickname/created/updated；本地数据，不入 Git）
- 运营方信息填本地 `.local/operators/<operator_key>.md`（不入 Git）；公司名/官网/邮箱等可供 AI 建档，但邮件末尾签名区只有纯个人昵称
- 换机/新会话：先跑 `onboard_check.py` 枚举 operation-record status，再按 `specs/migration-handoff.md` 从当前节点继续；禁止从 S0 重跑已有项目

**命名/标签铁律（RULES 7/8）**：
- 标签=**客户群体中文名**（不是你的产品）；记录一律 `id(名称)` 成对
- 内部命名（标签/视图/序列/模板分组）一律中文；邮件正文语言=目标市场（默认全球英语）
