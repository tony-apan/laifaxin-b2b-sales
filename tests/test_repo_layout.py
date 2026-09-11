#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""仓库目录布局纪律测试（防「影子副本」回退）。

背景（2026-09-11 全仓去重）：知识仓根目录曾散落 15 个旧副本——10 个 specs 旧版
（sequence-config/api-reference/data-structure/domain-scale-sop/environment-setup/
migration-handoff/node-playbook/operations-sop/operator-profile-sop/product-profile-sop）
+ lessons-learned/faq/T-token引导 + specs/RULES.md + tools/SKILL.md。它们的「真源」
在 specs/、lessons/、根 RULES.md、根 SKILL.md，根副本停在旧版本，会让 AI 读到过期规则。

另有一组产物模板被错放进 output-templates/（product-profile/segments/templates/
operation-record/reflection + 4 个 json），与 runs/_template/ 的真源重复——output-templates/
只应放「面向用户展示的话术卡片」，产物种子只在 runs/_template/。

本测试锁死这两条，防止再被复制回来。
"""
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# 产品/运营产物文件名：真源只在 runs/_template/(种子) 与 runs/<运营方>/<产品>/(实例)
ARTIFACT_NAMES = (
    "product-profile.md", "segments.md", "templates.md",
    "operation-record.md", "reflection.md",
    "audit-manifest.json", "compliance-check.json", "evidence.json",
    "recovery-manifest.json", "verification-manifest.json",
)

# output-templates/ 只允许「话术卡片」：S<节点>.md / T-*.md / Q*.md / README.md
import re
CARD_RE = re.compile(r"^(?:README\.md|S(?:0a|1[0-2]|[0-9])[^/]*\.md|T-[^/]*\.md|Q[0-9][^/]*\.md)$")

# 通用层真源目录：根目录 .md 不得与这些目录里的同名文件重复（那必是过期副本）
CANON_DIRS = ("specs", "lessons", "methodology")


class RootHasNoArtifactCopiesTest(unittest.TestCase):
    """产物文件不得出现在仓库根目录。"""

    def test_no_artifact_files_at_root(self):
        found = [n for n in ARTIFACT_NAMES if (ROOT / n).exists()]
        self.assertEqual(
            [], found,
            f"根目录出现产物文件副本（真源应在 runs/_template/ 或 runs/<运营方>/<产品>/）: {found}",
        )


class OutputTemplatesOnlyCardsTest(unittest.TestCase):
    """output-templates/ 只放话术卡片，不得混入产物模板或 json。"""

    def test_dir_exists(self):
        self.assertTrue((ROOT / "output-templates").is_dir(), "缺少 output-templates/ 目录")

    def test_only_card_files(self):
        d = ROOT / "output-templates"
        if not d.is_dir():
            self.skipTest("无 output-templates/")
        bad = [p.name for p in sorted(d.iterdir()) if p.is_file() and not CARD_RE.match(p.name)]
        self.assertEqual(
            [], bad,
            f"output-templates/ 混入非话术卡片文件（产物模板请放 runs/_template/）: {bad}",
        )

    def test_no_json(self):
        d = ROOT / "output-templates"
        if not d.is_dir():
            self.skipTest("无 output-templates/")
        jsons = [p.name for p in sorted(d.glob("*.json"))]
        self.assertEqual([], jsons, f"output-templates/ 不应有 json（产物清单放 runs/_template/）: {jsons}")


class NoRootDuplicateOfCanonicalTest(unittest.TestCase):
    """根目录 .md 若与 specs/lessons/methodology 下同名，即为过期副本。"""

    def test_no_duplicate_basenames(self):
        root_md = {p.name for p in ROOT.glob("*.md")}
        dups = {}
        for sub in CANON_DIRS:
            d = ROOT / sub
            if not d.is_dir():
                continue
            for p in d.rglob("*.md"):
                if p.name in root_md:
                    dups.setdefault(p.name, []).append(str(p.relative_to(ROOT)))
        self.assertEqual(
            {}, dups,
            f"根目录存在与真源目录同名的过期副本（删根副本、保留真源）: {dups}",
        )


if __name__ == "__main__":
    unittest.main()
