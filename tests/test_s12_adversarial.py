#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""S12 激活凭证链 · 对抗模拟测试（2026-09-17 用户要求"模拟对抗"后固化）。

本文件把一次真实攻击演练固化为可重复测试：在隔离副本里真跑工具、真发凭证，
逐一验证"想绕过闸门"的攻击都被拦住，并验证"正常确认"仍能签发（避免修成死锁）。

★本轮攻击命中并修复的真缺陷（攻击3）：疑问句被当成授权。
  用户说「真的要激活吗」（问句/犹豫）→ 旧实现真的签发了 S12 凭证。
  根因：疑问判定用**短语黑名单**（是否/能否/可否/要不要/是不是/确认吗/可以吗），
  穷举不全，漏掉句尾疑问助词（吗/呢/么）。现改为规则判定，见 `tools/approval.py`。

攻击清单（每条都真跑工具、检查账本）：
  A1 伪造原话（AI 自己编一句"确认激活"）        → 结构上无法防（原话由 AI 传递）；
                                                  但必须"缺原话即拒"、且凭证绑参数哈希
  A2 疑问句「真的要激活吗」                     → 必须拒绝（★本轮修复）
  A3 否定句「不要激活」「先别激活」「确认不激活」 → 必须拒绝
  A4 合规文件超 72 小时                        → 必须拒绝
  A5 合规文件含 simulation/mock 标记            → 必须拒绝
  A6 evidence_mode 改成 simulation             → 必须拒绝
  A7 档案 status=draft                        → 必须拒绝
  A8 record 停在 S10（未收口 S11）              → 必须拒绝
  A9 序列 id 与 record 不一致                   → 必须拒绝
  A10 档案不在标准路径                          → 必须拒绝
  A11 用 approval.py grant 铸造 S12            → 必须拒绝（唯一出口限制）
  A12 不带凭证直接激活                          → 必须拒绝
  A13 拿 A 项目凭证去激活 B 项目                 → 必须拒绝（哈希绑定）
"""
import json
import hashlib
import shutil
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SEQ = "a" * 24
ORG = "1234567"
PROJECT = "tony/pet-pack"

# 最小合法产品档案（status=declined = 用户明确跳过资料，仍可继续；过 profile_gate）
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


def _iso(dt=None):
    return (dt or datetime.now(timezone.utc)).isoformat()


class S12AdversarialTest(unittest.TestCase):
    """在隔离副本里真跑工具，逐一尝试绕过激活闸门。"""

    maxDiff = None

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="s12atk-"))
        self.repo = self.tmp / "repo"
        shutil.copytree(ROOT, self.repo, ignore=shutil.ignore_patterns(
            ".git", ".local", "runs", "__pycache__"))
        self.project_dir = self.repo / "runs" / "tony" / "pet-pack"
        self.project_dir.mkdir(parents=True)
        self.profile = self.project_dir / "product-profile.md"
        # ★自带合法夹具（不依赖运行档案：知识仓没有 runs/Tony/，公开仓才有）
        self.profile.write_text(PROFILE_FIXTURE, encoding="utf-8")
        self.record = self.project_dir / "operation-record.md"
        self.write_record("S11")
        self.compliance = self.project_dir / "compliance-check.json"
        self.write_compliance()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    # ---------- 夹具 ----------
    def write_record(self, status):
        self.record.write_text(
            "---\n"
            f"operator_key: tony\nproduct_key: pet-pack\nproject: {PROJECT}\n"
            f"status: {status}\nsequence_id: {SEQ}\n---\n", encoding="utf-8")

    def write_compliance(self, mode="live", age_hours=0, detail="已逐项核验通过（详细说明）"):
        ts = _iso(datetime.now(timezone.utc) - timedelta(hours=age_hours))
        doc = {"evidence_mode": mode, "project": PROJECT, "seq": SEQ,
               "checked_at": ts,
               "profile_sha256": hashlib.sha256(self.profile.read_bytes()).hexdigest()}
        for key in ("market", "list_source", "sender_identity", "unsubscribe", "suppression"):
            doc[key] = {"status": "pass",
                        "evidence": {"source": "平台后台 + 人工逐项核对确认",
                                     "detail": detail, "checked_at": ts}}
        self.compliance.write_text(json.dumps(doc), encoding="utf-8")

    def rows(self):
        path = self.repo / ".local" / "approvals.tsv"
        if not path.exists():
            return []
        lines = path.read_text(encoding="utf-8").splitlines()
        header = lines[0].split("\t")
        return [dict(zip(header, line.split("\t"))) for line in lines[1:]]

    def s12_rows(self):
        return [r for r in self.rows() if r.get("state", "").startswith("S12")]

    def issue(self, quote="确认激活 皮筏艇找客户", profile=None, seq=None, compliance=None):
        """走签发路径（默认用合法夹具）。"""
        return subprocess.run(
            [sys.executable, str(self.repo / "tools" / "flow_orchestrator.py"),
             "--resume-s12", "--org", ORG,
             "--profile", str(profile or self.profile),
             "--seq", seq or SEQ,
             "--compliance-file", str(compliance or self.compliance),
             "--confirm", quote],
            capture_output=True, text=True, cwd=self.repo, timeout=90)

    def activate(self, approval="", profile=None, project=None, record=None, compliance=None):
        return subprocess.run(
            [sys.executable, str(self.repo / "tools" / "activate_sequence.py"),
             "--token", "fake", "--org", ORG, "--seq", SEQ,
             "--project", project or PROJECT,
             "--profile", str(profile or self.profile),
             "--compliance-file", str(compliance or self.compliance),
             "--record", str(record or self.record),
             "--confirm", "确认激活 皮筏艇",
             "--approval", approval],
            capture_output=True, text=True, cwd=self.repo, timeout=90)

    # ---------- 基线：正常路径必须仍然可用 ----------
    def test_baseline_legit_confirmation_issues_and_keeps_s11(self):
        r = self.issue()
        self.assertEqual(0, r.returncode, r.stdout + r.stderr)
        rows = self.s12_rows()
        self.assertEqual(1, len(rows), "正常确认应签发一条 S12 凭证")
        self.assertEqual("confirmed", rows[0]["status"])
        self.assertIn("status: S11", self.record.read_text(encoding="utf-8"),
                      "签发凭证不得推进状态（激活由 activate 工具做）")

    def test_baseline_missing_quote_is_rejected(self):
        r = subprocess.run(
            [sys.executable, str(self.repo / "tools" / "flow_orchestrator.py"),
             "--resume-s12", "--org", ORG, "--profile", str(self.profile),
             "--seq", SEQ, "--compliance-file", str(self.compliance)],
            input="", capture_output=True, text=True, cwd=self.repo, timeout=90)
        self.assertEqual(2, r.returncode)
        self.assertEqual([], self.s12_rows(), "无原话不得签发")

    # ---------- A2/A3：原话语义 ----------
    def test_a2_interrogative_is_rejected(self):
        for quote in ("真的要激活吗", "要激活吗", "这样激活呢", "可以激活么", "为什么激活",
                      "激活行不行", "是不是要激活"):
            with self.subTest(quote=quote):
                for r in self.s12_rows():
                    pass
                (self.repo / ".local" / "approvals.tsv").unlink(missing_ok=True)
                r = self.issue(quote=quote)
                self.assertEqual([], self.s12_rows(),
                                 f"疑问句「{quote}」被当成授权（会误签发凭证）")

    def test_a3_negative_is_rejected(self):
        for quote in ("不要激活", "先别激活", "确认不激活", "取消激活", "暂停"):
            with self.subTest(quote=quote):
                (self.repo / ".local" / "approvals.tsv").unlink(missing_ok=True)
                self.issue(quote=quote)
                self.assertEqual([], self.s12_rows(), f"否定句「{quote}」被当成授权")

    # ---------- A4~A6：合规证据 ----------
    def test_a4_stale_compliance_is_rejected(self):
        self.write_compliance(age_hours=100)
        self.issue()
        self.assertEqual([], self.s12_rows(), "超过 72 小时的合规证据不得签发")

    def test_a5_simulation_marker_is_rejected(self):
        self.write_compliance(detail="这是 simulation 环境的 mock 结果")
        self.issue()
        self.assertEqual([], self.s12_rows(), "含 simulation/mock 标记不得签发")

    def test_a6_non_live_mode_is_rejected(self):
        self.write_compliance(mode="simulation")
        self.issue()
        self.assertEqual([], self.s12_rows(), "evidence_mode 非 live 不得签发")

    # ---------- A7~A10：状态/绑定 ----------
    def test_a7_draft_profile_is_rejected(self):
        text = self.profile.read_text(encoding="utf-8").replace("status: declined", "status: draft")
        self.profile.write_text(text, encoding="utf-8")
        self.issue()
        self.assertEqual([], self.s12_rows(), "draft 档案不得签发")

    def test_a8_record_not_s11_is_rejected(self):
        for status in ("S10", "S12", "ERROR_BLOCKED"):
            with self.subTest(status=status):
                (self.repo / ".local" / "approvals.tsv").unlink(missing_ok=True)
                self.write_record(status)
                self.issue()
                self.assertEqual([], self.s12_rows(), f"record={status} 不得签发")
        self.write_record("S11")

    def test_a9_sequence_mismatch_is_rejected(self):
        self.issue(seq="b" * 24)
        self.assertEqual([], self.s12_rows(), "序列 id 与 record 不一致不得签发")

    def test_a10_non_standard_profile_path_is_rejected(self):
        other = self.repo / "elsewhere" / "product-profile.md"
        other.parent.mkdir(parents=True, exist_ok=True)
        other.write_text(self.profile.read_text(encoding="utf-8"), encoding="utf-8")
        self.issue(profile=other)
        self.assertEqual([], self.s12_rows(), "非标准路径档案不得签发")

    # ---------- A11~A13：凭证链 ----------
    def test_a11_grant_cannot_mint_s12(self):
        r = subprocess.run(
            [sys.executable, str(self.repo / "tools" / "approval.py"), "grant",
             "--project", PROJECT, "--state", "S12_激活", "--quote", "确认激活",
             "--params", json.dumps({"project": PROJECT, "seq": SEQ})],
            capture_output=True, text=True, cwd=self.repo, timeout=60)
        self.assertEqual(2, r.returncode, r.stdout + r.stderr)
        self.assertEqual([], self.s12_rows(), "grant 不得铸造 S12 凭证")

    def test_a12_activation_requires_approval(self):
        r = self.activate(approval="")
        self.assertNotEqual(0, r.returncode)
        self.assertIn("审批凭证", r.stdout + r.stderr, "无凭证不得激活")

    def test_a13_approval_is_bound_to_project(self):
        self.issue()
        rows = self.s12_rows()
        self.assertEqual(1, len(rows), "前置条件：先拿到 A 项目的合法凭证")
        ap = rows[0]["id"]
        # 造 B 项目
        other_dir = self.repo / "runs" / "tony" / "other"
        other_dir.mkdir(parents=True)
        other_profile = other_dir / "product-profile.md"
        other_profile.write_text(
            self.profile.read_text(encoding="utf-8").replace("product_key: pet-pack", "product_key: other"),
            encoding="utf-8")
        other_record = other_dir / "operation-record.md"
        other_record.write_text(
            f"---\noperator_key: tony\nproduct_key: other\nproject: tony/other\n"
            f"status: S11\nsequence_id: {SEQ}\n---\n", encoding="utf-8")
        other_compliance = other_dir / "compliance-check.json"
        other_compliance.write_text(self.compliance.read_text(encoding="utf-8"), encoding="utf-8")
        r = self.activate(approval=ap, profile=other_profile, project="tony/other",
                          record=other_record, compliance=other_compliance)
        self.assertNotEqual(0, r.returncode, "跨项目复用凭证必须被拒")
        self.assertRegex(r.stdout + r.stderr, r"不匹配", "应报绑定不匹配")


if __name__ == "__main__":
    unittest.main()
