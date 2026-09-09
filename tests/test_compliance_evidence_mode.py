import datetime
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
sys.path.insert(0, str(TOOLS))
from compliance_validation import validate_compliance
from evidence_validation import NON_LIVE_EVIDENCE_MARKERS, find_non_live_marker


PROJECT = "operator/product"
SEQ = "0123456789abcdef01234567"
ORG = "org-for-compliance-tests"
QUOTE = "我确认激活"


def stable_hash(value):
    canonical = json.dumps(value, sort_keys=True, ensure_ascii=True, separators=(",", ":"), default=str)
    return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


class ComplianceValidationTest(unittest.TestCase):
    def setUp(self):
        self.checked_at = datetime.datetime.now().isoformat(timespec="seconds")
        evidence = {
            "source": "production policy review",
            "detail": "verified against the current production configuration",
            "checked_at": self.checked_at,
        }
        self.doc = {
            "project": PROJECT,
            "seq": SEQ,
            "profile_sha256": "a" * 64,
            "checked_at": self.checked_at,
            "evidence_mode": "live",
        }
        for key in ("market", "list_source", "sender_identity", "unsubscribe", "suppression"):
            self.doc[key] = {"status": "pass", "evidence": dict(evidence)}

    def validate(self, value=None):
        return validate_compliance(value or self.doc, PROJECT, SEQ, "a" * 64)

    def test_clean_live_document_passes_and_returns_sha(self):
        validated, issues, sha = self.validate()
        self.assertIs(validated, self.doc)
        self.assertEqual([], issues)
        self.assertRegex(sha, r"^[0-9a-f]{64}$")

    def test_mode_status_and_markers_are_strict(self):
        cases = []
        for mode in ("simulation", "LIVE", "mock", ""):
            doc = json.loads(json.dumps(self.doc))
            doc["evidence_mode"] = mode
            cases.append(doc)
        status_doc = json.loads(json.dumps(self.doc))
        status_doc["market"]["status"] = True
        cases.append(status_doc)
        for field, value in (("source", "network STUB result"), ("detail", "这是未联网核验得出的正式结论")):
            doc = json.loads(json.dumps(self.doc))
            doc["market"]["evidence"][field] = value
            cases.append(doc)
        for doc in cases:
            with self.subTest(doc=doc):
                self.assertTrue(self.validate(doc)[1])

    def test_path_sha_uses_exact_file_bytes(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "compliance.json"
            path.write_text(json.dumps(self.doc, indent=2) + "\n", encoding="utf-8")
            _, issues, sha = self.validate(path)
            self.assertEqual([], issues)
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), sha)

    def test_repository_template_cannot_pass_as_formal_evidence(self):
        template = ROOT / "runs" / "_template" / "compliance-check.json"
        _, issues, _ = validate_compliance(template, PROJECT, SEQ, "a" * 64)
        self.assertTrue(issues)
        self.assertIn("evidence_mode须为字面量live", issues)

    def test_shared_marker_vocabulary_preserves_union_and_casefold_matching(self):
        expected = {
            "模拟", "仿真", "离线", "网络桩", "桩数据", "测试桩", "假数据", "伪造", "占位",
            "placeholder", "mock", "stub", "simulated", "simulation", "not live", "not actual",
            "不代表线上", "未实际", "未联网", "未核验", "仅演练", "测试数据", "离线测试",
        }
        # 必须是超集（词汇表允许随对抗审查扩充，但不允许删掉已有标记）
        self.assertTrue(expected <= set(NON_LIVE_EVIDENCE_MARKERS),
                        f"词汇表缺失标记: {expected - set(NON_LIVE_EVIDENCE_MARKERS)}")
        self.assertEqual("simulated", find_non_live_marker("SiMuLaTeD evidence"))
        self.assertEqual("离线", find_non_live_marker("离线测试记录"))
        self.assertEqual("", find_non_live_marker("verified against production"))

    def test_english_test_fake_vocabulary_is_rejected(self):
        """2026-09-09 对抗审查：原先 fake/test 可洗白 live 证据，必须拦截。"""
        for text in ("fake source data", "this is test data not real", "dummy", "demo data",
                     "test-only", "unverified", "TODO"):
            with self.subTest(text=text):
                self.assertNotEqual("", find_non_live_marker(text), f"应拦截: {text}")

    def test_normal_wording_not_flagged(self):
        """不得误伤正常措辞（latest/attestation/protest 含 test 子串）。"""
        for text in ("latest audit report", "attestation from compliance officer",
                     "protest-free channel check", "verified against production"):
            with self.subTest(text=text):
                self.assertEqual("", find_non_live_marker(text), f"不应拦截: {text}")


class ActivateLocalGateOrderTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmp.name)
        (self.repo / "tools").mkdir()
        for name in (
            "activate_sequence.py", "approval.py", "compliance_validation.py", "evidence_validation.py", "profile_utils.py",
            "project_lock.py", "update_run_state.py", "workspace_guard.py", "credential_input.py",
        ):
            shutil.copy2(TOOLS / name, self.repo / "tools" / name)
        self.project_dir = self.repo / "runs" / "operator" / "product"
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
        self.record.write_text(
            f'---\nstatus: "S11"\nnext_state: "S12"\noperator_key: "operator"\n'
            f'product_key: "product"\nproject: "{PROJECT}"\nsequence_id: "{SEQ}"\n---\n',
            encoding="utf-8",
        )
        self.compliance = self.project_dir / "compliance.json"
        self.write_compliance()
        self.bin_dir = self.repo / "bin"
        self.bin_dir.mkdir()
        self.curl_log = self.repo / "curl.log"
        curl = self.bin_dir / "curl"
        curl.write_text(
            "#!/bin/sh\nprintf '%s\\n' called >> \"$CURL_LOG\"\n"
            "printf '%s' '{\"data\":{\"list\":[{\"id\":\"0123456789abcdef01234567\",\"status\":\"inactive\"}]}}'\n",
            encoding="utf-8",
        )
        curl.chmod(0o755)
        self.write_approval()

    def tearDown(self):
        self.tmp.cleanup()

    def write_compliance(self, mode="live", source="production policy review", detail="verified current production controls"):
        checked = datetime.datetime.now().isoformat(timespec="seconds")
        evidence = {"source": source, "detail": detail, "checked_at": checked}
        doc = {
            "project": PROJECT, "seq": SEQ,
            "profile_sha256": hashlib.sha256(self.profile.read_bytes()).hexdigest(),
            "checked_at": checked, "evidence_mode": mode,
        }
        for key in ("market", "list_source", "sender_identity", "unsubscribe", "suppression"):
            doc[key] = {"status": "pass", "evidence": dict(evidence)}
        self.compliance.write_text(json.dumps(doc), encoding="utf-8")

    def binding(self, project=PROJECT, quote=QUOTE):
        return {
            "project": project,
            "org_sha256": hashlib.sha256(ORG.encode()).hexdigest(),
            "seq": SEQ,
            "profile": {
                "sha256": hashlib.sha256(self.profile.read_bytes()).hexdigest(),
                "status": "declined", "version": "1",
            },
            "compliance": {"sha256": hashlib.sha256(self.compliance.read_bytes()).hexdigest()},
        }

    def write_approval(self, memo=None, quote=QUOTE):
        approvals = self.repo / ".local" / "approvals.tsv"
        approvals.parent.mkdir(exist_ok=True)
        memo = memo or stable_hash(self.binding())
        approvals.write_text(
            "id\tproject_id\tstate\tdecision\tuser_quote\tmemo\ttime\tstatus\n"
            f"ap-test\t{PROJECT}\tS12_激活\tconfirm\t{quote}\t{memo}\t2026-09-07 00:00:00\tconfirmed\n",
            encoding="utf-8",
        )

    def command(self, **overrides):
        values = {
            "--token": "token", "--org": ORG, "--seq": SEQ, "--project": PROJECT,
            "--profile": str(self.profile), "--compliance-file": str(self.compliance),
            "--record": str(self.record), "--confirm": QUOTE, "--approval": "ap-test",
        }
        values.update(overrides)
        command = [sys.executable, str(self.repo / "tools" / "activate_sequence.py")]
        for key, value in values.items():
            command.extend((key, value))
        return command

    def run_activate(self, env_overrides=None, **overrides):
        if self.curl_log.exists():
            self.curl_log.unlink()
        env = os.environ.copy()
        env["PATH"] = str(self.bin_dir) + os.pathsep + env.get("PATH", "")
        env["CURL_LOG"] = str(self.curl_log)
        env.update(env_overrides or {})
        result = subprocess.run(self.command(**overrides), text=True, capture_output=True, env=env, timeout=10)
        calls = self.curl_log.read_text(encoding="utf-8").splitlines() if self.curl_log.exists() else []
        return result, calls

    def assert_local_failure_has_no_network(self, **overrides):
        result, calls = self.run_activate(**overrides)
        self.assertNotEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertEqual([], calls, result.stdout + result.stderr)

    def test_simulation_marker_approval_profile_and_confirm_fail_before_network(self):
        self.write_compliance(mode="simulation")
        self.write_approval()
        self.assert_local_failure_has_no_network()

        self.write_compliance(detail="validated with MOCK evidence only")
        self.write_approval()
        self.assert_local_failure_has_no_network()

        self.write_compliance()
        self.write_approval(memo="sha256:0000000000000000")
        self.assert_local_failure_has_no_network()

        self.write_approval()
        self.assert_local_failure_has_no_network(**{"--project": "operator/other"})

        self.assert_local_failure_has_no_network(**{"--confirm": "暂不激活"})

    def test_profile_second_hash_failure_does_not_reach_network(self):
        self.write_approval()
        approval_module = self.repo / "tools" / "approval.py"
        source = approval_module.read_text(encoding="utf-8")
        source = source.replace(
            "    return r\n\n\ndef _tsv_cell",
            "    mutate = os.environ.get('MUTATE_PROFILE_AFTER_APPROVAL')\n"
            "    if mutate:\n"
            "        with open(mutate, 'a', encoding='utf-8') as handle:\n"
            "            handle.write('changed after approval\\n')\n"
            "    return r\n\n\ndef _tsv_cell",
        )
        approval_module.write_text(source, encoding="utf-8")
        result, calls = self.run_activate(
            env_overrides={"MUTATE_PROFILE_AFTER_APPROVAL": str(self.profile)}
        )
        self.assertNotEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertEqual([], calls, result.stdout + result.stderr)

    def test_clean_live_evidence_reaches_mocked_online_stage(self):
        self.write_compliance()
        self.write_approval()
        result, calls = self.run_activate()
        self.assertTrue(calls, result.stdout + result.stderr)

    def test_flow_and_activate_use_the_same_validator(self):
        flow = (TOOLS / "flow_orchestrator.py").read_text(encoding="utf-8")
        activate = (TOOLS / "activate_sequence.py").read_text(encoding="utf-8")
        self.assertIn("validate_compliance(", flow)
        self.assertIn("validate_compliance(", activate)


if __name__ == "__main__":
    unittest.main()
