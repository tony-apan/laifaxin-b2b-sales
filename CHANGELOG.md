# Changelog

本公开库版本记录。语义化版本：修复/改进 → 递增 minor（v0.x.0）；新首版 v0.1.0。

## [v0.2.0] - 2026-09-02
正式修复回落（对应对抗审查 ISS-48~53 与教训 L-44~47，脱敏抽象）：

### 修复
- **S2 推理档案建档**：客群推演须用 `inference-product-add` 建"推理档案"（旧用基础档案导致 `inference-segment-generate` 返回 500）；generate 后轮询列表（6×10s）直到非空。
- **审批闸门表头**：审批流水首次创建文件补写表头，并容错无表头旧文件——修复新账号首次使用时审批闸门全部失效。
- **按标签查人 filters 数组**：联系人按标签过滤须用 `filters` 数组 `[{property:tags,operator:include,...}]`（旧 `filter.tags` 返全库 total，导致对账假通过）。
- **清空工具防呆**：delete 类工具统一 `--execute` + `--confirm DELETE-ALL` 双重确认（含 delete_all_products 极性修复）。

### 新增
- `tools/activate_sequence.py`：S12 激活（激活后回读 status:active 防接口假成功；`--status` 只读查；须审批 + 用户明确"确认激活"）。激活接口早期 500 已实测恢复。
- `tools/seed_resolve.py`：S3 种子域名反查——候选公司名 → 精确查找反查真实域名（相似搜索候选无 domain 字段，拿公司名搜会命中同名异司）。

### 改进
- 模板钩子规范：正文首句须为买家视角钩子（痛点/利益），禁止 "We manufacture…" 能力陈述开场。
- 教训 L-44~L-47 入 lessons-learned.md（档案体系/判据固化/种子选型/激活防假等）。

## [v0.1.0] - 2026-09-01
首版发布：净化公开库（通用层 + 演示案例），GPL-3.0。
