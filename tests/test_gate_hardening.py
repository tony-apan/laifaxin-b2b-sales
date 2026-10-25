import json
import os
import pathlib
import subprocess
import sys
import tempfile
import unittest


REPO = pathlib.Path(__file__).resolve().parents[1]
TOOLS = REPO / "tools"


def _clean_env():
    return {k: v for k, v in os.environ.items()
            if not k.startswith("LFX_GATE_") and not k.startswith("STEP_GATE_")}


class GateHardeningTest(unittest.TestCase):
    def test_symlink_ledger_is_rejected(self):
        tmp = tempfile.mkdtemp(prefix="lfx-gate-link-")
        target = pathlib.Path(tmp) / "real.jsonl"
        target.write_text("", encoding="utf-8")
        link = pathlib.Path(tmp) / "link.jsonl"
        link.symlink_to(target)
        env = _clean_env()
        env.update({"LFX_GATE_TEST_MODE": "1", "LFX_GATE_LEDGER": str(link)})
        r = subprocess.run([sys.executable, str(TOOLS / "startup_gate.py"), "status"],
                           cwd=str(REPO), capture_output=True, text=True, env=env, timeout=60, encoding="utf-8", errors="replace")
        self.assertNotEqual(0, r.returncode, r.stdout + r.stderr)
        self.assertIn("符号链接", r.stdout + r.stderr)

    def test_ack_from_other_session_is_rejected(self):
        tmp = tempfile.mkdtemp(prefix="lfx-gate-sess-")
        ledger = pathlib.Path(tmp) / "startup.jsonl"
        base = _clean_env()
        base.update({"LFX_GATE_TEST_MODE": "1", "LFX_GATE_LEDGER": str(ledger)})
        ack_env = dict(base); ack_env["DSH_SESSION_ID"] = "sess-A"
        ack = subprocess.run([sys.executable, str(TOOLS / "startup_gate.py"), "ack",
                              "--nickname", "阿杰", "--product", "保温杯"],
                             cwd=str(REPO), capture_output=True, text=True, env=ack_env, timeout=60, encoding="utf-8", errors="replace")
        self.assertEqual(0, ack.returncode, ack.stdout + ack.stderr)
        other_env = dict(base); other_env["DSH_SESSION_ID"] = "sess-B"
        r = subprocess.run([sys.executable, str(TOOLS / "startup_gate.py"), "check"],
                           cwd=str(REPO), capture_output=True, text=True, env=other_env, timeout=60, encoding="utf-8", errors="replace")
        self.assertNotEqual(0, r.returncode, r.stdout + r.stderr)
        self.assertIn("另一个会话", r.stdout + r.stderr)

    def test_ticket_verify_requires_startup_ack(self):
        env = _clean_env()
        env["PYTHONPATH"] = str(TOOLS)
        code = "import auth_guard; auth_guard.verify('missing-ticket', {'a': 1})"
        r = subprocess.run([sys.executable, "-c", code], cwd=str(REPO),
                           capture_output=True, text=True, env=env, timeout=60, encoding="utf-8", errors="replace")
        self.assertNotEqual(0, r.returncode, r.stdout + r.stderr)
        self.assertIn("开工必读", r.stdout + r.stderr)
