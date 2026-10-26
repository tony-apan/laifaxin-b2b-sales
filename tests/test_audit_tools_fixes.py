# -*- coding: utf-8 -*-
"""探针/审计工具的 P1 回归：四区 filters、--domains 走 refine、loose 匹配率、错误上抛（P1-3/P1-4）。"""
import io
import json
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import audit_company  # noqa: E402
import find_critical  # noqa: E402
import find_threshold  # noqa: E402

FOUR_REGION_FILTERS = [{
    "property": "country_code", "operator": "exclude", "value": "",
    "values": ["CN", "TW", "HK", "MO"], "valueType": "select",
}]


def fake_run(captured, stdout, returncode=0):
    def run(cmd, **kwargs):
        captured.append(cmd)
        return SimpleNamespace(returncode=returncode, stdout=stdout, stderr="")
    return run


def payload_json(doc, status=200):
    return json.dumps(doc, ensure_ascii=False) + "\n__HTTP_STATUS__:%d" % status


class ProbeFiltersTest(unittest.TestCase):
    def _fetch_payload(self, module, call):
        captured = []
        stdout = json.dumps({"data": {"list": []}})
        fake = SimpleNamespace(run=fake_run(captured, stdout))
        with mock.patch.object(module, "subprocess", fake):
            result = call()
        self.assertEqual([], result.get("list"))
        cmd = captured[0]
        payload = json.loads(cmd[cmd.index("-d") + 1])
        return payload

    def test_find_critical_uses_four_region_filters(self):
        payload = self._fetch_payload(
            find_critical, lambda: find_critical.fetch(1, "kw", "token", "org"))
        self.assertEqual(FOUR_REGION_FILTERS, payload["filters"])

    def test_find_threshold_uses_four_region_filters(self):
        payload = self._fetch_payload(
            find_threshold, lambda: find_threshold.fetch(1, "kw", "token", "org"))
        self.assertEqual(FOUR_REGION_FILTERS, payload["filters"])


class AuditCompanyTest(unittest.TestCase):
    def test_loose_accuracy_uses_total_denominator(self):
        from collections import Counter
        stats = Counter({"MATCH": 6, "MARGINAL": 2, "REJECT": 2})
        self.assertAlmostEqual(80.0, audit_company.accuracy(stats, 10, "loose"))
        self.assertAlmostEqual(80.0, audit_company.accuracy(stats, 10, "moderate"))
        self.assertAlmostEqual(60.0, audit_company.accuracy(stats, 10, "strict"))
        # 分母按实际返回条数（尾页 5 条时不再除 10）
        self.assertAlmostEqual(100.0, audit_company.accuracy(Counter({"MATCH": 5}), 5, "strict"))

    def test_semantic_rows_flag_missing_chinese_and_do_not_substitute_english(self):
        buf = io.StringIO()
        rows = [
            {"company_name": "HasZh", "summary_zh": "椰子面包厂", "summary_en": "coconut bakery",
             "country_code": "US", "client_focus": "B2B"},
            {"company_name": "NoZh", "summary_zh": "", "summary_en": "coconut bakery",
             "country_code": "US", "client_focus": "B2B"},
        ]
        with redirect_stdout(buf):
            audit_company._print_semantic_rows(rows)
        out = buf.getvalue()
        self.assertIn("椰子面包厂", out)
        self.assertNotIn("coconut bakery", out)
        self.assertIn("中文可用1条，缺中文1条", out)
        self.assertIn("无法据此判断", out)

    def test_401_raises_and_does_not_retry(self):
        captured = []
        stdout = payload_json({"success": False, "message": "unauthorized"}, 401)
        fake = SimpleNamespace(run=fake_run(captured, stdout))
        with mock.patch.object(audit_company, "subprocess", fake):
            with self.assertRaises(audit_company.AuditHTTPError):
                audit_company.fetch(1, "kw", "token", "org")
        self.assertEqual(1, len(captured))

    def test_5xx_is_retried(self):
        captured = []
        responses = [
            payload_json({"success": False, "message": "server error"}, 500),
            payload_json({"success": True, "data": {"list": [{"company_name": "A"}]}}, 200),
        ]

        def run(cmd, **kwargs):
            captured.append(cmd)
            return SimpleNamespace(returncode=0, stdout=responses[len(captured) - 1], stderr="")

        with mock.patch.object(audit_company, "subprocess", SimpleNamespace(run=run)):
            data = audit_company.fetch(1, "kw", "token", "org", retries=2)
        self.assertEqual(2, len(captured))
        self.assertEqual(1, len(data["list"]))

    def test_non_json_raises_not_silent_empty(self):
        captured = []
        fake = SimpleNamespace(run=fake_run(captured, "<html>login</html>\n__HTTP_STATUS__:302", 0))
        with mock.patch.object(audit_company, "subprocess", fake):
            with self.assertRaises(audit_company.AuditHTTPError):
                audit_company.fetch(1, "kw", "token", "org")

    def test_domains_branch_uses_company_list_not_similar_list(self):
        calls = []

        def fake_fetch(page, keyword, token, org, filters=None, **kwargs):
            calls.append({"page": page, "keyword": keyword, "filters": filters})
            return {"list": [{"company_name": "Buyer Ltd", "summary_zh": "kayak shop", "country_code": "US"}]}

        args = SimpleNamespace(domains="buyer.example", query="", token="t", org="o",
                               mode="moderate", pages="")
        filters = list(FOUR_REGION_FILTERS)
        with mock.patch.object(audit_company, "fetch", side_effect=fake_fetch), \
             redirect_stdout(io.StringIO()):
            audit_company._run(args, filters)
        self.assertEqual(1, len(calls))
        self.assertEqual("buyer.example", calls[0]["keyword"])
        self.assertEqual(1, calls[0]["page"])
        self.assertEqual(filters, calls[0]["filters"])
        source = (TOOLS / "audit_company.py").read_text(encoding="utf-8")
        self.assertNotIn("domain/similar-list", source)
        self.assertNotIn("fetch_similar", source)

    def test_http_error_in_main_exits_2(self):
        args = ["audit_company.py", "--domains", "buyer.example",
                "--token", "t", "--org", "o", "--match-words", "kayak"]
        with mock.patch.object(audit_company, "fetch", side_effect=audit_company.AuditHTTPError("boom")), \
             mock.patch.object(sys, "argv", args), redirect_stdout(io.StringIO()):
            with self.assertRaises(SystemExit) as ctx:
                audit_company.main()
        self.assertEqual(2, ctx.exception.code)


if __name__ == "__main__":
    unittest.main()
