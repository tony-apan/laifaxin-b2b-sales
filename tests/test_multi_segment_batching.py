#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""多客群分批铁律测试（RULES 7d / 2026-09-09 用户拍板：允许分批、接受成本翻倍）。

背景：保温杯真实案例——3 个客群（家居厨房分销+户外露营零售+咖啡器具批发）共用
1 个标签 `英语-咖啡器具与保温杯-渠道商` 和 1 套话术；皮筏艇做对了（3 客群→3 标签→
3 套 120 模板→3 条序列）。本测试把"一客群一标签一计划"固化为可执行断言。
"""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = ROOT / "output-templates"


def read(name):
    return (ROOT / name).read_text(encoding="utf-8")


def user_blocks(text):
    return re.findall(r"```[a-zA-Z]*\n(.*?)```", text, re.S)


class MultiSegmentRuleTest(unittest.TestCase):
    """RULES 必须含铁律 7d，且要点齐全。"""

    def setUp(self):
        self.rules = read("RULES.md")

    def test_rule_exists(self):
        self.assertIn("7d.", self.rules, "缺少铁律 7d（一客群一标签一计划）")
        self.assertIn("一客群一标签一计划", self.rules)

    def test_rule_covers_key_points(self):
        for point in ("独立一对标签", "独立一套 120 模板", "独立一条序列", "禁止把多个客群合并"):
            with self.subTest(point=point):
                self.assertIn(point, self.rules, f"铁律 7d 缺少要点: {point}")

    def test_rule_allows_batching_but_serial_execution(self):
        self.assertIn("允许分批", self.rules)
        self.assertIn("执行必须分批", self.rules)
        self.assertIn("不得并行铺开", self.rules)

    def test_rule_requires_prompt_not_hard_block(self):
        self.assertIn("不硬拦", self.rules)
        self.assertIn("必须提示", self.rules)

    def test_rule_discloses_cost(self):
        self.assertIn("成本如实告知", self.rules)
        self.assertIn("120", self.rules)

    def test_rule_references_real_cases(self):
        """铁律要带正反案例（保温杯混存 / 皮筏艇分档）。"""
        self.assertIn("保温杯", self.rules)
        self.assertIn("皮筏艇", self.rules)

    def test_rule_requires_record_and_segments_files(self):
        self.assertIn("operation-record.md", self.rules)
        self.assertIn("segments/", self.rules)


class S2CardTest(unittest.TestCase):
    """S2 卡必须有：与 S0 措辞区分 + 多客群提示 + 落档 + 串行。"""

    def setUp(self):
        self.text = read("output-templates/S2-客群确认.md")

    def test_distinguishes_from_s0_direction(self):
        self.assertIn("获客方向", self.text, "S2 必须说明与 S0 的『获客方向』的区别")
        self.assertIn("具体客群", self.text)

    def test_multi_segment_prompt_block_present(self):
        block = "".join(user_blocks(self.text))
        for needed in ("建议**分开做**", "共用一个标签", "先做 1 个", "都做"):
            with self.subTest(needed=needed):
                self.assertIn(needed, block, f"S2 多客群提示缺少: {needed}")

    def test_multi_segment_prompt_discloses_cost(self):
        block = "".join(user_blocks(self.text))
        self.assertIn("120", block, "必须如实告知模板数量")
        self.assertIn("跟进计划", block, "必须如实告知序列数量")

    def test_requires_serial_execution(self):
        self.assertIn("分批", self.text)
        self.assertIn("再做下一个", self.text)

    def test_requires_recording(self):
        self.assertIn("落档", self.text)
        self.assertIn("operation-record.md", self.text)
        self.assertIn("segments/", self.text)


class S0CardWordingTest(unittest.TestCase):
    """S0 一律叫『获客方向』，不再叫『客群』——避免与 S2 混淆。"""

    def setUp(self):
        self.text = read("output-templates/S0-画像方案.md")

    def test_uses_direction_wording(self):
        block = "".join(user_blocks(self.text))
        self.assertIn("获客方向", block)
        self.assertNotIn("客群组合", block, "S0 不该再用『客群组合』措辞")
        self.assertNotIn("全部客群", block, "S0 不该再用『全部客群』措辞")

    def test_mentions_next_step_is_specific_segments(self):
        block = "".join(user_blocks(self.text))
        self.assertIn("具体客群", block, "S0 应说明下一轮会推演出具体客群，避免用户以为重复")


class BatchOwnershipInCardsTest(unittest.TestCase):
    """S5/S7/S9 三张卡必须写明本批客群归属。"""

    CASES = (
        ("output-templates/S5-保存确认.md", "本批客群", "标签"),
        ("output-templates/S7-模板确认.md", "批", "客群名"),
        ("output-templates/S9-序列确认.md", "批", "客群名"),
    )

    def test_cards_show_batch_ownership(self):
        for path, *needed in self.CASES:
            text = read(path)
            for token in needed:
                with self.subTest(file=path, token=token):
                    self.assertIn(token, text, f"{path} 缺少批次归属标记: {token}")

    def test_cards_forbid_merging_segments(self):
        for path, *_ in self.CASES:
            text = read(path)
            with self.subTest(file=path):
                self.assertRegex(text, r"铁律\s*7d|每批", f"{path} 必须引用铁律 7d 或写明每批规则")


class SopTest(unittest.TestCase):
    """SOP 必须含多客群分批执行章节。"""

    def test_operations_sop_has_batch_section(self):
        text = read("specs/operations-sop.md")
        self.assertIn("多客群分批执行 SOP", text)
        self.assertIn("执行顺序（严格串行）", text)
        # 公开仓不得出现真实标签ID——只校验结构样例存在
        self.assertIn("<tagA(名称)>", text, "应带分档结构样例")
        # 真实标签ID形如 7位小写字母数字混排且单独出现在表格单元格里
        self.assertNotRegex(text, r"^\| [^|]*\| `[a-z]{2}[a-z0-9]{5}` \|", "公开仓不得出现真实标签ID")

    def test_node_playbook_covers_batching(self):
        text = read("specs/node-playbook.md")
        self.assertIn("多客群分批", text)
        for node in ("每批独立保存", "每批一套模板", "每批一条序列"):
            with self.subTest(node=node):
                self.assertIn(node, text, f"node-playbook 缺少: {node}")


class TemplateNamingConsistencyTest(unittest.TestCase):
    """标签/模板/序列命名必须带客群标识（三方呼应）。"""

    def test_sop_states_three_way_naming(self):
        text = read("specs/operations-sop.md")
        self.assertIn("标签名必须带该客群自身角色", text)
        self.assertIn("序列名带客群档位后缀", text)

    def test_s5_forbids_merged_tag_name(self):
        text = read("output-templates/S5-保存确认.md")
        self.assertIn("不得合并客群", text)
        self.assertIn("英语-咖啡器具-批发商", text)


class SegmentTemplateFilesTest(unittest.TestCase):
    """客群档案模板必须完整且带归属三列（防 AI 建档无标准可依）。"""

    def test_field_dictionary_is_not_empty_stub(self):
        text = read("runs/_template/segments/README.md")
        self.assertGreater(len(text.splitlines()), 20, "字段字典不能是空壳")
        for field in ("segment_id", "segment_name", "query_en", "company_tag", "seeds"):
            with self.subTest(field=field):
                self.assertIn(field, text, f"字段字典缺少: {field}")

    def test_field_dictionary_documents_multi_segment_ownership(self):
        text = read("runs/_template/segments/README.md")
        self.assertIn("多客群归属", text)
        for col in ("标签", "模板", "序列"):
            with self.subTest(col=col):
                self.assertIn(col, text, f"归属表缺少: {col}")

    def test_segment_file_template_exists_with_ownership(self):
        path = ROOT / "runs" / "_template" / "segments" / "S01-客群档模板.md"
        self.assertTrue(path.is_file(), "缺少客群档模板文件")
        text = path.read_text(encoding="utf-8")
        self.assertIn("本客群归属", text)
        for col in ("company", "contacts", "tmap", "序列"):
            with self.subTest(col=col):
                self.assertIn(col, text, f"客群档模板缺少归属项: {col}")

    def test_index_template_has_batch_columns(self):
        text = read("runs/_template/segments.md")
        for col in ("标签", "模板批次", "序列"):
            with self.subTest(col=col):
                self.assertIn(col, text, f"客群索引模板缺少列: {col}")


if __name__ == "__main__":
    unittest.main()
