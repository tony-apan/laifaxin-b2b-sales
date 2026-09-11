#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""tmap 网格解析（★单一真源）：从 gen_templates 产出的 name→id 映射，解析"12 轮 × N 变体"并分组。

为什么单独一个模块：
  `build_sequence.py`（建序列要按轮挂模板）与 `rebuild_templates.py`（重建要按轮改步骤）都要按轮分组，
  且"每轮变体数"是**可调项**（2026-09-11 用户把 10 调成 4）——若各自硬编码 10/120，
  调整时会散落多处、漏改即错（同类教训 L-56：检查项必须与内容解耦）。
  故此处以"总数 ÷ 固定轮数"**动态推算**每轮变体数，调用方不再假设 10。

轮数固定为 12：这是序列步长铁律（30分/5/15/30天），不是可调项（见 sequence-config）。
"""
import re

ROUNDS = 12
_GRID_RE = re.compile(r"R(\d{2}).*V(\d{2})")


class GridError(ValueError):
    """tmap 不满足"12 轮 × 每轮等量变体"的网格要求。"""


def per_round_count(total):
    """由模板总数推算每轮变体数；总数须为 12 的正整数倍。"""
    if not isinstance(total, int) or total <= 0:
        raise GridError(f"模板总数={total!r}，应为正整数")
    if total % ROUNDS:
        raise GridError(f"模板总数={total} 不是 {ROUNDS} 的整数倍——每轮变体数必须一致")
    return total // ROUNDS


def group_by_round(mapping):
    """把 name→id 映射按轮分组。

    返回 ``(groups, exact)``：groups = [(轮号, [该轮模板id, ...]), ...]（轮号升序）；
    exact = True 表示按 name 的 `R##...V##` 网格精确分组，False 表示 name 不含该模式、
    按插入顺序等分（顺序由 gen_templates 产出保证，手工重排则有错组风险）。
    """
    total = len(mapping)
    n = per_round_count(total)
    grid, unparsed = {}, 0
    for name, tid in mapping.items():
        m = _GRID_RE.search(str(name or ""))
        if m:
            grid[(int(m.group(1)), int(m.group(2)))] = tid
        else:
            unparsed += 1
    expected = {(r, v) for r in range(1, ROUNDS + 1) for v in range(1, n + 1)}
    if not unparsed and set(grid) == expected:
        return [(r, [grid[(r, v)] for v in range(1, n + 1)]) for r in range(1, ROUNDS + 1)], True
    ids = list(mapping.values())
    return [(r, ids[(r - 1) * n:r * n]) for r in range(1, ROUNDS + 1)], False
