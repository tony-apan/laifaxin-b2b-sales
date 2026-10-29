#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""浏览器显式本机 CDP 接入的协议级回归（不连接真实浏览器/平台）。"""
import base64
import contextlib
import hashlib
import io
import json
import shlex
import http.server
import socket
import sys
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import browser_login as b  # noqa: E402

TOKEN = "aa&bb&cc"
ORG = "org-test-1"


class CDPStub:
    def __init__(self, include_token=True, mode="normal"):
        self.include_token = include_token
        self.mode = mode
        self.ws_hits = []
        outer = self

        class Handler(http.server.BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _json(self, obj):
                body = json.dumps(obj).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self):
                port = self.server.server_port
                if self.path == "/json/version":
                    if outer.mode == "redirect":
                        self.send_response(302)
                        self.send_header("Location", "https://example.com/")
                        self.end_headers()
                        return None
                    if outer.mode == "error":
                        self.send_response(500)
                        self.end_headers()
                        self.wfile.write(("boom " + TOKEN).encode())
                        return None
                    if outer.mode == "bad_json":
                        body = b"not-json"
                        self.send_response(200)
                        self.send_header("Content-Length", str(len(body)))
                        self.end_headers()
                        self.wfile.write(body)
                        return None
                    if outer.mode == "missing_ws":
                        return self._json({})
                    ws = ("ws://127.0.0.1:%d/devtools/browser/x" % port
                          if outer.mode != "external_ws" else "ws://example.com/devtools/browser/x")
                    return self._json({"webSocketDebuggerUrl": ws})
                if self.path == "/json/list":
                    return self._json([
                        {"id": "http-lfx", "type": "page", "url": "http://web.laifaxin.com/",
                         "webSocketDebuggerUrl": f"ws://127.0.0.1:{port}/devtools/page/http"},
                        {"id": "lfx", "type": "page", "url": "https://web.laifaxin.com/",
                         "webSocketDebuggerUrl": f"ws://127.0.0.1:{port}/devtools/page/lfx"},
                        {"id": "evil", "type": "page", "url": "https://example.com/",
                         "webSocketDebuggerUrl": f"ws://127.0.0.1:{port}/devtools/page/evil"},
                    ])
                if self.path.startswith("/devtools/page/") and self.headers.get("Upgrade", "").lower() == "websocket":
                    outer.ws_hits.append(self.path)
                    key = self.headers.get("Sec-WebSocket-Key", "")
                    accept = base64.b64encode(hashlib.sha1((key + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11").encode()).digest()).decode()
                    self.send_response(101)
                    self.send_header("Upgrade", "websocket")
                    self.send_header("Connection", "Upgrade")
                    self.send_header("Sec-WebSocket-Accept", accept)
                    self.end_headers()
                    time.sleep(0.02)
                    try:
                        self.request.recv(4096)
                    except OSError:
                        pass
                    values = ([{"host": "web.laifaxin.com", "accesstoken": TOKEN, "orgId": ORG}]
                              if outer.include_token else [])
                    payload = json.dumps({"id": 1, "result": {"result": {"value": values}}}).encode()
                    self.wfile.write(bytes([0x81, len(payload)]) + payload)
                    return None
                self.send_error(404)

        self.srv = http.server.HTTPServer(("127.0.0.1", 0), Handler)
        self.port = self.srv.server_port
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()

    def close(self):
        self.srv.shutdown()
        self.srv.server_close()


class CDPAdapterTest(unittest.TestCase):
    def test_endpoint_only_reads_laifaxin_and_hides_token(self):
        stub = CDPStub()
        self.addCleanup(stub.close)
        with mock.patch.object(b, "verify") as verify:
            code, result = b.connect_cdp(ROOT, f"127.0.0.1:{stub.port}", timeout=3)
        self.assertEqual(0, code)
        self.assertEqual("cdp", result["source"])
        self.assertEqual("verified", result["workspace"])
        self.assertEqual(["/devtools/page/lfx"], stub.ws_hits, "不得读取无关页面")
        verify.assert_called_once()
        self.assertNotIn(TOKEN, json.dumps(result), "结果不得回显凭据")

    def test_non_loopback_or_missing_port_rejected_before_connect(self):
        for value in ("example.com:9222", "127.0.0.1", "::1:9222", "127.0.0.1:0"):
            with self.subTest(value=value):
                with self.assertRaises(b.Failure):
                    b.connect_cdp(ROOT, value, timeout=1)

    def test_no_token_never_reports_success(self):
        stub = CDPStub(include_token=False)
        self.addCleanup(stub.close)
        with mock.patch.object(b, "verify"):
            with self.assertRaises(b.Failure) as cm:
                b.connect_cdp(ROOT, f"127.0.0.1:{stub.port}", timeout=0.2)
        self.assertIn(cm.exception.code, (10, 11))

    def test_http_laifaxin_page_never_evaluated(self):
        stub = CDPStub()
        self.addCleanup(stub.close)
        with mock.patch.object(b, "verify"):
            b.connect_cdp(ROOT, f"127.0.0.1:{stub.port}", timeout=3)
        self.assertEqual(["/devtools/page/lfx"], stub.ws_hits)

    def test_external_ws_redirect_and_error_body_rejected(self):
        for mode in ("external_ws", "redirect", "error"):
            with self.subTest(mode=mode):
                stub = CDPStub(mode=mode)
                try:
                    with self.assertRaises(b.Failure):
                        b.connect_cdp(ROOT, f"127.0.0.1:{stub.port}", timeout=1)
                finally:
                    stub.close()

    def test_workspace_conflict_never_success(self):
        stub = CDPStub()
        self.addCleanup(stub.close)
        with mock.patch.object(b, "verify", side_effect=b.Failure(15, "verify")):
            with self.assertRaises(b.Failure) as cm:
                b.connect_cdp(ROOT, f"127.0.0.1:{stub.port}", timeout=3)
        self.assertEqual(15, cm.exception.code)

    def test_external_browser_not_launched_closed_or_profiled(self):
        stub = CDPStub()
        self.addCleanup(stub.close)
        with mock.patch.object(b, "verify"), mock.patch.object(b, "launch") as launch, \
             mock.patch.object(b, "stop") as stop, mock.patch.object(b, "terminate_owner") as kill:
            b.connect_cdp(ROOT, f"127.0.0.1:{stub.port}", timeout=3)
        launch.assert_not_called(); stop.assert_not_called(); kill.assert_not_called()

    def test_main_output_has_no_token(self):
        stub = CDPStub()
        self.addCleanup(stub.close)
        buf = io.StringIO()
        with mock.patch.object(b, "verify"), contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
            code = b.main(["--cdp-endpoint", f"127.0.0.1:{stub.port}"])
        self.assertEqual(0, code)
        self.assertNotIn(TOKEN, buf.getvalue())

    def test_invalid_explicit_endpoint_does_not_fall_back(self):
        with mock.patch.object(b, "load_ready") as session, mock.patch.object(b, "execute") as visible:
            with self.assertRaises(b.Failure):
                b.connect_preferred("https://example.com:9222")
        session.assert_not_called(); visible.assert_not_called()

    def test_preferred_endpoint_success_skips_visible_window(self):
        stub = CDPStub()
        self.addCleanup(stub.close)
        with mock.patch.object(b, "load_ready", side_effect=b.SessionError("E_NO_SESSION", "missing")), \
             mock.patch.object(b, "verify"), mock.patch.object(b, "execute") as visible:
            code, result = b.connect_preferred(f"127.0.0.1:{stub.port}")
        self.assertEqual(0, code)
        self.assertEqual("cdp", result["source"])
        visible.assert_not_called()

    def _preferred_with_cdp_failure(self, failure):
        with mock.patch.object(b, "load_ready", side_effect=b.SessionError("E_NO_SESSION", "missing")), \
             mock.patch.object(b, "connect_cdp", side_effect=failure), \
             mock.patch.object(b, "execute") as visible:
            code, result = b.connect_preferred("127.0.0.1:9222")
        visible.assert_not_called()
        return code, result

    def test_workspace_conflict_stops_not_visible(self):
        code, result = self._preferred_with_cdp_failure(b.Failure(15, "verify"))
        self.assertEqual(15, code)
        self.assertEqual("stop", result["next"])
        self.assertEqual("E_CONFLICT", result["reason"])

    def test_login_verification_rejection_stops_not_visible(self):
        code, result = self._preferred_with_cdp_failure(b.Failure(12, "verify"))
        self.assertEqual(12, code)
        self.assertEqual("stop", result["next"])

    def test_transient_verification_keeps_diagnostic_and_stops(self):
        code, result = self._preferred_with_cdp_failure(b.Failure(23, "verify", "E_VERIFY_TRANSIENT"))
        self.assertEqual(23, code)
        self.assertEqual("stop", result["next"])
        self.assertEqual("E_VERIFY_TRANSIENT", result["reason"])

    def test_environment_unavailable_may_offer_visible(self):
        code, result = self._preferred_with_cdp_failure(b.Failure(11, "probe", "E_CDP_UNAVAILABLE"))
        self.assertEqual(11, code)
        self.assertEqual("visible", result["next"])

    def test_no_token_awaits_login_not_visible(self):
        code, result = self._preferred_with_cdp_failure(b.Failure(10, "read", "E_NO_TOKEN"))
        self.assertEqual(10, code)
        self.assertEqual("awaiting_login", result["next"])
        self.assertNotIn("--resume", result["resume"])
        self.assertIn("127.0.0.1:9222", result["resume"])

    def test_no_token_resume_rechecks_same_endpoint(self):
        calls = []

        def fake_connect(root, endpoint, timeout=30):
            calls.append(endpoint)
            if len(calls) == 1:
                raise b.Failure(10, "read", "E_NO_TOKEN")
            return 0, {"source": "cdp", "workspace": "verified"}

        with mock.patch.object(b, "load_ready", side_effect=b.SessionError("E_NO_SESSION", "missing")), \
             mock.patch.object(b, "connect_cdp", side_effect=fake_connect), \
             mock.patch.object(b, "execute") as visible:
            code, result = b.connect_preferred("127.0.0.1:9222")
            args = shlex.split(result["resume"])
            self.assertEqual(["--connect-preferred", "--cdp-endpoint", "127.0.0.1:9222"], args)
            self.assertEqual("127.0.0.1:9222", args[2])
            code2, result2 = b.connect_preferred(args[2])
        visible.assert_not_called()
        self.assertEqual(0, code2)
        self.assertEqual("cdp", result2["source"])
        self.assertEqual(["127.0.0.1:9222", "127.0.0.1:9222"], calls)

    def test_visible_profile_awaiting_login_keeps_resume(self):
        with mock.patch.object(b, "load_ready", side_effect=b.SessionError("E_NO_SESSION", "missing")), \
             mock.patch.object(b, "execute", side_effect=b.Failure(10, "read", "E_NO_TOKEN")):
            code, result = b.connect_preferred()
        self.assertEqual(10, code)
        self.assertEqual("awaiting_login", result["next"])
        self.assertEqual("--resume", result["resume"])

    def test_unknown_wait_failure_stops(self):
        code, result = self._preferred_with_cdp_failure(b.Failure(10, "wait"))
        self.assertEqual(10, code)
        self.assertEqual("stop", result["next"])

    def test_reachable_protocol_errors_stop_not_visible(self):
        for mode in ("external_ws", "redirect", "error", "bad_json", "missing_ws"):
            with self.subTest(mode=mode):
                stub = CDPStub(mode=mode)
                try:
                    with mock.patch.object(b, "load_ready", side_effect=b.SessionError("E_NO_SESSION", "missing")), \
                         mock.patch.object(b, "execute") as visible:
                        code, result = b.connect_preferred(f"127.0.0.1:{stub.port}")
                finally:
                    stub.close()
                self.assertNotEqual(0, code)
                self.assertEqual("stop", result["next"], mode)
                self.assertEqual("E_CDP_PROTOCOL", result["reason"], mode)
                self.assertNotEqual("E_CDP_UNAVAILABLE", result["reason"])
                visible.assert_not_called()

    def test_unreachable_explicit_endpoint_returns_visible_choice_not_success(self):
        stub = CDPStub(); port = stub.port; stub.close()
        with mock.patch.object(b, "load_ready", side_effect=b.SessionError("E_NO_SESSION", "missing")), \
             mock.patch.object(b, "execute") as visible:
            code, result = b.connect_preferred(f"127.0.0.1:{port}")
        self.assertNotEqual(0, code)
        self.assertEqual("visible", result["next"])
        self.assertEqual("cdp", result["source"])
        self.assertEqual("E_CDP_UNAVAILABLE", result["reason"])
        visible.assert_not_called()


if __name__ == "__main__":
    unittest.main()
