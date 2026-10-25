#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""新手首测（第 0–4 屏）暴露的边界话术回归。

2026-10-23 真人视角模拟发现 5 个会卡住的场景，修复后用本文件锁死：
1) 第 0 屏用户只答一半 / 回「1」/ 只发产品照片；
2) 连接平台时只有 Safari、或用户说「先不连」；
3) 平台只返回一家样板客户；
4) 审计总时长没有依据时不许空口承诺；
5) 产品照片/链接代替文字时的处理。
"""
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(rel):
    return (ROOT / rel).read_text(encoding="utf-8")


class NoviceEdgeCaseTest(unittest.TestCase):
    def test_half_answer_and_numeric_reply_rule(self):
        opening = read("output-templates/S0-opening-questions.md")
        self.assertIn("C1c", opening)
        self.assertIn("不得把数字当昵称", opening)
        self.assertIn("只答一半时"[:5], opening + read("specs/beginner-flow.md"))

    def test_beginner_flow_notes_half_answer(self):
        flow = read("specs/beginner-flow.md")
        self.assertIn("只答一半时", flow)
        self.assertIn("不得把数字当昵称", flow)

    def test_safari_and_refuse_connect_paths(self):
        token = read("output-templates/T-token-guide.md")
        self.assertIn("Safari", token)
        self.assertIn("不想连", token)

    def test_single_seed_candidate_has_no_dead_end(self):
        s3 = read("output-templates/S3-seed-confirm.md")
        self.assertIn("只返回一家样板", s3)
        self.assertIn("再找一轮", s3)
        self.assertIn("该回什么", s3)
        self.assertIn("回复数字 1", s3)

    def test_audit_eta_must_not_be_guessed(self):
        s4 = read("output-templates/S4-audit-running.md")
        self.assertIn("总时长不许空口编", s4)
        self.assertIn("第一批", s4)

    def test_product_photo_or_link_is_accepted(self):
        profile = read("output-templates/S0-product-profile.md")
        self.assertIn("产品照片", profile)


if __name__ == "__main__":
    unittest.main()
