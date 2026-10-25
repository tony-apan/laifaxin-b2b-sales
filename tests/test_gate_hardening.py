import json
import os
import shutil
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



try:
    from gate_env import gate_test_env
except ImportError:
    from tests.gate_env import gate_test_env

class GateHardeningTest(unittest.TestCase):
    def test_symlink_ledger_is_rejected(self):
        tmp = tempfile.mkdtemp(prefix="lfx-gate-link-")
        target = pathlib.Path(tmp) / "real.jsonl"
        target.write_text("", encoding="utf-8")
        link = pathlib.Path(tmp) / "link.jsonl"
        link.symlink_to(target)
        env = _clean_env()
        env.update({**gate_test_env(), "LFX_GATE_LEDGER": str(link)})
        r = subprocess.run([sys.executable, str(TOOLS / "startup_gate.py"), "status"],
                           cwd=str(REPO), capture_output=True, text=True, env=env, timeout=60, encoding="utf-8", errors="replace")
        self.assertNotEqual(0, r.returncode, r.stdout + r.stderr)
        self.assertIn("符号链接", r.stdout + r.stderr)

    def test_ack_from_other_session_is_rejected(self):
        tmp = tempfile.mkdtemp(prefix="lfx-gate-sess-")
        ledger = pathlib.Path(tmp) / "startup.jsonl"
        base = _clean_env()
        base.update({**gate_test_env(), "LFX_GATE_LEDGER": str(ledger)})
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
        # 复制一份干净仓库再验：不依赖本机真实 .local/gate（本机做过验收 ack 会假通过）
        with tempfile.TemporaryDirectory(prefix="lfx-gate-ticket-") as tmp:
            repo = pathlib.Path(tmp) / "repo"
            shutil.copytree(REPO, repo, ignore=shutil.ignore_patterns(
                ".git", ".local", "__pycache__", "runs"))
            env["PYTHONPATH"] = str(repo / "tools")
            code = "import auth_guard; auth_guard.verify('missing-ticket', {'a': 1})"
            r = subprocess.run([sys.executable, "-c", code], cwd=str(repo),
                               capture_output=True, text=True, env=env, timeout=60,
                               encoding="utf-8", errors="replace")
        self.assertNotEqual(0, r.returncode, r.stdout + r.stderr)
        self.assertIn("开工必读", r.stdout + r.stderr)

    def test_bare_test_mode_env_is_rejected(self):
        """裸 LFX_GATE_TEST_MODE=1（无票据）不得放行；带一次性票据才放行。"""
        env = _clean_env()
        env["LFX_GATE_TEST_MODE"] = "1"
        env["PYTHONPATH"] = str(TOOLS)
        code = "import startup_gate; print('ALLOWED' if startup_gate._test_mode_allowed() else 'DENIED')"
        r = subprocess.run([sys.executable, "-c", code], cwd=str(REPO), capture_output=True,
                           text=True, env=env, timeout=60, encoding="utf-8", errors="replace")
        self.assertIn("DENIED", r.stdout, r.stdout + r.stderr)
        env.update(gate_test_env())
        r2 = subprocess.run([sys.executable, "-c", code], cwd=str(REPO), capture_output=True,
                            text=True, env=env, timeout=60, encoding="utf-8", errors="replace")
        self.assertIn("ALLOWED", r2.stdout, r2.stdout + r2.stderr)

    def test_stale_ticket_is_rejected(self):
        """票据超过有效期（10 分钟）后即使文件还在，三处入口也不得放行。"""
        nonce = "stale-nonce-" + str(os.getpid())
        with tempfile.TemporaryDirectory(prefix="lfx-gate-stale-") as tmp:
            ticket = pathlib.Path(tmp) / "ticket"
            ticket.write_text(nonce, encoding="utf-8")
            old = ticket.stat().st_mtime - 700
            os.utime(ticket, (old, old))
            env = _clean_env()
            env.update({
                "LFX_GATE_TEST_MODE": "1",
                "LFX_GATE_TEST_TICKET": str(ticket),
                "LFX_GATE_TEST_NONCE": nonce,
                "PYTHONPATH": str(TOOLS),
            })
            code = (
                "import startup_gate, workspace_guard, auth_guard\n"
                "print(startup_gate._test_mode_allowed())\n"
                "print(workspace_guard._is_test_mode())\n"
                "print(auth_guard._test_mode_allowed())\n"
            )
            r = subprocess.run([sys.executable, "-c", code], cwd=str(REPO), capture_output=True,
                               text=True, env=env, timeout=60, encoding="utf-8", errors="replace")
        self.assertEqual(["False", "False", "False"], r.stdout.split(), r.stdout + r.stderr)
