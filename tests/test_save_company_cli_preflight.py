# -*- coding: utf-8 -*-
"""save_company_cli.execute 的 workspace_guard 预检回归（P0-2）。

RULES 声称保存链内置 workspace_guard 预检：execute 真正写之前必须先调
workspace_guard.preflight()；预检阻断/异常时不得构造 transport、不得调保存接口。
"""
import inspect
import io
import json
import sys
import tempfile
import types
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

# tools/search_company.py 依赖仓库中尚不存在的 segment_fields 模块（不在本次修复范围）；
# 这里注入最小桩，让 save_company_cli 可导入，从而能验证 execute 的真实预检顺序。
if "segment_fields" not in sys.modules:
    try:
        import segment_fields  # noqa: F401
    except ModuleNotFoundError:
        _stub = types.ModuleType("segment_fields")

        class _SegmentFieldError(Exception):
            pass

        def _assert_search_keyword(*args, **kwargs):
            return None

        _stub.SegmentFieldError = _SegmentFieldError
        _stub.assert_search_keyword = _assert_search_keyword
        sys.modules["segment_fields"] = _stub

import save_company_cli as cli  # noqa: E402


class WorkspaceGuardPreflightTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.plan = Path(self.tmp.name) / "plan.json"
        self.plan.write_text(json.dumps({
            "kind": "save_plan",
            "plan_id": "p-test", "revision": 1,
            "wire_payload": {"keyword": "seed.example"},
        }, ensure_ascii=False), encoding="utf-8")
        self.args = SimpleNamespace(
            token="web.laifaxin.com&uid&hash", org="org-test", plan=str(self.plan),
            ticket_json="{}", ticket_file=None, render=str(Path(self.tmp.name) / "render.json"),
            root=self.tmp.name, timeout=1, run="test-run",
        )

    def tearDown(self):
        self.tmp.cleanup()

    def test_blocked_preflight_makes_zero_http_writes(self):
        with mock.patch.object(cli.workspace_guard, "preflight",
                               side_effect=SystemExit(1)) as preflight, \
             mock.patch.object(cli.save_guard, "save_company_v2") as save_v2:
            buffer = io.StringIO()
            with redirect_stdout(buffer):
                rc = cli._cmd_execute(self.args)
        self.assertEqual(2, rc, buffer.getvalue())
        preflight.assert_called_once()
        save_v2.assert_not_called()
        self.assertIn("E_WORKSPACE_GUARD", buffer.getvalue())

    def test_preflight_runs_before_save_call(self):
        order = []

        def fake_preflight(token, org, dry_run=False, what=""):
            order.append("preflight")
            return ""

        def fake_save(**kwargs):
            order.append("save")
            return {"ok": True, "report_text": ""}

        with mock.patch.object(cli.workspace_guard, "preflight", side_effect=fake_preflight), \
             mock.patch.object(cli.save_guard, "save_company_v2", side_effect=fake_save):
            with redirect_stdout(io.StringIO()):
                rc = cli._cmd_execute(self.args)
        self.assertEqual(0, rc)
        self.assertEqual(["preflight", "save"], order)

    def test_execute_source_orders_preflight_before_save(self):
        source = inspect.getsource(cli._cmd_execute)
        self.assertIn("workspace_guard.preflight(", source)
        self.assertLess(source.index("workspace_guard.preflight("),
                        source.index("save_guard.save_company_v2("))


class ConfirmPresentationBindingTest(unittest.TestCase):
    """TASK-20261027：CLI confirm 必须显式携带 --presentation（卡引用）。

    隐式拿最新卡会把旧确认套进新计划；缺引用直接 E_CARD_REQUIRED，不铸票。
    """

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.plan = self.root / "plan.json"
        self.plan.write_text(json.dumps({
            "kind": "save_plan", "plan_id": "p-cc", "revision": 1,
            "status": "draft", "project": "op/prod",
            "wire_payload": {"keyword": "seed.example"},
        }, ensure_ascii=False), encoding="utf-8")
        self.addCleanup(self.tmp.cleanup)

    def test_confirm_without_presentation_denied_before_confirm(self):
        args = SimpleNamespace(root=str(self.root), plan=str(self.plan),
                               quote="确认", quote_ref="ref-1",
                               presentation=None)
        with mock.patch.object(cli.planlib, "confirm_plan") as confirm, \
             mock.patch.object(cli.auth_guard, "authorize_save_plan") as auth:
            buffer = io.StringIO()
            with redirect_stdout(buffer):
                rc = cli._cmd_confirm(args)
        self.assertEqual(2, rc, buffer.getvalue())
        out = json.loads(buffer.getvalue())
        self.assertEqual("E_CARD_REQUIRED", out["code"])
        confirm.assert_not_called()
        auth.assert_not_called()

    def test_present_then_confirm_passes_card_ref_through(self):
        card_ref = "card-" + "0" * 15 + "1"
        args = SimpleNamespace(root=str(self.root), plan=str(self.plan),
                               quote="20", quote_ref=card_ref,
                               presentation=card_ref)
        confirmed = {"status": "confirmed", "plan_id": "p-cc", "revision": 1,
                     "project": "op/prod", "selectTotal": 20,
                     "quote": "20", "quote_ref": card_ref,
                     "wire_payload": {"keyword": "seed.example"},
                     "computed": {"estimated_points": "45"},
                     "confirmed_at": "2026-10-27T00:00:00Z"}
        render = {"path": str(self.root / "render.json"), "task": "t-cc"}
        issued = {"ok": True, "ticket_path": str(self.root / "t.json")}
        with mock.patch.object(cli.planlib, "load_plan",
                               return_value=confirmed), \
             mock.patch.object(cli.planlib, "confirm_plan",
                               return_value=confirmed) as confirm, \
             mock.patch.object(cli, "_make_render", return_value=render), \
             mock.patch.object(cli.auth_guard, "authorize_save_plan",
                               return_value=issued):
            buffer = io.StringIO()
            with redirect_stdout(buffer):
                rc = cli._cmd_confirm(args)
        self.assertEqual(0, rc, buffer.getvalue())
        confirm.assert_called_once()
        kwargs = confirm.call_args.kwargs
        self.assertEqual(card_ref, kwargs.get("presentation"))


class ConfirmNoFalseStateOnAuthDenyTest(unittest.TestCase):
    """真实 prepare/present/CLI 确认，检查规范计划路径。"""

    def setUp(self):
        from test_save_confirm_plain import CountCardChainTest
        self.case = CountCardChainTest()
        self.case.setUp()
        self.addCleanup(self.case.doCleanups)
        self.draft = self.case._prepare()
        self.card = self.case._present(self.draft)
        self.args = SimpleNamespace(root=str(self.case.root), plan=str(self.draft),
                                    quote="20", quote_ref=self.card["card_ref"],
                                    presentation=self.card["card_ref"])
        self.path = cli.planlib.plan_path(self.case.root, "plan-cc1", 1)

    def run_confirm(self, result):
        v, s = self.case._registry_stub()
        with v, s, mock.patch.object(cli.auth_guard, "authorize_save_plan", return_value=result), \
             redirect_stdout(io.StringIO()):
            return cli._cmd_confirm(self.args)

    def test_auth_deny_leaves_no_confirmed_state(self):
        self.assertEqual(2, self.run_confirm({"ok": False, "code": "DENY", "reason": "deny"}))
        self.assertNotEqual("confirmed", json.loads(self.path.read_text())["status"])
        with self.assertRaises(cli.planlib.PlanError):
            cli.planlib.load_confirmed(self.case.root, "plan-cc1", 1)
        plan = cli.planlib.load_plan(self.path)
        http = mock.Mock()
        v, s = self.case._registry_stub()
        with v, s:
            result = cli.save_guard.save_company_v2(payload=plan["wire_payload"], http=http,
                                                    plan=plan, ticket={}, root=self.case.root)
        self.assertFalse(result["ok"])
        http.assert_not_called()

    def test_exceptions_leave_no_executable_plan(self):
        for target in ("_make_render", "authorize_save_plan", "commit_confirmed"):
            with self.subTest(target=target):
                owner = cli if target == "_make_render" else (cli.auth_guard if target == "authorize_save_plan" else cli.planlib)
                v, s = self.case._registry_stub()
                with v, s, mock.patch.object(cli.auth_guard, "authorize_save_plan", return_value={"ok": True, "ticket_path": "ticket"}), \
                     mock.patch.object(owner, target, side_effect=RuntimeError("injected")), \
                     redirect_stdout(io.StringIO()):
                    self.assertEqual(2, cli._cmd_confirm(self.args))
                with self.assertRaises(cli.planlib.PlanError):
                    cli.planlib.load_confirmed(self.case.root, "plan-cc1", 1)

    def test_different_card_cannot_replace_success(self):
        ok = {"ok": True, "ticket_path": "ticket"}
        self.assertEqual(0, self.run_confirm(ok))
        before = self.path.read_bytes()
        from test_save_confirm_plain import _CC_NOW
        other = cli.planlib.present_card(self.case.root, self.draft, now=_CC_NOW["t"] - 60)
        self.args.presentation = other["card_ref"]
        self.args.quote_ref = other["card_ref"]
        self.assertEqual(2, self.run_confirm(ok))
        self.assertEqual(before, self.path.read_bytes())

    def test_success_commits_confirmed_once(self):
        ok = {"ok": True, "ticket_path": str(self.case.root / "ticket.json")}
        self.assertEqual(0, self.run_confirm(ok))
        before = self.path.read_bytes()
        self.assertEqual("confirmed", cli.planlib.load_confirmed(self.case.root, "plan-cc1", 1)["status"])
        self.assertEqual(2, self.run_confirm({"ok": False, "code": "DENY", "reason": "deny"}))
        self.assertEqual(before, self.path.read_bytes())
        self.assertEqual("confirmed", cli.planlib.load_confirmed(self.case.root, "plan-cc1", 1)["status"])


class StatusAutoTaskIdTest(unittest.TestCase):
    """保存成功后 status 不必手工喂 task_id：从已受理 scope 账本自解析。"""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.scopes = self.root / ".local" / "guard_v2" / "scopes"
        self.scopes.mkdir(parents=True)
        self.plan = self.root / "plan.json"
        self.plan.write_text(json.dumps({
            "kind": "save_plan", "plan_id": "p-1", "revision": 1,
            "project": "tony/x", "query_scope": {"query_scope_key": "abc"},
            "wire_payload": {"keyword": "k"},
        }, ensure_ascii=False), encoding="utf-8")
        self.args = SimpleNamespace(
            token="t", org="o", plan=str(self.plan), task_id=None,
            attempt_id=None, root=str(self.root), timeout=1,
        )

    def tearDown(self):
        self.tmp.cleanup()

    def _write_scope(self, **overrides):
        scope = {
            "kind": "query_scope", "query_scope_key": "abc",
            "owner": "owner-1", "attempt_id": "att-1",
            "plan_id": "p-1", "revision": 1, "state": "accepted",
            "task_id": "task-9", "transport_started": True,
        }
        scope.update(overrides)
        (self.scopes / "scope-abc.json").write_text(
            json.dumps(scope, ensure_ascii=False), encoding="utf-8")

    def test_status_reads_task_id_from_accepted_scope(self):
        self._write_scope()
        seen = {}

        def fake_http(token, org, timeout, endpoint=None):
            def call(payload):
                seen["payload"] = payload
                return {"success": True, "data": {"status": "finished"}}
            return call

        with mock.patch.object(cli, "_http", side_effect=fake_http):
            buffer = io.StringIO()
            with redirect_stdout(buffer):
                rc = cli._cmd_status(self.args)
        self.assertEqual(0, rc, buffer.getvalue())
        out = json.loads(buffer.getvalue())
        self.assertEqual("task-9", out["task_id"])
        records = list((self.root / ".local" / "guard_v2" / "status-ledger").glob("rec-*.json"))
        self.assertEqual(1, len(records), "应落一条 status 记录")
        record = json.loads(records[0].read_text(encoding="utf-8"))
        self.assertEqual("att-1", record.get("attempt_id"))
        self.assertIn("payload", seen)

    def test_status_ignores_stale_or_unaccepted_scope(self):
        self._write_scope(state="attempted", task_id="")
        with mock.patch.object(cli, "_http") as http:
            buffer = io.StringIO()
            with redirect_stdout(buffer):
                rc = cli._cmd_status(self.args)
        self.assertEqual(2, rc, buffer.getvalue())
        self.assertIn("E_RECONCILE_SOURCE", buffer.getvalue())
        http.assert_not_called()

    def test_status_does_not_borrow_other_plan_scope(self):
        self._write_scope(plan_id="p-other")
        with mock.patch.object(cli, "_http") as http:
            buffer = io.StringIO()
            with redirect_stdout(buffer):
                rc = cli._cmd_status(self.args)
        self.assertEqual(2, rc, buffer.getvalue())
        http.assert_not_called()


if __name__ == "__main__":
    unittest.main()
