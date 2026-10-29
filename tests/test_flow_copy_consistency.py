#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""专项测试：C旧口径与新手回复文案同步（TASK-20261028-interface-C.md & TASK-20261029-interface-R2.md）。

覆盖 C1-C5 及 R2 增量验收项：
- C1: S3内部旧“连接成功后先问网址”同步为仅S3问一次，档案不问、已给不重问、不把沉默代选。
- C2: 15-live-run-pitfalls.md 速查数字范围包含资料数字、候选编号、保存精确N含N=1；激活仍必须含确认激活。
- C3: 从安装起、连接后、资料确认后分别算明回复次数，表项总和准确；从资料确认后到发信前正常主路5次，不把S10明细算独立一次。演示图/正文/契约同口径，无“只回确认”旧资料规则。
- C4: 卖点/截图为同屏可选补充，不加必须回答关；资料未知用通用样稿，不编事实、不让用户先回2才修改。
- C5: 拒绝修改/未知时用户提示只给唯一下一步；精简不扩步骤，无铁律放宽。
- C-R2-1: S9/S10 模板与 A 机器卡对齐：公司/邮箱/人数分单位，计划公司数不冒称实际完成，未知来源不宣称三数相等，加入前回读不一致不加；回1/回2各自独行、修改直说。
- C-R2-2: 第1屏昵称产品已回后包含最后激活总7次，demo/契约原型/beginner-flow/step-map全文真值一致为7，不只排除旧10。
"""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TEMPLATES = ROOT / "output-templates"
SPECS = ROOT / "specs"
DOCS = ROOT / "docs"


class TestInterfaceCopyRemediationC(unittest.TestCase):
    """C旧口径与新手回复文案同步专项测试。"""

    def test_c1_s3_timing_and_no_premature_url_prompt(self):
        """C1: S3内部旧“连接成功后先问网址”同步为仅S3问一次，档案不问、已给不重问、不把沉默代选。"""
        s3_path = TEMPLATES / "S3-seed-confirm.md"
        s3_text = s3_path.read_text(encoding="utf-8")

        self.assertNotIn("连接平台成功后先问一次", s3_text, "S3仍残留'连接平台成功后先问一次'旧时序")
        self.assertNotIn("连接成功后先问网址", s3_text, "S3仍残留'连接成功后先问网址'旧时序")

        self.assertTrue(
            "档案" in s3_text and "不问" in s3_text,
            "S3未明确产品档案屏不问网址"
        )
        self.assertIn("已给过网址不再重问", s3_text)
        self.assertTrue(
            "沉默" in s3_text and ("代选" in s3_text or "不替用户选" in s3_text),
            "S3未明确沉默或跳过不代选"
        )

    def test_c2_pitfalls_numeric_scope(self):
        """C2: 速查数字范围包含资料数字、候选编号、保存精确N含N=1；激活仍必须含确认激活。"""
        pitfalls_path = DOCS / "15-live-run-pitfalls.md"
        p_text = pitfalls_path.read_text(encoding="utf-8")

        self.assertNotIn("只有 S7/S9/S10 接受纯数字", p_text, "15-live-run-pitfalls仍残留过时的纯数字范围描述")

        self.assertTrue(
            ("资料" in p_text or "S0" in p_text) and "1" in p_text,
            "未包含产品资料数字认可"
        )
        self.assertTrue(
            "候选" in p_text or "编号" in p_text,
            "未包含候选编号纯数字"
        )
        self.assertTrue(
            "N=1" in p_text,
            "未明确保存精确N中N=1的特殊处理"
        )
        self.assertTrue(
            "确认激活" in p_text,
            "未明确激活必须含确认激活"
        )

    def test_c3_reply_count_and_demo_consistency(self):
        """C3: 从安装起、连接后、资料确认后分别算明回复次数，表项总和准确；从资料确认后到发信前正常主路5次，不把S10明细算独立一次。演示图/正文/契约同口径，无“只回确认”旧资料规则。"""
        contract_path = SPECS / "novice-flow-contract.md"
        c_text = contract_path.read_text(encoding="utf-8")

        sec0 = c_text.split("## 0. 三条硬指标", 1)[1].split("## 1. 开场两屏", 1)[0]
        self.assertTrue(
            "连接选择" in sec0 or "第 0 屏" in sec0,
            "contract 0.2分项遗漏了初始连接选择1次"
        )

        self.assertTrue(
            "发信前" in c_text and "5 次" in c_text,
            "contract未明确保留资料确认后到发信前5次主路"
        )

        demo_path = DOCS / "14-novice-walkthrough-demo.md"
        d_text = demo_path.read_text(encoding="utf-8")
        self.assertNotIn(
            "核对产品资料·回「确认」", d_text,
            "14-novice-walkthrough-demo Mermaid 图仍写旧口径'核对产品资料·回「确认」'"
        )

        sec_first = d_text.split("### 紧接着｜第 1 屏", 1)[1].split("### 环节 1A", 1)[0]
        self.assertNotIn(
            "顺利约回 10 次", sec_first,
            "第1屏内部已在连接和问两样后，不应再宣称从本处起还要回10次"
        )

    def test_c4_optional_selling_points_and_draft_revision(self):
        """C4: 卖点/截图为同屏可选补充，不加必须回答关；资料未知用通用样稿，不编事实、不让用户先回2才修改。"""
        s7_path = TEMPLATES / "S7-template-confirm.md"
        s7_text = s7_path.read_text(encoding="utf-8")

        self.assertTrue(
            "可选" in s7_text and ("不" in s7_text and "等待" in s7_text or "同屏" in s7_text),
            "S7未明确卖点补充为同屏可选不等待"
        )
        self.assertTrue(
            "通用" in s7_text and "不编" in s7_text or "宁缺不编" in s7_text or "通用介绍" in s7_text,
            "S7未明确资料未知用通用样稿宁缺不编"
        )

        bf_path = SPECS / "beginner-flow.md"
        bf_text = bf_path.read_text(encoding="utf-8")
        self.assertTrue(
            "可选" in bf_text and "卖点" in bf_text,
            "beginner-flow未明确卖点为同屏可选"
        )

    def test_c5_single_next_step_on_rejection_or_unknown(self):
        """C5: 拒绝修改/未知时用户提示只给唯一下一步，精简不扩步骤。"""
        contract_path = SPECS / "novice-flow-contract.md"
        c_text = contract_path.read_text(encoding="utf-8")
        self.assertTrue(
            "唯一下一步" in c_text or "一个下一步" in c_text,
            "contract未强调失败或未知时只给唯一下一步"
        )

    def test_c_r2_1_s9_s10_bundle_card_alignment(self):
        """C-R2-1: S9/S10 模板与 A 机器卡对齐：公司/邮箱/人数分单位，计划公司数不冒称实际完成，未知来源不宣称三数相等，加入前回读不一致不加；回1/回2各自独行、修改直说。"""
        s9_text = (TEMPLATES / "S9-sequence-confirm.md").read_text(encoding="utf-8")
        s10_text = (TEMPLATES / "S10-contacts-confirm.md").read_text(encoding="utf-8")

        for text, name in ((s9_text, "S9"), (s10_text, "S10")):
            self.assertNotIn("已保存 = 名单 = 本次加", text, f"{name}模板仍在宣称'已保存 = 名单 = 本次加'")
            self.assertNotIn("三数核对一致才加", text, f"{name}模板仍在宣称'三数核对一致才加'")
            self.assertNotIn("三数核对", text, f"{name}模板仍在使用过时的'三数核对'口径")
            self.assertNotIn("已保存 <M> = 名单 <M> = 要加 <N>", text, f"{name}模板仍在宣称'已保存=名单=要加'")

        self.assertNotIn("客户保存 已完成，共存", s10_text, "S10把计划公司数冒充为实际已完成")

        for text, name in ((s9_text, "S9"), (s10_text, "S10")):
            self.assertTrue(
                "单位" in text and ("家" in text or "公司" in text) and ("人" in text or "邮箱" in text),
                f"{name}模板未区分公司/邮箱/人数单位"
            )
            self.assertTrue(
                "回读" in text or "加入前" in text,
                f"{name}模板未明确加入前按平台回读核对"
            )

        card_block = re.search(r"```text\n(.*?)```", s9_text, re.S).group(1)
        self.assertIn("- 回 **1**", card_block, "S9 缺少回 1 独立行")
        self.assertIn("- 回 **2**", card_block, "S9 缺少回 2 独立行")
        lines = card_block.splitlines()
        r1_line = next(i for i, l in enumerate(lines) if "- 回 **1**" in l)
        r2_line = next(i for i, l in enumerate(lines) if "- 回 **2**" in l)
        self.assertNotEqual(r1_line, r2_line, "S9 回 1 与 回 2 不能在同一行")

    def test_c_r2_2_first_screen_remaining_count_exact_seven(self):
        """C-R2-2: 第1屏昵称产品已回后包含最后激活总7次，demo/契约原型/beginner-flow/step-map全文真值一致为7，不只排除旧10。"""
        bf_text = (SPECS / "beginner-flow.md").read_text(encoding="utf-8")
        bf_screen1 = bf_text.split("### 第 1 屏 · 拿到昵称和产品后", 1)[1].split("### 下一屏", 1)[0]
        self.assertIn("还要回 7 次", bf_screen1, "beginner-flow.md 第1屏未统一为真值 7 次")
        self.assertNotIn("还要回 8 次", bf_screen1, "beginner-flow.md 第1屏仍残留 8 次")

        step_text = (SPECS / "step-map.md").read_text(encoding="utf-8")
        m2_sec = step_text.split("### M2 第1屏：6步全景", 1)[1].split("### M3", 1)[0]
        self.assertIn("还要回 7 次", m2_sec, "step-map.md M2 节未统一为真值 7 次")
        self.assertNotIn("还要回 8 次", m2_sec, "step-map.md M2 节仍残留 8 次")

        demo_text = (DOCS / "14-novice-walkthrough-demo.md").read_text(encoding="utf-8")
        demo_screen1 = demo_text.split("### 紧接着｜第 1 屏", 1)[1].split("### 环节 1A", 1)[0]
        self.assertIn("顺利约回 7 次", demo_screen1, "14-novice-walkthrough-demo 第1屏未统一为真值 7 次")

        contract_text = (SPECS / "novice-flow-contract.md").read_text(encoding="utf-8")
        c_screen1 = contract_text.split("### 第 1 屏 · 连接成功、拿到昵称和产品后", 1)[1].split("## 1.5", 1)[0]
        self.assertIn("还要回 7 次", c_screen1, "novice-flow-contract 第1屏原型未统一为真值 7 次")
        self.assertNotIn("还要回 8 次", c_screen1, "novice-flow-contract 第1屏原型仍残留 8 次")

        # 验收清单也必须同步：只检查原型会漏掉此处（D R2 实证 :105 仍写 8）。
        accept_check = contract_text.split("## 6. 验收测试", 1)[1].split("## 7.", 1)[0]
        self.assertIn("还要回 7 次", accept_check, "novice-flow-contract 验收清单未同步第1屏真值 7 次")
        self.assertNotIn("还要回 8 次", accept_check, "novice-flow-contract 验收清单仍残留 8 次")


    def test_c_r4_exact_quote_and_modification_handling(self):
        """C-R4: 附带修改先改卡重出再确认，不能把混合句截成同意；S5纯N须等卡N；S12必须完整口令且拒否定/条件句。"""
        # 1. S0: 附带修改先更新再确认，不截取混合句
        s0_text = (TEMPLATES / "S0-product-profile.md").read_text(encoding="utf-8")
        self.assertTrue(
            "附带修改" in s0_text or "修改意图" in s0_text or "先更新" in s0_text,
            "S0未明确附带修改先更新档案再用干净原话重新确认"
        )
        self.assertTrue(
            "截取" in s0_text or "混合" in s0_text,
            "S0未明确禁止从混合句中截取确认"
        )

        # 2. S5: 附带修改拒绝且不授权旧卡；纯数字必须精确等卡面N
        s5_text = (TEMPLATES / "S5-save-confirm.md").read_text(encoding="utf-8")
        self.assertTrue(
            "附带修改" in s5_text or "改邮箱" in s5_text or "新卡" in s5_text,
            "S5未明确附带修改拒绝并不授权旧卡"
        )
        self.assertTrue(
            "精确" in s5_text or "泛确认" in s5_text or "菜单" in s5_text,
            "S5未明确纯数字必须精确等卡面N，不能当菜单1泛确认"
        )

        # 3. S9: 附带修改人数或配置不铸审批，不能截取混合句为同意
        s9_text = (TEMPLATES / "S9-sequence-confirm.md").read_text(encoding="utf-8")
        self.assertTrue(
            "改数量" in s9_text or "改人数" in s9_text or "附带修改" in s9_text,
            "S9未明确附带修改不铸审批、重新出卡"
        )
        self.assertTrue(
            "截取" in s9_text or "混合" in s9_text,
            "S9未明确禁止截取混合句为同意"
        )

        # 4. S12: 界面只推荐完整口令「确认激活」，拒绝含口令的修改/否定/条件句，不展示名称后缀选项
        s12_text = (TEMPLATES / "S12-activation-confirm.md").read_text(encoding="utf-8")
        self.assertTrue(
            "否定" in s12_text and ("条件" in s12_text or "修改" in s12_text),
            "S12未明确拒绝含口令的否定/条件/修改句"
        )
        blocks = re.findall(r"```text\n(.*?)```", s12_text, re.S)
        self.assertIn("回「确认激活」真发", blocks[0], "S12卡面必须推荐纯'确认激活'")
        self.assertNotIn("确认激活 <计划名>", s12_text, "S12不得向用户展示或引导'确认激活 <计划名>'")
        self.assertNotIn("激活 <计划名>", blocks[0], "S12默认卡面不得包含计划名口令")

        # 5. specs/novice-flow-contract.md 明确整句状态绑定与附带修改先改卡再确认
        contract_text = (SPECS / "novice-flow-contract.md").read_text(encoding="utf-8")
        self.assertTrue(
            "附带修改" in contract_text or "混合句" in contract_text or "先改卡" in contract_text,
            "contract未明确附带修改先改卡重出再确认"
        )


    def test_c_r4_s0a_two_stage_website_card(self):
        """C-R4补齐: S0a网站卡两阶段对齐，选择词仅定范围，精确卡回1/确认采纳；不增加主路5次，不露内部词。"""
        s0a_text = (TEMPLATES / "S0a-website-profile.md").read_text(encoding="utf-8")

        # 1. 明确两阶段：选择词仅选范围，精确变更卡才确认采纳
        self.assertTrue(
            "变更卡" in s0a_text or "两阶段" in s0a_text,
            "S0a未明确按选择列出精确变更卡的两阶段机制"
        )
        self.assertTrue(
            "回 1" in s0a_text and ("采纳" in s0a_text or "确认" in s0a_text),
            "S0a精确变更卡未提供推荐回1或确认采纳"
        )
        self.assertTrue(
            "直接" in s0a_text and ("选择" in s0a_text or "批准" in s0a_text),
            "S0a未明确不能把选择词直接当最终批准"
        )

        # 2. 内部执行要点明确不增加资料确认后发信前5次主路
        self.assertTrue(
            "5 次" in s0a_text or "5次" in s0a_text,
            "S0a执行要点未明确选范围为可选分支不增加主路5次"
        )

        # 3. 用户可见块不出现内部词 patch / hash / 白名单
        blocks = re.findall(r"```text\n(.*?)```", s0a_text, re.S)
        for b in blocks:
            for forbidden in ("patch", "hash", "白名单"):
                self.assertNotIn(forbidden, b.lower(), f"S0a用户卡块出现内部词 {forbidden}")

    def test_feedback_1_six_steps_each_line_standalone(self):
        """①: 用户全景代码块每序号独行，Markdown硬换行有效，不把多步挤在一行。"""
        for file_path, name in ((SPECS / "beginner-flow.md", "beginner-flow"), (SPECS / "novice-flow-contract.md", "contract")):
            text = file_path.read_text(encoding="utf-8")
            # 提取第 1 屏代码块
            m = re.search(r"```text\n(.*?)```", text, re.S)
            self.assertIsNotNone(m, f"{name} 缺少全景代码块")
            block = m.group(1)
            for line in block.splitlines():
                symbols = [s for s in ("①", "②", "③", "④", "⑤", "⑥") if s in line]
                self.assertLessEqual(len(symbols), 1, f"{name} 代码块中行【{line.strip()}】包含多个序号，未实现每序号独行")

    def test_feedback_2_long_cycle_not_prematurely_denied(self):
        """②: 长周期/精准客群说明先定位合适买家按采购周期跟进，不先说不适合、不默认小样，不承诺效果。"""
        pf_text = (SPECS / "product-fit.md").read_text(encoding="utf-8")
        rules_text = (ROOT / "RULES.md").read_text(encoding="utf-8")

        self.assertIn("先定位合适买家、按采购周期跟进", pf_text, "product-fit.md 未说明先定位合适买家、按采购周期跟进")
        self.assertNotIn("默认小样验证", pf_text, "product-fit.md 仍残留'默认小样验证'")
        self.assertNotIn("默认小样", rules_text, "RULES.md 仍残留'默认小样'")
        self.assertTrue("不承诺效果" in pf_text or "不许无条件承诺效果" in pf_text or "不承诺" in pf_text)

    def test_feedback_4_metrics_attribution_and_no_fictional_thresholds(self):
        """④: 区分发送/拦截/硬退/软退/投递/回复，未知写未知；不拿2%-3%评平台拦截，不虚构5000封48h询盘线。"""
        s12_text = (TEMPLATES / "S12-activation-confirm.md").read_text(encoding="utf-8")

        self.assertNotIn("48 小时判断（从首封发出算）", s12_text, "S12仍在虚构48小时判定生死线")
        self.assertNotIn("名单 ≥5000 当天即可看出", s12_text, "S12仍在虚构5000封合格线")
        self.assertTrue(
            "硬退信" in s12_text and "软退信" in s12_text and "拦截" in s12_text,
            "S12未区分发送/平台拦截/硬退信/软退信/投递/回复等指标"
        )

    def test_feedback_5_sufficient_testing_and_sample_context(self):
        """⑤: 精准且预算内足量客群测试，约3000封仅作上下文建议非统一门槛，不默认100-200家/先少存/48h定生死。"""
        pf_text = (SPECS / "product-fit.md").read_text(encoding="utf-8")
        sop_text = (SPECS / "operations-sop.md").read_text(encoding="utf-8")
        self.assertTrue(
            "精准且在预算内足量" in pf_text or "精准且预算内足量" in pf_text or "足量客群测试" in pf_text,
            "product-fit未说明精准且预算内足量客群测试"
        )
        self.assertNotIn("48h定生死", sop_text, "operations-sop 不得宣称48h定生死")

    def test_feedback_7_info_and_title_unknown_attribution(self):
        """⑦: info和无职位不可一刀切排除；系统邮箱待核按用户现有策略不自动过滤(contactExcludes仍[])，单独过滤须明确变更。"""
        mr_text = (SPECS / "marketing-rules-2.0.md").read_text(encoding="utf-8")
        rtc_text = (SPECS / "redteam-fix-checklist.md").read_text(encoding="utf-8")

        # 1. 政策一致性：contactExcludes 仍保持 []，不自动过滤
        self.assertIn("contactExcludes 仍 []", mr_text, "marketing-rules 未保持 contactExcludes 仍 [] 策略")
        self.assertIn("不自动过滤", mr_text, "marketing-rules 未明确按现有策略不自动过滤")
        self.assertIn("单独过滤需用户明确变更策略", mr_text, "marketing-rules 未明确单独过滤需用户明确变更策略")
        self.assertNotIn("依证明确排除", mr_text, "marketing-rules 仍残留依证排除导致相邻段冲突")
        self.assertNotIn("绝对排除", mr_text, "marketing-rules 仍残留绝对排除导致冲突")

        # 2. redteam-fix-checklist 同样保持 contactExcludes=[] 政策
        self.assertNotIn("依证排除", rtc_text, "redteam-fix-checklist 仍残留依证排除")

        # 3. info 与无职位不可一刀切排除/认定导致低回复
        self.assertTrue("一刀切" in mr_text, "未明确禁止一刀切排除info")
        self.assertTrue("职位未知不等" in mr_text or "职位未知不等于" in mr_text, "未明确职位未知不等于邮箱无效")

    def test_luna_review_product_fit_and_skill_rewritten(self):
        """Luna独审问题①: product-fit重写为客群定位与采购节奏，消除旧否定入口；SKILL同步。"""
        pf_text = (SPECS / "product-fit.md").read_text(encoding="utf-8")
        skill_text = (ROOT / "SKILL.md").read_text(encoding="utf-8")

        # 1. product-fit 消除旧否定与长周期窄众偏见词
        for banned in ("漏斗会空转", "真正吃不下这套漏斗", "强/条件/弱三档", "弱适配信号", "弱适配打法"):
            self.assertNotIn(banned, pf_text, f"product-fit.md 仍残留否定词 '{banned}'")

        # 2. product-fit 包含正向定位与采购节奏
        self.assertIn("先定位合适买家、按采购周期跟进", pf_text)
        self.assertTrue("采购节奏" in pf_text and "客群定位" in pf_text)
        self.assertTrue("不承诺任何产品必有效" in pf_text or "不许无条件承诺效果" in pf_text)

        # 3. SKILL.md 100/238 行同步消除强/条件/弱三档入口
        skill_lines = skill_text.splitlines()
        self.assertNotIn("强/条件/弱三档", skill_lines[99], "SKILL.md:100 仍残留强/条件/弱三档")
        self.assertNotIn("适配三档", skill_lines[237], "SKILL.md:238 仍残留适配三档")

    def test_luna_review_marketing_rules_no_arbitrary_bands(self):
        """Luna独审问题②: marketing-rules消除固定几千封小批和统一2%-3%决策门，改为按匹配预算采购窗口。"""
        mr_text = (SPECS / "marketing-rules-2.0.md").read_text(encoding="utf-8")

        # 1. 生效规则表中不包含固定几千封小批和统一2-3%决策门
        self.assertNotIn("先小批验证（几千封）", mr_text, "marketing-rules 仍残留先小批验证（几千封）")
        self.assertNotIn("退信 < 2-3%，垃圾投诉 < 0.1-0.3%", mr_text, "marketing-rules 仍残留无来源统一健康线")

        # 2. 包含按匹配/预算/采购窗口/有效样本规划建议
        self.assertTrue(
            "采购窗口" in mr_text and ("有效样本" in mr_text or "匹配" in mr_text),
            "marketing-rules 未明确按匹配/预算/采购窗口/有效样本规划"
        )
        self.assertIn("不作为当前决策门", mr_text, "marketing-rules 未明确历史比率不作当前决策门")

    def test_live_consistency_product_fit_and_fit_notes(self):
        """生效一致性①: 消除全仓S0-fit-notes/RULES/CORE/README/docs13/sop中的旧三档与默认小样入口。"""
        # 1. output-templates/S0-fit-notes.md 消除旧三档（适合/一般/吃力/默认<=500）
        s0_notes = (TEMPLATES / "S0-fit-notes.md").read_text(encoding="utf-8")
        for banned in ("判强/条件/弱", "弱适配", "先小范围试（≤500", "≤500 家只发 1 轮"):
            self.assertNotIn(banned, s0_notes, f"S0-fit-notes 仍残留 '{banned}'")
        self.assertIn("先定位合适买家、按采购周期跟进", s0_notes)

        # 2. output-templates/S0-fit-plan.md 与 output-templates/README.md 消除旧三档
        s0_plan = (TEMPLATES / "S0-fit-plan.md").read_text(encoding="utf-8")
        self.assertNotIn("强/条件/弱适配由", s0_plan)
        tpl_readme = (TEMPLATES / "README.md").read_text(encoding="utf-8")
        self.assertNotIn("判强/条件/弱适配", tpl_readme)

        # 3. RULES.md:73/246 消除旧三档/弱适配
        rules_text = (ROOT / "RULES.md").read_text(encoding="utf-8")
        self.assertNotIn("（条件/弱适配）", rules_text)
        self.assertNotIn("适配三档", rules_text)

        # 4. CORE-POINTS.md:143 消除旧弱适配小样条目
        core_text = (ROOT / "CORE-POINTS.md").read_text(encoding="utf-8")
        self.assertNotIn("弱适配「建议用户选择小样（如 ≤500 家/1 轮）」", core_text)

        # 5. docs/13-rule-ensure-read.md:160 消除弱适配小样500
        d13_text = (DOCS / "13-rule-ensure-read.md").read_text(encoding="utf-8")
        self.assertNotIn("弱适配 → 诚实解释，由用户选择是否小样；不默认 500", d13_text)

        # 6. specs/product-profile-sop.md:82 消除三档买家盘
        pps_text = (SPECS / "product-profile-sop.md").read_text(encoding="utf-8")
        self.assertNotIn("对应 product-fit 三档的买家盘", pps_text)

        # 7. methodology/best-practices.md:56 消除弱适配小样
        bp_text = (ROOT / "methodology" / "best-practices.md").read_text(encoding="utf-8")
        self.assertNotIn("弱适配只解释不默认500", bp_text)

    def test_live_consistency_scale_and_48h_inquiry_bounds(self):
        """生效一致性②: SKILL与docs09/10消除3000硬门与48h3询盘万能线，3000仅上下文建议，不自动加量。"""
        skill_text = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        d09_text = (DOCS / "09-mass-outreach-to-precision-follow-up.md").read_text(encoding="utf-8")
        d10_text = (DOCS / "10-execution-guardrails.md").read_text(encoding="utf-8")

        # 1. SKILL.md:134/141 消除不足3000先加量硬门与48小时视为量足
        self.assertNotIn("发信量是否 ≥3000/次：不足先加量", skill_text)
        self.assertNotIn("单次 ≥3000 封且满 48 小时即视为量足", skill_text)

        # 2. docs/09 生效建议消除单批>=3000硬门与48h3询盘万能门
        self.assertNotIn("单批 ≥3000 封再看打开率/回复率；量不足先加量", d09_text)
        self.assertNotIn("首波发出后 **48 小时**，数**有效询盘**（A/B 级才算", d09_text)

        # 3. docs/10 消除硬性建议3000+邮箱
        self.assertNotIn("单次建议 3000+ 邮箱", d10_text)

    def test_final_residuals_skill_state_table(self):
        """残留修复1: SKILL.md 状态机执行表 S0(183) 与 S9(193) 消除旧三档与默认不激活。"""
        skill_text = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        s_lines = skill_text.splitlines()
        # 检查 S0 状态行 (183附近)
        s0_line = next(l for l in s_lines if "| S0 INPUT_GATE |" in l)
        self.assertNotIn("强/条件/弱", s0_line, "SKILL.md S0状态行仍残留'强/条件/弱'")
        self.assertIn("客群定位与采购节奏", s0_line, "SKILL.md S0状态行未包含客群定位与采购节奏")

        # 检查 S9 状态行 (193附近)
        s9_line = next(l for l in s_lines if "| S9 SEQUENCE_PENDING |" in l)
        self.assertNotIn("（条件/弱适配）", s9_line, "SKILL.md S9状态行仍残留条件/弱适配")
        self.assertNotIn("建议先不激活", s9_line, "SKILL.md S9状态行不得因长周期自动建议不激活")
        self.assertIn("确认激活", s9_line, "S9状态行必须保留确认激活硬门")

    def test_final_residuals_docs09_boundary_and_rules73(self):
        """残留修复2: docs/09 第8节边界、RULES:73 与 docs/14:413 消除旧漏斗空转与默认不激活。"""
        d09_text = (DOCS / "09-mass-outreach-to-precision-follow-up.md").read_text(encoding="utf-8")
        rules_text = (ROOT / "RULES.md").read_text(encoding="utf-8")
        d14_text = (DOCS / "14-novice-walkthrough-demo.md").read_text(encoding="utf-8")

        # docs/09 第8节
        self.assertNotIn("漏斗会空转", d09_text, "docs/09 仍残留'漏斗会空转'")
        self.assertNotIn("冷邮件基本不会带来询盘", d09_text, "docs/09 仍残留'冷邮件基本不会带来询盘'")
        self.assertNotIn("建议先不激活", d09_text, "docs/09 仍残留'建议先不激活'")

        # RULES.md:73
        r_lines = rules_text.splitlines()
        r73_line = next(l for l in r_lines if "S9 SEQUENCE_PENDING" in l)
        self.assertNotIn("建议结合实际采购窗口与需求再开，或转人工低频培育", r73_line, "RULES.md:73 仍保留预设停止处置")

        # docs/14:413
        self.assertNotIn("慢周期提示先不激活", d14_text, "docs/14:413 仍残留'慢周期提示先不激活'")

    def test_final_residuals_demo_fixed_metrics_and_s12_qa(self):
        """残留修复3&4: docs/14 固定口径与 S12 独立问答，指标严格区分，不拿统一阈值定生死。"""
        d14_text = (DOCS / "14-novice-walkthrough-demo.md").read_text(encoding="utf-8")
        s12_text = (TEMPLATES / "S12-activation-confirm.md").read_text(encoding="utf-8")
        rtc_text = (SPECS / "redteam-fix-checklist.md").read_text(encoding="utf-8")

        # docs/14:16 与 416 不得将退信与两轮0询盘当固定死线
        d14_head = "\n".join(d14_text.splitlines()[:25])
        self.assertNotIn("退信 20%–30% 先查内容暂不停发、>30% 先停发", d14_head, "docs/14:16 未将退信移为历史运营参考")
        self.assertNotIn("连续两轮 0 个询盘才止损", d14_head, "docs/14:16 未将两轮0询盘止损移为历史参考")

        # S12 独立问答 (102-104)
        qa3_sec = s12_text.split("3. 「退信多是不是我域名/邮箱坏了」", 1)[1].split("4. 「打开率低", 1)[0]
        self.assertTrue("平台安全拦截" in qa3_sec or "硬退信" in qa3_sec, "S12独立问答未区分平台拦截与硬/软退信")
        self.assertTrue("分母" in qa3_sec or "未知" in qa3_sec, "S12独立问答未说明分母窗口未知不套阈值")

        # redteam-fix-checklist:50-56
        self.assertTrue("历史运营口径" in rtc_text or "历史参考" in rtc_text or "来源" in rtc_text)

    def test_final_residuals_faq_and_replay_script(self):
        """残留修复5&6: wiki/faq.md 消除旧三档/默认小样；docs/11 入口增加历史复盘边界说明。"""
        faq_text = (ROOT / "wiki" / "faq.md").read_text(encoding="utf-8")
        d11_text = (DOCS / "11-replay-script.md").read_text(encoding="utf-8")

        # wiki/faq.md:66-67
        self.assertNotIn("强适配 / 条件适配 / 弱适配", faq_text, "wiki/faq.md 仍残留强/条件/弱三档")
        self.assertNotIn("弱适配：", faq_text, "wiki/faq.md 仍残留弱适配判定")
        self.assertNotIn("≤500 家只发 1 轮", faq_text, "wiki/faq.md 仍残留默认≤500家小样")
        self.assertIn("先定位合适买家、按采购周期跟进", faq_text, "wiki/faq.md 未对齐新口径")

        # docs/11:15-16
        d11_head = "\n".join(d11_text.splitlines()[:20])
        self.assertIn("历史2026运行复盘", d11_head, "docs/11 入口未声明历史复盘边界")

    def test_final_metric_fix_five_residuals(self):
        """最终收口: 彻底清除FAQ/S12建议/SKILL短答/docs09诊断表/docs14剧本B中的固定百分比触发动作与48h硬线。"""
        faq_text = (ROOT / "wiki" / "faq.md").read_text(encoding="utf-8")
        s12_text = (TEMPLATES / "S12-activation-confirm.md").read_text(encoding="utf-8")
        skill_text = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        d09_text = (DOCS / "09-mass-outreach-to-precision-follow-up.md").read_text(encoding="utf-8")
        d14_text = (DOCS / "14-novice-walkthrough-demo.md").read_text(encoding="utf-8")

        # 1. wiki/faq.md 问答中移除 48h>=3合格/两轮0止损硬门
        self.assertNotIn("发出后 48 小时数有效询盘", faq_text, "wiki/faq 仍残留发出后48小时数有效询盘")
        self.assertNotIn("连续两轮都是 0 个 → 才建议停止该项目止损", faq_text, "wiki/faq 仍残留两轮0个止损硬门")

        # 2. output-templates/S12-activation-confirm.md 行91建议移除固定百分比触发动作
        s12_rec = s12_text.split("## 激活后建议", 1)[1].split("## 用户看数据时最常问", 1)[0]
        self.assertNotIn("硬退信率在 20% 以内属正常长尾波动", s12_rec, "S12激活后建议仍残留固定百分比硬线")
        self.assertNotIn("20%–30% 之间先排查邮件内容与主题；超过 30% 建议暂停发信", s12_rec, "S12激活后建议仍残留固定百分比触发动作")

        # 3. SKILL.md:122 移除短答中的固定百分比触发动作
        sk_qa = skill_text.split("### 🔔 客户问退信怎么答", 1)[1].split("#### 🧩 发信通道", 1)[0]
        self.assertNotIn("硬退信在 20% 左右按长尾正常情况看", sk_qa, "SKILL短答仍残留20%左右正常口号")
        self.assertNotIn("超过 30% 先暂停发信再排查内容与客群匹配", sk_qa, "SKILL短答仍残留超30%停发动作")

        # 4. docs/09-mass-outreach-to-precision-follow-up.md 诊断表移除固定百分比触发动作
        self.assertNotIn("硬退信 20% 以内属长尾正常、20–30% 先查内容暂不停发、超过 30% 建议停发排查", d09_text, "docs/09 诊断表仍残留固定百分比动作")

        # 5. docs/14-novice-walkthrough-demo.md 剧本B移除固定百分比触发动作
        self.assertNotIn("硬退信 20% 以内属长尾正常、20%–30% 先查内容暂不停发、超过 30% 建议停发排查", d14_text, "docs/14 剧本B仍残留固定百分比动作")

if __name__ == "__main__":
    unittest.main()
