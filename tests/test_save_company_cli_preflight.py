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


if __name__ == "__main__":
    unittest.main()
