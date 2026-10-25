import os, pathlib, shutil, subprocess, sys, tempfile, unittest


REPO = pathlib.Path(__file__).resolve().parents[1]


class StartupGateIntegrationTest(unittest.TestCase):
    def test_write_scripts_have_cli_gate(self):
        names = ["build_sequence.py", "gen_templates.py", "save_first_n.py", "contact_add.py",
                 "contact_add_authorized.py", "activate_sequence.py", "tag_add.py",
                 "flow_orchestrator.py", "rebuild_templates.py", "delete_all_products.py",
                 "resolve_schedule.py", "seed_resolve.py", "segments_infer.py",
                 "verify_sequence.py", "wait_save_done.py", "check_template_diff.py"]
        missing = [n for n in names if "enforce_cli_startup" not in (REPO / "tools" / n).read_text(encoding="utf-8")]
        self.assertEqual([], missing, "写脚本缺少开工门: %s" % missing)

    def test_unacked_cli_rejected_with_human_message(self):
        tmp = tempfile.mkdtemp(prefix="lfx-gate-it-")
        try:
            copy = pathlib.Path(tmp) / "repo"
            shutil.copytree(REPO, copy, ignore=shutil.ignore_patterns(".git", ".local", "__pycache__"))
            env = {k: v for k, v in os.environ.items() if not k.startswith("LFX_GATE_") and not k.startswith("STEP_GATE_")}
            r = subprocess.run([sys.executable, "tools/startup_gate.py", "check"],
                               cwd=str(copy), capture_output=True, text=True, env=env, timeout=60, encoding="utf-8", errors="replace")
            self.assertNotEqual(0, r.returncode, "未登记却通过: %s%s" % (r.stdout, r.stderr))
            self.assertIn("开工必读", r.stdout + r.stderr)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_ack_then_check_passes_and_docs_change_rejects(self):
        tmp = tempfile.mkdtemp(prefix="lfx-gate-it2-")
        try:
            copy = pathlib.Path(tmp) / "repo"
            shutil.copytree(REPO, copy, ignore=shutil.ignore_patterns(".git", ".local", "__pycache__"))
            env = {k: v for k, v in os.environ.items() if not k.startswith("LFX_GATE_") and not k.startswith("STEP_GATE_")}
            ack = subprocess.run([sys.executable, "tools/startup_gate.py", "ack", "--nickname", "阿杰", "--product", "保温杯"],
                                 cwd=str(copy), capture_output=True, text=True, env=env, timeout=60, encoding="utf-8", errors="replace")
            self.assertEqual(0, ack.returncode, ack.stdout + ack.stderr)
            chk = subprocess.run([sys.executable, "tools/startup_gate.py", "check"],
                                 cwd=str(copy), capture_output=True, text=True, env=env, timeout=60, encoding="utf-8", errors="replace")
            self.assertEqual(0, chk.returncode, chk.stdout + chk.stderr)
            rules = copy / "RULES.md"
            rules.write_text(rules.read_text(encoding="utf-8") + "\n<!-- drift -->\n", encoding="utf-8")
            again = subprocess.run([sys.executable, "tools/startup_gate.py", "check"],
                                   cwd=str(copy), capture_output=True, text=True, env=env, timeout=60, encoding="utf-8", errors="replace")
            self.assertNotEqual(0, again.returncode, "文档变化后仍通过")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
