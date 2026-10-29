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
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
NOW_ISO = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
from pathlib import Path
import os as _os

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


def _install_curl(bin_dir, cwd_dir, body):
    """POSIX 用 sh 壳；Windows 编译 curl.exe 到工具 cwd（CreateProcess 先查当前目录）。"""
    bin_dir = Path(bin_dir)
    cwd_dir = Path(cwd_dir)
    fake_py = cwd_dir / "fake_curl.py"
    fake_py.write_text(body, encoding="utf-8")
    if os.name != "nt":
        curl = bin_dir / "curl"
        curl.write_text('#!/bin/sh\nexec "%s" "%s" "$@"\n' % (sys.executable, fake_py), encoding="utf-8")
        curl.chmod(0o755)
        return
    try:
        from test_cross_platform import _WIN_CURL_SHIM_CS
    except ImportError:
        from tests.test_cross_platform import _WIN_CURL_SHIM_CS
    win = Path(os.environ.get("WINDIR", r"C:\Windows"))
    csc = next((q for q in (
        win / "Microsoft.NET" / "Framework64" / "v4.0.30319" / "csc.exe",
        win / "Microsoft.NET" / "Framework" / "v4.0.30319" / "csc.exe",
    ) if q.exists()), None)
    if csc is None:
        raise unittest.SkipTest("Windows 需要 .NET Framework csc.exe 编译 curl 影子")
    src = cwd_dir / "curl_shim.cs"
    src.write_text(_WIN_CURL_SHIM_CS, encoding="utf-8")
    exe = cwd_dir / "curl.exe"
    subprocess.run([str(csc), "/nologo", "/out:" + str(exe), str(src)],
                   capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120, check=True)




try:
    from gate_env import gate_test_env
except ImportError:
    from tests.gate_env import gate_test_env

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
            f"status: {status}\nsequence_id: {SEQ}\n"
            + ('s11_finalized_at: "' + NOW_ISO + '"\ns11_manifest_sha256: "' + 'a' * 64 + '"\n' if status == "S11" else "")
            + "---\n", encoding="utf-8")

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
        lines = path.read_text(encoding="utf-8-sig").splitlines()
        header = lines[0].split("\t")
        return [dict(zip(header, line.split("\t"))) for line in lines[1:]]

    def s12_rows(self):
        return [r for r in self.rows() if r.get("state", "").startswith("S12")]

    def issue(self, quote="确认激活", profile=None, seq=None, compliance=None):
        """走签发路径（默认用合法夹具）。"""
        return subprocess.run(
            [sys.executable, str(self.repo / "tools" / "flow_orchestrator.py"),
             "--resume-s12", "--org", ORG,
             "--profile", str(profile or self.profile),
             "--seq", seq or SEQ,
             "--compliance-file", str(compliance or self.compliance),
             "--confirm", quote],
            capture_output=True, text=True, cwd=self.repo, timeout=90, encoding="utf-8", errors="replace")

    def activate(self, approval="", profile=None, project=None, record=None, compliance=None):
        return subprocess.run(
            [sys.executable, str(self.repo / "tools" / "activate_sequence.py"),
             "--token", "fake", "--org", ORG, "--seq", SEQ,
             "--project", project or PROJECT,
             "--profile", str(profile or self.profile),
             "--compliance-file", str(compliance or self.compliance),
             "--record", str(record or self.record),
             "--confirm", "确认激活",
             "--approval", approval],
            capture_output=True, text=True, cwd=self.repo, timeout=90, encoding="utf-8", errors="replace")

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
            input="", capture_output=True, text=True, cwd=self.repo, timeout=90, encoding="utf-8", errors="replace")
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
            capture_output=True, text=True, cwd=self.repo, timeout=60, encoding="utf-8", errors="replace")
        self.assertEqual(2, r.returncode, r.stdout + r.stderr)
        self.assertEqual([], self.s12_rows(), "grant 不得铸造 S12 凭证")

    def test_a12_activation_requires_approval(self):
        r = self.activate(approval="")
        self.assertNotEqual(0, r.returncode)
        self.assertIn("审批凭证", r.stdout + r.stderr, "无凭证不得激活")

    # ---------- ★P0-B 激活口令：必须含「确认激活」四个字 ----------
    def activate_offline(self, confirm, approval=""):
        """不联网跑 activate_sequence：假 curl 只记录调用（用于验证本地口令闸门且零网络）。"""
        bin_dir = self.tmp / "bin-offline"
        bin_dir.mkdir(exist_ok=True)
        log = self.tmp / "activate-curl.log"
        _install_curl(bin_dir, self.repo,
            "import os, sys\n"
            "with open(os.environ['ACT_LOG'], 'a', encoding='utf-8') as f:\n"
            "    f.write(' '.join(sys.argv[1:]) + '\\n')\n"
            "print('{\"success\": true}')\n")
        env = os.environ.copy()
        env["PATH"] = str(bin_dir) + os.pathsep + env.get("PATH", "")
        env["ACT_LOG"] = str(log)
        env.update(gate_test_env())
        env["LFX_FAKE_PYTHON"] = sys.executable
        r = subprocess.run(
            [sys.executable, str(self.repo / "tools" / "activate_sequence.py"),
             "--token", "fake", "--org", ORG, "--seq", SEQ,
             "--project", PROJECT, "--profile", str(self.profile),
             "--compliance-file", str(self.compliance),
             "--record", str(self.record),
             "--confirm", confirm, "--approval", approval],
            capture_output=True, text=True, cwd=self.repo, env=env, timeout=90, encoding="utf-8", errors="replace")
        calls = log.read_text(encoding="utf-8").splitlines() if log.exists() else []
        return r, calls

    def test_p0b_only_activation_word_is_rejected_without_network(self):
        """★旧缺陷：activate_sequence 只要求原话含「激活」→「激活 皮筏艇」即可放行。"""
        r, calls = self.activate_offline("激活 皮筏艇")
        self.assertEqual(2, r.returncode, r.stdout + r.stderr)
        self.assertIn("确认激活", r.stdout + r.stderr, "拒绝原因须指出必须含「确认激活」")
        self.assertEqual([], calls, "口令闸门必须在任何联网之前拒绝")

    def test_p0b_confirm_activation_passes_local_gates_without_network(self):
        """「确认激活 …」须通过本地口令闸门（随后因缺审批凭证 exit 1，证明不是死锁）。"""
        r, calls = self.activate_offline("确认激活")
        self.assertEqual(1, r.returncode, r.stdout + r.stderr)
        self.assertNotIn("确认原话校验未过", r.stdout + r.stderr,
                         "「确认激活」不应被口令闸门拒绝")
        self.assertIn("审批凭证", r.stdout + r.stderr,
                      "应停在审批闸门（无 --approval），而不是口令闸门")
        self.assertEqual([], calls, "本地闸门未过前不得联网")

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
            "---\noperator_key: tony\nproduct_key: other\nproject: tony/other\n"
            f"status: S11\nsequence_id: {SEQ}\n"
            's11_finalized_at: "' + NOW_ISO + '"\n'
            f's11_manifest_sha256: "{"a" * 64}"\n---\n',
            encoding="utf-8")
        other_compliance = other_dir / "compliance-check.json"
        other_compliance.write_text(self.compliance.read_text(encoding="utf-8"), encoding="utf-8")
        r = self.activate(approval=ap, profile=other_profile, project="tony/other",
                          record=other_record, compliance=other_compliance)
        self.assertNotEqual(0, r.returncode, "跨项目复用凭证必须被拒")
        self.assertRegex(r.stdout + r.stderr, r"不匹配", "应报绑定不匹配")


if __name__ == "__main__":
    unittest.main()


FAKE_PLATFORM = r'''#!/usr/bin/env python3
import json, os, sys
from urllib.parse import urlparse
args = sys.argv[1:]
url = next((a for a in args if a.startswith("http")), "")
path = urlparse(url).path
{log_code}
marker = {marker!r}
SEQ = {seq!r}
STATUS = {status!r}
TPL = {tpl}
if path.endswith("/sequences/sequence-list"):
    active = STATUS == "active" or (marker and os.path.exists(marker))
    out = {{"success": True, "data": {{"list": [{{"id": SEQ, "status": "active" if active else "inactive"}}]}}}}
elif path.endswith("/sequences/sequence-details"):
    out = {{"success": True, "data": {{"rules": {{"max_emails_per_day": 30000, "domain_emails_per_day": 5,
             "notSentTags": ["000000000000000000000043", "000000000000000000000044"]}}}}}}
elif path.endswith("/benefits/refine-data"):
    out = {{"success": True, "data": {{"isOrg": True, "vip": 2, "dailyLimit": 500,
             "monthlyLimit": 10000, "dailyUsed": 1, "monthlyUsed": 2}}}}
elif path.endswith("/contacts/tags-list"):
    out = {{"success": True, "data": {{"list": [{{"id": "000000000000000000000043", "name": "询盘"}},
             {{"id": "000000000000000000000044", "name": "不发"}}]}}}}
elif path.endswith("/sequences/step-list"):
    waits = [("minute", 30), ("day", 5), ("day", 15)] + [("day", 30)] * 9
    out = {{"success": True, "data": [{{"step": i + 1, "template_ids": [TPL[i]],
             "wait_mode": waits[i][0], "wait_time": waits[i][1]}} for i in range(12)]}}
elif path.endswith("/mailbox/templates-list"):
    out = {{"success": True, "data": {{"list": [{{"_id": t}} for t in TPL]}}}}
elif path.endswith("/sequences/sequence-active"):
    if marker:
        open(marker, "w").write("1")
    out = {{"success": True, "data": {{}}}}
else:
    out = {{"success": True, "data": {{}}}}
print(json.dumps(out))
'''


def _fake_platform_script(status, log_code=""):
    tpl = "[" + ", ".join('"%024x"' % (i + 0x300) for i in range(12)) + "]"
    return FAKE_PLATFORM.format(status=status, seq=SEQ, marker=None, log_code=log_code, tpl=tpl)


class ManualActivationSyncTest(unittest.TestCase):
    """★2026-09-17 用户要求：给用户第二条路——自己去网页手动激活，AI 只做核对与同步。

    背景：此前只有"聊天里说一句让 AI 激活"一条路。用户提出"另外可以引导用户去网页上
    查看下再手动激活"——想亲眼看一遍数据的人应该能自己开开关（透明、可信），
    AI 不该把这一步垄断。

    契约（`activate_sequence.py --sync-manual`）：
      · 只读回读平台确认真的 active + 写本地 record；**不发起任何平台写操作、不需要审批凭证**
        （审批凭证用于授权"AI 代为写平台"；这条路径没有平台写操作）
      · 仍要求原话含"激活"（登记用户意志）、seq 与 record 一致（防串台）
      · 回读非 active / 读不到 → 一律拒绝且保持 S11（不猜、不替用户激活）
    """

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="s12sync-"))
        self.repo = self.tmp / "repo"
        shutil.copytree(ROOT, self.repo, ignore=shutil.ignore_patterns(
            ".git", ".local", "runs", "__pycache__"))
        self.project_dir = self.repo / "runs" / "tony" / "pet-pack"
        self.project_dir.mkdir(parents=True)
        (self.project_dir / "product-profile.md").write_text(PROFILE_FIXTURE, encoding="utf-8")
        self.record = self.project_dir / "operation-record.md"
        self.write_record("S11")
        self.bin = self.tmp / "bin"
        self.bin.mkdir()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def write_record(self, status):
        self.record.write_text(
            f"---\noperator_key: tony\nproduct_key: pet-pack\nproject: {PROJECT}\n"
            f"status: {status}\nsequence_id: {SEQ}\n"
            + ('s11_finalized_at: "' + NOW_ISO + '"\ns11_manifest_sha256: "' + 'a' * 64 + '"\n' if status == "S11" else "")
            + "---\n", encoding="utf-8")

    def status(self):
        for line in self.record.read_text(encoding="utf-8").splitlines():
            if line.startswith("status:"):
                return line.split(":", 1)[1].strip()
        return ""

    def fake_platform(self, seq_status=None, log=None):
        """模拟平台：给定序列状态（None=接口返回空）。"""
        status = "none" if seq_status is None else seq_status
        log_code = ""
        if log is not None:
            log_code = 'with open(' + repr(str(log)) + ', "a") as fh:\n    fh.write(path + "\\n")'
        _install_curl(self.bin, self.repo, _fake_platform_script(status, log_code))

    def sync(self, confirm="我已在网页激活 皮筏艇找客户", seq=None, record=None, extra=()):
        env = os.environ.copy()
        env.update(gate_test_env())
        env["PATH"] = str(self.bin) + os.pathsep + env.get("PATH", "")
        env["LFX_FAKE_PYTHON"] = sys.executable
        return subprocess.run(
            [sys.executable, str(self.repo / "tools" / "activate_sequence.py"),
             "--token", "fake", "--org", ORG, "--seq", seq or SEQ, "--sync-manual",
             "--record", str(record or self.record), *( ("--confirm", confirm) if confirm is not None else () ),
             *extra],
            capture_output=True, text=True, cwd=self.repo, env=env, timeout=90, encoding="utf-8", errors="replace")

    # ---- 正向：用户在网页开好后同步 ----
    def test_sync_after_manual_activation_advances_local(self):
        self.fake_platform("active")
        r = self.sync()
        self.assertEqual(0, r.returncode, r.stdout + r.stderr)
        self.assertEqual("S12", self.status(), "平台已 active 时本地应同步为 S12")
        self.assertIn("未发起任何平台写操作", r.stdout, "应说明本路径没有平台写操作")

    def test_sync_is_idempotent_when_already_s12(self):
        self.write_record("S12")
        self.fake_platform("active")
        r = self.sync()
        self.assertEqual(0, r.returncode, r.stdout + r.stderr)
        self.assertIn("无需重复同步", r.stdout)

    # ---- 反向：一律不猜、不改本地 ----
    def test_sync_rejects_when_platform_still_inactive(self):
        self.fake_platform("inactive")
        r = self.sync()
        self.assertNotEqual(0, r.returncode)
        self.assertEqual("S11", self.status(), "平台未 active 时本地必须保持 S11")
        self.assertRegex(r.stdout + r.stderr, r"没生效|未开启|开在别的工作空间",
                         "应提示用户回去确认开关是否真的开了")

    def test_sync_rejects_when_platform_unreadable(self):
        self.fake_platform(None)
        r = self.sync()
        self.assertNotEqual(0, r.returncode)
        self.assertEqual("S11", self.status(), "读不到状态时不得改本地")

    def test_sync_requires_activation_word(self):
        self.fake_platform("active")
        r = self.sync(confirm="我开好了")
        self.assertNotEqual(0, r.returncode)
        self.assertEqual("S11", self.status(), "原话不含'激活'不得同步")

    def test_sync_rejects_interrogative(self):
        self.fake_platform("active")
        r = self.sync(confirm="已经激活了吗")
        self.assertNotEqual(0, r.returncode)
        self.assertEqual("S11", self.status(), "疑问句不得当授权")

    def test_sync_requires_confirm(self):
        self.fake_platform("active")
        r = self.sync(confirm=None)
        self.assertNotEqual(0, r.returncode)
        self.assertEqual("S11", self.status())

    def test_sync_rejects_sequence_mismatch(self):
        self.fake_platform("active")
        r = self.sync(seq="b" * 24)
        self.assertNotEqual(0, r.returncode)
        self.assertEqual("S11", self.status(), "seq 与 record 不一致时不得同步（防串台）")

    def test_sync_requires_record(self):
        self.fake_platform("active")
        env = os.environ.copy()
        env.update(gate_test_env())
        env["PATH"] = str(self.bin) + os.pathsep + env.get("PATH", "")
        r = subprocess.run(
            [sys.executable, str(self.repo / "tools" / "activate_sequence.py"),
             "--token", "fake", "--org", ORG, "--seq", SEQ, "--sync-manual",
             "--confirm", "我已在网页激活"],
            capture_output=True, text=True, cwd=self.repo, env=env, timeout=90, encoding="utf-8", errors="replace")
        self.assertNotEqual(0, r.returncode)

    def test_sync_makes_no_write_call_to_platform(self):
        """★关键：这条路径不得对平台发起任何写请求（只回读）。"""
        self.fake_platform("active")
        log = self.tmp / "curl.log"
        self.fake_platform("active", log=log)
        r = self.sync()
        self.assertEqual(0, r.returncode, r.stdout + r.stderr)
        calls = log.read_text(encoding="utf-8") if log.exists() else ""
        self.assertIn("sequence-list", calls, "应当只读查询序列状态")
        self.assertNotIn("sequence-active", calls,
                         "★该路径不得调用激活接口（开关是用户自己在网页开的）")
