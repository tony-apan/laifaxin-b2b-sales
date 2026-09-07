# Website Profile（独立可选模块）

这个目录只放网站资料增强模块的结构契约。完整执行规则见：

- [网站资料增强 SOP](../specs/website-profile-sop.md)
- [用户确认话术](../output-templates/S0a-网站资料确认.md)
- [CLI 工具](../tools/website_profile.py)
- [候选模板](../runs/_template/website-profile-candidate.json)
- [补丁模板](../runs/_template/website-profile-patch.json)

## 它不做什么

- 不联网、不爬站；网页由 AI 的公开页面读取能力访问。
- 不需要来发信 token 或 orgId。
- 不修改联系人、模板、序列、激活状态或线上网站。
- 不改变 S0-S12 状态编号。
- 没有网址、用户跳过或模块失败时，不影响原获客流程。

## 数据链

```text
AI 读取公开页面
→ 生成六区 candidate
→ validate-candidate
→ prepare-patch（公司/产品分开）
→ AI 展示条目、差异、patch_id/patch_sha256
→ 用户明确批准
→ approve-patch --ack-patch <patch_id>
→ apply-patch
→ 产品档案回 draft，再走现有 product_profile.py confirm
```

候选的六个区：`facts`、`company_claims`、`ai_analysis`、`recommendations`、`conflicts`、`unverified`。只有 `facts/company_claims` 可被选入补丁；冲突或未核实内容存在时整份补丁拒绝。

JSON Schema 用于结构提示，最终安全校验以 `tools/website_profile_utils.py` 为准。
