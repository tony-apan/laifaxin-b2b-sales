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

    def test_s2_display_is_capped_at_four(self):
        """S2 平台可能返回 20 类；对新手只展示前 4 类，其余折叠。"""
        t = FLOW.read_text(encoding="utf-8")
        self.assertIn("也只对用户列 4 个", t)
        self.assertIn("S2 候选只展示 4 类", read("AGENTS.md"))

    def test_windows_python_has_no_heredoc(self):
        """Windows Bash 工具 stdin 不关闭，py - <<EOF 会卡死；入口必须禁用 heredoc。"""
        agents = read("AGENTS.md")
        self.assertIn("Windows 下禁用 heredoc", agents)
        self.assertIn("py -3", agents)
        self.assertIn("禁止 `py - <<EOF`", agents)

    def test_s4_audit_requires_semantic_judgment(self):
        """S4 必须读中文描述直接判断，禁止用关键词下结论。"""
        agents = read("AGENTS.md")
        self.assertIn("S4 审计必须语义判断", agents)
        self.assertIn("中文公司描述", agents)
        self.assertIn("--semantic", agents)
        self.assertNotIn("S4 审计必须用 `--mode strict`", agents)

    def test_s4_docs_are_semantic_only(self):
        playbook = read('specs/node-playbook.md')
        self.assertIn('--semantic', playbook)
        self.assertNotIn('--match-words', playbook)
        self.assertIn('禁止用于 S4 定界', playbook)
        card = read('output-templates/S4-audit-running.md')
        self.assertIn('只读中文描述', card)
        self.assertIn('不再参与判定', card)

    def test_threshold_probe_is_product_agnostic(self):
        probe = read('specs/threshold-probe-spec.md')
        self.assertNotIn('户外品类', probe)
        self.assertNotIn('帐篷或成套露营品', probe)
        self.assertIn('product-profile', probe)
        self.assertIn('禁止套用任何行业样例', probe)

    def test_core_points_invalidates_keyword_safe_zone(self):
        """旧的 620 页安全区来自关键词口径，语义复核后必须带作废标记。"""
        t = read('CORE-POINTS.md')
        self.assertIn('旧关键词 classify 口径', t)
        self.assertIn('第 380 页', t)
        self.assertIn('禁止把 620 页当安全区', t)

    def test_flow_has_no_jargon(self):
        t = FLOW.read_text(encoding='utf-8').lower()
        for word in BANNED:
            self.assertNotIn(word.lower(), t, '新手页出现黑话: ' + word)

    def test_problem_ledger_has_no_internal_path(self):
        t = read('specs/problems-and-fixes-2026-10-23.md')
        self.assertNotIn('.local/', t, '台账泄露内部路径')


if __name__ == '__main__':
    unittest.main()
