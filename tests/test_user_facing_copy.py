#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""用户可见文案纪律测试（2026-09-09 用户拍板：小白要能看懂，不许用黑话）。

背景：某次外部 AI 的输出给用户看的是 `SEND_READY` / `NOT_SEND_READY` / `Shadow Run` /
"十三套单测全部 0 失败" / "5 个文件已更改 +425 -0"，还要求用户设 `LAIFAXIN_TOKEN`
环境变量、声称可以用"只读接口取授权"——小白完全看不懂，且违反两条铁律。

本测试只检查**用户可见部分**（output-templates 里代码块内的正文），
不检查"AI 执行要点与边界"（那是给 AI 看的，允许出现内部术语）。
"""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = ROOT / "output-templates"

# 用户可见文案中禁止出现的内部术语/黑话
FORBIDDEN_IN_USER_VIEW = (
    "SEND_READY", "NOT_SEND_READY", "Shadow Run", "shadow run",
    "blockers", "Blocker", "实调回填", "十三套单测", "单测",
    "sha256", "content_sha256", "profile_version",
    "status=", "status:", "confirmed", "declined", "draft",
    "approval", "approvals.tsv", "claims",
    "runs/", ".local/", ".py ", ".py`", "gate_check", "workspace_guard",
    "S0a", "S11", "S12", "ERROR_BLOCKED", "evidence_mode",
    "query_en", "base-info", "similar-list", "lfxFieldVeriable",
    "SEND_READY_WITH_MANUAL_REPLY_REVIEW",
)

# 明确禁止的"要求用户做的事"（凭据相关铁律）
FORBIDDEN_USER_ASKS = (
    "环境变量", ".env", "export ", "set TOKEN", "LAIFAXIN_TOKEN",
)


def user_view_blocks(text):
    """提取 markdown 中代码块内的内容（= 用户实际看到的话术）。"""
    return re.findall(r"```[a-zA-Z]*\n(.*?)```", text, re.S)


class UserFacingCopyDisciplineTest(unittest.TestCase):
    def test_no_internal_jargon_in_user_visible_blocks(self):
        for path in sorted(TEMPLATES.glob("*.md")):
            if path.name == "README.md":
                continue
            blocks = user_view_blocks(path.read_text(encoding="utf-8"))
            for index, block in enumerate(blocks, 1):
                for term in FORBIDDEN_IN_USER_VIEW:
                    with self.subTest(file=path.name, block=index, term=term):
                        self.assertNotIn(term, block,
                                         f"{path.name} 第 {index} 个用户话术块出现内部术语「{term}」")

    def test_no_credential_asks_in_user_visible_blocks(self):
        for path in sorted(TEMPLATES.glob("*.md")):
            if path.name == "README.md":
                continue
            for index, block in enumerate(user_view_blocks(path.read_text(encoding="utf-8")), 1):
                for ask in FORBIDDEN_USER_ASKS:
                    with self.subTest(file=path.name, block=index, ask=ask):
                        self.assertNotIn(ask, block,
                                         f"{path.name} 第 {index} 个用户话术块要求用户「{ask}」——凭据只能浏览器复制后粘贴到聊天框")

    def test_no_readonly_token_claim(self):
        """平台没有只读 token 这种权限级别——不得向用户宣称只读授权。

        注意：规则文档里"禁止声称只读 token"这类**禁令原文**是允许的（它是给 AI 看的边界），
        只有出现在**用户话术块**里才算违规。"""
        for path in sorted(TEMPLATES.glob("*.md")):
            for index, block in enumerate(user_view_blocks(path.read_text(encoding="utf-8")), 1):
                for bad in ("只读 token", "只读token", "只读接口取授权", "只读授权"):
                    with self.subTest(file=path.name, block=index, term=bad):
                        self.assertNotIn(bad, block,
                                         f"{path.name} 第 {index} 个用户话术块出现「{bad}」——平台无只读 token")


class ConnectCardTest(unittest.TestCase):
    """连接平台卡（唯一需要用户动手的一步）必须存在且包含关键要素。"""

    def setUp(self):
        self.path = TEMPLATES / "T-token引导.md"
        self.text = self.path.read_text(encoding="utf-8")

    def test_card_exists_and_is_single_source(self):
        self.assertTrue(self.path.is_file(), "连接平台引导卡必须存在")
        # 不得再新增重复的同类卡（单一真源）
        duplicates = [p.name for p in TEMPLATES.glob("*连接平台*.md")]
        self.assertEqual([], duplicates, f"连接平台话术应只有 T-token引导.md，发现重复: {duplicates}")

    def test_user_block_has_step_by_step_and_no_jargon(self):
        block = user_view_blocks(self.text)[0]
        for needed in ("web.laifaxin.com", "控制台", "accesstoken", "orgId"):
            self.assertIn(needed, block, f"连接卡缺少关键要素: {needed}")
        self.assertIn("不搜索", block, "连接卡必须说明只读、不搜索不保存")

    def test_card_forbids_env_var_and_readonly_claim(self):
        self.assertIn("禁止要求用户设置环境变量", self.text)
        self.assertIn("只读 token", self.text)  # 在"禁止"语境中出现
        self.assertIn("禁止声称", self.text)

    def test_card_specifies_check_order(self):
        """检查顺序：登录校验 → 落点校验 → 账号状态卡。"""
        for needed in ("check_login.py", "workspace_guard.py", "S0-连接成功.md"):
            self.assertIn(needed, self.text, f"连接卡缺少检查步骤: {needed}")


class ProfileCardStartsPointTest(unittest.TestCase):
    """档案确认卡必须带起点引导（用户截图圈出的地方）。"""

    def setUp(self):
        self.text = (TEMPLATES / "S0-产品知识档案.md").read_text(encoding="utf-8")

    def test_user_block_mentions_start_point(self):
        block = user_view_blocks(self.text)[0]
        self.assertIn("询盘客户", block, "档案确认卡必须引导用户提供询盘客户/精准买家官网")
        self.assertIn("起点", block)

    def test_user_block_has_no_internal_status_words(self):
        block = user_view_blocks(self.text)[0]
        for term in ("status=", "sha256", "runs/", "draft", "confirmed", "declined", "product_profile.py"):
            self.assertNotIn(term, block, f"档案卡用户话术出现内部术语: {term}")

    def test_next_step_is_connect_platform(self):
        self.assertIn("T-token引导.md", self.text, "档案确认后必须接连接平台")


class SeedCardGuidanceTest(unittest.TestCase):
    """S3 必须主动引导，而不是旧版的"用户没网址就不追问"。"""

    def setUp(self):
        self.text = (TEMPLATES / "S3-种子确认.md").read_text(encoding="utf-8")

    def test_active_guidance_present(self):
        self.assertIn("优先主动引导", self.text)
        self.assertNotIn("自动走标准路径，**不追问**", self.text,
                         "旧版'用户没网址就不追问'必须删除——改为优先引导询盘客户/精准买家官网")

    def test_start_point_must_map_to_segment(self):
        """起点必须关联客群（S4 匹配率分母/客户线计数依赖）。"""
        self.assertIn("起点必须关联客群", self.text)
        self.assertIn("S4", self.text)


class FlowOrderAndSeedInferenceTest(unittest.TestCase):
    """静态核对 flow_orchestrator 的流程顺序与新行为（方案B）。"""

    def setUp(self):
        self.source = (ROOT / "tools" / "flow_orchestrator.py").read_text(encoding="utf-8")

    def test_connect_happens_before_segment_inference(self):
        """连接平台（登录检查）必须在 S2 推演之前。"""
        login_at = self.source.index("check_login_first()")
        s2_at = self.source.index("●S2 SEGMENT_PENDING")
        self.assertLess(login_at, s2_at, "登录检查必须早于客群推演")

    def test_both_paths_infer_segments(self):
        """方案B：S2 推演不得再被 `if not pathA` 挡住。"""
        marker = "if not pathA:\n    print(" + chr(34) + chr(9679) + "S2 SEGMENT_PENDING"
        self.assertNotIn(marker, self.source, "S2 不能再只在标准路径执行")
        self.assertIn('if _CUR_STATE in ("S1", "S2", "")', self.source,
                      "S2 应以流程状态（S1/S2）为条件，两条路径都推演")

    def test_seed_context_feeds_inference(self):
        """有种子时，种子描述要并入推演输入。"""
        self.assertIn("def seed_context(", self.source)
        self.assertIn("种子参考买家", self.source, "种子描述必须并入推演输入")
        self.assertIn('api("domain/base-info"', self.source, "种子描述来自只读 base-info")

    def test_inference_failure_degrades_without_claiming_success(self):
        """推演失败要告警继续，且不得谎称成功/推进 S2。"""
        self.assertIn("客群推演未完成", self.source)
        self.assertIn("不影响后面选起点", self.source)
        # 推演失败分支内不得出现 update_frontmatter 推进 S2
        fail_block = self.source[self.source.index("客群推演未完成"):]
        fail_block = fail_block[:fail_block.index("else:")] if "else:" in fail_block else fail_block
        self.assertNotIn('"status": "S2"', fail_block, "推演失败不得推进 S2")

    def test_completed_project_skips_reinference(self):
        """已完成 S3+ 的项目不得重复推演。"""
        self.assertIn("（已过推演）——跳过推演", self.source)


if __name__ == "__main__":
    unittest.main()
