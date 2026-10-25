import json, os, subprocess, sys, tempfile, unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
GATE = TOOLS / "startup_gate.py"

DOCS = ["SKILL.md", "RULES.md", "CORE-POINTS.md", "specs/beginner-flow.md",
        "specs/novice-flow-contract.md", "specs/problems-and-fixes-2026-10-23.md"]


def make_env(tmp: Path):
    docs = tmp / "docs"
    for rel in DOCS:
        p = docs / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("原文 " + rel, encoding="utf-8")
    env = dict(os.environ)
    env.update({
        "LFX_GATE_TEST_MODE": "1",
        "LFX_GATE_LEDGER": str(tmp / "ledger" / "startup.jsonl"),
        "LFX_GATE_DOCS_DIR": str(docs),
    })
    return env, docs, tmp / "ledger" / "startup.jsonl"


def run(args, env):
    return subprocess.run([sys.executable, str(GATE)] + args,
                          capture_output=True, text=True, env=env, cwd=str(ROOT))


class StartupGateTest(unittest.TestCase):
    def test_check_without_ack_blocks(self):
        with tempfile.TemporaryDirectory() as d:
            env, _, led = make_env(Path(d))
            r = run(["check"], env)
            self.assertEqual(r.returncode, 2)
            self.assertIn("还差一步", r.stderr)
            self.assertIn("昵称和产品", r.stderr)
            self.assertNotIn("SKILL.md", r.stderr, "不得把必读文件名漏给零技术用户")
            self.assertEqual(r.stdout + r.stderr, r.stdout + r.stderr)
            self.assertFalse(led.is_file())

    def test_ack_then_check_passes_and_ledger_records_hashes(self):
        with tempfile.TemporaryDirectory() as d:
            env, _, led = make_env(Path(d))
            r = run(["ack", "--nickname", "Tony", "--product", "户外帐篷"], env)
            self.assertEqual(r.returncode, 0, r.stderr)
            rows = [json.loads(x) for x in led.read_text(encoding="utf-8").splitlines() if x.strip()]
            self.assertEqual(rows[-1]["event"], "ack")
            self.assertEqual(rows[-1]["nickname"], "Tony")
            self.assertEqual(len(rows[-1]["doc_sha256"]), len(DOCS))
            r2 = run(["check"], env)
            self.assertEqual(r2.returncode, 0, r2.stderr)
            self.assertIn("开工必读已登记", r2.stdout)

    def test_doc_change_invalidates_ack(self):
        with tempfile.TemporaryDirectory() as d:
            env, docs, _ = make_env(Path(d))
            self.assertEqual(run(["ack", "--nickname", "Tony", "--product", "帐篷"], env).returncode, 0)
            (docs / "RULES.md").write_text("被改了", encoding="utf-8")
            r = run(["check"], env)
            self.assertEqual(r.returncode, 2)
            self.assertIn("必读文档已变化", r.stderr)
            self.assertIn("RULES.md", r.stderr)

    def test_ack_rejects_missing_nickname_or_product(self):
        with tempfile.TemporaryDirectory() as d:
            env, _, led = make_env(Path(d))
            r = run(["ack", "--nickname", "", "--product", "帐篷"], env)
            self.assertEqual(r.returncode, 2)
            self.assertFalse(led.is_file())

    def test_env_override_forbidden_outside_test_mode(self):
        with tempfile.TemporaryDirectory() as d:
            env, _, _ = make_env(Path(d))
            env.pop("LFX_GATE_TEST_MODE", None)
            r = run(["check"], env)
            self.assertEqual(r.returncode, 2)
            self.assertIn("禁止用环境变量", r.stderr)

    def test_missing_doc_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            env, docs, _ = make_env(Path(d))
            (docs / "specs/novice-flow-contract.md").unlink()
            r = run(["ack", "--nickname", "Tony", "--product", "帐篷"], env)
            self.assertEqual(r.returncode, 2)
            self.assertIn("必读文档缺失", r.stderr)
            self.assertIn("novice-flow-contract.md", r.stderr)

    def test_require_ack_raises_and_passes(self):
        with tempfile.TemporaryDirectory() as d:
            env, _, _ = make_env(Path(d))
            old = dict(os.environ)
            os.environ.update({k: env[k] for k in ("LFX_GATE_TEST_MODE", "LFX_GATE_LEDGER", "LFX_GATE_DOCS_DIR")})
            try:
                if str(TOOLS) not in sys.path:
                    sys.path.insert(0, str(TOOLS))
                import startup_gate
                with self.assertRaises(startup_gate.StartupGateError):
                    startup_gate.require_ack()
                self.assertEqual(run(["ack", "--nickname", "Tony", "--product", "帐篷"], env).returncode, 0)
                startup_gate.require_ack()
            finally:
                os.environ.clear()
                os.environ.update(old)
                sys.modules.pop("startup_gate", None)

    def test_step_gate_is_wired_to_startup_gate(self):
        src = (TOOLS / "step_gate.py").read_text(encoding="utf-8")
        self.assertIn("from startup_gate import require_ack", src)
        self.assertIn("_require_startup_gate()", src)
        # check_card 内必须先过分门再读卡
        self.assertIn("_require_startup_gate()\n    card = load_card(state)", src)

    def test_auth_guard_mints_only_after_startup_ack(self):
        src = (TOOLS / "auth_guard.py").read_text(encoding="utf-8")
        self.assertIn("from startup_gate import require_ack", src)
        self.assertIn("_require_startup_ack()", src)
        self.assertLess(src.index("_require_startup_ack()"), src.index("if not isinstance(action, str)"))

    def test_install_docs_mention_machine_gate(self):
        for rel in ("README.md", "SKILL.md", "AGENTS.md", "INDEX.md"):
            text = (ROOT / rel).read_text(encoding="utf-8")
            with self.subTest(file=rel):
                self.assertIn("startup_gate.py", text, f"{rel} 需说明开工必读机器门命令")


if __name__ == "__main__":
    unittest.main()
