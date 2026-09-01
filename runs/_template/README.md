# 📂 runs/ 模板（新公司/新产品从这里复制）

**用法**：`cp -r runs/_template runs/<运营方昵称或公司名>/<产品名>/` → 按 RULES 状态机 S0→S12 跑 → 每步把结果写进这三个文件（可核查记录）。

> 📌 **两点说明**：
> 1. 模板内的相对链接（`../../../specs/...`）按**复制后位置**书写——从 `runs/<运营方>/<产品>/` 出发 `../../../` = 仓库根目录，复制后即可解析（模板原位 `_template/` 深度浅一层，原位解析不到属正常）；审批凭证等本地文件在 `.local/`，不入 Git。
> 2. 模板**不含** `verify-*.txt` 空桩——它们是抽验输出，跑完 S12 终检（verify_sequence / verify_exclude / check_template_diff）后生成。

**目录规则**（INDEX「运行档案」+ RULES「多公司/多产品」）：
- 通用层（RULES/specs/lessons/tools）不分公司共享，**不要**往根目录散放产品记录
- 每个产品一个目录：`operation-record.md`（流程每步+参数+结果）+ `reflection.md`（做对的/犯错的/优化点）+ `evidence.json`（机读凭证快照）+ verify-*.txt（抽验输出）
- 跑完更新本地运行记录 `db/runs.tsv` 一行（product/seed/…/status/nickname/created/updated；本地数据，不入 Git）
- 运营方信息（昵称/公司/官网/联系方式/市场语言）填本地 `.local/operator-profile.md`（不入 Git），档案里不重复写

**命名/标签铁律（RULES 7/8）**：
- 标签=**客户群体中文名**（不是你的产品）；记录一律 `id(名称)` 成对
- 内部命名（标签/视图/序列/模板分组）一律中文；邮件正文语言=目标市场（默认全球英语）
