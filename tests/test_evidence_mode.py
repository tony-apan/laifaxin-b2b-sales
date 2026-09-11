import datetime
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
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

    def write_audit_manifest(self, mode="live", generated_at=None, audit_text=None):
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
            "evidence": {
                "audit": self.evidence_item(audit),
                "review": self.evidence_item(review),
            },
        }
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
            panel_text or "标签 客群 保存 模板 配额 审查\n测试不激活\n",
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
        )

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
        )

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
