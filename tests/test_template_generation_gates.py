#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""S8 模板生成三道门的回归测试（P0-C 价格硬门 / P0-D 12轮×4 断言 / P1-E 自动差异检查）。

背景（静态红队）：
  · P0-C：RISK_RE 缺 cheap/FOB/CIF，且 PRICE/DISCOUNT 是可认领 claim 类 → 只要 plan 给 claims
    就能把"价格/折扣"放进模板正文。现在必须在任何 claims 放行之前硬拒。
  · P0-D：tools/gen_templates.py 只要求 directions/variants 非空，:684 动态相乘；
    tmap_grid 只要求 12 的倍数 → 11×4 / 12×3 也能生成，build_sequence 再静默错组。
  · P1-E：文档称"生成后必跑 check_template_diff"，但工具从未调用 → 差异不达标没人发现。

本测试用真跑 gen_templates.py 的本地闸门（不需要平台：价格门/网格门都在联网之前）+
静态断言锁自动差异检查的调用位置。
"""
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
GEN = TOOLS / "gen_templates.py"

TITLES = [
    "aurora", "brass", "copper", "denim", "ember", "frost", "granite", "harbor",
    "ivory", "jade", "kelp", "lumen", "marble", "nectar", "onyx", "pearl",
    "quartz", "raven", "slate", "topaz", "umber", "velvet", "willow", "xenon",
    "yarrow", "zephyr", "alcove", "birch", "cedar", "drift", "elm", "fjord",
    "glade", "hazel", "iris", "juniper", "kite", "larch", "maple", "nimbus",
    "oak", "pine", "quill", "reed", "sage", "teak", "vine", "wren",
]

PROFILE_FIXTURE = """---
profile_version: 1
status: declined
operator_key: tony
product_key: pet-pack
created_at: 2026-09-17T00:00:00
updated_at: 2026-09-17T00:00:00
confirmed_at:
confirmed_by:
confirm_quote:
content_sha256:
sources_status: declined
sources_present: no
---

# 产品知识档案

## ① 产品定位（卖给谁/解决什么）
- 内容：（待补）
- source: none
- confidence: low

## ② 产品线（品类/子品类/SKU/成分配比）
- 内容：（待补）
- source: none
- confidence: low

## ③ 核心卖点（≤5 条，每条一句：为什么买你）
- 内容：（待补）
- source: none
- confidence: low

## ④ 目标客群+市场（国家/语言/渠道角色）
- 内容：（待补）
- source: none
- confidence: low

## ⑤ 规格/认证（型号/标准号/证书/参数——有来源才写）
- 内容：（待补）
- source: none
- confidence: low

## ⑥ 差异化（vs 竞品强在哪）
- 内容：（待补）
- source: none
- confidence: low

## ⑦ 合规/禁忌（禁运区/受管制品类/环保声明——有依据才写）
- 内容：（待补）
- source: none
- confidence: low

## ⑧ 可引用数字（产能/MOQ/交期/价格带——用户给或官网可查才写，没有不编）
- 内容：（待补）
- source: none
- confidence: low
"""


def build_plan(variants, rounds=12, titles=None, claims=None, profile_sha="0" * 64):
    """按 variants 个数给每轮同数量的逐变体标题（load_plan 要求标题数=变体数）。"""
    titles = titles or TITLES
    n = len(variants)
    directions = []
    for i in range(rounds):
        subj = [titles[i * n + v] for v in range(n)]
        directions.append([f"R{i + 1:02d}", "破冰", subj, f"Production idea about {titles[i]}"])
    plan = {"profile_sha256": profile_sha, "directions": directions,
            "variants": variants, "claims": claims if claims is not None else []}
    return plan


class GridGateTest(unittest.TestCase):
    """P0-D：48=12轮×4 必须是硬断言（不再动态相乘）。"""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="gridgate-"))

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def run_plan(self, plan, profile="runs/tony/pet-pack/product-profile.md"):
        p = self.tmp / "plan.json"
        p.write_text(json.dumps(plan, ensure_ascii=False), encoding="utf-8")
        return subprocess.run(
            [sys.executable, str(GEN), "--plan", str(p), "--token", "x", "--org", "1",
             "--product", "pet-pack", "--name", "Tony", "--prefix", "英-pet-",
             "--project", "tony/pet-pack", "--profile", str(profile)],
            capture_output=True, text=True, cwd=ROOT, timeout=120)

    def variants(self):
        return ["Sharing a quick production idea for linen.",
                "Sharing a quick production idea for canvas.",
                "Sharing a quick production idea for twill.",
                "Sharing a quick production idea for knit."]

    def test_rejects_11_rounds(self):
        plan = build_plan(self.variants(), rounds=11,
                          titles=TITLES[:44])
        r = self.run_plan(plan)
        self.assertEqual(2, r.returncode, r.stdout + r.stderr)
        self.assertIn("轮数=11", r.stdout)
        self.assertIn("12", r.stdout)
        self.assertIn("exit 2", r.stdout)

    def test_rejects_3_variants(self):
        plan = build_plan(["Sharing a quick idea for linen.",
                           "Sharing a quick idea for canvas.",
                           "Sharing a quick idea for twill."], rounds=12,
                          titles=TITLES[:36])
        r = self.run_plan(plan)
        self.assertEqual(2, r.returncode, r.stdout + r.stderr)
        self.assertIn("变体数=3", r.stdout)
        self.assertIn("4", r.stdout)

    def test_accepts_12x4_grid(self):
        r = self.run_plan(build_plan(self.variants()))
        # 网格门通过后停在产品档案闸门（4）；关键是不因网格被拒（2）
        self.assertEqual(4, r.returncode, r.stdout + r.stderr)
        self.assertIn("✅ plan 网格: 12 轮 × 4 变体 = 48", r.stdout)
        self.assertNotIn("不符禁止生成", r.stdout)

    def test_post_generation_grid_is_fail_closed(self):
        """生成后必须用 tmap_grid 精确复核；exact=False 静默顺序切分 → fail-closed。"""
        src = GEN.read_text(encoding="utf-8")
        self.assertIn("EXPECTED_ROUNDS = 12", src)
        self.assertIn("EXPECTED_VARIANTS = 4", src)
        self.assertIn("group_by_round", src)
        self.assertIn("_exact", src)
        self.assertRegex(src, r"not _exact|if not _exact", "exact=False 必须 fail-closed")


class PriceGateTest(unittest.TestCase):
    """P0-C：价格/折扣硬门必须在 claims 之前，命中 exit 2。"""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="pricegate-"))
        self.profile = self.tmp / "product-profile.md"
        self.profile.write_text(PROFILE_FIXTURE, encoding="utf-8")
        self.sha = hashlib.sha256(self.profile.read_bytes()).hexdigest()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def run_plan(self, plan):
        p = self.tmp / "plan.json"
        p.write_text(json.dumps(plan, ensure_ascii=False), encoding="utf-8")
        return subprocess.run(
            [sys.executable, str(GEN), "--plan", str(p), "--token", "x", "--org", "1",
             "--product", "pet-pack", "--name", "Tony", "--prefix", "英-pet-",
             "--project", "tony/pet-pack", "--profile", str(self.profile),
             "--record", str(self.tmp / "operation-record.md"),
             "--out", str(self.tmp / "tmap.json")],
            capture_output=True, text=True, cwd=ROOT, timeout=120)

    def plan_with(self, bodies, claims=None):
        dirs = []
        for i in range(12):
            subj = [TITLES[i * 4 + v] for v in range(4)]
            dirs.append([f"R{i + 1:02d}", "破冰", subj, f"Production idea about {TITLES[i]}"])
        return {"profile_sha256": self.sha, "directions": dirs,
                "variants": bodies, "claims": claims if claims is not None else []}

    def assert_price_rejected(self, body, word):
        r = self.run_plan(self.plan_with(
            [body, "Sharing a quick production idea for canvas.",
             "Sharing a quick production idea for twill.",
             "Sharing a quick production idea for knit."]))
        self.assertEqual(2, r.returncode, r.stdout + r.stderr)
        self.assertIn("价格/折扣硬门", r.stdout, f"「{word}」未被价格硬门拦截")
        self.assertIn(word, r.stdout)

    def test_rejects_price(self):
        self.assert_price_rejected("Our factory price is very competitive.", "price")

    def test_rejects_pricing(self):
        self.assert_price_rejected("Ask us for pricing today.", "pricing")

    def test_rejects_discount(self):
        self.assert_price_rejected("We offer a discount for first orders.", "discount")

    def test_rejects_cheap(self):
        self.assert_price_rejected("We offer cheap samples for your brand.", "cheap")

    def test_rejects_fob(self):
        self.assert_price_rejected("FOB Shenzhen quotes on request.", "FOB")

    def test_rejects_cif(self):
        self.assert_price_rejected("CIF Rotterdam quotes on request.", "CIF")

    def test_rejects_price_in_chinese(self):
        self.assert_price_rejected("可以直接告诉您价格。", "价格")

    def test_claims_cannot_whitelist_price(self):
        """关键：价格是硬门，claims 覆盖也不能放行（旧实现 PRICE/DISCOUNT 可认领）。"""
        body = "Our best FOB price is ready for you."
        fake_claim = {"exact_text": body, "source": "none", "profile_field": "①",
                      "evidence_text": "none"}
        r = self.run_plan(self.plan_with(
            [body, "Sharing a quick production idea for canvas.",
             "Sharing a quick production idea for twill.",
             "Sharing a quick production idea for knit."],
            claims=[fake_claim]))
        self.assertEqual(2, r.returncode, r.stdout + r.stderr)
        self.assertIn("价格/折扣硬门", r.stdout)
        self.assertIn("claims 也不得放行", r.stdout)

    def test_clean_text_passes_price_gate(self):
        plan = self.plan_with(["Sharing a quick production idea for linen.",
                               "Sharing a quick production idea for canvas.",
                               "Sharing a quick production idea for twill.",
                               "Sharing a quick production idea for knit."])
        r = self.run_plan(plan)
        self.assertNotIn("价格/折扣硬门", r.stdout, "正常文本被价格硬门误伤")
        self.assertIn("✅ 事实闸门", r.stdout, "正常文本应过事实闸门（价格门之后）")


class AutoDiffCheckTest(unittest.TestCase):
    """P1-E：模板创建成功后必须自动跑 check_template_diff，且早于"完成"输出。"""

    def setUp(self):
        self.src = GEN.read_text(encoding="utf-8")

    def _call_anchor(self):
        """定位实现处的 subprocess 调用（不是 docstring 里那句"必跑"）。"""
        return self.src.index("_diff = subprocess.run(")

    def test_auto_diff_call_exists(self):
        call = self._call_anchor()
        seg = self.src[call:call + 900]
        self.assertIn("check_template_diff.py", seg)
        self.assertIn("--limit", seg)
        self.assertIn("str(len(results))", seg, "limit 必须跟随实际生成数")

    def test_auto_diff_is_fail_closed(self):
        call = self._call_anchor()
        tail = self.src[call:call + 2000]
        self.assertRegex(tail, r"returncode\s*!=\s*0", "非 0 必须判失败")
        self.assertIn("sys.exit(2)", tail, "差异检查失败必须整体 exit 2")
        self.assertIn("❌", tail)

    def test_auto_diff_has_timeout(self):
        call = self._call_anchor()
        self.assertIn("timeout=", self.src[call:call + 900],
                      "外部检查必须有超时（卡死不能拖住整批）")

    def test_auto_diff_runs_before_completion_output(self):
        """调用必须早于 tmap 落盘/S8 推进等"完成"输出，否则会先报成功再失败。"""
        call = self._call_anchor()
        for later in ("已落盘溯源元数据", "运行状态已推进"):
            pos = self.src.find(later, call)
            with self.subTest(later=later):
                self.assertGreater(pos, call, f"「{later}」出现在差异检查之前（会先报成功）")


if __name__ == "__main__":
    unittest.main()


class SpamWordGateTest(unittest.TestCase):
    """垃圾邮件触发词硬门：标题/正文命中 exit 2；clean 文本不受影响。"""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="spamgate-"))
        self.profile = self.tmp / "product-profile.md"
        self.profile.write_text(PROFILE_FIXTURE, encoding="utf-8")
        self.sha = hashlib.sha256(self.profile.read_bytes()).hexdigest()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def run_plan(self, plan):
        p = self.tmp / "plan.json"
        p.write_text(json.dumps(plan, ensure_ascii=False), encoding="utf-8")
        return subprocess.run(
            [sys.executable, str(GEN), "--plan", str(p), "--token", "x", "--org", "1",
             "--product", "pet-pack", "--name", "Tony", "--prefix", "英-pet-",
             "--project", "tony/pet-pack", "--profile", str(self.profile),
             "--record", str(self.tmp / "operation-record.md"),
             "--out", str(self.tmp / "tmap.json")],
            capture_output=True, text=True, cwd=ROOT, timeout=120)

    def plan_with(self, bodies, subjects=None):
        dirs = []
        for i in range(12):
            subj = ([subjects[i] for i in range(4)] if subjects else [TITLES[i * 4 + v] for v in range(4)])
            dirs.append([f"R{i + 1:02d}", "破冰", subj, f"Production idea about {TITLES[i]}"])
        return {"profile_sha256": self.sha, "directions": dirs, "variants": bodies, "claims": []}

    def assert_spam_rejected(self, bodies, word):
        r = self.run_plan(self.plan_with(bodies))
        self.assertEqual(2, r.returncode, r.stdout + r.stderr)
        self.assertIn("垃圾邮件触发词", r.stdout, f"「{word}」未被垃圾词硬门拦截")
        self.assertIn(word.lower(), r.stdout.lower())

    def test_rejects_click_here(self):
        self.assert_spam_rejected(["Click here to see our new designs.",
                                   "Sharing a quick production idea for canvas.",
                                   "Sharing a quick production idea for twill.",
                                   "Sharing a quick production idea for knit."], "click here")

    def test_rejects_buy_now(self):
        self.assert_spam_rejected(["Buy now to lock your production slot.",
                                   "Sharing a quick production idea for canvas.",
                                   "Sharing a quick production idea for twill.",
                                   "Sharing a quick production idea for knit."], "buy now")

    def test_rejects_bang_bang_bang(self):
        self.assert_spam_rejected(["Great news!!! We launch a new line.",
                                   "Sharing a quick production idea for canvas.",
                                   "Sharing a quick production idea for twill.",
                                   "Sharing a quick production idea for knit."], "!!!")

    def test_rejects_spam_word_in_subject(self):
        dirs = []
        for i in range(12):
            subj = [TITLES[i * 4 + v] for v in range(4)]
            if i == 0:
                subj[0] = "Act now for your line"
            dirs.append([f"R{i + 1:02d}", "破冰", subj, f"Production idea about {TITLES[i]}"])
        plan = {"profile_sha256": self.sha, "directions": dirs,
                "variants": ["Sharing a quick production idea for linen.",
                             "Sharing a quick production idea for canvas.",
                             "Sharing a quick production idea for twill.",
                             "Sharing a quick production idea for knit."],
                "claims": []}
        r = self.run_plan(plan)
        self.assertEqual(2, r.returncode, r.stdout + r.stderr)
        self.assertIn("标题含垃圾邮件触发词", r.stdout)
        self.assertIn("act now", r.stdout.lower())

    def test_rejects_double_space_bypass(self):
        self.assert_spam_rejected(["Click  here to see our designs.",
                                   "Sharing a quick production idea for canvas.",
                                   "Sharing a quick production idea for twill.",
                                   "Sharing a quick production idea for knit."], "click here")

    def test_rejects_html_split_bypass(self):
        self.assert_spam_rejected(["<b>Click</b> here to see our designs.",
                                   "Sharing a quick production idea for canvas.",
                                   "Sharing a quick production idea for twill.",
                                   "Sharing a quick production idea for knit."], "click here")

    def test_rejects_hyphen_bypass(self):
        self.assert_spam_rejected(["Click-here to see our designs.",
                                   "Sharing a quick production idea for canvas.",
                                   "Sharing a quick production idea for twill.",
                                   "Sharing a quick production idea for knit."], "click here")

    def test_rejects_zero_width_bypass(self):
        self.assert_spam_rejected(["Click" + chr(0x200b) + " here to see our designs.",
                                   "Sharing a quick production idea for canvas.",
                                   "Sharing a quick production idea for twill.",
                                   "Sharing a quick production idea for knit."], "click here")

    def test_rejects_no_space_bypass(self):
        self.assert_spam_rejected(["Clickhere to see our designs.",
                                   "Sharing a quick production idea for canvas.",
                                   "Sharing a quick production idea for twill.",
                                   "Sharing a quick production idea for knit."], "click here")

    def test_contract_now_not_false_positive(self):
        r = self.run_plan(self.plan_with(["The contract now includes packaging.",
                                         "Sharing a quick production idea for canvas.",
                                         "Sharing a quick production idea for twill.",
                                         "Sharing a quick production idea for knit."]))
        self.assertNotIn("垃圾邮件触发词", r.stdout, "contract now 被 act now 误伤")

    def test_rejects_html_entity_bypass(self):
        self.assert_spam_rejected(["cl&#105;ck here to see our designs.",
                                   "Sharing a quick production idea for canvas.",
                                   "Sharing a quick production idea for twill.",
                                   "Sharing a quick production idea for knit."], "click here")

    def test_rejects_fullwidth_bypass(self):
        self.assert_spam_rejected(["ｃｌｉｃｋ ｈｅｒｅ to see our designs.",
                                   "Sharing a quick production idea for canvas.",
                                   "Sharing a quick production idea for twill.",
                                   "Sharing a quick production idea for knit."], "click here")

    def run_plan_named(self, plan, name):
        p = self.tmp / "plan.json"
        p.write_text(json.dumps(plan, ensure_ascii=False), encoding="utf-8")
        return subprocess.run(
            [sys.executable, str(GEN), "--plan", str(p), "--token", "x", "--org", "1",
             "--product", "pet-pack", "--name", name, "--prefix", "英-pet-",
             "--project", "tony/pet-pack", "--profile", str(self.profile),
             "--record", str(self.tmp / "operation-record.md"),
             "--out", str(self.tmp / "tmap.json")],
            capture_output=True, text=True, cwd=ROOT, timeout=120)

    def test_rejects_signature_spam(self):
        plan = self.plan_with(["Sharing a quick production idea for linen.",
                               "Sharing a quick production idea for canvas.",
                               "Sharing a quick production idea for twill.",
                               "Sharing a quick production idea for knit."])
        r = self.run_plan_named(plan, "Congratulations")
        self.assertEqual(2, r.returncode, r.stdout + r.stderr)
        self.assertIn("[签名]", r.stdout)
        self.assertIn("垃圾邮件触发词", r.stdout)

    def test_rejects_entity_space_bypass(self):
        self.assert_spam_rejected(["click&#32;here to see our designs.",
                                   "Sharing a quick production idea for canvas.",
                                   "Sharing a quick production idea for twill.",
                                   "Sharing a quick production idea for knit."], "click here")

    def test_rejects_word_joiner_bypass(self):
        self.assert_spam_rejected(["click" + chr(0x2060) + "here to see our designs.",
                                   "Sharing a quick production idea for canvas.",
                                   "Sharing a quick production idea for twill.",
                                   "Sharing a quick production idea for knit."], "click here")

    def test_rejects_unicode_hyphen(self):
        self.assert_spam_rejected(["A risk" + chr(0x2011) + "free sample for you.",
                                   "Sharing a quick production idea for canvas.",
                                   "Sharing a quick production idea for twill.",
                                   "Sharing a quick production idea for knit."], "risk free")
    def test_clean_text_has_no_spam_issue(self):
        r = self.run_plan(self.plan_with(["Sharing a quick production idea for linen.",
                                         "Sharing a quick production idea for canvas.",
                                         "Sharing a quick production idea for twill.",
                                         "Sharing a quick production idea for knit."]))
        self.assertNotIn("垃圾邮件触发词", r.stdout, "正常文本被垃圾词硬门误伤")
