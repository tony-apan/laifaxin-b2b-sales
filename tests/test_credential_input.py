import io
import json
import os
import pty
import stat
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import BytesIO
from pathlib import Path
from urllib.error import HTTPError, URLError
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
sys.path.insert(0, str(TOOLS))

import check_login
from credential_input import Invalid, parse_credentials


TOKEN = "web.laifaxin.com&user-42&secret-value"
BLOB = f"accesstoken={TOKEN}\norgId=org-9\n"


class CredentialParserTest(unittest.TestCase):
    def test_accepts_line_endings_and_aliases(self):
        for sep, token_key, org_key in (
            ("\n", "accesstoken", "orgId"),
            ("\r\n", "TOKEN", "ORG"),
            ("\r", "accesstoken", "ORG"),
        ):
            with self.subTest(sep=repr(sep), token_key=token_key, org_key=org_key):
                parsed = parse_credentials(
                    f"{token_key}={TOKEN}{sep}{org_key}=org-9{sep}".encode()
                )
                self.assertEqual(parsed, (TOKEN, "org-9"))

    def test_rejects_bad_inputs(self):
        cases = {
            "duplicate alias": f"accesstoken={TOKEN}\nTOKEN={TOKEN}\norgId=x",
            "unknown line": f"accesstoken={TOKEN}\norgId=x\nextra=y",
            "unknown bare line": f"accesstoken={TOKEN}\norgId=x\nwat",
            "null": f"accesstoken={TOKEN}\norgId=null",
            "empty": f"accesstoken={TOKEN}\norgId=",
            "whitespace": f"accesstoken={TOKEN}\norgId=two words",
            "control": f"accesstoken={TOKEN}\norgId=x\x00y",
            "two token segments": "accesstoken=a&b\norgId=x",
            "four token segments": "accesstoken=a&b&c&d\norgId=x",
            "empty first": "accesstoken=&b&c\norgId=x",
            "empty middle": "accesstoken=a&&c\norgId=x",
            "empty third": "accesstoken=a&b&\norgId=x",
        }
        for label, value in cases.items():
            with self.subTest(label=label), self.assertRaises(Invalid):
                parse_credentials(value.encode())

    def test_rejects_oversize_and_invalid_utf8(self):
        with self.assertRaises(Invalid):
            parse_credentials(b"x" * 8193)
        with self.assertRaises(Invalid):
            parse_credentials(b"accesstoken=a&b&c\norgId=\xff")


class LoginTest(unittest.TestCase):
    def run_main(self, argv, raw=BLOB.encode(), responses=None, tty=False):
        out, err = io.StringIO(), io.StringIO()
        stdin = mock.Mock()
        stdin.isatty.return_value = tty
        stdin.buffer.read.return_value = raw
        request_mock = mock.Mock(side_effect=responses or [])
        sleeps = []
        with tempfile.TemporaryDirectory() as tmp, redirect_stdout(out), redirect_stderr(err):
            rc = check_login.main(
                argv,
                stdin=stdin,
                request=request_mock,
                sleep=sleeps.append,
                fail_file=Path(tmp) / "token-fail.json",
            )
            fail = Path(tmp) / "token-fail.json"
            saved = fail.read_text(encoding="utf-8") if fail.exists() else ""
        return rc, out.getvalue(), err.getvalue(), request_mock, sleeps, saved, stdin

    def run_real_request(self, error):
        out, err = io.StringIO(), io.StringIO()
        stdin = mock.Mock()
        stdin.isatty.return_value = False
        stdin.buffer.read.return_value = BLOB.encode()
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(
            check_login.request, "urlopen", side_effect=error
        ), redirect_stdout(out), redirect_stderr(err):
            rc = check_login.main(
                ["--credentials-stdin"],
                stdin=stdin,
                request=check_login.request_once,
                sleep=lambda _: None,
                fail_file=Path(tmp) / "token-fail.json",
            )
            fail = Path(tmp) / "token-fail.json"
            saved = fail.read_text(encoding="utf-8") if fail.exists() else ""
        return rc, out.getvalue(), err.getvalue(), saved

    def test_stdin_success_and_http_receives_header_outside_argv(self):
        response = {"success": True, "data": {"vip": 2}}
        rc, out, err, request_mock, _, _, _ = self.run_main(
            ["--credentials-stdin", "--gate-mode"], responses=[response]
        )
        self.assertEqual(rc, 0, out + err)
        self.assertIn("登录校验通过", out)
        self.assertNotIn(TOKEN, out + err)
        self.assertEqual(request_mock.call_args.args, (TOKEN, "org-9"))

    def test_success_response_fields_cannot_echo_token(self):
        response = {
            "success": True,
            "data": {
                "vip": TOKEN,
                "dailyLimit": TOKEN,
                "dailyUsed": TOKEN,
                "monthlyLimit": TOKEN,
                "monthlyUsed": TOKEN,
                "monthlyChargeCount": TOKEN,
                "monthlyAutoCharge": TOKEN,
            },
        }
        rc, out, err, _, _, _, _ = self.run_main(
            ["--credentials-stdin"], responses=[response]
        )
        self.assertEqual(rc, 0, out + err)
        self.assertNotIn(TOKEN, out + err)
        self.assertNotIn("user-42", out + err)
        self.assertNotIn("org-9", out + err)
        self.assertIn("***r-42", out)
        self.assertIn("*rg-9", out)
        self.assertNotIn("本月充值", out)

    def test_success_outputs_whitelisted_monthly_charge_fields(self):
        response = {
            "success": True,
            "data": {"monthlyChargeCount": 3, "monthlyAutoCharge": True},
        }
        rc, out, err, _, _, _, _ = self.run_main(
            ["--credentials-stdin"], responses=[response]
        )
        self.assertEqual(rc, 0, out + err)
        self.assertIn("本月充值：3 次（自动充值：已开启）", out)
        self.assertNotIn(TOKEN, out + err)

    def test_success_omits_monthly_charge_when_fields_are_missing(self):
        rc, out, err, _, _, _, _ = self.run_main(
            ["--credentials-stdin"], responses=[{"success": True, "data": {}}]
        )
        self.assertEqual(rc, 0, out + err)
        self.assertNotIn("本月充值", out)

    def test_identifier_mask_hides_short_values(self):
        self.assertEqual(check_login.mask_identifier("abcd"), "****")
        self.assertEqual(check_login.mask_identifier("abc"), "***")
        self.assertEqual(check_login.mask_identifier("abcdef"), "**cdef")

    def test_http_error_json_is_business_response_and_redacted(self):
        error = HTTPError(
            "https://example.invalid", 401, "unauthorized", {},
            BytesIO(json.dumps({"success": False, "message": f"失效: {TOKEN}"}).encode()),
        )
        rc, out, err, saved = self.run_real_request(error)
        self.assertEqual(rc, 1, out + err)
        self.assertNotIn(TOKEN, out + err + saved)
        self.assertEqual(set(json.loads(saved)), {"token_hash", "count", "last"})

    def test_http_error_non_json_is_platform_error(self):
        error = HTTPError(
            "https://example.invalid", 502, "bad gateway", {}, BytesIO(b"not json")
        )
        rc, out, err, saved = self.run_real_request(error)
        self.assertEqual(rc, 3, out + err)
        self.assertEqual(saved, "")
        self.assertNotIn("not json", out + err)
        self.assertIn("平台返回错误页/非JSON", err)
        self.assertNotIn("网络不通", out + err)

    def test_url_error_and_timeout_are_network_errors(self):
        for failure in (URLError("offline"), TimeoutError("slow")):
            with self.subTest(failure=type(failure).__name__):
                rc, out, err, saved = self.run_real_request(failure)
                self.assertEqual(rc, 3, out + err)
                self.assertEqual(saved, "")

    def test_org_is_urlencoded_in_request_url(self):
        response = mock.MagicMock()
        response.__enter__.return_value.read.return_value = b'{"success": true}'
        with mock.patch.object(check_login.request, "urlopen", return_value=response) as urlopen:
            result = check_login.request_once(TOKEN, "org?x=1&y=2")
        self.assertTrue(result["success"])
        request_object = urlopen.call_args.args[0]
        self.assertIn("uid=org%3Fx%3D1%26y%3D2", request_object.full_url)
        self.assertNotIn("org?x=1&y=2", request_object.full_url)

    def test_invalid_token_response_is_redacted_and_hash_only_is_saved(self):
        response = {"success": False, "message": f"失效: {TOKEN}"}
        rc, out, err, _, _, saved, _ = self.run_main(
            ["--credentials-stdin"], responses=[response]
        )
        self.assertEqual(rc, 1)
        self.assertNotIn(TOKEN, out + err + saved)
        record = json.loads(saved)
        self.assertEqual(set(record), {"token_hash", "count", "last"})
        self.assertEqual(record["count"], 1)

    def test_failure_file_is_mode_600(self):
        with tempfile.TemporaryDirectory() as tmp:
            fail_file = Path(tmp) / "token-fail.json"
            check_login._record_failure(TOKEN, fail_file, lambda: "now")
            self.assertEqual(stat.S_IMODE(fail_file.stat().st_mode), 0o600)
            self.assertEqual(
                set(json.loads(fail_file.read_text(encoding="utf-8"))),
                {"token_hash", "count", "last"},
            )
            self.assertEqual(list(fail_file.parent.glob(".token-fail.json.*.tmp")), [])

    def test_failure_file_fchmods_descriptor_before_write(self):
        with tempfile.TemporaryDirectory() as tmp:
            fail_file = Path(tmp) / "token-fail.json"
            events = []
            real_fchmod = os.fchmod
            real_fdopen = os.fdopen

            def tracked_fchmod(descriptor, mode):
                events.append(("fchmod", mode))
                return real_fchmod(descriptor, mode)

            def tracked_fdopen(descriptor, *args, **kwargs):
                events.append(("fdopen", None))
                return real_fdopen(descriptor, *args, **kwargs)

            with mock.patch.object(check_login.os, "fchmod", side_effect=tracked_fchmod), mock.patch.object(
                check_login.os, "fdopen", side_effect=tracked_fdopen
            ):
                check_login._record_failure(TOKEN, fail_file, lambda: "now")
            self.assertEqual(events[0], ("fchmod", 0o600))
            self.assertEqual(events[1], ("fdopen", None))
            self.assertEqual(stat.S_IMODE(fail_file.stat().st_mode), 0o600)

    def test_failure_record_fchmod_error_still_uses_mkstemp_mode(self):
        with tempfile.TemporaryDirectory() as tmp:
            fail_file = Path(tmp) / "token-fail.json"
            with mock.patch.object(check_login.os, "fchmod", side_effect=OSError("unsupported")):
                count = check_login._record_failure(TOKEN, fail_file, lambda: "now")
            self.assertEqual(count, 1)
            self.assertEqual(stat.S_IMODE(fail_file.stat().st_mode), 0o600)
            self.assertEqual(
                set(json.loads(fail_file.read_text(encoding="utf-8"))),
                {"token_hash", "count", "last"},
            )

    def test_failure_record_chmod_error_still_replaces_complete_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            fail_file = Path(tmp) / "token-fail.json"
            with mock.patch.object(check_login.os, "chmod", side_effect=OSError("unsupported")):
                count = check_login._record_failure(TOKEN, fail_file, lambda: "now")
            self.assertEqual(count, 1)
            self.assertEqual(
                set(json.loads(fail_file.read_text(encoding="utf-8"))),
                {"token_hash", "count", "last"},
            )

    def test_failure_record_write_error_does_not_change_invalid_exit(self):
        with mock.patch.object(check_login, "_record_failure", side_effect=OSError("denied")):
            rc, out, err, _, _, _, _ = self.run_main(
                ["--credentials-stdin"],
                responses=[{"success": False, "message": "失效"}],
            )
        self.assertEqual(rc, 1, out + err)

    def test_network_error_is_exit_three_and_redacted(self):
        rc, out, err, _, _, _, _ = self.run_main(
            ["--credentials-stdin"], responses=[RuntimeError(TOKEN)]
        )
        self.assertEqual(rc, 3)
        self.assertNotIn(TOKEN, out + err)

    def test_empty_response_retries_three_times_with_five_second_delays(self):
        rc, _, _, request_mock, sleeps, _, _ = self.run_main(
            ["--credentials-stdin", "--gate-mode"], responses=[None, None, None]
        )
        self.assertEqual(rc, 3)
        self.assertEqual(request_mock.call_count, 3)
        self.assertEqual(sleeps, [5, 5])

    def test_legacy_requires_both_values_and_never_falls_back(self):
        rc, _, _, request_mock, _, _, _ = self.run_main(["--token", TOKEN], raw=b"")
        self.assertEqual(rc, 2)
        request_mock.assert_not_called()

    def test_stdin_and_legacy_cannot_mix(self):
        rc, _, _, request_mock, _, _, _ = self.run_main(
            ["--credentials-stdin", "--token", TOKEN, "--org", "org-9"]
        )
        self.assertEqual(rc, 2)
        request_mock.assert_not_called()

    def test_pipe_without_flag_is_not_read(self):
        rc, out, _, request_mock, _, _, stdin = self.run_main([], raw=BLOB.encode())
        self.assertEqual(rc, 2)
        self.assertIn("聊天框", out)
        stdin.buffer.read.assert_not_called()
        request_mock.assert_not_called()

    def test_tty_stdin_exits_quickly_without_reading(self):
        rc, _, _, request_mock, _, _, stdin = self.run_main(
            ["--credentials-stdin"], tty=True
        )
        self.assertEqual(rc, 2)
        stdin.buffer.read.assert_not_called()
        request_mock.assert_not_called()

    def test_real_pty_exits_without_waiting(self):
        master, slave = pty.openpty()
        try:
            proc = subprocess.run(
                [sys.executable, str(TOOLS / "check_login.py"), "--credentials-stdin"],
                stdin=slave,
                capture_output=True,
                timeout=2,
            )
        finally:
            os.close(master)
            os.close(slave)
        self.assertEqual(proc.returncode, 2)


class ShellRoutingTest(unittest.TestCase):
    def run_script(self, name, args=(), input_text=None):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            capture = tmp_path / "capture.jsonl"
            fake = tmp_path / "python3"
            # 追加写入：脚本可能调用多个 python3 工具（登录校验 + 工作空间校验），全部记录
            fake.write_text(
                "#!/bin/sh\n"
                "\"$REAL_PYTHON\" -c 'import json,os,sys; "
                "open(os.environ[\"CAPTURE\"],\"a\").write(json.dumps({\"argv\":sys.argv[1:],\"stdin\":sys.stdin.read()})+\"\\n\")' \"$@\"\n"
                "exit \"${FAKE_RC:-0}\"\n",
                encoding="utf-8",
            )
            fake.chmod(0o755)
            env = os.environ.copy()
            env.update({
                "PATH": f"{tmp}{os.pathsep}{env.get('PATH', '')}",
                "REAL_PYTHON": sys.executable,
                "CAPTURE": str(capture),
                "FAKE_RC": "0",
            })
            result = subprocess.run(
                ["bash", str(TOOLS / name), *args],
                cwd=ROOT,
                input=input_text,
                text=True,
                capture_output=True,
                env=env,
                timeout=5,
            )
            calls = ([json.loads(line) for line in capture.read_text(encoding="utf-8").splitlines() if line]
                     if capture.exists() else [])
            return result, calls

    def test_gate_routes_stdin_without_token_argv(self):
        result, calls = self.run_script("gate_check.sh", ["--credentials-stdin"], BLOB)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertTrue(calls, "gate_check.sh 应至少调用一次 python3 工具")
        for call in calls:
            self.assertEqual(call["stdin"], BLOB)  # 凭据原样转发（含末尾换行），不得改写
            self.assertIn("--credentials-stdin", call["argv"])
            self.assertNotIn(TOKEN, " ".join(call["argv"]))
        login = next(c for c in calls if any("check_login.py" in a for a in c["argv"]))
        self.assertIn("--gate-mode", login["argv"])
        self.assertTrue(any("workspace_guard.py" in a for c in calls for a in c["argv"]),
                        "gate_check.sh 必须做工作空间落点校验")

    def test_rules_routes_stdin_without_token_argv(self):
        result, calls = self.run_script("check_rules.sh", ["--credentials-stdin"], BLOB)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertTrue(calls)
        self.assertEqual(calls[0]["stdin"], BLOB)
        self.assertNotIn(TOKEN, " ".join(calls[0]["argv"]))

    def test_rules_without_credentials_is_offline_and_does_not_run_python(self):
        result, calls = self.run_script("check_rules.sh")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual([], calls)
        self.assertIn("未做登录校验", result.stdout)
        self.assertNotIn("token有效", result.stdout)

    def test_shell_help_marks_legacy_arguments_deprecated_and_unsafe(self):
        for name in ("gate_check.sh", "check_rules.sh"):
            with self.subTest(name=name):
                result, calls = self.run_script(name, ["--help"])
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertEqual([], calls)
                self.assertIn("deprecated", result.stdout.lower())
                self.assertIn("argv", result.stdout.lower())
                self.assertNotIn(TOKEN, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
