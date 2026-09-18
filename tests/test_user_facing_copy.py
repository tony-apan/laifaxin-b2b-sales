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

    # 交互卡：用户需要行动。★2026-09-17 补："我马上开始/我现在开始"这类
    # "AI 直接推进、用户不用动手"的收尾也算合规（连接成功卡就是这种：连上就继续跑）
    ACTION_WORDS = re.compile(r"回复|确认|请选|告诉我|选编号|该您|请您|需要您|您可以|您不用|轮到您|我马上开始|我现在开始|马上开始")

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


class FailureReportingDisciplineTest(unittest.TestCase):
    """失败/停下时的汇报纪律（2026-09-11 用户实测截图后的对抗加固）。

    实测反例：某次 AI 给用户看的是
      「1. onboard_check.py：通过…  3. gate_check.sh：未通过。登录复核和工作空间落点复核均失败，
        因此已按规则停止。」
    ——满屏工具文件名与行话，小白只看懂"失败"，还会误以为**自己账号坏了**
    （实际只是 AI 还没收到账号钥匙）。这组断言把"工具名不得进用户视野"与
    "失败必给唯一下一步"锁死，覆盖**任何时刻**（不只模板代码块）。
    """

    # 工具/脚本名（含去后缀写法）——给用户的任何文本都不得出现
    TOOL_NAMES = (
        "onboard_check", "gate_check", "check_login", "workspace_guard",
        "flow_orchestrator", "check_rules", "gen_templates", "build_sequence",
        "save_first_n", "contact_add", "activate_sequence", "rebuild_templates",
        "render_preview", "render_html_preview", "segments_infer", "evidence_validation",
        "compliance_validation", "finalize_run", "finalize_audit", "update_run_state",
        "audit_company", "find_threshold", "find_critical", "verify_sequence",
        "verify_exclude", "wait_save_done", "resolve_schedule", "seed_resolve",
        "tmap_grid", "tag_add", "delete_all_products",
    )
    # 内部行话（面向用户时禁止）
    JARGON = ("落点", "凭据", "rc=", "[PASS]", "[FAIL]", "校验未通过",
              "复核失败", "退出码", "workspace", "isOrg",
              # ★复审 F-11R1 补：token 对小白是黑话；失败/连接场景不该出现
              #   （T-token引导卡例外——那张卡必须展示一键复制命令，见下方专项断言）
              "token", "orgId", "accesstoken")

    def user_blocks(self, name):
        text = (TEMPLATES / name).read_text(encoding="utf-8")
        return re.findall(r"```[a-zA-Z]*\n(.*?)```", text, re.S)

    def test_failure_card_exists_and_is_single_source(self):
        p = TEMPLATES / "S0-连接未通过.md"
        self.assertTrue(p.exists(), "缺少「连接未通过」卡——AI 失败时没有可照抄的话术")
        dups = [q.name for q in TEMPLATES.glob("*未通过*.md")]
        self.assertEqual(["S0-连接未通过.md"], dups, f"失败卡应只有一个真源，实际: {dups}")

    def test_failure_card_blocks_have_no_tool_names_or_jargon(self):
        for bi, block in enumerate(self.user_blocks("S0-连接未通过.md"), 1):
            for word in self.TOOL_NAMES + self.JARGON:
                with self.subTest(block=bi, word=word):
                    self.assertNotIn(word, block,
                                     f"失败卡用户话术块出现工具名/行话「{word}」")

    def test_failure_card_covers_the_screenshot_cases(self):
        """必须覆盖实测四类：没收到 / 用不了 / 连错空间 / 网络问题。"""
        text = (TEMPLATES / "S0-连接未通过.md").read_text(encoding="utf-8")
        for kw in ("不是您的账号有问题", "重新执行一次复制命令",
                   "不是您想用的那个工作空间", "网络或平台临时"):
            with self.subTest(kw=kw):
                self.assertIn(kw, text, f"失败卡缺场景：{kw}")

    def test_every_failure_block_says_its_not_users_fault_or_gives_action(self):
        """每个用户块：要么明说"不是您的问题"，要么给出唯一动作；且都有下一步动作词。"""
        ACTION = re.compile(r"回复|确认|请您|您不用|什么都不用做|我来处理|我再试")
        for bi, block in enumerate(self.user_blocks("S0-连接未通过.md"), 1):
            with self.subTest(block=bi):
                self.assertRegex(block, ACTION, "失败话术缺明确下一步")

    def test_failure_blocks_declare_no_data_touched(self):
        """检查类失败必须说明本次没动数据（用户最担心的第二件事）。"""
        text = (TEMPLATES / "S0-连接未通过.md").read_text(encoding="utf-8")
        self.assertRegex(text, r"没搜索|没有搜索")
        self.assertRegex(text, r"没保存|没有保存")

    def test_rules_has_anytime_discipline(self):
        """RULES 必须有"对用户开口任何时刻"的总纪律（不能只约束模板代码块）。"""
        text = (ROOT / "RULES.md").read_text(encoding="utf-8")
        self.assertIn("任何时刻", text, "RULES 缺『对用户开口任何时刻』总纪律")
        self.assertRegex(text, r"唯一下一步|唯一的下一步",
                         "RULES 缺『失败必给唯一下一步』要求")
        self.assertRegex(text, r"是不是您的|跟您有没有关系|不是您的账号|不是用户的问题",
                         "RULES 缺『先说跟用户有没有关系』要求")

    def test_skill_points_to_failure_card(self):
        text = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("S0-连接未通过", text, "SKILL 未把失败汇报列为必照模板的固化产出")

    def test_card_index_lists_failure_card(self):
        text = (TEMPLATES / "README.md").read_text(encoding="utf-8")
        self.assertIn("S0-连接未通过", text, "output-templates 索引未挂失败卡")

    def test_gate_check_emits_user_plain_section(self):
        """工具自己必须产出可直接照抄的白话段（否则换个 AI 还会照抄工具原文）。"""
        src = (ROOT / "tools" / "gate_check.sh").read_text(encoding="utf-8")
        self.assertIn("给用户看的这一段", src, "gate_check 缺『给用户看的这一段』白话段")
        self.assertIn("禁止原样转述给用户", src, "gate_check 未标注明细行不可转述")
        # 空输入必须归类为"还差一步"，不得报成失败
        self.assertIn("[还差一步]", src, "gate_check 缺『还差一步』分类（会把没收到误报成失败）")
        self.assertIn("不是您的账号有问题", src, "gate_check 白话段缺『不是您的账号』声明")

    def test_workspace_guard_distinguishes_misroute_from_undetermined(self):
        """★2026-09-11 实测缺陷：钥匙失效时曾报成"您连错空间了"（误导用户去切空间）。

        契约：exit 1 专指确凿误路由；"无法判定"（平台未返回/钥匙失效）用 exit 5。
        两者对用户的说法完全不同，混用就是把用户往错方向指。
        """
        import subprocess, sys
        # 假凭据 → 探测必然失败 → 无法判定（不是"空间连错"）
        result = subprocess.run(
            [sys.executable, str(ROOT / "tools" / "workspace_guard.py"),
             "--credentials-stdin", "--require-verified"],
            input="accesstoken=web.laifaxin.com&fakeuid&fakehash\norgId=999999\n",
            text=True, capture_output=True, cwd=ROOT, timeout=120,
        )
        self.assertEqual(5, result.returncode,
                         "无法判定必须是 exit 5；用 1 会让上游误报『您连错空间了』")
        src = (ROOT / "tools" / "workspace_guard.py").read_text(encoding="utf-8")
        self.assertIn("无法判定", src)
        self.assertIn("1 与 5 都是", src, "退出码契约须在文档串里写清，供调用方区分")

    def test_gate_check_maps_undetermined_separately(self):
        """gate_check 对 exit 5 必须说"没能判定/不等于空间错了"，不得说"连错空间"。"""
        src = (ROOT / "tools" / "gate_check.sh").read_text(encoding="utf-8")
        self.assertIn("5) bad", src, "gate_check 未单独处理 exit 5")
        idx = src.index("5) bad")
        line = src[idx:src.index("\n", idx)]
        self.assertIn("不等于空间错了", line,
                      "exit 5 的话术必须排除『空间错了』的误导")

    def test_gate_check_empty_stdin_is_not_failure(self):
        """★实测复现：空 stdin（=AI 没接到钥匙）不得计入『不通过』。"""
        import subprocess, sys
        result = subprocess.run(
            ["bash", str(ROOT / "tools" / "gate_check.sh"), "--credentials-stdin"],
            input="", text=True, capture_output=True, cwd=ROOT, timeout=60,
        )
        self.assertIn("还差一步", result.stdout, "空输入应报『还差一步』")
        self.assertNotIn("[FAIL] 账号钥匙失效", result.stdout,
                         "空输入不得误报成『钥匙失效』（会让用户白重登）")
        self.assertIn("不是您的账号有问题", result.stdout,
                      "空输入场景必须明说不是用户账号问题")
        plain = result.stdout.split("给用户看的这一段")[-1]
        self.assertNotIn("check_login.py", plain, "白话段不得出现工具名")
        # ★复审 F-11R3 补：白话段整体扫行话与工具名（原先只查单个工具名）
        for word in ("落点", "凭据", "[FAIL]", "[PASS]", "rc=", "workspace_guard",
                     "gate_check", "onboard_check", ".py", ".sh"):
            with self.subTest(word=word):
                self.assertNotIn(word, plain, f"白话段出现内部词/工具名「{word}」")


class StepGuidanceTest(unittest.TestCase):
    """每张交互卡必须"先给引导"（2026-09-11 用户：说人话 **并做好引导**）。

    小白最怕两个时刻：①不知道该做什么 ②点了头之后不知道会发生什么。
    因此交互卡必须说清「接下来/确认之后会怎样」——不能只在失败时补救。
    """

    # 交互卡（用户需回复才能推进）→ 必须含"接下来会发生什么"
    CONFIRM_CARDS = (
        "S0-产品知识档案.md", "S0-画像方案.md", "S2-客群确认.md", "S3-种子确认.md",
        "S5-保存确认.md", "S7-模板确认.md", "S9-序列确认.md",
        "S10-加联系人确认.md", "S12-激活确认.md",
        "S0a-运营方档案.md", "S0a-网站资料确认.md",
    )
    # 描述"之后会发生什么"的表述（任一即可）
    NEXT_RE = re.compile(
        r"确认之后|选完之后|回完|回复之后|发完|完成后|接下来|之后我会|"
        r"之后的流程|做完再把|做完这个再|存完我会|加完会把|通过后进入|马上开始"
    )

    def first_block(self, name):
        text = (TEMPLATES / name).read_text(encoding="utf-8")
        blocks = re.findall(r"```[a-zA-Z]*\n(.*?)```", text, re.S)
        self.assertTrue(blocks, f"{name} 应有用户话术块")
        return blocks[0]

    def test_confirm_cards_explain_what_happens_next(self):
        for name in self.CONFIRM_CARDS:
            with self.subTest(card=name):
                block = self.first_block(name)
                self.assertRegex(block, self.NEXT_RE,
                                 f"{name} 没说清『接下来/确认之后会发生什么』——小白点了头不知道会怎样")

    def test_confirm_cards_state_whether_user_must_act(self):
        """每张交互卡都要明确"要不要您动手"。"""
        for name in self.CONFIRM_CARDS:
            with self.subTest(card=name):
                block = self.first_block(name)
                self.assertRegex(block, r"您不用做|不用您|请您|需要您|您回|您确认|回复|等您",
                                 f"{name} 未说明用户是否需要动手")

    def test_process_cards_give_time_estimate(self):
        """过程卡（S4/S8/S5）必须给时间预期，否则小白干等会焦虑。"""
        for name in ("S4-审计进行中.md", "S8-模板构建中.md", "S5-保存确认.md"):
            with self.subTest(card=name):
                block = self.first_block(name)
                self.assertRegex(block, r"分钟|小时|稍等|估计|预计|很快",
                                 f"{name} 缺时间预期")

    def test_activation_card_says_first_email_timing(self):
        """激活卡是最后一道闸：必须说清"确认之后多久真的会发信"。

        ★2026-09-17 对抗审查 F-03/F-11.1：先前断言用 `|立即生效|按排程发出` 多选，
        只要块里出现任一词就通过——把"30 分钟"整句删掉或改成"30 天"都能过（漏网）。
        现在要求**两个必要条件同时成立**：①有明确首封时间预期 ②说明只在工作时段发送
        （否则周五晚激活的用户会以为 30 分钟内必到而误判出错）。
        """
        block = self.first_block("S12-激活确认.md")
        self.assertRegex(block, r"\d+\s*分钟|按.*时间表",
                         "S12 应说明激活后首次发送的时间预期（工作时段不能替代首封时间说法）")
        self.assertRegex(block, r"工作时间|工作日|周一至周五",
                         "S12 必须限定发送时段（非工作时段激活时首封顺延），否则属过度承诺")

    def test_activation_card_states_real_stop_mechanism(self):
        """S12 必须写真实停发机制：回复本身不会停，打上询盘标签生效后才停。

        ★对抗审查 F-02（P0）：曾写"有人回复或打上标签会停止跟进"——与
        `specs/sequence-config.md`「公司触发器=什么都不做」和 S9 卡「禁写自动停发」相悖；
        会让用户以为不用打标签，导致对已回复买家继续群发。
        """
        block = self.first_block("S12-激活确认.md")
        self.assertRegex(block, r"不会自动停|标签生效后才停|标签.{0,6}生效",
                         "S12 须写明『回复不会自动停、标签生效才停』")
        self.assertNotRegex(block, r"有人回复.{0,4}会停止",
                            "S12 不得声称回复会自动停发（事实错误）")

    def test_s9_does_not_merge_contact_add_into_sequence_confirmation(self):
        """★对抗审查 F-01（P0）：S9 不得把"加客户"说成同一句确认就做，
        否则架空 S10 的独立确认闸门（RULES: 人数对账且用户确认后才 contact-add）。"""
        block = self.first_block("S9-序列确认.md")
        self.assertRegex(block, r"再确认一次|单独.{0,4}确认|另.{0,4}确认",
                         "S9 须说明加客户前会再确认一次（不得一次确认做到底）")
        # ★复审 F-11R2 补禁止式：只查存在会被"保留再确认一次 + 同时说会加人"绕过
        self.assertRegex(block, r"这一步不加入任何客户|不加入任何客户",
                         "S9 须明确本步不加客户")
        self.assertNotRegex(block, r"确认之后[^。]{0,10}(?:把客户加进去|加进客户|加入客户)",
                            "S9 不得把加客户并进建序列同一步（架空 S10 确认闸门）")

    def test_profile_card_next_step_is_connect_not_inference(self):
        """★对抗审查 F-04：档案卡不得说"确认后带您推演客群"（应先连接平台）。"""
        block = self.first_block("S0-产品知识档案.md")
        self.assertNotRegex(block, r'回[「"]?确认[」"]?.{0,14}推演',
                            "档案卡确认后应是『连接平台』，不是直接推演客群")

    def test_portrait_card_orders_profile_before_connect(self):
        """★对抗审查 F-05：画像方案的下一步顺序须为 建档→连接→推演。"""
        block = self.first_block("S0-画像方案.md")
        i_prof = min([m.start() for m in re.finditer(r"产品/公司资料", block)] or [10**9])
        i_conn = block.find("连接来发信账号")
        i_infer = block.find("推演具体客群")
        self.assertLess(i_prof, i_conn, "建档应排在连接之前")
        self.assertLess(i_conn, i_infer, "连接应排在推演客群之前")

    def test_failure_card_covers_all_steps(self):
        """失败卡必须覆盖"任何步骤卡住"，不能只管连接。"""
        text = (TEMPLATES / "S0-连接未通过.md").read_text(encoding="utf-8")
        for kw in ("其他步骤卡住时怎么说", "通用兜底话术", "抽查名单质量",
                   "开发信没通过检查", "激活失败"):
            with self.subTest(kw=kw):
                self.assertIn(kw, text, f"失败卡缺全步骤覆盖：{kw}")

    def test_no_stale_credential_jargon_in_check_login_output(self):
        """工具对用户输出不得出现 token 等黑话（用户看不懂 token）。"""
        src = (ROOT / "tools" / "check_login.py").read_text(encoding="utf-8")
        for m in re.finditer(r'print\(\s*f?["\']([^"\']{8,})["\']', src):
            raw = m.group(1)
            # 只查字面文案：剥掉成对的 {表达式}，再截断到残留的左花括号
            # （正则匹配会在表达式内的引号处提前结束，故残留左括号必须丢掉）
            s = re.sub(r"\{[^{}]*\}", "", raw)
            if "{" in s:
                s = s[:s.index("{")]
            if not re.search(r"[\u4e00-\u9fff]", s):
                continue
            with self.subTest(line=s[:60]):
                self.assertNotIn("token", s.lower(),
                                 f"面向用户的输出出现 token：{s[:60]}")
                self.assertNotIn("凭据", s, f"面向用户的输出出现内部词『凭据』：{s[:60]}")

    def test_no_card_claims_auto_stop_on_reply(self):
        """★对抗审查 F-02 衍生（2026-09-17）：**任何卡片**都不得声称"回复会自动停发"。

        实测机制（specs/sequence-config.md「公司触发器=什么都不做」）：平台不会因收到回复
        自动停发，只有「询盘」标签实际生效后才停。Q1-Q5 卡原先写"对方回复后，自动跟进已停止"
        ——与 S9/S12 口径矛盾，会让用户不再催促打标，对已回复买家继续群发。
        """
        BAD = re.compile(r"回复[^。\n]{0,8}(?:自动|即|就)[^。\n]{0,6}(?:停止|停发|已停)")
        offenders = []
        for path in sorted(TEMPLATES.glob("*.md")):
            text = path.read_text(encoding="utf-8")
            for block in re.findall(r"```[a-zA-Z]*\n(.*?)```", text, re.S):
                for m in BAD.finditer(block):
                    seg = m.group(0)
                    # 允许"不会自动停""不自动停"这类否定表述
                    if re.search(r"不会|不得|不自动|禁", seg):
                        continue
                    offenders.append(f"{path.name}: {seg}")
        self.assertEqual([], offenders,
                         f"卡片声称回复会自动停发（事实错误，实际靠『询盘』标签生效后停）: {offenders}")


class NoTokenJargonOutsideCredentialCardTest(unittest.TestCase):
    """★复审 F-11R1：除「T-token引导」卡外，任何卡的用户话术都不得出现 token/orgId/accesstoken。

    T-token引导卡是唯一例外——它必须展示一键复制命令（含 `accesstoken=`/`orgId=`），
    并提醒"token 等同账号密码"。其余卡片（含失败卡、状态卡、各确认卡）用"登录信息/账号钥匙"白话。
    """

    EXEMPT = {"T-token引导.md", "README.md"}

    def test_no_token_words_in_other_cards(self):
        offenders = []
        for path in sorted(TEMPLATES.glob("*.md")):
            if path.name in self.EXEMPT:
                continue
            text = path.read_text(encoding="utf-8")
            for bi, block in enumerate(re.findall(r"```[a-zA-Z]*\n(.*?)```", text, re.S), 1):
                for word in ("token", "orgId", "accesstoken"):
                    if re.search(word, block, re.IGNORECASE):
                        offenders.append(f"{path.name} 块{bi}: {word}")
        self.assertEqual([], offenders,
                         f"非凭据卡出现 token/orgId/accesstoken（小白看不懂）: {offenders}")


class GatePlainTextSingleSourceTest(unittest.TestCase):
    """★复审 F-07 收口：gate_check 输出的白话段与话术卡必须**逐字一致**（单一真源）。

    gate_check.sh 把白话直接打给 AI 照抄（权威版本），话术卡是同一套话的存档版。
    两处手抄必然漂移（复审已实测出 env 分支差一句）——这里用机器对账锁死：
    gate_check 白话段里的每个中文句子，必须能在「连接未通过」或「连接成功」卡里逐字找到。
    """

    def sentences(self):
        sh = (ROOT / "tools" / "gate_check.sh").read_text(encoding="utf-8")
        plain = sh.split("给用户看的这一段")[-1]
        out = []
        for s in re.findall(r'echo "(.*?)"(?:\s*;;|\s*$)', plain, re.M):
            if re.search(r"[\u4e00-\u9fff]", s):
                out.append(re.sub(r"\s+", "", s).replace("**", ""))
        return out

    def card_text(self):
        t = ((TEMPLATES / "S0-连接未通过.md").read_text(encoding="utf-8")
             + (TEMPLATES / "S0-连接成功.md").read_text(encoding="utf-8"))
        return re.sub(r"\s+", "", t).replace("**", "")

    def test_every_plain_sentence_exists_in_cards(self):
        card = self.card_text()
        missing = [s[:60] for s in self.sentences() if s.strip("*") not in card]
        self.assertEqual([], missing,
                         f"gate_check 白话句在话术卡里找不到对应（两处需逐字同步）: {missing}")

    def test_plain_section_has_no_tool_names(self):
        """白话段本身不得含工具名/行话（AI 会直接照抄，含了就漏给用户）。"""
        sh = (ROOT / "tools" / "gate_check.sh").read_text(encoding="utf-8")
        plain = sh.split("给用户看的这一段")[-1]
        for word in ("workspace_guard", "check_login.py", "gate_check.sh", "onboard_check",
                     "落点", "凭据", "[FAIL]", "[PASS]", "rc="):
            with self.subTest(word=word):
                self.assertNotIn(word, plain, f"白话段含内部词「{word}」")


class ActivationIsOneChatLineTest(unittest.TestCase):
    """★2026-09-17 用户拍板：激活不再要求用户开终端。

    背景：旧设计要求用户在自己电脑上打开 PowerShell/终端、粘贴一行命令、再输入确认。
    用户判定这是**拦路虎**而非安全（普通用户不认识终端），且与项目自身的威胁模型冲突——
    README 早已写明"审批闸门用于防误操作，**不用于对抗主动篡改**"；而 TTY 检查既能被
    主动绕过（pty 包装），又让每个用户在最关键一步付出最高学习成本。
    同类步骤（S5/S7/S9/S10）全部是"用户聊天里说一句 + 工具绑定原话"，S12 不比它们高危到需要换渠道。

    新契约：用户在自己聊天框里回「确认激活 <序列名>」即可；工具仍要求原话**含"激活"**，
    含糊应答（"好的""可以"）一律拒绝；所有本地闸门（S11/档案/合规live/参数哈希绑定）不变。
    """

    def setUp(self):
        self.card = (TEMPLATES / "S12-激活确认.md").read_text(encoding="utf-8")

    def test_no_card_asks_user_to_open_a_terminal(self):
        """任何用户话术卡都不得要求开终端/粘命令（含 PowerShell、cmd、Git Bash 等）。"""
        BAD = ("PowerShell", "powershell", "终端窗口", "打开终端", "命令行窗口",
               "Git Bash", "cmd.exe", "粘贴运行", "控制台粘贴")
        offenders = []
        for path in sorted(TEMPLATES.glob("*.md")):
            for bi, block in enumerate(re.findall(r"```[a-zA-Z]*\n(.*?)```", path.read_text(encoding="utf-8"), re.S), 1):
                for w in BAD:
                    if w in block:
                        offenders.append(f"{path.name} 块{bi}: {w}")
        self.assertEqual([], offenders, f"卡片仍在要求用户使用终端: {offenders}")

    def test_activation_happens_in_chat(self):
        """激活卡必须给出两条路，且都不需要开终端/粘命令。

        ★2026-09-17 用户要求：①聊天里说一句让我来 ②用户自己去网页手动开启后我同步。
        两种方式都不涉及终端；"自己去网页"是有意提供的透明选项，不是门槛。
        """
        self.assertRegex(self.card, r"确认激活", "激活卡未给出用户要回的话")
        self.assertIn("方式一", self.card, "激活卡未给出'让我来'的方式")
        self.assertIn("方式二", self.card, "激活卡未给出'您去网页自己开'的方式")
        # 方式二必须说明去哪、做什么、回来怎么讲
        # ★2026-09-17 修：旧值 mailing/sequence 是 404（用户实测），真值 /marketing/sequences
        self.assertIn("web.laifaxin.com/marketing/sequences", self.card,
                      "方式二未给出正确的序列页地址（用户会点到 404）")
        self.assertRegex(self.card, r"我已在网页激活", "方式二未给出用户回来说什么")
        # ★只查**用户话术块**：AI 要点里"不需要开终端"这类否定说明是合法且必要的
        block = re.findall(r"```[a-zA-Z]*\n(.*?)```", self.card, re.S)[0]
        for bad in ("终端", "PowerShell", "命令行", "粘贴命令", ".py", "approval"):
            with self.subTest(bad=bad):
                self.assertNotIn(bad, block, f"激活卡用户话术出现终端类要求「{bad}」")

    def test_activation_no_longer_mentions_previous_terminal_flow(self):
        """★只查**用户话术块**：AI 要点里"不需要开终端"这类否定说明是合法的。"""
        block = re.findall(r"```[a-zA-Z]*\n(.*?)```", self.card, re.S)[0]
        for bad in ("--print-s12-command", "PowerShell", "终端", "ap- 编号", "整段复制", ".py"):
            with self.subTest(bad=bad):
                self.assertNotIn(bad, block, f"激活卡用户话术仍残留旧终端流程字样「{bad}」")

    def test_obsolete_confirm_card_is_gone(self):
        self.assertFalse((TEMPLATES / "S12-您亲自确认.md").exists(),
                         "旧『您亲自确认』卡应已删除（该步骤不复存在）")

    def test_tool_accepts_in_chat_confirmation_without_tty(self):
        """工具必须能在非终端环境（AI 代跑、stdin 为管道）用 --confirm 签发凭证。"""
        import subprocess, sys
        r = subprocess.run(
            [sys.executable, str(ROOT / "tools" / "flow_orchestrator.py"),
             "--resume-s12", "--confirm", "确认激活 测试序列",
             "--org", "1", "--profile", "runs/none/x/product-profile.md",
             "--seq", "a" * 24, "--compliance-file", "runs/none/x/c.json"],
            input="", capture_output=True, text=True, cwd=ROOT, timeout=60)
        # 档案不存在 → 应在闸门处失败（exit 4），而不是在 TTY 检查处 exit 2
        self.assertEqual(4, r.returncode,
                         f"应因档案闸门失败(4)，而不是终端检查失败(2)：{r.stdout}{r.stderr}")
        self.assertNotIn("只能在当前交互式终端", r.stdout + r.stderr,
                         "工具仍拒绝非终端环境（旧 TTY 限制未移除）")

    def test_tool_still_requires_the_activation_word(self):
        """含含糊应答的原话不得签发凭证。"""
        src = (ROOT / "tools" / "flow_orchestrator.py").read_text(encoding="utf-8")
        idx = src.index("def resume_s12")
        body = src[idx:idx + 6000]
        self.assertIn('"激活" in answer', body, "仍须要求原话含『激活』字样")
        self.assertIn("confirm_quote_ok", body, "仍须过滤否定/犹豫/疑问句")

    def test_tool_rejects_empty_confirmation_without_tty(self):
        """没给原话、又不是终端 → 明确报错且不写凭证。"""
        import subprocess, sys
        r = subprocess.run(
            [sys.executable, str(ROOT / "tools" / "flow_orchestrator.py"),
             "--resume-s12", "--org", "1", "--profile", "runs/none/x/product-profile.md",
             "--seq", "a" * 24, "--compliance-file", "runs/none/x/c.json"],
            input="", capture_output=True, text=True, cwd=ROOT, timeout=60)
        self.assertEqual(2, r.returncode, r.stdout + r.stderr)
        self.assertIn("--confirm", r.stdout + r.stderr, "报错须告诉 AI 要传用户原话")

    def test_threat_model_documented_as_mistake_prevention_not_tamper_proof(self):
        """README 必须继续写明审批闸门是防误操作、不防主动篡改（避免后人再加重机械门槛）。"""
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertRegex(readme, r"防误操作.*不用于对抗主动篡改|不用于对抗主动篡改",
                         "README 未声明威胁模型边界")

    def test_no_mechanical_gate_added_for_activation(self):
        """★反过度设计保障（2026-09-17 用户判定旧 TTY 设计为拦路虎）：

        激活是"防误操作"场景，不是"防对抗篡改"场景（README 已声明威胁模型边界）。
        不得为激活再引入：终端/命令/环境变量/手工编辑文件等任何形式的手动机械门槛。
        用户唯一动作 = 在聊天里说出确认激活。
        """
        import subprocess, sys
        src = (ROOT / "tools" / "flow_orchestrator.py").read_text(encoding="utf-8")
        idx = src.index("def resume_s12")
        body = src[idx:idx + 8000]
        for bad in ("isatty():\n        print(\"❌ --resume-s12 只能在", "print_s12_command"):
            with self.subTest(bad=bad[:40]):
                self.assertNotIn(bad, body, f"激活路径疑似又引入机械门槛: {bad[:40]}")
        # 用户侧：不得要求开窗口/粘命令/设变量（在 S12 卡用户话术块内）
        card = (TEMPLATES / "S12-激活确认.md").read_text(encoding="utf-8")
        block = re.findall(r"```[a-zA-Z]*\n(.*?)```", card, re.S)[0]
        for bad in ("环境变量", "PowerShell", "命令行", "运行下面", "粘贴到"):
            with self.subTest(bad=bad):
                self.assertNotIn(bad, block, f"S12 用户话术出现机械门槛「{bad}」")


class ConfirmationQuoteInterrogativeTest(unittest.TestCase):
    """★2026-09-17 对抗模拟命中真缺陷：疑问句被当成授权。

    攻击用例：用户说「**真的要激活吗**」——是个问句/犹豫，旧实现却签发了 S12 激活凭证。
    根因：旧过滤用**疑问短语黑名单**（是否/能否/可否/要不要/是不是/确认吗/可以吗），
    穷举不全，漏掉最常见的**句尾疑问助词**（吗/呢/么）。

    修复：改为规则判定——①任何问号 ②剥尾标点后的句尾助词 ③疑问代词 ④A-not-A 疑问式
    ⑤英文疑问词。这样不必再穷举短语。
    """

    POSITIVE = ("确认激活", "我确认激活", "确认激活 皮筏艇找客户", "确认", "可以", "好的", "没问题")
    NEGATIVE = (
        "真的要激活吗", "要激活吗", "激活吗", "这样激活呢", "可以激活么", "要激活吗。",
        "为什么激活", "怎么激活", "难道要激活", "凭什么激活",
        "激活行不行", "激活能不能", "是不是要激活", "要不要激活", "should i activate",
        "不要激活", "先别激活", "确认不激活", "等等再说", "取消", "暂停",
    )

    def test_interrogatives_rejected(self):
        import sys
        sys.path.insert(0, str(ROOT / "tools"))
        from approval import confirm_quote_ok
        for q in self.NEGATIVE:
            with self.subTest(quote=q):
                self.assertFalse(confirm_quote_ok(q), f"疑问/否定句被当成授权，会误签发凭证：{q!r}")

    def test_positive_still_accepted(self):
        import sys
        sys.path.insert(0, str(ROOT / "tools"))
        from approval import confirm_quote_ok
        for q in self.POSITIVE:
            with self.subTest(quote=q):
                self.assertTrue(confirm_quote_ok(q), f"正常确认被误拒：{q!r}")

    def test_no_phrase_blacklist_regression(self):
        """禁止退回"短语黑名单"式实现（那种写法必然漏）。"""
        src = (ROOT / "tools" / "approval.py").read_text(encoding="utf-8")
        idx = src.index("def confirm_quote_ok")
        body = src[idx:idx + 1800]
        self.assertIn("endswith", body, "须用句尾助词规则判定，而非穷举疑问短语")
        self.assertIn("吗", body, "须覆盖中文句尾疑问助词")


class NoSelfInflictedFrictionTest(unittest.TestCase):
    """★2026-09-17 用户要求"再审查：有没有存心给用户制造的麻烦"后的防回退断言。

    判据来自项目自己的边界（RULES：审批闸门**防误操作、不防主动篡改**）：
    用户的合理动作只有三种——聊天里说话、发网址、贴一次浏览器复制的凭据。
    其余（跑命令/开终端/设变量/改文件/找路径/抄内部编号/读警告墙/重复提供已给过的信息）
    都是自找的摩擦，会让小白卡住或烦躁。

    每条断言都对应一次真实审查发现（UG-01~UG-06），防止回退。
    """

    def blocks(self, name):
        text = (TEMPLATES / name).read_text(encoding="utf-8")
        return re.findall(r"```[a-zA-Z]*\n(.*?)```", text, re.S)

    # ---- UG-01：连接成功卡不得重复索取已收过的信息 ----
    def test_connect_success_does_not_reask_nickname_or_product(self):
        block = self.blocks("S0-连接成功.md")[0]
        self.assertNotRegex(
            block, r"告诉我您的落款昵称|您的落款昵称 ?\+|一句话产品（您卖什么",
            "连接成功卡又在重复索取昵称/产品（这两项在流程开头已收过，T-token卡明令不重复问）")

    def test_index_does_not_say_connect_card_asks_nickname(self):
        idx = (TEMPLATES / "README.md").read_text(encoding="utf-8")
        self.assertNotIn("顺带要昵称", idx, "索引仍写连接卡'顺带要昵称'（与不重复问规则矛盾）")

    # ---- UG-04：不得让用户抄内部编号 ----
    def test_no_internal_id_copy_for_users(self):
        """用户话术里不得要求抄 f-001 这类内部取证编号。"""
        for path in sorted(TEMPLATES.glob("*.md")):
            for bi, block in enumerate(re.findall(r"```[a-zA-Z]*\n(.*?)```",
                                                  path.read_text(encoding="utf-8"), re.S), 1):
                with self.subTest(card=path.name, block=bi):
                    self.assertNotRegex(
                        block, r"确认导入[^：\n]{0,8}：\s*<?(?:编号|f-\d)",
                        f"{path.name} 要用户抄内部编号（应让用户按顺序说第几条，编号映射由 AI 做）")

    # ---- UG-03：引导卡不得甩警告墙 ----
    def test_credential_card_has_no_warning_wall(self):
        """T-token 引导的提示不得超过 3 条（7 条警告墙会放大畏难心理）。"""
        block = self.blocks("T-token引导.md")[0]
        bullet_lines = [l for l in block.splitlines() if l.strip().startswith(("- ", "· "))]
        self.assertLessEqual(len(bullet_lines), 3,
                             f"引导卡提示条数 {len(bullet_lines)} 条过多（应 ≤3，其余移到 AI 要点/失败时才讲）")

    # ---- UG-06：环境兜底不得让用户自己装东西 ----
    def test_env_fallback_marked_ai_only(self):
        """工具里的"手动装 Python/Homebrew"等兜底必须标注仅 AI 内部执行。"""
        src = (ROOT / "tools" / "onboard_check.py").read_text(encoding="utf-8")
        idx = src.index("未找到 python")
        window = src[idx:idx + 900]
        self.assertIn("仅供 AI 内部执行", window,
                      "环境兜底文案未标注'仅 AI 内部'，有被转述给用户的风险")
        self.assertRegex(window, r"禁止直接转述|勿转述",
                         "未明确禁止把兜底步骤转述给用户")

    # ---- UG-02：不得虚假承诺 AI 自动盯回复（平台无名单接口）----
    def test_no_false_promise_of_auto_reply_monitoring(self):
        """回复监控类措辞不得暗示 AI 能自动发现并打标（平台只给回复总数）。"""
        for path in sorted(TEMPLATES.glob("*.md")):
            text = path.read_text(encoding="utf-8")
            for bi, block in enumerate(re.findall(r"```[a-zA-Z]*\n(.*?)```", text, re.S), 1):
                with self.subTest(card=path.name, block=bi):
                    self.assertNotRegex(
                        block, r"(?:我|我会)[^。\n]{0,6}定期检查回复|自动(?:帮您)?(?:监控|巡检)回复",
                        f"{path.name} 暗示 AI 能自动盯回复（平台无此接口，属虚假承诺）")

    # ---- UG-05：二次确认必须收窄 ----
    def test_website_import_second_confirm_is_narrowed(self):
        """导入后的二次确认须用变更摘要，不得让用户重看整表。"""
        text = (ROOT / "specs" / "website-profile-sop.md").read_text(encoding="utf-8")
        self.assertRegex(text, r"变更摘要|只展示变更",
                         "网站导入二次确认未收窄（用户要重看同样内容=重复劳动）")


class PlatformLinkTruthTest(unittest.TestCase):
    """★平台链接真值表（2026-09-17 用户实测 404 后建立）。

    事故：S12 卡引导用户去旧序列页地址（见下方 DEAD 表）手动激活，
    用户点开是 **404 页面未找到**——小白会以为系统坏了。
    根因：这些链接是历史版本写的，平台改版后路径变了（旧 `/mailing/*` 已不存在），
    而**没有任何测试校验链接真实性**，所以错了很久没人发现。

    真值来源：web.laifaxin.com 首页 → `/assets/index-*.js` bundle 里的路由对象
    （`pt={...marketing:{sequences:"/marketing/sequences"}...setting:{sequence:"/settings/sequence"}...}`）。
    平台是 SPA，未登录也能拿到路由表（HTTP 一律 200，只有客户端才渲染 404，所以不能靠状态码判断）。

    本测试把已知真值固化，任何人再写旧路径/瞎猜路径都会被拦下。
    """

    # 平台真实路由（JS bundle 提取；值为中文界面名称）
    TRUTH = {
        "/marketing/tasks": "邮件群发",
        "/marketing/tracks": "邮件追踪",
        "/marketing/sequences": "智能跟进计划（序列）",
        "/search/saved-tasks": "已保存任务",
        "/search/refine-search": "AI数据库搜索",
        "/settings/templets": "邮件模板",
        "/settings/sequence": "计划时间",
        "/settings/signatures": "邮件签名",
        "/settings/tags": "标签管理",
        "/settings/accounts": "邮箱账号",
        "/settings/product-profile": "产品档案",
        "/contacts/contacts": "联系人",
        "/reports/overview": "数据总览",
    }
    # 已废弃路径（平台改版前存在，现在 404）——出现即失败
    DEAD = (
        "/mailing/sequence", "/mailing/send", "/mailing/tracks",
        "/settings/time-plan", "/settings/templates", "/search/tasks",
    )

    def all_platform_urls(self):
        """扫全仓平台链接。

        ★排除测试目录：本文件要**写出**废弃路径作为反面样例（DEAD 表 + 事故说明），
        扫自己会把断言用的字符串误判成"仓库里有 404 链接"（自指）。
        真正的检查对象是文档/工具/卡片里**会给用户看**的链接。
        """
        import re as _re
        urls = set()
        for base in (ROOT / "output-templates", ROOT / "tools", ROOT / "specs"):
            for path in base.rglob("*"):
                if path.is_file() and path.suffix in (".md", ".py", ".sh"):
                    urls.update(_re.findall(r"https://web\.laifaxin\.com/[A-Za-z0-9/_-]*",
                                            path.read_text(encoding="utf-8", errors="ignore")))
        for name in ("RULES.md", "SKILL.md", "README.md", "INDEX.md"):
            f = ROOT / name
            if f.exists():
                urls.update(_re.findall(r"https://web\.laifaxin\.com/[A-Za-z0-9/_-]*",
                                        f.read_text(encoding="utf-8", errors="ignore")))
        return sorted({u for u in urls if "/api/" not in u})

    def test_no_dead_platform_paths(self):
        """★任何文件都不得再出现已废弃的平台路径（用户点了会看到 404）。"""
        offenders = []
        for u in self.all_platform_urls():
            path = u.replace("https://web.laifaxin.com", "").rstrip("/")
            if path in self.DEAD:
                offenders.append(path)
        self.assertEqual([], offenders,
                         f"出现平台已废弃路径（用户会点到 404）: {offenders}")

    def test_all_platform_urls_are_known_truth(self):
        """所有平台链接必须能在真值表里找到（防瞎猜新路径）。"""
        unknown = []
        for u in self.all_platform_urls():
            path = u.replace("https://web.laifaxin.com", "").rstrip("/")
            if path not in self.TRUTH and path not in ("", "/"):
                unknown.append(path)
        self.assertEqual([], unknown,
                         f"发现未经验证的新平台路径（须先核对 JS 路由表再写入真值表）: {unknown}")

    def test_sequence_page_link_is_marketing_sequences(self):
        """序列页（手动激活入口）必须是 /marketing/sequences——用户实测的正确地址。"""
        card = (TEMPLATES / "S12-激活确认.md").read_text(encoding="utf-8")
        self.assertIn("/marketing/sequences", card, "序列页地址不对")
        self.assertNotIn("/mailing/sequence", card, "序列页仍是 404 旧地址")
