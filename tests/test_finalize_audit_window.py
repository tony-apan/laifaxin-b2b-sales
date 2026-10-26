# -*- coding: utf-8 -*-
"""S4 finalize_audit 的审计窗口机器校验（P0-1 回归测试）。

夹具风格沿用 tests/test_evidence_mode.py：临时目录里造 operation-record / product-profile /
manifest / audit.md / review.md，再真跑 tools/finalize_audit.py 断言退出码与 record 不被改动。
"""
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
SEED = "seed.example"


class FinalizeAuditWindowTest(unittest.TestCase):
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
        self.manifest = self.project_dir / "audit-manifest.json"
        self.write_record()

    def tearDown(self):
        self.tmp.cleanup()

    def write_record(self):
        self.record.write_text(
            "---\nstatus: S3\nnext_state: pending\noperator_key: operator\n"
            "product_key: product\nseed: seed.example\n---\nrecord body\n",
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

    @staticmethod
    def window_doc():
        # specs/threshold-probe-spec.md §4.4 已实测骨架（367-371 = 36/50 = 72%）
        return {
            "pages": [367, 368, 369, 370, 371],
            "page_rows": [
                {"page": 367, "matched": 9, "total": 10},
                {"page": 368, "matched": 6, "total": 10},
                {"page": 369, "matched": 8, "total": 10},
                {"page": 370, "matched": 8, "total": 10},
                {"page": 371, "matched": 5, "total": 10},
            ],
            "numerator": 36,
            "denominator": 50,
            "method": "连续5页滑动平均，所有滑动窗口>=70%，覆盖临界页",
        }

    @staticmethod
    def boundary_doc(critical=371):
        return {
            "critical_page": critical,
            "result": "above",
            "next_page": 372,
            "next_result": "below",
            "page_rows": [
                {"page": 371, "matched": 5, "total": 10},
                {"page": 372, "matched": 5, "total": 10},
            ],
        }

    def write_manifest(self, window=True, boundary=True):
        audit = self.write_evidence(
            "s4-audit.md", "70% 临界 50页 三页平均 逐页 敏感性\n审计通过\n")
        review = self.write_evidence("s4-review.md", "放行\nP0=0\nP1=0\n")
        doc = {
            "evidence_mode": "live",
            "project": PROJECT,
            "profile_sha256": hashlib.sha256(self.profile.read_bytes()).hexdigest(),
            "seed": SEED,
            "generated_at": datetime.datetime.now().isoformat(timespec="seconds"),
            "run_id": "run-2026-10-23-window",
            "source": {"platform_product_id": "prod-1", "generation_id": "gen-1",
                        "segment_id": "seg-1", "keyword": "tent"},
            "evidence": {"audit": self.evidence_item(audit),
                         "review": self.evidence_item(review)},
        }
        if window is True:
            doc["window"] = self.window_doc()
        elif isinstance(window, dict):
            doc["window"] = window
        if boundary is True:
            doc["boundary"] = self.boundary_doc()
        elif isinstance(boundary, dict):
            doc["boundary"] = boundary
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
            timeout=30,
        encoding="utf-8", errors="replace")

    # ---- 1) 合法窗口通过 ----
    def test_legal_window_advances_to_s4(self):
        self.write_manifest()
        result = self.run_audit()
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertIn("status: S4", self.record.read_text(encoding="utf-8"))

    # ---- 2) 连续 5 页窗口 <70% 被拒（exit 2，record 不动）----
    def test_five_page_window_below_70_rejected(self):
        window = self.window_doc()
        window.update({
            "pages": [1, 2, 3, 4, 5],
            "page_rows": [{"page": p, "matched": 6, "total": 10} for p in range(1, 6)],
            "numerator": 30,
            "denominator": 50,
        })
        self.write_manifest(window=window, boundary=self.boundary_doc(critical=4))
        before = self.record.read_bytes()
        result = self.run_audit()
        self.assertEqual(2, result.returncode, result.stdout + result.stderr)
        self.assertIn("审计窗口校验失败", result.stdout)
        self.assertIn("70%", result.stdout)
        self.assertEqual(before, self.record.read_bytes())

    # ---- 3) 临界页 != 首个<70%窗口起点+3 被拒 ----
    def test_critical_page_not_first_drop_start_plus_three_rejected(self):
        self.write_manifest(boundary=self.boundary_doc(critical=370))
        before = self.record.read_bytes()
        result = self.run_audit()
        self.assertEqual(2, result.returncode, result.stdout + result.stderr)
        self.assertIn("critical_page=370", result.stdout)
        self.assertIn("critical_page=371", result.stdout)
        self.assertEqual(before, self.record.read_bytes())

    # ---- 4) page_rows 缺字段 → 中文点名缺哪个字段 ----
    def test_missing_page_row_field_is_named(self):
        window = self.window_doc()
        window["page_rows"][2] = {"page": 369, "matched": 8}  # 故意缺 total
        self.write_manifest(window=window)
        result = self.run_audit()
        self.assertEqual(2, result.returncode, result.stdout + result.stderr)
        self.assertIn("缺字段 total", result.stdout)

    # ---- 5) 四件套 manifest 缺 window → 拒绝（不得靠省略 window 绕过）----
    def test_missing_window_with_contract_fields_rejected(self):
        self.write_manifest(window=False, boundary=False)
        result = self.run_audit()
        self.assertEqual(2, result.returncode, result.stdout + result.stderr)
        self.assertIn("缺 window", result.stdout)

    # ---- 6) 历史兼容：window 与四件套其余字段全缺 → 告警放行（现有夹具依赖）----
    def test_legacy_manifest_without_contract_fields_warns_but_passes(self):
        doc = self.write_manifest(window=False, boundary=False)
        doc.pop("run_id", None)
        self.manifest.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
        result = self.run_audit()
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertIn("兼容模式", result.stdout)


if __name__ == "__main__":
    unittest.main()
