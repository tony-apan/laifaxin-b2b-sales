# -*- coding: utf-8 -*-
"""离线验证保存状态监视，禁止真实网络。"""
import contextlib
import io
import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import save_company_cli as cli
import save_progress


class WatchTest(unittest.TestCase):
    def run_watch(self, responses, extra=(), task=True):
        out, err = io.StringIO(), io.StringIO()
        plan = {"plan_id": "p", "revision": 1, "project": "x", "query_scope": {"query_scope_key": "q"}}
        with patch.object(cli.planlib, "load_plan", return_value=plan),              patch.object(cli.planlib, "find_accepted_scope", return_value={}),              patch.object(cli.planlib, "record_status", return_value="r") as record,              patch.object(cli, "_http", return_value=lambda payload: next(responses)) as http,              patch("time.sleep") as sleep, contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            args = ["status", "--plan", "unused", "--watch", "--interval", "5", "--max-polls", "2"]
            if task:
                args += ["--task-id", "t", "--attempt-id", "a"]
            try:
                code = cli.main(args + list(extra))
            except (OSError, KeyboardInterrupt):
                self.fail("watch 应处理网络失败或中断")
        return code, out.getvalue(), err.getvalue(), record.call_args_list, http.call_count, sleep.call_count

    def test_running_finished_records_each_and_waits_reconcile(self):
        responses = iter([{"success": True, "data": {"status": "running", "finished": 8, "total": 8}},
                          {"success": True, "data": {"status": "finished", "finished": 8, "total": 8}}])
        code, out, err, records, calls, sleeps = self.run_watch(responses)
        self.assertEqual((code, len(records), calls, sleeps), (0, 2, 2, 1))
        self.assertIn("等待平台", err)
        self.assertIn("对账", err)
        self.assertEqual(records[0].kwargs["record"]["attempt_id"], "a")
        self.assertIn('"response"', out)

    def test_missing_counts_and_limit(self):
        response = {"success": True, "data": {"status": "running", "contactSaveCount": 99}}
        code, out, err, records, calls, sleeps = self.run_watch(iter([response, response]))
        self.assertNotEqual(code, 0)
        self.assertIn("未知", err)
        self.assertNotIn("99", err)
        self.assertEqual(len(records), 2)

    def test_failures_and_unknown_status(self):
        for response in ({"success": False}, [], {"success": True, "data": {"status": "mystery"}}):
            with self.subTest(response=response):
                code, _, _, records, calls, _ = self.run_watch(iter([response]))
                self.assertNotEqual(code, 0)
                self.assertEqual(len(records), 1)
        code, _, _, records, calls, _ = self.run_watch(iter([]), task=False)
        self.assertNotEqual(code, 0)
        self.assertEqual(calls, 0)

    def test_network_error_and_interrupt_stop(self):
        for error in (OSError("offline"), subprocess.TimeoutExpired("curl", 1), KeyboardInterrupt()):
            with self.subTest(error=type(error).__name__), \
                 patch.object(cli.planlib, "load_plan", return_value={"plan_id": "p"}), \
                 patch.object(cli, "_http", side_effect=error) as http, \
                 patch.object(cli.planlib, "record_status") as record, \
                 contextlib.redirect_stderr(io.StringIO()):
                code = cli.main(["status", "--plan", "unused", "--task-id", "t", "--watch"])
                self.assertNotEqual(code, 0)
                self.assertEqual(http.call_count, 1)
                record.assert_not_called()

    def test_default_single_json(self):
        out = io.StringIO()
        response = {"success": True, "data": {"status": "running"}}
        with patch.object(cli.planlib, "load_plan", return_value={"plan_id": "p"}), \
             patch.object(cli, "_http", return_value=lambda _: response) as http, \
             patch.object(cli.planlib, "record_status", return_value="r") as record, \
             contextlib.redirect_stdout(out):
            self.assertEqual(cli.main(["status", "--plan", "unused", "--task-id", "t"]), 0)
        self.assertEqual(http.call_count, 1)
        self.assertEqual(record.call_count, 1)
        self.assertIn('"response"', out.getvalue())

    def test_invalid_options_no_http(self):
        for option, value in [("--interval", "nan"), ("--interval", "inf"), ("--interval", "0"),
                              ("--interval", "-1"), ("--max-polls", "0"), ("--max-polls", "-1")]:
            with self.subTest(option=option, value=value):
                code, _, _, _, calls, _ = self.run_watch(iter([]), [option, value])
                self.assertNotEqual(code, 0)
                self.assertEqual(calls, 0)

    def test_eta_uses_only_observed_increment(self):
        cases = [([100, 110], [1000, 1000], [False, True]),
                 ([100, 100], [1000, 1000], [False, False]),
                 ([100, 90], [1000, 1000], [False, False]),
                 ([100, 110], [1000, 2000], [False, False]),
                 ([100, None], [1000, 1000], [False, False])]
        for counts, totals, expected in cases:
            with self.subTest(counts=counts, totals=totals):
                responses = iter([{"success": True, "data": {"status": "running", "finished": n, "total": t}}
                                  for n, t in zip(counts, totals)])
                with patch("time.monotonic", side_effect=[0, 5, 10, 15, 20, 25]):
                    _, _, err, _, _, _ = self.run_watch(responses)
                lines = [line for line in err.splitlines() if line.startswith("进度：")]
                self.assertEqual(["预计还要" in line for line in lines], expected)

    def test_accumulated_counts_do_not_imply_elapsed_rate(self):
        self.assertNotIn("预计还要", save_progress.format_progress(8, 9560, elapsed_s=0.3))
        self.assertNotIn("预计还要", save_progress.format_progress(800, 9560, elapsed_s=0.5))

    def test_format_rejects_invalid_counts_and_elapsed(self):
        for invalid in (True, 1.5, -1, float("nan"), float("inf"), "2"):
            with self.subTest(value=invalid):
                self.assertIn("未知", save_progress.format_progress(invalid, 10, elapsed_s=float("nan")))
        self.assertIn("999/100", save_progress.format_progress(999, 100))
        self.assertNotIn("快好了", save_progress.format_progress(1, 2, elapsed_s=float("nan")))
        self.assertNotIn("预计", save_progress.format_progress(1, 2, elapsed_s=10**1000))


if __name__ == "__main__":
    unittest.main()
