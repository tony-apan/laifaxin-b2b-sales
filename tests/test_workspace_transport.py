#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""工作空间传输方式测试（2026-09-09 真实双空间对照实测）。

★根因（实测推翻旧认知）：
  平台的工作空间由 **HTTP header `uid`** 决定，**query 参数 `?uid=` 不起作用**。
  实测对照（同一 token、同一 orgId=企业ID）：
    - header uid=企业ID → account/current 余额 4,661,777、isOrg=true（企业空间）
    - query  uid=企业ID → account/current 余额   768,265、isOrg=false（个人空间）
  且 query 传任意值（含不存在的 99999999999）都返回个人空间数据。

  这解释了"给了企业 orgId 却写进个人账号"的事故：旧工具把 uid 放 query，永远操作个人空间。

本测试用静态断言锁定：所有平台调用必须带 header `uid`。
"""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"


def read(name):
    return (TOOLS / name).read_text(encoding="utf-8")


class WorkspaceTransportTest(unittest.TestCase):
    """每个调用平台 API 的脚本都必须把 uid 放进 header。"""

    # 所有会调用平台 API 的脚本
    API_TOOLS = (
        "check_login.py", "workspace_guard.py", "flow_orchestrator.py",
        "tag_add.py", "save_first_n.py", "contact_add.py", "build_sequence.py",
        "activate_sequence.py", "gen_templates.py", "rebuild_templates.py",
        "delete_all_products.py", "segments_infer.py", "audit_company.py",
        "check_template_diff.py", "verify_sequence.py", "verify_exclude.py",
        "wait_save_done.py", "resolve_schedule.py", "seed_resolve.py",
        "find_critical.py", "find_threshold.py",
    )

    def test_every_api_tool_sends_uid_header(self):
        for name in self.API_TOOLS:
            source = read(name)
            with self.subTest(tool=name):
                # curl 形态： "-H", f"uid: {args.org}" 或 {"uid": org}
                has_curl_header = re.search(r'"-H",\s*f"uid: \{(args\.org|org)\}"', source)
                has_urllib_header = re.search(r'"uid":\s*(args\.org|org)\b', source)
                self.assertTrue(has_curl_header or has_urllib_header,
                                f"{name} 未把 uid 放进 HTTP header——query 参数无效，会操作个人空间")

    def test_uid_header_uses_org_not_token(self):
        """header uid 必须取 org（工作空间ID），不能误用 token。"""
        for name in self.API_TOOLS:
            source = read(name)
            with self.subTest(tool=name):
                self.assertNotIn('f"uid: {args.token}"', source, f"{name} header uid 误用 token")
                self.assertNotIn('f"uid: {token}"', source, f"{name} header uid 误用 token")
                self.assertNotRegex(source, r'"uid":\s*(args\.token|token)\b',
                                    f"{name} header uid 误用 token")

    def test_query_uid_is_kept_for_compat_but_not_sole_mechanism(self):
        """允许保留 query uid（向后兼容），但不得只有 query。"""
        for name in self.API_TOOLS:
            source = read(name)
            if "uid={args.org}" in source or 'urlencode({"uid"' in source or "uid={org}" in source:
                with self.subTest(tool=name):
                    self.assertTrue(
                        re.search(r'"-H",\s*f"uid: \{(args\.org|org)\}"', source)
                        or re.search(r'"uid":\s*(args\.org|org)\b', source),
                        f"{name} 只有 query uid、缺 header uid")


class WorkspaceGuardProbeTest(unittest.TestCase):
    """workspace_guard 的探测必须走 header uid，否则永远判个人空间、误拦企业空间。"""

    def test_probe_uses_uid_header(self):
        source = read("workspace_guard.py")
        self.assertIn('"-H", f"uid: {org}"', source,
                      "workspace_guard 探测未带 header uid——会永远判个人空间")

    def test_guard_explains_header_mechanism(self):
        source = read("workspace_guard.py")
        self.assertIn("header", source.lower(), "应注明工作空间靠 header uid 传输")


class DocsMentionHeaderMechanismTest(unittest.TestCase):
    """规则文档必须写明"工作空间靠 header uid"，防后人再走 query 老路。"""

    def test_rules_documents_header_uid(self):
        text = (ROOT / "RULES.md").read_text(encoding="utf-8")
        self.assertIn("header", text.lower())
        self.assertRegex(text, r"header.*uid|uid.*header", "RULES 应写明 header uid 机制")

    def test_api_reference_documents_header_uid(self):
        text = (ROOT / "specs" / "api-reference.md").read_text(encoding="utf-8")
        self.assertRegex(text, r"header.*uid|uid.*header", "api-reference 应写明 header uid 机制")


class ShellAndSeedQualityTest(unittest.TestCase):
    """真机跑出来的两个断点的防回归断言。"""

    def test_gate_check_documented_as_bash(self):
        """断点#1：gate_check.sh 是 bash 脚本，文档必须写 bash 调用，避免误用 python3。"""
        for name in ("RULES.md", "SKILL.md", "specs/node-playbook.md"):
            with self.subTest(file=name):
                text = (ROOT / name).read_text(encoding="utf-8")
                self.assertIn("bash", text, f"{name} 未标注 gate_check 用 bash 调用")
                self.assertRegex(text, r"bash[^\n]*gate_check\.sh",
                                 f"{name} 未给出 bash 调用形式")

    def test_seed_discovery_requires_query_en(self):
        """断点#2：S3 必须用客群 query_en 长句搜种子，禁用单关键词（真机实测单词质量差）。"""
        text = (ROOT / "output-templates" / "S3-种子确认.md").read_text(encoding="utf-8")
        self.assertIn("query_en", text, "S3 未要求用 query_en 长句")
        self.assertRegex(text, r"禁用.{0,10}单关键词|禁止用产品词", "S3 未明确禁用单关键词")
        self.assertIn("paddle", text, "S3 应带真机反例（paddle 单词首页质量差）")

    def test_node_playbook_seed_rule_synced(self):
        text = (ROOT / "specs" / "node-playbook.md").read_text(encoding="utf-8")
        self.assertRegex(text, r"必须用 query_en 完整长句", "node-playbook 未同步长句规则")


class AuditToolProductWordsTest(unittest.TestCase):
    """断点#3：审计工具内置词表是宠物包装样例，换产品必须传 --match-words，否则全页 0%。"""

    def test_requires_match_words(self):
        import subprocess, sys
        result = subprocess.run(
            [sys.executable, str(TOOLS / "audit_company.py"),
             "--query", "x", "--pages", "1", "--token", "t", "--org", "o"],
            capture_output=True, text=True, timeout=30)
        self.assertEqual(2, result.returncode, "缺 --match-words 应 fail-fast 退出 2")
        self.assertIn("--match-words", result.stdout)

    def test_docstring_marks_words_as_product_specific(self):
        source = read("audit_company.py")
        self.assertIn("产品词必须由调用方传入", source)
        self.assertIn("0%", source, "应写明不带产品词的后果")

    def test_sop_requires_match_words(self):
        """S4 相关 SOP/卡必须写明审计要带本产品词。"""
        for name in ("specs/threshold-method.md", "output-templates/S4-审计进行中.md"):
            text = (ROOT / name).read_text(encoding="utf-8")
            with self.subTest(file=name):
                self.assertRegex(text, r"match-words|产品词",
                                 f"{name} 未写明审计需带本产品词")


class TemplateIdempotencyAndFolderTest(unittest.TestCase):
    """真机断点#6/#8：分组 id 取值 + 模板幂等复用。"""

    def test_folder_reuse_reads_underscore_id(self):
        source = read("gen_templates.py")
        # 必须读 _id（真机返回字段名），且不得误取 foid（那是父目录字段，值常为 "0"）
        self.assertIn('f.get("id") or f.get("_id")', source, "分组复用须读 _id")
        self.assertNotIn('or f.get("foid")', source, "不得把 foid（父目录字段）当分组 id")

    def test_template_add_is_idempotent(self):
        """重跑时同名模板应复用现有 id，而不是整体报失败。"""
        source = read("gen_templates.py")
        self.assertIn("_existing_template_id", source, "缺同名模板复用查询")
        self.assertIn("幂等复用", source, "缺幂等复用提示")

    def test_plan_duplicate_precheck_exists(self):
        """生成前预检 plan 重复（真机：旧流程建完整批才发现撞车）。"""
        source = read("gen_templates.py")
        self.assertIn("check_plan_duplicates", source)
        self.assertIn("去重预检", source)


if __name__ == "__main__":
    unittest.main()
