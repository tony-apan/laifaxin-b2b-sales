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
    # ★2026-09-10 对抗审查补：这些也曾泄漏到用户话术块
    "specs/", "methodology/", "docs/0", "verification-panel", "product-fit",
    "companySaveCount", "contactSaveCount", "selectOption", "notSentTags",
    "Jaccard", "断言", "幂等", "finished", "verify 通过",
    "公司触发器", "候选锚", "条目ID", "临界第",
)

# 会出现在用户话术块里的内部文件名/状态码（正则，因为前后文多变）
FORBIDDEN_IN_USER_VIEW_RE = (
    re.compile(r"[a-zA-Z0-9_\-]+\.(?:py|md|json|tsv|sh)\b"),
    re.compile(r"\bS(?:0a|1[0-2]|[0-9])\b(?![\w])"),
    re.compile(r"\b(?:finished|sha256)\b", re.IGNORECASE),
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
                for rx in FORBIDDEN_IN_USER_VIEW_RE:
                    found = rx.search(block)
                    if found:
                        self.fail(f"{path.name} 第 {index} 个用户话术块出现内部术语/文件名「{found.group(0)}」")

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


class CardActionAndSummaryTest(unittest.TestCase):
    """卡片可读性两铁律（2026-09-10 对抗推进）：
    ①每张卡结尾必须有明确行动指引（用户知道现在该做什么/不用做什么）
    ②重卡片必须结论先行（表格前先给一句话，别让小白先啃表）"""

    # 交互卡：用户需要行动
    ACTION_WORDS = re.compile(r"回复|确认|请选|告诉我|选编号|该您|请您|需要您|您可以|您不用|轮到您")

    # 重卡片（表格 ≥6 行 或 列 ≥6）：必须结论先行
    HEAVY = ("S0-产品知识档案.md", "S2-客群确认.md", "S5-保存确认.md", "S12-激活确认.md")

    def blocks_of(self, name):
        text = (TEMPLATES / name).read_text(encoding="utf-8")
        return re.findall(r"```[a-zA-Z]*\n(.*?)```", text, re.S)

    def test_every_card_ends_with_action_guidance(self):
        for path in sorted(TEMPLATES.glob("*.md")):
            if path.name == "README.md":
                continue
            for bi, block in enumerate(self.blocks_of(path.name), 1):
                tail = "\n".join(block.strip().splitlines()[-6:])
                with self.subTest(file=path.name, block=bi):
                    self.assertRegex(tail, self.ACTION_WORDS,
                                     f"{path.name} 卡结尾缺明确行动指引（用户不知道该做什么）")

    def test_heavy_cards_lead_with_one_line_conclusion(self):
        for name in self.HEAVY:
            block = self.blocks_of(name)[0]
            first_table = block.find("|")
            with self.subTest(file=name):
                self.assertGreater(first_table, 0, f"{name} 应有表格")
                head = block[:first_table]
                self.assertRegex(head, r"💡|一句话",
                                 f"{name} 重表格前必须先给一句话结论（别让用户先啃表）")

    def test_process_cards_say_you_need_do_nothing(self):
        """过程卡（S4审计/S8构建）必须明确告诉用户'不用做什么'——否则小白干等会焦虑。"""
        for name in ("S4-审计进行中.md", "S8-模板构建中.md"):
            with self.subTest(file=name):
                block = self.blocks_of(name)[0]
                self.assertRegex(block, r"您不用做|不用做任何事|等我",
                                 f"{name} 过程卡应说明用户无需操作")

    def test_table_headers_are_plain_language(self):
        """重卡片表头必须白话（禁'量级/询盘速度/邮箱可得'这类内部维度名）。"""
        block = self.blocks_of("S2-客群确认.md")[0]
        for jargon in ("量级", "询盘速度", "邮箱可得", "竞争度", "精准买家?"):
            with self.subTest(jargon=jargon):
                self.assertNotIn(jargon, block, f"S2 表头仍是内部术语「{jargon}」")

    def test_consistent_second_person_pronoun(self):
        """★称谓统一为「您」（2026-09-10）：同一套话术忽"你"忽"您"显得不专业。

        ⚠️ 例外：一键双取命令是给用户复制的**代码**，内部文案固定用「你」且必须逐字一致
        （见 OneClickCommandConsistencyTest）——校验时须剔除该命令行。
        """
        for path in sorted(TEMPLATES.glob("*.md")):
            if path.name == "README.md":
                continue
            for bi, block in enumerate(self.blocks_of(path.name), 1):
                # 剔除一键双取命令所在行（命令是代码，不适用文案规范）
                checked = "\n".join(
                    l for l in block.splitlines()
                    if "var t=localStorage" not in l
                )
                with self.subTest(file=path.name, block=bi):
                    self.assertNotIn("你", checked, f"{path.name} 用户话术块用了「你」，应统一用「您」")

    def test_s2_explains_each_column(self):
        block = self.blocks_of("S2-客群确认.md")[0]
        self.assertIn("表头人话解释", block, "S2 应逐列解释表头（小白看不懂六维缩写）")


if __name__ == "__main__":
    unittest.main()


class RulePrecisionTest(unittest.TestCase):
    """规则精度（2026-09-10 AI 执行层审查）：
    ①「同一家公司 5 封」必须是【每日】上限——写成总量会误导
    ②规则文档不得出现不精确的"单家5"简写"""

    def test_per_domain_limit_states_daily(self):
        """用户话术与规则里，单域名上限必须写明"每天/每日"。"""
        targets = (
            ("output-templates/S9-序列确认.md", "同一家公司"),
            ("output-templates/S12-激活确认.md", "同一家公司"),
        )
        for name, needle in targets:
            text = (ROOT / name).read_text(encoding="utf-8")
            idx = text.find(needle)
            with self.subTest(file=name):
                self.assertGreater(idx, -1, f"{name} 应提到「{needle}」上限")
                window = text[idx:idx + 60]
                self.assertRegex(window, r"每天|每日",
                                 f"{name} 单公司上限必须写明是【每天】，实际: {window[:50]}")

    def test_no_ambiguous_shortform_in_rules(self):
        """规则文件不得用"单家5"这种会被读成总量上限的简写。"""
        for name in ("RULES.md", "SKILL.md", "specs/sequence-config.md",
                     "specs/operations-sop.md", "specs/node-playbook.md"):
            with self.subTest(file=name):
                text = (ROOT / name).read_text(encoding="utf-8")
                self.assertNotIn("单家5", text, f"{name} 出现含糊简写「单家5」")
                self.assertNotIn("单家 5", text, f"{name} 出现含糊简写「单家 5」")

    def test_sequence_config_defines_both_limits_explicitly(self):
        text = (ROOT / "specs" / "sequence-config.md").read_text(encoding="utf-8")
        self.assertIn("max_emails_per_day", text)
        self.assertIn("domain_emails_per_day", text)
        self.assertRegex(text, r"domain_emails_per_day[^\n]*每天|每天[^\n]*domain_emails_per_day",
                         "sequence-config 应写明 domain_emails_per_day 是每日上限")


if __name__ == "__main__":
    unittest.main()


class NoLineNumberReferenceTest(unittest.TestCase):
    """规则文档不得用行号引用（2026-09-10 AI 执行层审查）。

    行号引用天然脆弱：本次实测 10 处 RULES L## 全部漂移（+2~+6），
    node-playbook 的 `API L54` 甚至指向了空行——AI 照行号去查会拿到无关内容。
    改用稳定的「节点名/章节名/接口名」引用。
    """

    DOCS = (
        "RULES.md", "SKILL.md", "specs/node-playbook.md",
        "specs/operations-sop.md", "specs/sequence-config.md",
    )

    # 允许：教训编号 L-45；目录结构里的 L0/L1/L2/L3
    ALLOW = re.compile(r"L-\d+|L[0-3]\s|L[0-3]/|L[0-3]$")

    def test_no_line_number_references(self):
        # 两种形态都拦：`xxx.md` L99，以及裸 L99（指向本文档/他文档行号）
        patterns = (
            re.compile(r"`[a-zA-Z0-9_/.\-]+\.md`\s*L(\d{1,3})"),
            re.compile(r"(?<![A-Za-z0-9_\-])L(\d{1,3})(?![0-9])"),
        )
        for name in self.DOCS:
            path = ROOT / name
            if not path.is_file():
                continue
            for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                if self.ALLOW.search(line):
                    continue
                for rx in patterns:
                    m = rx.search(line)
                    if m:
                        with self.subTest(file=name, line=i):
                            self.fail(f"{name}:L{i} 出现行号引用「{m.group(0)}」——行号会漂移，请改用节点名/章节名")


if __name__ == "__main__":
    unittest.main()


class OneClickCommandConsistencyTest(unittest.TestCase):
    """一键双取命令必须逐字一致（2026-09-10 发现：v0.5.16 统一"你/您"时误改了命令内文案，
    导致 6 份副本出现 2 个版本）。命令是给用户复制的代码，不得被文案规范波及。"""

    COMMAND_START = "var t=localStorage"

    def _extract(self, path):
        for line in Path(path).read_text(encoding="utf-8").splitlines():
            if self.COMMAND_START in line:
                c = line[line.index(self.COMMAND_START):]
                return c[:c.rindex(");") + 2]
        return None

    def test_all_copies_are_byte_identical(self):
        repo = ROOT
        knowledge = ROOT.parent / "laifaxin-knowledge"
        copies = {}
        for base in (repo, knowledge):
            if not base.is_dir():
                continue
            for p in base.rglob("*.md"):
                if ".git" in str(p):
                    continue
                c = self._extract(p)
                if c:
                    copies.setdefault(c, []).append(str(p.relative_to(base.parent)))
        self.assertGreaterEqual(len(copies), 1, "未找到一键双取命令副本")
        self.assertEqual(
            1, len(copies),
            f"命令副本不一致（{len(copies)} 个版本）——命令是给用户复制的代码，必须逐字一致：\n"
            + "\n".join(f"  版本{i+1}: {v[0]} (共{len(v)}份)" for i, v in enumerate(copies.values())))

    def test_command_keeps_original_second_person(self):
        """命令内部文案用「你」——不随用户话术的「您」规范改动（改了会让副本不一致）。"""
        cmd = self._extract(ROOT / "SKILL.md")
        self.assertIsNotNone(cmd, "SKILL.md 应含一键双取命令")
        self.assertIn("你", cmd, "命令内部应保持原文用「你」")
        self.assertNotIn("您", cmd, "命令内部不得出现「您」（会与其他副本不一致）")

    def test_command_is_single_line(self):
        cmd = self._extract(ROOT / "SKILL.md")
        self.assertNotIn("\n", cmd, "命令必须单行（多行粘贴到控制台会失败）")


class GateBoundaryTest(unittest.TestCase):
    """工具闸门边界（2026-09-10 对抗补：审批/哈希此前无边界测试，仅集成测试覆盖主路径）。

    这里直接调用纯函数验证判定逻辑，不联网、不碰真实数据。
    """

    @classmethod
    def setUpClass(cls):
        import sys as _sys
        _sys.path.insert(0, str(ROOT / "tools"))

    def test_params_hash_is_key_order_insensitive(self):
        from approval import stable_params_hash as H
        a = {"project": "p/x", "tags": ["a", "b"], "n": 100}
        b = {"n": 100, "tags": ["a", "b"], "project": "p/x"}
        self.assertEqual(H(a), H(b), "键顺序不应影响哈希（换机会重算）")

    def test_params_hash_detects_value_and_type_change(self):
        from approval import stable_params_hash as H
        base = {"project": "p/x", "n": 100}
        self.assertNotEqual(H(base), H({"project": "p/x", "n": 101}), "值变化必须改变哈希")
        self.assertNotEqual(H(base), H({"project": "p/x", "n": "100"}), "类型变化必须改变哈希")

    def test_params_hash_is_nested_and_list_sensitive(self):
        from approval import stable_params_hash as H
        d1 = {"p": {"sha": "x", "status": "declined"}, "tags": ["a", "b"]}
        d2 = {"tags": ["a", "b"], "p": {"status": "declined", "sha": "x"}}
        self.assertEqual(H(d1), H(d2), "嵌套键序不应影响哈希")
        self.assertNotEqual(H(d1), H({"p": {"sha": "x", "status": "declined"}, "tags": ["b", "a"]}),
                            "列表顺序变化必须改变哈希（调用方须先排序）")

    def test_confirm_quote_rejects_negative_and_question(self):
        from approval import confirm_quote_ok
        for bad in ("不要保存", "确认保存吗？", "等我想想", "先别动", "是否激活"):
            with self.subTest(quote=bad):
                self.assertFalse(confirm_quote_ok(bad), f"应拒绝非正向确认: {bad}")

    def test_confirm_quote_accepts_explicit_positive(self):
        from approval import confirm_quote_ok
        for good in ("确认", "确认保存", "确认激活", "可以"):
            with self.subTest(quote=good):
                self.assertTrue(confirm_quote_ok(good), f"应接受明确正向确认: {good}")

    def test_require_approval_fails_closed(self):
        import io, contextlib
        from approval import require_approval
        for aid in ("", "ap-does-not-exist"):
            with self.subTest(approval=aid):
                with contextlib.redirect_stdout(io.StringIO()):
                    with self.assertRaises(SystemExit) as ctx:
                        require_approval(aid, "p/x", ("S5",), what="测试")
                self.assertEqual(1, ctx.exception.code, "审批缺失/无效必须 fail-closed")
