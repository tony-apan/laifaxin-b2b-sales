#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""发布一致性回归：版本号、CHANGELOG、README/总索引入口、模板改名映射。

背景：v0.6.0 发布前发现 SKILL 版本与 CHANGELOG 脱节，onboard_check 的版本检查
（SKILL 版本 vs GitHub 最新 Release）会把新分支误报成「已是最新」；演示稿也没有
挂在 README 首屏。这里把三件事机器锁住。
"""

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


class ReleaseConsistencyTest(unittest.TestCase):
    def test_skill_version_matches_latest_changelog(self):
        skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        m = re.search(r"(?m)^version:\s*(\d+\.\d+\.\d+)\s*$", skill)
        self.assertIsNotNone(m, "SKILL.md 缺 version 行")
        changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
        versions = re.findall(r"(?m)^##\s*\[v(\d+\.\d+\.\d+)\]", changelog)
        self.assertTrue(versions, "CHANGELOG.md 缺版本条目")
        self.assertEqual(
            m.group(1), versions[0],
            "SKILL.md 版本与 CHANGELOG 最新条目不一致：先同步再发布",
        )

    def test_readme_and_root_index_link_walkthrough(self):
        for name in ("README.md", "INDEX.md"):
            text = (ROOT / name).read_text(encoding="utf-8")
            self.assertIn(
                "docs/14-novice-walkthrough-demo.md", text,
                f"{name} 没有挂 docs/14 演示稿；新手找不到全流程说明",
            )

    def test_changelog_records_template_rename_mapping(self):
        changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
        for stage, rest, new in (
            ("S0", "任务菜单.md", "S0-task-menu.md"),
            ("S5", "保存确认.md", "S5-save-confirm.md"),
            ("S7", "模板确认.md", "S7-template-confirm.md"),
            ("S12", "激活确认.md", "S12-activation-confirm.md"),
        ):
            old = stage + "-" + rest
            self.assertIn(old, changelog, f"CHANGELOG 缺旧模板名 {old} 的迁移记录")
            self.assertIn(new, changelog, f"CHANGELOG 缺新模板名 {new} 的迁移记录")


if __name__ == "__main__":
    unittest.main()
