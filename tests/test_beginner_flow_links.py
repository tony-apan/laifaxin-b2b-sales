#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""新手入口链接纪律测试（2026-10-23）。

目标：新用户装好后，AI 必须能从入口页一路读到 6 步流程；
任何人把入口页删掉或断开引用，本测试立即变红。

对应验收口径：另一个仓的 novice-verified（新手无需人帮就能跑完主流程）。
"""
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FLOW = ROOT / 'specs' / 'beginner-flow.md'
BANNED = ('preview', '硬门', '审批凭证', '哈希', '指纹')


def read(rel):
    return (ROOT / rel).read_text(encoding='utf-8')


class BeginnerFlowLinkTest(unittest.TestCase):
    """入口页存在、被引用、内容完整、无黑话。"""

    def test_flow_file_exists(self):
        self.assertTrue(FLOW.is_file(), 'specs/beginner-flow.md 缺失')

    def test_flow_has_six_steps_and_gates(self):
        t = FLOW.read_text(encoding='utf-8')
        for key in ('找买家', '筛名单', '存客户', '写开发信', '建模板', '建跟进计划'):
            self.assertIn(key, t, '新手页缺步骤: ' + key)
        for key in ('确认激活', '回编号', '截图', 'email-style', '内部口径对照', 'S0', 'S12'):
            self.assertIn(key, t, '新手页缺要素: ' + key)

    def test_flow_referenced_everywhere(self):
        self.assertIn('beginner-flow', read('SKILL.md'), 'SKILL.md 未引用新手页')
        self.assertIn('beginner-flow', read('INDEX.md'), 'INDEX.md 未引用新手页')
        self.assertIn('beginner-flow', read('README.md'), 'README.md 未引用新手页')
        self.assertIn('beginner-flow', read('specs/operations-sop.md'),
                      'operations-sop.md 未引用新手页')

    def test_flow_has_no_jargon(self):
        t = FLOW.read_text(encoding='utf-8').lower()
        for word in BANNED:
            self.assertNotIn(word.lower(), t, '新手页出现黑话: ' + word)

    def test_problem_ledger_has_no_internal_path(self):
        t = read('specs/problems-and-fixes-2026-10-23.md')
        self.assertNotIn('.local/', t, '台账泄露内部路径')


if __name__ == '__main__':
    unittest.main()
