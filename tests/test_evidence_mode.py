import datetime
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LEGAL_PANEL = (
    "核实面板（平台回读）\n"
    "- 标签：询盘、不发两个停止标签已挂好\n"
    "- 客群：宠物食品包装采购商，本批 25 人\n"
    "- 保存：25 人已加入「英语-宠物食品包装-12轮」\n"
    "- 模板：48 个模板已挂到 12 轮\n"
    "- 配额：全账号 30000/天、单公司 5/天\n"
    "- 审查：12 步顺序与时区 America/New_York 已核对\n"
    "状态 inactive，等待人工决策（测试不激活）\n"
)

PROJECT = "operator/product"
ORG = "org-for-evidence-tests"
SEQ = "0123456789abcdef01234567"


class EvidenceModeTest(unittest.TestCase):
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
        self.manifest = self.project_dir / "manifest.json"

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

    def audit_company_rows(self, per_page=((369, 7), (370, 7), (371, 7))):
        """逐行公司级语义表：每页 10 行，前 matched 行 matched=True（真实逐行对象，非计数空壳）。"""
        rows = []
        for page, matched in per_page:
            for i in range(1, 11):
                is_match = i <= matched
                rows.append({
                    "page": page,
                    "company_id": f"c-{page}-{i}",
                    "company_name": f"公司{page}-{i}",
                    "summary_zh": f"外贸B2B采购帐篷与露营装备{page}-{i}",
                    "matched": is_match,
                    "reason": "卖帐篷与露营装备" if is_match else "纯内容站不采购",
                })
        return rows

    def write_audit_manifest(self, mode="live", generated_at=None, audit_text=None,
                             window=True, company_rows=True):
        audit = self.write_evidence(
            "s4-audit.md",
            audit_text or "70% 临界 50页 三页平均 逐页 敏感性\n审计通过\n",
        )
        review = self.write_evidence("s4-review.md", "放行\nP0=0\nP1=0\n")
        doc = {
            "project": PROJECT,
            "profile_sha256": hashlib.sha256(self.profile.read_bytes()).hexdigest(),
            "seed": "seed.example",
            "generated_at": generated_at or datetime.datetime.now().isoformat(timespec="seconds"),
            "evidence_mode": mode,
            "source": {"platform_product_id": "prod-1", "generation_id": "gen-1",
                        "segment_id": "seg-1", "keyword": "tent"},
            "evidence": {
                "audit": self.evidence_item(audit),
                "review": self.evidence_item(review),
            },
        }
        # 2026-10-27：正式 live 收口必须带完整四件套 + 逐行公司级语义表
        if window:
            doc["run_id"] = "run-2026-10-27-evidence"
            doc["window"] = {
                "pages": [369, 370, 371],
                "page_rows": [
                    {"page": 369, "matched": 7, "total": 10},
                    {"page": 370, "matched": 7, "total": 10},
                    {"page": 371, "matched": 7, "total": 10},
                ],
                "numerator": 21,
                "denominator": 30,
                "method": "连续3页（每页≥50%）滑动平均，所有滑动窗口>=70%，覆盖临界页",
            }
            doc["boundary"] = {
                "critical_page": 371, "result": "above",
                "next_page": 372, "next_result": "below",
                "page_rows": [
                    {"page": 371, "matched": 7, "total": 10},
                    {"page": 372, "matched": 5, "total": 10},
                ],
            }
        if company_rows:
            doc["company_rows"] = self.audit_company_rows()
        self.manifest.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
        return doc

    def write_verification_manifest(self, mode="live", generated_at=None, panel_text=None):
        sequence = self.write_evidence(
            "verify-seq.txt", f"{SEQ}\n步骤数: 12\n状态=inactive\n全部12步\n"
        )
        exclude = self.write_evidence("verify-exclude.txt", "含4区=0\n排除生效\n")
        diff = self.write_evidence("verify-diff.txt", "模板数: 48\n最大相似度 20%\n差异≥30%达标\n")
        panel = self.write_evidence(
            "verification-panel.md",
            panel_text or LEGAL_PANEL,
        )
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

    def run_audit(self):
        return subprocess.run(
            [
                sys.executable,
                str(ROOT / "tools" / "finalize_audit.py"),
                "--record", str(self.record),
                "--profile", str(self.profile),
                "--project", PROJECT,
                "--manifest", str(self.manifest),
            ],
            text=True,
            capture_output=True,
            timeout=10,
        encoding="utf-8", errors="replace")

    def run_verification(self):
        return subprocess.run(
            [
                sys.executable,
                str(ROOT / "tools" / "finalize_run.py"),
                "--record", str(self.record),
                "--profile", str(self.profile),
                "--project", PROJECT,
                "--org", ORG,
                "--seq", SEQ,
                "--manifest", str(self.manifest),
            ],
            text=True,
            capture_output=True,
            timeout=10,
        encoding="utf-8", errors="replace")

    def assert_record_unchanged(self, before):
        self.assertEqual((self.record.read_bytes(), self.record.stat().st_mtime_ns), before)

    def test_audit_rejects_non_live_modes_without_mutating_record(self):
        for mode in ("simulation", "mock", "stub", "", "unknown", "LIVE"):
            with self.subTest(mode=mode):
                self.write_record("S3")
                self.write_audit_manifest(mode=mode)
                before = (self.record.read_bytes(), self.record.stat().st_mtime_ns)
                result = self.run_audit()
                self.assertEqual(2, result.returncode, result.stdout + result.stderr)
                self.assert_record_unchanged(before)

    def test_audit_live_rejects_offline_stub_marker_without_mutating_record(self):
        self.write_record("S3")
        self.write_audit_manifest(
            audit_text="离线网络桩采集\n70% 临界 50页 三页平均 逐页 敏感性\n"
        )
        before = (self.record.read_bytes(), self.record.stat().st_mtime_ns)
        result = self.run_audit()
        self.assertEqual(1, result.returncode, result.stdout + result.stderr)
        self.assert_record_unchanged(before)

    def test_verification_rejects_non_live_modes_without_mutating_record(self):
        for mode in ("simulation", "mock", "stub", "", "unknown", "Live"):
            with self.subTest(mode=mode):
                self.write_record("S10")
                self.write_verification_manifest(mode=mode)
                before = (self.record.read_bytes(), self.record.stat().st_mtime_ns)
                result = self.run_verification()
                self.assertEqual(2, result.returncode, result.stdout + result.stderr)
                self.assert_record_unchanged(before)

    def test_verification_live_rejects_marker_without_mutating_record(self):
        self.write_record("S10")
        self.write_verification_manifest(panel_text="标签 客群 保存 模板 配额 审查\nSiMuLaTeD evidence\n")
        before = (self.record.read_bytes(), self.record.stat().st_mtime_ns)
        result = self.run_verification()
        self.assertEqual(1, result.returncode, result.stdout + result.stderr)
        self.assert_record_unchanged(before)

    def test_clean_live_audit_advances_to_s4(self):
        self.write_record("S3")
        self.write_audit_manifest()
        result = self.run_audit()
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertIn("status: S4", self.record.read_text(encoding="utf-8"))

    # ---- 2026-10-27 审计边界与公司级证据修复 ----

    def test_audit_live_without_window_rejected_even_if_legacy(self):
        """历史无四件套 manifest：live 收口明确拒绝（不再兼容放行）。"""
        self.write_record("S3")
        self.write_audit_manifest(window=False, company_rows=False)
        before = (self.record.read_bytes(), self.record.stat().st_mtime_ns)
        result = self.run_audit()
        self.assertEqual(2, result.returncode, result.stdout + result.stderr)
        self.assertIn("缺 window", result.stdout)
        self.assert_record_unchanged(before)

    def test_audit_live_without_company_rows_rejected(self):
        """live 收口缺逐行公司级语义表 → exit 2 且 record 不变。"""
        self.write_record("S3")
        self.write_audit_manifest(company_rows=False)
        before = (self.record.read_bytes(), self.record.stat().st_mtime_ns)
        result = self.run_audit()
        self.assertEqual(2, result.returncode, result.stdout + result.stderr)
        self.assertIn("缺公司级语义表", result.stdout)
        self.assert_record_unchanged(before)

    def test_audit_live_count_shell_company_rows_rejected(self):
        """{page,count} 聚合空壳不得充当公司级语义表。"""
        self.write_record("S3")
        doc = self.write_audit_manifest(company_rows=False)
        doc["company_rows"] = [{"page": p, "count": 10} for p in (369, 370, 371)]
        self.manifest.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
        before = (self.record.read_bytes(), self.record.stat().st_mtime_ns)
        result = self.run_audit()
        self.assertEqual(2, result.returncode, result.stdout + result.stderr)
        self.assertIn("空壳", result.stdout)
        self.assert_record_unchanged(before)

    def test_clean_live_verification_advances_to_s11_and_allows_test_inactive_text(self):
        self.write_record("S10")
        self.write_verification_manifest()
        result = self.run_verification()
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertIn("status: S11", self.record.read_text(encoding="utf-8"))

    def test_audit_path_constraint_still_rejects_without_mutation(self):
        self.write_record("S3")
        doc = self.write_audit_manifest()
        outside = Path(self.tmp.name) / "outside.md"
        outside.write_text("70% 临界 50页 三页平均 逐页 敏感性", encoding="utf-8")
        doc["evidence"]["audit"] = {
            "status": "pass",
            "path": str(outside),
            "sha256": hashlib.sha256(outside.read_bytes()).hexdigest(),
        }
        self.manifest.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
        before = (self.record.read_bytes(), self.record.stat().st_mtime_ns)
        result = self.run_audit()
        self.assertNotEqual(0, result.returncode, result.stdout + result.stderr)
        self.assert_record_unchanged(before)

    def test_verification_hash_constraint_still_rejects_without_mutation(self):
        self.write_record("S10")
        doc = self.write_verification_manifest()
        doc["evidence"]["diff"]["sha256"] = "0" * 64
        self.manifest.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
        before = (self.record.read_bytes(), self.record.stat().st_mtime_ns)
        result = self.run_verification()
        self.assertNotEqual(0, result.returncode, result.stdout + result.stderr)
        self.assert_record_unchanged(before)

    def test_72_hour_expiry_still_rejects_both_finalizers_without_mutation(self):
        expired = (datetime.datetime.now() - datetime.timedelta(hours=73)).isoformat(timespec="seconds")
        for status, writer, runner in (
            ("S3", self.write_audit_manifest, self.run_audit),
            ("S10", self.write_verification_manifest, self.run_verification),
        ):
            with self.subTest(status=status):
                self.write_record(status)
                writer(generated_at=expired)
                before = (self.record.read_bytes(), self.record.stat().st_mtime_ns)
                result = runner()
                self.assertEqual(2, result.returncode, result.stdout + result.stderr)
                self.assert_record_unchanged(before)


if __name__ == "__main__":
    unittest.main()
