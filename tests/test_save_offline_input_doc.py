#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""保存命令文档回归（任务C）：SKILL/operations-sop 示例参数与代码一致 + offline-input schema 文档。

缺陷：旧文档示例写 prepare --project/--segment-id/--generation-id/--audit-manifest/--request
和 execute ... --ticket，但代码真实参数是 --request-file/--request-json/--root/--out/--run
与 --ticket-file/--ticket-json。AI 照文档跑会直接参数错误。本测试锁三件事：
  ① specs/save-offline-input.md 存在且含关键字段
  ② 文档内最小样例的 wire_payload 能通过 rule_check 的真实校验
  ③ SKILL.md / operations-sop.md 保存示例只出现代码真实参数
"""
import json
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import rule_check  # noqa: E402

DOC = ROOT / "specs" / "save-offline-input.md"
TRIPLE = chr(96) * 3
DOC_FLAGS = ("--request-file", "--request-json", "--root", "--out", "--run")
KEY_FIELDS = ("project", "source", "platform_product_id", "generation_id", "segment_id",
              "keyword", "wire_payload", "audit_manifest", "budget", "coefficients",
              "selectTotal", "companyTags", "contactTags")
OLD_FLAGS = ("--project <项目键>", "--segment-id", "--generation-id", "--selection-id",
             "--audit-manifest")
JSON_BLOCK = re.compile(TRIPLE + r"json\n(.*?)\n" + TRIPLE, re.S)


def save_block(text):
    """截取真正的 prepare 命令示例代码块（锚定 --request-file，避开正文里的同名词）。"""
    idx = text.find("--request-file")
    assert idx != -1, "文档缺 prepare --request-file 示例"
    start = text.rfind(TRIPLE, 0, idx)
    end = text.find(TRIPLE, idx)
    assert start != -1 and end != -1, "保存示例不在代码块内"
    return text[start:end]


class SaveOfflineInputDocTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        assert DOC.is_file(), "缺少 specs/save-offline-input.md"
        cls.text = DOC.read_text(encoding="utf-8")
        cls.sample = None
        for block in JSON_BLOCK.findall(cls.text):
            try:
                data = json.loads(block)
            except json.JSONDecodeError:
                continue
            if isinstance(data, dict) and "wire_payload" in data:
                cls.sample = data
                break
        assert cls.sample is not None, "文档缺完整最小样例（含 wire_payload 的 json 代码块）"

    # ---------- ① 文档存在 + 关键字段/真实参数 ----------
    def test_doc_has_key_fields_and_flags(self):
        for field in KEY_FIELDS:
            self.assertIn(field, self.text, "schema 文档缺关键字段 " + field)
        for flag in DOC_FLAGS:
            self.assertIn(flag, self.text, "schema 文档缺真实参数 " + flag)

    # ---------- ② 样例逐项过真实校验 ----------
    def test_sample_top_level_fields(self):
        for field in ("project", "source", "wire_payload", "audit_manifest",
                      "budget", "coefficients", "selectTotal"):
            self.assertIn(field, self.sample, "最小样例缺 " + field)
        source = self.sample["source"]
        for key in ("platform_product_id", "generation_id", "segment_id", "keyword"):
            self.assertTrue(str(source.get(key) or "").strip(),
                            "source 缺 " + key)

    def test_sample_wire_payload_is_valid(self):
        wire = self.sample["wire_payload"]
        self.assertEqual(18, len(wire), "wire_payload 必须恰为 18 字段")
        self.assertEqual({"selectTotal": self.sample["selectTotal"]},
                         rule_check.validate_wire(wire))

    def test_sample_budget_and_coefficients_are_valid(self):
        est = self.sample["coefficients"]
        rule_check.check_coefficient_sources(est)
        check = rule_check.check_budget(
            self.sample["selectTotal"], est,
            self.sample["budget"]["budget_points"],
            self.sample["budget"]["max_points"])
        self.assertEqual(675, int(check["points"]), "样例预算示例数应与文档一致")

    # ---------- ③ 命令示例只用代码真实参数 ----------
    def test_skill_and_sop_use_real_cli_flags(self):
        for name in ("SKILL.md", "specs/operations-sop.md"):
            text = (ROOT / name).read_text(encoding="utf-8")
            block = save_block(text)
            with self.subTest(file=name):
                for flag in ("--request-file", "--request-json",
                             "--ticket-file", "--ticket-json"):
                    self.assertIn(flag, block, name + " 保存示例缺真实参数 " + flag)
                for old in OLD_FLAGS:
                    self.assertNotIn(old, block, name + " 保存示例仍用旧参数 " + old)
                self.assertNotRegex(block, r"--request\s", name + " 仍有不存在的 --request")
                self.assertNotRegex(block, r"--ticket\s", name + " 仍有不存在的 --ticket")
                self.assertIn("specs/save-offline-input.md", text,
                              name + " 未指向 offline-input schema 文档")


if __name__ == "__main__":
    unittest.main()
