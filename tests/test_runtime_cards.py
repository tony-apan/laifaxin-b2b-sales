#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""执行卡就位测试：全新 checkout 必须自带 runtime/cards，保存链才可用。"""
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import step_gate  # noqa: E402

CARDS = ROOT / "runtime" / "cards"
EXPECTED = ("S0a", "S2", "S3", "S4", "S5", "S7", "S9", "S10", "S12")


class RuntimeCardsTest(unittest.TestCase):
    def test_s5_card_exists(self):
        """保存链依赖 S5 执行卡；缺卡时 save_company_cli 会 exit 2。"""
        self.assertTrue((CARDS / "S5.json").is_file(),
                        "runtime/cards/S5.json 缺失：全新 checkout 无法执行保存链")

    def test_all_expected_cards_present(self):
        missing = [s for s in EXPECTED if not (CARDS / (s + ".json")).is_file()]
        self.assertEqual([], missing, "缺执行卡: %s" % missing)

    def test_cards_schema_valid(self):
        for state in EXPECTED:
            data = json.loads((CARDS / (state + ".json")).read_text(encoding="utf-8"))
            for key in step_gate._CARD_REQUIRED_FIELDS:
                self.assertIn(key, data, "%s 缺字段 %s" % (state, key))
            self.assertEqual(state, data["state"], "%s 的 state 与文件名不一致" % state)
            self.assertEqual(data["next"], step_gate.load_card(state).data["next"])

    def test_step_gate_loads_s5(self):
        card = step_gate.load_card("S5")
        self.assertEqual("S5", card.state)
        self.assertTrue(len(card.sha256) == 64)


if __name__ == "__main__":
    unittest.main()
