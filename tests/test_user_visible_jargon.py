#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""用户可见话术黑话闸门（对抗审查加固，2026-10-23）。

output-templates/*.md 里的代码块就是发给用户看的原文（含 <占位符>）。
按 specs/novice-flow-contract.md §4 术语对照：对外只用左列，右列内部词不得出现在用户可见文本。
允许内部词只出现在：<占位符>、URL、代码块之外的 AI 侧说明。
"""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TEMPLATES = ROOT / "output-templates"

# 术语对照（内部词 -> 对外该怎么说）；只作用于用户可见代码块
BANNED = {
    "客群": "买家类型",
    "序列": "跟进计划",
    "硬门": "检查",
    "审批凭证": "您的确认",
    "preview": "先看样子",
    "状态机": "进度",
    "指纹": "标识",
    "哈希": "校验值",
    "载荷": "内容",
    "消费票据": "确认记录",
    "模版": "模板（规范用字）",
    "验真": "自动核对邮箱真假",
    "未知邮箱": "暂时查不到真假的邮箱",
    "固定标签": "平台里的标记",
    "档案": "资料",
    "推演": "平台列出几类买家",
}
BANNED_PATTERNS = {
    r"\bS\d\d\b": "内部状态编号（如 S12），对外只说第几步",
    r"\.py\b": "脚本名，用户不需要知道",
    r"\.local/": "内部路径",
    r"runs/": "内部路径",
}


def _user_blocks(path):
    text = path.read_text(encoding="utf-8")
    return re.findall(r"```[a-zA-Z]*\n(.*?)```", text, re.S)


def _clean(block):
    text = re.sub(r"https?://\S+", "", block)  # URL 不算黑话
    text = re.sub(r"<[^>\n]*>", "", text)      # <占位符> 由 AI 换真实值
    return text


class UserVisibleJargonGateTest(unittest.TestCase):
    def test_no_internal_terms_in_user_blocks(self):
        problems = []
        for path in sorted(TEMPLATES.glob("*.md")):
            for block in _user_blocks(path):
                clean = _clean(block)
                for word, good in BANNED.items():
                    if word in clean:
                        problems.append(f"{path.name}: 「{word}」→ 应说「{good}」")
                for pattern, why in BANNED_PATTERNS.items():
                    m = re.search(pattern, clean, re.I)
                    if m:
                        problems.append(f"{path.name}: 「{m.group(0)}」→ {why}")
        self.assertEqual([], problems,
                         "用户可见话术出现内部术语：\n" + "\n".join(problems))

    def test_gate_has_meaningful_coverage(self):
        """防闸门空转：必须真的扫到足够多的话术块。"""
        total = 0
        for path in sorted(TEMPLATES.glob("*.md")):
            blocks = _user_blocks(path)
            total += len(blocks)
            for i, b in enumerate(blocks, 1):
                self.assertTrue(b.strip(), f"{path.name} 第 {i} 个话术块为空")
        self.assertGreaterEqual(total, 30, f"只扫到 {total} 个话术块，黑话闸门可能失效")


if __name__ == "__main__":
    unittest.main()
