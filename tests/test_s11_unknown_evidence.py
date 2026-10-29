#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""S11 终检“全未知/空壳面板”永久回归（B1-B4）。

历史反例：panel 只写六个关键词、取值全“未知”，finalize_run 仍 exit 0 并写
S11/next=S12 收口字段（.local/history-recheck-20261028/test-logs/edge-probe.log）。
本文件先固化失败：面板必须是六项“字段：取值”，取值不得为空/未知/否定/非实时；
合法完整面板（含“未知数：0/无未知项”正向汇总）必须继续通过。
"""
import datetime
import hashlib
import importlib.util
import json
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROJECT = "operator/product"
ORG = "org-for-s11-unknown-tests"
SEQ = "0123456789abcdef01234567"

LEGAL_PANEL = (
    "核实面板（平台回读，2026-10-28）\n"
    "- 标签：询盘、不发两个停止标签已挂好\n"
    "- 客群：宠物食品包装采购商，本批 25 人\n"
    "- 保存：25 人已加入「英语-宠物食品包装-12轮」\n"
    "- 模板：48 个模板已挂到 12 轮\n"
    "- 配额：全账号 30000/天、单公司 5/天\n"
    "- 审查：12 步顺序与时区 America/New_York 已核对\n"
    "未知数：0\n"
    "无未知项\n"
)
HISTORICAL_UNKNOWN = "标签未知 客群未知 保存未知 模板未知 配额未知 审查未知\n"
SIX_WORD_SHELL = "标签 客群 保存 模板 配额 审查 已核对\n"

SPEC = importlib.util.spec_from_file_location("_s11_closure", ROOT / "tools" / "s11_closure.py")


def load_closure():
    mod = importlib.util.module_from_spec(SPEC)
    SPEC.loader.exec_module(mod)
    return mod


class S11UnknownEvidenceTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.project_dir = Path(self.tmp.name) / "runs" / "operator" / "product"
        self.project_dir.mkdir(parents=True)
        self.profile = self.project_dir / "product-profile.md"
        fields = "\n".join(
            f"## {'①②③④⑤⑥⑦⑧'[i]} field\n- 内容：待补\n- source: none\n- confidence: low"
            for i in range(8)
        )
        self.profile.write_text(
            "---\nprofile_version: 1\nstatus: declined\noperator_key: operator\n"
            "product_key: product\ncreated_at: 2026-09-07\nupdated_at: 2026-09-07\n"
            "sources_status: declined\nsources_present: no\n---\n\n" + fields + "\n",
            encoding="utf-8",
        )
        self.record = self.project_dir / "operation-record.md"
        self.manifest = self.project_dir / "verification-manifest.json"
        self.write_record("S10")

    def tearDown(self):
        self.tmp.cleanup()

    def write_record(self, status):
        self.record.write_text(
            "---\n"
            f"status: {status}\nnext_state: pending\noperator_key: operator\n"
            f"product_key: product\nseed: seed.example\nsequence_id: {SEQ}\n"
            "---\nrecord body\n",
            encoding="utf-8",
        )

    def write_evidence(self, name, content):
        path = self.project_dir / name
        path.write_text(content, encoding="utf-8")
        return path

    @staticmethod
    def evidence_item(path):
        return {
            "status": "pass",
            "path": path.name,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        }

    def write_verification_manifest(self, panel_text=LEGAL_PANEL, generated_at=None, mode="live"):
        sequence = self.write_evidence(
            "verify-seq.txt", f"序列 {SEQ}\n步骤数: 12\n状态=inactive\n全部12步\n"
        )
        exclude = self.write_evidence("verify-exclude.txt", "含4区=0\n排除生效\n")
        diff = self.write_evidence(
            "verify-diff.txt", "模板数: 48\n最大相似度 20%\n差异≥30%达标\n"
        )
        panel = self.write_evidence("verification-panel.md", panel_text)
        doc = {
            "project": PROJECT,
            "org_sha256": hashlib.sha256(ORG.encode()).hexdigest(),
            "seq": SEQ,
            "profile_sha256": hashlib.sha256(self.profile.read_bytes()).hexdigest(),
            "generated_at": generated_at or datetime.datetime.now().isoformat(timespec="seconds"),
            "evidence_mode": mode,
            "evidence": {
                "sequence": self.evidence_item(sequence),
                "exclude": self.evidence_item(exclude),
                "diff": self.evidence_item(diff),
                "panel": self.evidence_item(panel),
            },
        }
        self.manifest.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
        return doc

    def run_finalize(self):
        return subprocess.run(
            [
                sys.executable, str(ROOT / "tools" / "finalize_run.py"),
                "--record", str(self.record), "--profile", str(self.profile),
                "--project", PROJECT, "--org", ORG, "--seq", SEQ,
                "--manifest", str(self.manifest),
            ],
            text=True, capture_output=True, timeout=20, cwd=str(ROOT),
        )

    def record_meta(self):
        text = self.record.read_text(encoding="utf-8")
        head = text.split("---", 2)[1]
        meta = {}
        for line in head.splitlines():
            if ":" in line:
                key, value = line.split(":", 1)
                meta[key.strip()] = value.strip().strip('"')
        return meta

    def assert_rejected_without_mutation(self, result, label):
        self.assertNotEqual(0, result.returncode, f"{label}: {result.stdout}{result.stderr}")
        self.assertNotIn("s11_finalized_at", self.record.read_text(encoding="utf-8"), label)
        self.assertIn("status: S10", self.record.read_text(encoding="utf-8"), label)
        self.assertTrue(load_closure().check_s11_closure(self.record_meta()), label)

    # ---- B1：历史反例（真实 finalize CLI） ----
    def test_b1_historical_all_unknown_panel_rejected_and_record_stays_s10(self):
        self.write_verification_manifest(panel_text=HISTORICAL_UNKNOWN)
        before = (self.record.read_bytes(), self.record.stat().st_mtime_ns)
        result = self.run_finalize()
        self.assert_rejected_without_mutation(result, "历史全未知面板")
        self.assertEqual(before, (self.record.read_bytes(), self.record.stat().st_mtime_ns))
        self.assertIn("panel", result.stdout)
        self.assertIn("S11未收口", result.stdout)

    # ---- B2：缺项/空值/未知/否定/非实时 ----
    def test_b2_missing_empty_unknown_negative_nonlive_variants_rejected(self):
        cases = {
            "缺项": LEGAL_PANEL.replace("- 审查：12 步顺序与时区 America/New_York 已核对\n", ""),
            "空值": LEGAL_PANEL.replace(
                "- 客群：宠物食品包装采购商，本批 25 人", "- 客群："
            ),
            "暂无": LEGAL_PANEL.replace(
                "- 保存：25 人已加入「英语-宠物食品包装-12轮」", "- 保存：暂无"
            ),
            "未核": LEGAL_PANEL.replace(
                "- 模板：48 个模板已挂到 12 轮", "- 模板：未核对"
            ),
            "unknown": LEGAL_PANEL.replace(
                "- 配额：全账号 30000/天、单公司 5/天", "- 配额：unknown"
            ),
            "非实时": LEGAL_PANEL.replace(
                "- 审查：12 步顺序与时区 America/New_York 已核对", "- 审查：模拟环境值"
            ),
            "否定": LEGAL_PANEL.replace(
                "- 审查：12 步顺序与时区 America/New_York 已核对", "- 审查：未通过"
            ),
        }
        for label, text in cases.items():
            with self.subTest(label=label):
                self.write_record("S10")
                self.write_verification_manifest(panel_text=text)
                before = (self.record.read_bytes(), self.record.stat().st_mtime_ns)
                result = self.run_finalize()
                self.assert_rejected_without_mutation(result, label)
                self.assertEqual(before, (self.record.read_bytes(), self.record.stat().st_mtime_ns), label)

    # ---- B2：篡改/错项目/复用/过期 ----
    def test_b2_tamper_wrong_project_reuse_and_expiry_rejected(self):
        cases = {}
        self.write_verification_manifest()
        doc = json.loads(self.manifest.read_text(encoding="utf-8"))
        doc["evidence"]["diff"]["sha256"] = "0" * 64
        cases["篡改"] = doc

        doc2 = json.loads(self.manifest.read_text(encoding="utf-8"))
        doc2["project"] = "other/product"
        cases["错项目"] = doc2

        doc3 = json.loads(self.manifest.read_text(encoding="utf-8"))
        doc3["evidence"]["panel"] = dict(doc3["evidence"]["diff"])
        cases["复用"] = doc3

        expired = (datetime.datetime.now() - datetime.timedelta(hours=73)).isoformat(timespec="seconds")
        self.write_verification_manifest(generated_at=expired)
        cases["过期"] = json.loads(self.manifest.read_text(encoding="utf-8"))

        for label, manifest_doc in cases.items():
            with self.subTest(label=label):
                self.write_record("S10")
                self.manifest.write_text(json.dumps(manifest_doc, ensure_ascii=False), encoding="utf-8")
                before = (self.record.read_bytes(), self.record.stat().st_mtime_ns)
                result = self.run_finalize()
                self.assert_rejected_without_mutation(result, label)
                self.assertEqual(before, (self.record.read_bytes(), self.record.stat().st_mtime_ns), label)

    # ---- B2 正向：真正六项已核对材料必须通过（不误拒未知数0/无未知项） ----
    def test_b2_legal_six_field_panel_passes_and_binds_closure(self):
        self.write_verification_manifest()
        result = self.run_finalize()
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        text = self.record.read_text(encoding="utf-8")
        self.assertIn("status: S11", text)
        self.assertIn("next_state: S12", text)
        meta = self.record_meta()
        self.assertEqual([], load_closure().check_s11_closure(meta), meta)
        self.assertRegex(meta.get("s11_manifest_sha256", ""), r"^[0-9a-f]{64}$")

    # ---- B3：旧六关键词空壳/旧夹具前提必须被拒 ----
    def test_b3_old_six_keyword_shell_is_rejected(self):
        self.write_verification_manifest(panel_text=SIX_WORD_SHELL)
        result = self.run_finalize()
        self.assert_rejected_without_mutation(result, "六关键词空壳")

    # ---- B4：同一未知材料收口后仍不可再接受；失败不授予收口证明 ----
    def test_b4_same_unknown_material_rejected_twice_and_no_closure_granted(self):
        for attempt in (1, 2):
            self.write_verification_manifest(panel_text=HISTORICAL_UNKNOWN)
            result = self.run_finalize()
            self.assert_rejected_without_mutation(result, f"第{attempt}次")
        meta = self.record_meta()
        self.assertNotIn("s11_finalized_at", meta)
        issues = load_closure().check_s11_closure(meta)
        self.assertTrue(any("s11_finalized_at" in i for i in issues), issues)

    # ---- R2（B-R2-1）：正向汇总串只能出现在独立汇总行，不能充当字段取值 ----
    def test_r2_summary_token_as_every_field_value_rejected(self):
        variants = {
            "全无未知项": "无未知项",
            "全未知数0": "未知数：0",
            "全已核对无未知项": "已核对，无未知项",
        }
        for label, token in variants.items():
            with self.subTest(label=label):
                panel = "".join(
                    f"- {field}：{token}\n"
                    for field in ("标签", "客群", "保存", "模板", "配额", "审查")
                )
                self.write_record("S10")
                self.write_verification_manifest(panel_text=panel)
                before = (self.record.read_bytes(), self.record.stat().st_mtime_ns)
                result = self.run_finalize()
                self.assert_rejected_without_mutation(result, label)
                self.assertEqual(before, (self.record.read_bytes(), self.record.stat().st_mtime_ns), label)

    # ---- R2（B-R2-2）：纯 pass/yes/ok/已核对等通用肯定语不能充当字段实际值 ----
    def test_r2_generic_affirmation_as_every_field_value_rejected(self):
        for token in ("pass", "yes", "ok", "已核对", "确认", "通过"):
            with self.subTest(token=token):
                panel = "".join(
                    f"- {field}：{token}\n"
                    for field in ("标签", "客群", "保存", "模板", "配额", "审查")
                )
                self.write_record("S10")
                self.write_verification_manifest(panel_text=panel)
                result = self.run_finalize()
                self.assert_rejected_without_mutation(result, token)

    # ---- R2（自测补充）：只写“同上/见汇总”等引用、没有实际内容也不得充当字段值 ----
    def test_r2_reference_only_placeholder_as_every_field_value_rejected(self):
        for token in ("同上", "见汇总", "详见汇总行", "见上", "无未知项（见汇总）"):
            with self.subTest(token=token):
                panel = "".join(
                    f"- {field}：{token}\n"
                    for field in ("标签", "客群", "保存", "模板", "配额", "审查")
                )
                self.write_record("S10")
                self.write_verification_manifest(panel_text=panel)
                result = self.run_finalize()
                self.assert_rejected_without_mutation(result, token)

    # ---- R2（自测补充）：六项完全相同不能冒充六个核对项（如“无异常/正常/48”） ----
    def test_r2_identical_value_across_all_six_fields_rejected(self):
        for token in ("无异常", "正常", "48"):
            with self.subTest(token=token):
                panel = "".join(
                    f"- {field}：{token}\n"
                    for field in ("标签", "客群", "保存", "模板", "配额", "审查")
                )
                self.write_record("S10")
                self.write_verification_manifest(panel_text=panel)
                result = self.run_finalize()
                self.assert_rejected_without_mutation(result, token)

    # ---- R2 正向：六个实际取值 + 独立汇总行（LEGAL_PANEL 已含）仍须通过 ----
    def test_r2_legal_values_with_independent_summary_lines_still_pass(self):
        self.write_verification_manifest(panel_text=LEGAL_PANEL)
        result = self.run_finalize()
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertIn("status: S11", self.record.read_text(encoding="utf-8"))
        self.assertEqual([], load_closure().check_s11_closure(self.record_meta()))


if __name__ == "__main__":
    unittest.main()
