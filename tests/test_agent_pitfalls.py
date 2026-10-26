# -*- coding: utf-8 -*-
"""agent-pitfalls.json 契约测试：结构完整、引用真实、与实现和文档不漂移。

对抗审查发现的真实风险：排障库是给 AI 直接执行的指令集——
一旦它引用了不存在的脚本，或声明的确认语义与 approval.py 相反，
AI 会照错的库执行。本测试把那三类漂移变成红灯。
"""
import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "agent-pitfalls.json"
HUMAN_DOC = ROOT / "docs" / "15-live-run-pitfalls.md"
REQUIRED = ("id", "match", "cause", "action", "verify")


class AgentPitfallsTest(unittest.TestCase):
    def setUp(self):
        self.data = json.loads(DATA.read_text(encoding="utf-8"))
        self.items = self.data["items"]

    def test_schema_and_unique_ids(self):
        self.assertGreaterEqual(len(self.items), 12, "排障库条目过少，覆盖不足")
        ids = []
        for item in self.items:
            for key in REQUIRED:
                value = item.get(key)
                self.assertIsInstance(value, str, f"{item.get('id')} 的 {key} 不是字符串")
                self.assertTrue(value.strip(), f"{item.get('id')} 的 {key} 为空")
            ids.append(item["id"])
        self.assertEqual(len(ids), len(set(ids)), "排障库 id 重复")

    def test_referenced_scripts_exist(self):
        text = json.dumps(self.data, ensure_ascii=False)
        for rel in sorted(set(re.findall(r"tools/[a-z_0-9]+\.py", text))):
            self.assertTrue((ROOT / rel).is_file(), f"排障库引用了不存在的脚本：{rel}")

    def test_numeric_confirm_claim_matches_approval(self):
        src = (ROOT / "tools" / "approval.py").read_text(encoding="utf-8")
        match = re.search(r"_NUMERIC_CONFIRM_STATES\s*=\s*\(([^)]*)\)", src)
        self.assertIsNotNone(match, "approval.py 缺 _NUMERIC_CONFIRM_STATES，排障库的确认语义无从校验")
        states = set(re.findall(r'"(S\d+)"', match.group(1)))
        self.assertTrue({"S7", "S9", "S10"} <= states, f"排障库声明 S7/S9/S10 可回数字，实现却是 {states}")

    def test_human_doc_rows_match_machine_library(self):
        rows = [ln for ln in HUMAN_DOC.read_text(encoding="utf-8").splitlines() if re.match(r"^\|\s*\d+\s*\|", ln)]
        self.assertEqual(len(self.items), len(rows), "人读踩坑表条目数与机器库不一致，会出现两边说法不同")


if __name__ == "__main__":
    unittest.main()
