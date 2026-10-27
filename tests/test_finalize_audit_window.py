# -*- coding: utf-8 -*-
"""S4 finalize_audit 的审计窗口机器校验（P0-1 回归；2026-10-27 审计边界与公司级证据修复）。

夹具风格沿用 tests/test_evidence_mode.py：临时目录里造 operation-record / product-profile /
manifest / audit.md / review.md，再真跑 tools/finalize_audit.py 断言退出码与 record 不被改动。

2026-10-27 契约（TASK-20261027-audit-proof）：
- 窗口 = 连续 3 页（WINDOW_SIZE）：三页合计 >=70% 且单页 >=50%；空页/不足3页/不连续失败；
- 无跌破窗口时 critical_page 只认最后一个完整实测窗口末页，不得无依据前移；
- 有跌破时须存在前一实测连续达标窗口（首窗口即跌破 → 拒绝定界），公式按 WINDOW_SIZE 推导；
- 正式 live 收口必须带逐行公司级语义表；{page,count} 空壳、计数映射、缺表、计数不符、
  重复 id、页外行、缺中文强判均 exit 2 且 record 不变；
- 历史无四件套 manifest 不再兼容放行（明确拒绝测试）；
- 末页不足 10 条按实际数，不造满 10。
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

DEFAULT_ROWS = [
    {"page": 369, "matched": 7, "total": 10},
    {"page": 370, "matched": 7, "total": 10},
    {"page": 371, "matched": 7, "total": 10},
]


def window_doc(page_rows):
    return {
        "pages": [row["page"] for row in page_rows],
        "page_rows": [dict(row) for row in page_rows],
        "numerator": sum(row["matched"] for row in page_rows),
        "denominator": sum(row["total"] for row in page_rows),
        "method": "连续3页（每页≥50%）滑动平均，所有滑动窗口>=70%，覆盖临界页",
    }


def boundary_doc(critical=371):
    return {
        "critical_page": critical,
        "result": "above",
        "next_page": 372,
        "next_result": "below",
        "page_rows": [
            {"page": 371, "matched": 7, "total": 10},
            {"page": 372, "matched": 5, "total": 10},
        ],
    }


def company_rows_doc(per_page=((369, 7), (370, 7), (371, 7)), totals=None):
    """生成逐行公司级语义表：每页 totals[page]（默认 10）行，前 matched 行 matched=True。"""
    rows = []
    for page, matched in per_page:
        total = (totals or {}).get(page, 10)
        for i in range(1, total + 1):
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

    def write_manifest(self, window=True, boundary=True, company_rows=True):
        audit = self.write_evidence(
            "s4-audit.md", "70% 临界 50页 三页平均 逐页 敏感性\n审计通过\n")
        review = self.write_evidence("s4-review.md", "放行\nP0=0\nP1=0\n")
        doc = {
            "evidence_mode": "live",
            "project": PROJECT,
            "profile_sha256": hashlib.sha256(self.profile.read_bytes()).hexdigest(),
            "seed": SEED,
            "generated_at": datetime.datetime.now().isoformat(timespec="seconds"),
            "run_id": "run-2026-10-27-window",
            "source": {"platform_product_id": "prod-1", "generation_id": "gen-1",
                        "segment_id": "seg-1", "keyword": "tent"},
            "evidence": {"audit": self.evidence_item(audit),
                         "review": self.evidence_item(review)},
        }
        if window is True:
            doc["window"] = window_doc(DEFAULT_ROWS)
        elif isinstance(window, dict):
            doc["window"] = window
        if boundary is True:
            doc["boundary"] = boundary_doc()
        elif isinstance(boundary, dict):
            doc["boundary"] = boundary
        if company_rows is True:
            doc["company_rows"] = company_rows_doc()
        elif isinstance(company_rows, list):
            doc["company_rows"] = company_rows
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
            timeout=60,
            encoding="utf-8", errors="replace")

    # ---- 1) 合法 3 页窗口 + 逐行语义表 → 通过 ----
    def test_legal_window_advances_to_s4(self):
        self.write_manifest()
        result = self.run_audit()
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertIn("status: S4", self.record.read_text(encoding="utf-8"))

    # ---- 2) 3 页窗口合计 <70% 被拒（exit 2，record 不动）----
    def test_three_page_window_below_70_rejected(self):
        rows = [{"page": p, "matched": 6, "total": 10} for p in (369, 370, 371)]
        rows2 = [{"page": p, "matched": 6, "total": 10} for p in (369, 370, 371)]
        self.write_manifest(window=window_doc(rows),
                            boundary=boundary_doc(critical=369),
                            company_rows=company_rows_doc(
                                per_page=((369, 6), (370, 6), (371, 6))))
        before = self.record.read_bytes()
        result = self.run_audit()
        self.assertEqual(2, result.returncode, result.stdout + result.stderr)
        self.assertIn("审计窗口校验失败", result.stdout)
        self.assertIn("70%", result.stdout)
        self.assertEqual(before, self.record.read_bytes())
        self.assertEqual(30, sum(r["total"] for r in rows2))

    # ---- 2b) 窗口合计达标、但单页 <50% 仍被拒 ----
    def test_single_page_below_floor_rejected(self):
        rows = [
            {"page": 369, "matched": 10, "total": 10},
            {"page": 370, "matched": 10, "total": 10},
            {"page": 371, "matched": 3, "total": 10},
        ]
        self.write_manifest(window=window_doc(rows),
                            company_rows=company_rows_doc(
                                per_page=((369, 10), (370, 10), (371, 3))))
        before = self.record.read_bytes()
        result = self.run_audit()
        self.assertEqual(2, result.returncode, result.stdout + result.stderr)
        self.assertIn("单页下限", result.stdout)
        self.assertEqual(before, self.record.read_bytes())

    # ---- 3) 临界页 != 前一实测达标窗口末页（首个<70%窗口起点+1）被拒 ----
    def test_critical_page_must_be_prev_window_end_rejected(self):
        self.write_manifest(boundary=boundary_doc(critical=370))
        before = self.record.read_bytes()
        result = self.run_audit()
        self.assertEqual(2, result.returncode, result.stdout + result.stderr)
        self.assertIn("critical_page=370", result.stdout)
        self.assertIn("critical_page=371", result.stdout)
        self.assertEqual(before, self.record.read_bytes())

    # ---- 4) page_rows 缺字段 → 中文点名缺哪个字段 ----
    def test_missing_page_row_field_is_named(self):
        window = window_doc(DEFAULT_ROWS)
        window["page_rows"][2] = {"page": 371, "matched": 7}  # 故意缺 total
        self.write_manifest(window=window)
        result = self.run_audit()
        self.assertEqual(2, result.returncode, result.stdout + result.stderr)
        self.assertIn("缺字段 total", result.stdout)

    # ---- 5) 四件套 manifest 缺 window → 拒绝（不得靠省略 window 绕过）----
    def test_missing_window_with_contract_fields_rejected(self):
        self.write_manifest(window=False, boundary=False, company_rows=False)
        result = self.run_audit()
        self.assertEqual(2, result.returncode, result.stdout + result.stderr)
        self.assertIn("缺 window", result.stdout)

    # ---- 6) 历史无四件套 manifest：2026-10-27 起明确拒绝（原「兼容放行」改为拒绝测试）----
    def test_legacy_manifest_without_contract_fields_now_rejected(self):
        doc = self.write_manifest(window=False, boundary=False, company_rows=False)
        doc.pop("run_id", None)
        self.manifest.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
        before = self.record.read_bytes()
        result = self.run_audit()
        self.assertEqual(2, result.returncode, result.stdout + result.stderr)
        self.assertIn("缺 window", result.stdout)
        self.assertEqual(before, self.record.read_bytes())

    # ---- 7) live 收口缺公司级语义表 → 拒绝 ----
    def test_missing_semantic_rows_rejected(self):
        self.write_manifest(company_rows=False)
        before = self.record.read_bytes()
        result = self.run_audit()
        self.assertEqual(2, result.returncode, result.stdout + result.stderr)
        self.assertIn("缺公司级语义表", result.stdout)
        self.assertEqual(before, self.record.read_bytes())

    # ---- 8) {page,count} 聚合空壳 → 拒绝 ----
    def test_count_shell_semantic_rows_rejected(self):
        shell = [{"page": p, "count": 10} for p in (369, 370, 371)]
        self.write_manifest(company_rows=shell)
        before = self.record.read_bytes()
        result = self.run_audit()
        self.assertEqual(2, result.returncode, result.stdout + result.stderr)
        self.assertIn("空壳", result.stdout)
        self.assertEqual(before, self.record.read_bytes())

    # ---- 9) 语义表行数与 page_rows.total 不符 → 拒绝 ----
    def test_semantic_row_count_mismatch_rejected(self):
        rows = company_rows_doc()
        del rows[10]  # 370 页少一行 → 9 行 ≠ total=10
        self.write_manifest(company_rows=rows)
        before = self.record.read_bytes()
        result = self.run_audit()
        self.assertEqual(2, result.returncode, result.stdout + result.stderr)
        self.assertIn("行数=9 与 page_rows.total=10 不一致", result.stdout)
        self.assertEqual(before, self.record.read_bytes())

    # ---- 10) 语义表 matched=true 行数与 page_rows.matched 不符 → 拒绝 ----
    def test_semantic_matched_count_mismatch_rejected(self):
        rows = company_rows_doc()
        rows[16]["matched"] = False  # 370 页第 7 行翻为 false → 6 ≠ 7
        self.write_manifest(company_rows=rows)
        before = self.record.read_bytes()
        result = self.run_audit()
        self.assertEqual(2, result.returncode, result.stdout + result.stderr)
        self.assertIn("matched=true 行数=6 与 page_rows.matched=7 不一致", result.stdout)
        self.assertEqual(before, self.record.read_bytes())

    # ---- 11) 重复 company_id → 拒绝 ----
    def test_duplicate_company_id_rejected(self):
        rows = company_rows_doc()
        rows[10]["company_id"] = rows[0]["company_id"]  # 370 页复用 369 页 id
        self.write_manifest(company_rows=rows)
        before = self.record.read_bytes()
        result = self.run_audit()
        self.assertEqual(2, result.returncode, result.stdout + result.stderr)
        self.assertIn("重复", result.stdout)
        self.assertEqual(before, self.record.read_bytes())

    # ---- 12) 缺中文描述却强判 matched=true → 拒绝（缺中文/身份行只能 null 未知）----
    def test_missing_chinese_forced_match_rejected(self):
        rows = company_rows_doc()
        rows[0]["summary_zh"] = ""
        self.write_manifest(company_rows=rows)
        before = self.record.read_bytes()
        result = self.run_audit()
        self.assertEqual(2, result.returncode, result.stdout + result.stderr)
        self.assertIn("只能 matched=null", result.stdout)
        self.assertEqual(before, self.record.read_bytes())

    # ---- 12b) R2：英文非空 summary_zh + matched=false → 同样拒绝（正负判定一致要中文）----
    def test_english_summary_with_matched_false_rejected(self):
        rows = company_rows_doc()
        # 第 369 页第 8 行（matched=false）换成非空英文描述——判定依据必须同样来自中文描述
        rows[7]["summary_zh"] = "wholesale outdoor gear distributor"
        self.write_manifest(company_rows=rows)
        before = (self.record.read_bytes(), self.record.stat().st_mtime_ns)
        result = self.run_audit()
        self.assertEqual(2, result.returncode, result.stdout + result.stderr)
        self.assertIn("非中文", result.stdout)
        self.assertEqual(before, (self.record.read_bytes(), self.record.stat().st_mtime_ns))

    # ---- 12c) R2：matched=null（未知）行不需要中文，不算匹配，仍放行 ----
    def test_null_matched_without_chinese_still_accepted(self):
        rows = company_rows_doc()
        rows[-1]["summary_zh"] = ""
        rows[-1]["matched"] = None
        rows[-1]["reason"] = "缺中文描述，无法判定"
        self.write_manifest(company_rows=rows)
        result = self.run_audit()
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertIn("status: S4", self.record.read_text(encoding="utf-8"))

    # ---- 13) 页外行 → 拒绝 ----
    def test_offpage_semantic_row_rejected(self):
        rows = company_rows_doc()
        rows[0]["page"] = 999
        self.write_manifest(company_rows=rows)
        before = self.record.read_bytes()
        result = self.run_audit()
        self.assertEqual(2, result.returncode, result.stdout + result.stderr)
        self.assertIn("页外行", result.stdout)
        self.assertEqual(before, self.record.read_bytes())

    # ---- 14) 首个窗口即跌破、无前一实测达标窗口 → 不得定界 ----
    def test_first_window_drop_without_prior_window_rejected(self):
        rows = [{"page": p, "matched": 5, "total": 10} for p in (1, 2, 3)]
        boundary = {
            "critical_page": 1, "result": "below",
            "next_page": 2, "next_result": "below",
            "page_rows": [
                {"page": 1, "matched": 5, "total": 10},
                {"page": 2, "matched": 5, "total": 10},
            ],
        }
        self.write_manifest(window=window_doc(rows), boundary=boundary,
                            company_rows=company_rows_doc(
                                per_page=((1, 5), (2, 5), (3, 5))))
        before = self.record.read_bytes()
        result = self.run_audit()
        self.assertEqual(2, result.returncode, result.stdout + result.stderr)
        self.assertIn("不能定界", result.stdout)
        self.assertEqual(before, self.record.read_bytes())

    # ---- 15) 无跌破时 critical_page 前移 → 拒绝；只认最后完整实测窗口末页 ----
    def test_no_drop_critical_cannot_move_earlier_rejected(self):
        boundary = {"critical_page": 370, "result": "above"}
        self.write_manifest(boundary=boundary)
        before = self.record.read_bytes()
        result = self.run_audit()
        self.assertEqual(2, result.returncode, result.stdout + result.stderr)
        self.assertIn("不得无依据前移", result.stdout)
        self.assertEqual(before, self.record.read_bytes())

    # ---- 15b) 无跌破且 critical=末页 → 通过 ----
    def test_no_drop_critical_last_full_window_end_accepted(self):
        boundary = {"critical_page": 371, "result": "above"}
        self.write_manifest(boundary=boundary)
        result = self.run_audit()
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertIn("status: S4", self.record.read_text(encoding="utf-8"))

    # ---- 16) 末页不足 10 条按实际数（total=7），不造满 10 → 通过 ----
    def test_last_page_partial_total_accepted(self):
        rows = [
            {"page": 369, "matched": 7, "total": 10},
            {"page": 370, "matched": 7, "total": 10},
            {"page": 371, "matched": 5, "total": 7},
        ]
        rows_semantic = company_rows_doc(
            per_page=((369, 7), (370, 7), (371, 5)), totals={371: 7})
        # 末页最后一行缺中文 → 只能未知 null（不计匹配）
        last = rows_semantic[-1]
        last["summary_zh"] = ""
        last["matched"] = None
        last["reason"] = "缺中文描述，无法判定"
        self.write_manifest(window=window_doc(rows),
                            boundary={"critical_page": 371, "result": "above"},
                            company_rows=rows_semantic)
        result = self.run_audit()
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertIn("status: S4", self.record.read_text(encoding="utf-8"))


class WindowWordingTest(unittest.TestCase):
    """R2 AC2：现行文案不得再出现 5 页/起点+3 旧口径，且从 WINDOW_SIZE 常量生成。"""

    def test_no_live_five_page_wording_in_runtime_messages(self):
        source = (ROOT / "tools" / "finalize_audit.py").read_text(encoding="utf-8")
        for text in ("连续5页窗口", "连续 5 页窗口", "连续5页滑动", "起点+3", "起点 +3",
                     "该窗口起点+3"):
            self.assertNotIn(text, source, f"运行时文案残留旧口径: {text}")
        # 运行时字符串须引用常量而非写死页数
        self.assertIn("连续{WINDOW_SIZE}页窗口", source)
        self.assertIn("连续 {WINDOW_SIZE} 页滑动窗口至少要", source)

    def test_old_wording_only_allowed_in_history_comments(self):
        source = (ROOT / "tools" / "finalize_audit.py").read_text(encoding="utf-8")
        for line in source.splitlines():
            if any(k in line for k in ("连续5页", "连续 5 页", "起点+3", "起点 +3")):
                stripped = line.strip()
                self.assertTrue(stripped.startswith("#"), f"非注释残留旧口径: {line}")
                self.assertTrue(
                    any(k in stripped for k in ("2026-10", "历史", "v3", "旧")),
                    f"注释未注明历史: {line}",
                )


if __name__ == "__main__":
    unittest.main()
