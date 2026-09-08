import datetime
import hashlib
import json
import os
import pty
import select
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FLOW_FILES = (
    "flow_orchestrator.py",
    "approval.py",
    "compliance_validation.py",
    "evidence_validation.py",
    "profile_utils.py",
    "update_run_state.py",
)
SEQ = "0123456789abcdef01234567"
ORG = "org-for-s12-tests"


def stable_hash(value):
    canonical = json.dumps(value, sort_keys=True, ensure_ascii=True, separators=(",", ":"), default=str)
    return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


class ResumeS12Test(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmp.name)
        (self.repo / "tools").mkdir()
        for name in FLOW_FILES:
            shutil.copy2(ROOT / "tools" / name, self.repo / "tools" / name)
        self.project = "operator/product"
        self.project_dir = self.repo / "runs" / "operator" / "product"
        self.project_dir.mkdir(parents=True)
        self.profile = self.project_dir / "product-profile.md"
        fields = "\n".join(
            f"## {'①②③④⑤⑥⑦⑧'[i - 1]} field\n- 内容：待补\n- source: none\n- confidence: low"
            for i in range(1, 9)
        )
        self.profile.write_text(
            "---\nprofile_version: 1\nstatus: declined\noperator_key: operator\n"
            "product_key: product\ncreated_at: 2026-09-07\nupdated_at: 2026-09-07\n"
            "sources_status: declined\nsources_present: no\n---\n\n" + fields + "\n",
            encoding="utf-8",
        )
        self.record = self.project_dir / "operation-record.md"
        self.write_record("S11")
        self.compliance = self.project_dir / "compliance.json"
        self.write_compliance()

    def tearDown(self):
        self.tmp.cleanup()

    def write_record(self, status, seq=SEQ, **extra):
        values = {
            "status": status,
            "next_state": "S12",
            "operator_key": "operator",
            "product_key": "product",
            "project": self.project,
            "sequence_id": seq,
            **extra,
        }
        body = "\n".join(f'{key}: "{value}"' for key, value in values.items())
        self.record.write_text(f"---\n{body}\n---\n", encoding="utf-8")

    def write_compliance(self, *, seq=SEQ, profile_sha=None, checked_at=None, bad_key=None,
                         evidence_mode="live", source="manual review", detail="reviewed and verified"):
        checked_at = checked_at or datetime.datetime.now().isoformat(timespec="seconds")
        evidence = {"source": source, "detail": detail, "checked_at": checked_at}
        doc = {
            "project": self.project,
            "seq": seq,
            "profile_sha256": profile_sha or hashlib.sha256(self.profile.read_bytes()).hexdigest(),
            "checked_at": checked_at,
            "evidence_mode": evidence_mode,
        }
        for key in ("market", "list_source", "sender_identity", "unsubscribe", "suppression"):
            doc[key] = {"status": "fail" if key == bad_key else "pass", "evidence": dict(evidence)}
        self.compliance.write_text(json.dumps(doc), encoding="utf-8")

    def command(self, *extra):
        return [
            sys.executable,
            str(self.repo / "tools" / "flow_orchestrator.py"),
            "--org", ORG,
            "--profile", str(self.profile),
            "--resume-s12",
            "--seq", SEQ,
            "--compliance-file", str(self.compliance),
            *extra,
        ]

    def run_non_tty(self, *extra):
        return subprocess.run(self.command(*extra), input="确认激活\n", text=True, capture_output=True, timeout=10)

    def run_tty(self, answer):
        master, slave = pty.openpty()
        proc = subprocess.Popen(
            self.command(), stdin=slave, stdout=slave, stderr=slave,
            cwd=self.repo, close_fds=True,
        )
        os.close(slave)
        output = bytearray()
        sent = False
        deadline = time.monotonic() + 10
        try:
            while time.monotonic() < deadline:
                ready, _, _ = select.select([master], [], [], 0.1)
                if ready:
                    try:
                        chunk = os.read(master, 4096)
                    except OSError:
                        break
                    if not chunk:
                        break
                    output.extend(chunk)
                    if not sent and "确认节点 S12_激活".encode() in output:
                        os.write(master, (answer + "\n").encode())
                        sent = True
                if proc.poll() is not None:
                    break
            returncode = proc.wait(timeout=2)
        finally:
            os.close(master)
            if proc.poll() is None:
                proc.kill()
                proc.wait()
        return returncode, output.decode("utf-8", errors="replace")

    def run_ordinary_tty(self):
        check_login = self.repo / "tools" / "check_login.py"
        check_login.write_text("raise SystemExit(0)\n", encoding="utf-8")
        flow = self.repo / "tools" / "flow_orchestrator.py"
        source = flow.read_text(encoding="utf-8")
        api_start = source.index("def api(")
        api_end = source.index("LOGIN_GUIDE_URL", api_start)
        source = source[:api_start] + "def api(path, p, t=60):\n    return {}\n\n" + source[api_end:]
        flow.write_text(source, encoding="utf-8")
        self.write_record("S1")
        plan = self.project_dir / "plan.json"
        tmap = self.project_dir / "tmap.json"
        plan.write_text("{}\n", encoding="utf-8")
        tmap.write_text("{}\n", encoding="utf-8")
        command = [
            sys.executable, str(flow), "--token", "local-test-token", "--org", ORG,
            "--nickname", "Tony", "--product", "product", "--product-info", "金属粉末产品说明",
            "--profile", str(self.profile), "--seed", "example.com", "--save-n", "10",
            "--plan", str(plan), "--tmap", str(tmap), "--seq", SEQ,
            "--contact-tags", "tag-1", "--task", "task-1", "--compliance-file", str(self.compliance),
        ]
        master, slave = pty.openpty()
        proc = subprocess.Popen(command, stdin=slave, stdout=slave, stderr=slave, cwd=self.repo, close_fds=True)
        os.close(slave)
        output = bytearray()
        answered = 0
        deadline = time.monotonic() + 10
        try:
            while time.monotonic() < deadline:
                ready, _, _ = select.select([master], [], [], 0.1)
                if ready:
                    try:
                        chunk = os.read(master, 4096)
                    except OSError:
                        break
                    if not chunk:
                        break
                    output.extend(chunk)
                    prompts = output.count("回复「确认」继续".encode())
                    while answered < prompts:
                        os.write(master, "确认\n".encode())
                        answered += 1
                if proc.poll() is not None:
                    break
            returncode = proc.wait(timeout=2)
        finally:
            os.close(master)
            if proc.poll() is None:
                proc.kill()
                proc.wait()
        return returncode, output.decode("utf-8", errors="replace"), answered

    def approval_rows(self):
        path = self.repo / ".local" / "approvals.tsv"
        if not path.exists():
            return []
        lines = path.read_text(encoding="utf-8").splitlines()
        header = lines[0].split("\t")
        return [dict(zip(header, line.split("\t"))) for line in lines[1:]]

    def test_non_tty_rejected_without_write(self):
        result = self.run_non_tty()
        self.assertEqual(2, result.returncode, result.stdout + result.stderr)
        self.assertEqual([], self.approval_rows())

    def test_only_s11_record_is_accepted(self):
        for status in ("S10", "S12", "ERROR_BLOCKED"):
            with self.subTest(status=status):
                self.write_record(status)
                code, output = self.run_tty("确认激活")
                self.assertEqual(4, code, output)
                self.assertEqual([], self.approval_rows())

    def test_sequence_mismatch_is_rejected(self):
        self.write_record("S11", seq="f" * 24)
        code, output = self.run_tty("确认激活")
        self.assertEqual(4, code, output)
        self.assertEqual([], self.approval_rows())

    def test_record_identity_fields_must_match_when_present(self):
        cases = (
            {"operator_key": "other"},
            {"product_key": "other"},
            {"project": "operator/other"},
        )
        for case in cases:
            with self.subTest(case=case):
                self.write_record("S11", **case)
                code, output = self.run_tty("确认激活")
                self.assertEqual(4, code, output)
                self.assertEqual([], self.approval_rows())

    def test_compliance_hash_items_and_expiry_are_rejected(self):
        cases = (
            {"profile_sha": "0" * 64},
            {"bad_key": "suppression"},
            {"checked_at": (datetime.datetime.now() - datetime.timedelta(hours=73)).isoformat(timespec="seconds")},
        )
        for case in cases:
            with self.subTest(case=case):
                self.write_compliance(**case)
                code, output = self.run_tty("确认激活")
                self.assertEqual(2, code, output)
                self.assertEqual([], self.approval_rows())

    def test_simulation_mode_and_non_live_markers_do_not_issue_credential(self):
        cases = (
            {"evidence_mode": "simulation"},
            {"detail": "Reviewed using a SiMuLaTeD data source"},
            {"source": "离线测试记录"},
        )
        for case in cases:
            with self.subTest(case=case):
                self.write_compliance(**case)
                code, output = self.run_tty("确认激活")
                self.assertEqual(2, code, output)
                self.assertEqual([], self.approval_rows())

    def test_decline_does_not_issue_credential(self):
        code, output = self.run_tty("否")
        self.assertEqual(0, code, output)
        self.assertEqual([], self.approval_rows())

    def test_explicit_activation_issues_schema_bound_approval_and_keeps_s11(self):
        code, output = self.run_tty("我确认激活")
        self.assertEqual(0, code, output)
        rows = self.approval_rows()
        self.assertEqual(1, len(rows))
        row = rows[0]
        self.assertEqual("S12_激活", row["state"])
        self.assertEqual("confirm", row["decision"])
        self.assertEqual("confirmed", row["status"])
        binding = {
            "project": self.project,
            "org_sha256": hashlib.sha256(ORG.encode()).hexdigest(),
            "seq": SEQ,
            "profile": {
                "sha256": hashlib.sha256(self.profile.read_bytes()).hexdigest(),
                "status": "declined",
                "version": "1",
            },
            "compliance": {"sha256": hashlib.sha256(self.compliance.read_bytes()).hexdigest()},
        }
        self.assertEqual(stable_hash(binding), row["memo"])
        self.assertIn("status: \"S11\"", self.record.read_text(encoding="utf-8"))

    def test_confirm_without_activation_word_does_not_issue_credential(self):
        code, output = self.run_tty("确认")
        self.assertEqual(0, code, output)
        self.assertEqual([], self.approval_rows())

    def test_resume_and_dry_run_are_mutually_exclusive(self):
        result = self.run_non_tty("--dry-run")
        self.assertEqual(2, result.returncode)
        self.assertIn("not allowed", result.stderr)

    def test_resume_branch_contains_no_network_or_ordinary_flow_calls(self):
        source = (self.repo / "tools" / "flow_orchestrator.py").read_text(encoding="utf-8")
        start = source.index("def resume_s12")
        end = source.index("\n# ---------- 签名昵称硬闸门", start)
        branch = source[start:end]
        for forbidden in ("api(", "check_login_first(", "ensure_operator_profile(", "_urlrequest", "S0", "S10"):
            self.assertNotIn(forbidden, branch)

    def test_normal_flow_still_requires_original_arguments(self):
        result = subprocess.run(
            [sys.executable, str(self.repo / "tools" / "flow_orchestrator.py"), "--org", ORG, "--profile", str(self.profile)],
            text=True, capture_output=True, timeout=10,
        )
        self.assertEqual(2, result.returncode)
        self.assertIn("--token", result.stderr)
        self.assertIn("--nickname", result.stderr)
        self.assertIn("--product", result.stderr)

    def test_ordinary_flow_with_complete_s12_params_and_tty_only_records_pending(self):
        code, output, answered = self.run_ordinary_tty()
        self.assertEqual(0, code, output)
        self.assertEqual(5, answered, output)
        rows = [row for row in self.approval_rows() if row["state"] == "S12_激活"]
        self.assertEqual(1, len(rows), output)
        self.assertEqual("decision_pending", rows[0]["decision"])
        self.assertEqual("pending", rows[0]["status"])
        self.assertNotIn("S12绑定凭证已", output)
        self.assertIn("--resume-s12", output)

    def test_ordinary_dry_run_does_not_write_s12_pending(self):
        result = subprocess.run(
            [
                sys.executable, str(self.repo / "tools" / "flow_orchestrator.py"),
                "--token", "unused-dry-run-token", "--org", ORG, "--nickname", "Tony",
                "--product", "product", "--product-info", "金属粉末产品说明",
                "--profile", str(self.profile), "--seed", "example.com", "--seq", SEQ,
                "--compliance-file", str(self.compliance), "--dry-run",
            ],
            text=True, capture_output=True, timeout=10,
        )
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertEqual([], self.approval_rows())
        self.assertIn("dry-run 不写凭证", result.stdout)
        self.assertIn("--resume-s12", result.stdout)


if __name__ == "__main__":
    unittest.main()
