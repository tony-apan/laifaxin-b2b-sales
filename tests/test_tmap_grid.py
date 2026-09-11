#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""tmap 网格分组测试（2026-09-11 每轮变体数 10→4 后立）。

契约：轮数固定 12（序列步长铁律）；每轮变体数**可调**，由总数动态推算。
任何工具都不得再硬编码 10 或 120（同类教训 L-56：检查项须与内容解耦）。
"""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import tmap_grid  # noqa: E402


def make_map(rounds=12, per_round=4):
    return {f"英-皮筏艇-R{r:02d}-方向-V{v:02d}-RT": f"{r * 100 + v:024x}"
            for r in range(1, rounds + 1) for v in range(1, per_round + 1)}


class PerRoundCountTest(unittest.TestCase):
    def test_current_default_is_4(self):
        self.assertEqual(4, tmap_grid.per_round_count(48),
                         "用户 2026-09-11 拍板：每轮 4 变体 → 整批 48")

    def test_supports_other_valid_counts(self):
        for total, want in ((12, 1), (24, 2), (48, 4), (120, 10), (144, 12)):
            with self.subTest(total=total):
                self.assertEqual(want, tmap_grid.per_round_count(total))

    def test_rejects_non_multiple_of_rounds(self):
        for bad in (0, -1, 47, 50, 121):
            with self.subTest(total=bad):
                with self.assertRaises(tmap_grid.GridError):
                    tmap_grid.per_round_count(bad)


class GroupByRoundTest(unittest.TestCase):
    def test_groups_four_per_round_in_order(self):
        m = make_map(per_round=4)
        groups, exact = tmap_grid.group_by_round(m)
        self.assertTrue(exact, "名称含 R##/V## 时应精确分组")
        self.assertEqual(12, len(groups), "轮数固定 12")
        for (rnd, ids) in groups:
            self.assertEqual(4, len(ids), f"第 {rnd} 轮应有 4 个模板")
        # 第 1 轮必须正好是 V01..V04（顺序正确才不会被错组）
        self.assertEqual([m[f"英-皮筏艇-R01-方向-V{v:02d}-RT"] for v in range(1, 5)], groups[0][1])

    def test_still_supports_ten_per_round(self):
        """旧批次（每轮 10）仍须能正确分组——不得破坏已跑批次的兼容。"""
        m = make_map(per_round=10)
        groups, exact = tmap_grid.group_by_round(m)
        self.assertTrue(exact)
        self.assertEqual([10] * 12, [len(ids) for _, ids in groups])

    def test_falls_back_when_names_unparsable(self):
        m = {f"模板{i:03d}": f"{i:024x}" for i in range(1, 49)}
        groups, exact = tmap_grid.group_by_round(m)
        self.assertFalse(exact, "名称不含 R/V 时应回退并标记不精确")
        self.assertEqual([4] * 12, [len(ids) for _, ids in groups])

    def test_rounds_constant_is_twelve(self):
        self.assertEqual(12, tmap_grid.ROUNDS, "轮数=12 是步长铁律，不是可调项")


class NoHardcodedTemplateCountTest(unittest.TestCase):
    """工具不得再硬编码每轮 10 / 整批 120（防回归）。"""

    def test_build_sequence_uses_grid_helper(self):
        src = (ROOT / "tools" / "build_sequence.py").read_text(encoding="utf-8")
        self.assertIn("from tmap_grid import", src, "build_sequence 应用 tmap_grid 动态推算")
        self.assertNotRegex(src, r"!=\s*120", "build_sequence 不应再硬断言 120")
        self.assertNotRegex(src, r"i\s*\*\s*10", "build_sequence 不应再按固定 10 切分")

    def test_rebuild_templates_uses_grid_helper(self):
        src = (ROOT / "tools" / "rebuild_templates.py").read_text(encoding="utf-8")
        self.assertIn("from tmap_grid import", src, "rebuild_templates 应用 tmap_grid")
        self.assertNotRegex(src, r"==\s*120", "rebuild_templates 不应再硬断言 120")
        self.assertNotRegex(src, r"i\s*\*\s*10", "rebuild_templates 不应再按固定 10 切分")


if __name__ == "__main__":
    unittest.main()
