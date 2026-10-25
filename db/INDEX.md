---
doc_id: "db-index"
title: "db 索引"
description: "目录索引：本地数据表 docs.tsv 与 tools.tsv 的用途说明，定位数据来源时读。"
type: "index"
status: "active"
updated: "2026-10-23"
---

# db 索引
> 一句话：这里放文档与工具的登记数据表（本地运行数据表不入 Git）；查登记状态或定位数据来源时读。

## 子目录

| 子目录 | 说明 | 什么时候进 |
|---|---|---|
| （无） | 本目录没有子目录 | - |

## 文件

| 文件 | 说明 | 什么时候读 |
|---|---|---|
| docs.tsv | 核心文档登记表（path/category/title/status/tags） | 查文档是否已登记、补登记时 |
| tools.tsv | 全量工具登记表（含未随库分发的历史条目） | 查工具用途/状态、新增工具登记时 |
