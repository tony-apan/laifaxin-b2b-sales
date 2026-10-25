"""跨平台一致性测试：Windows/macOS 通用入口、行尾、文案与自检行为。"""
import ast
import contextlib
import importlib.util
import io
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


class CrossPlatformTest(unittest.TestCase):
    def test_preflight_py_is_cross_platform(self):
        p = ROOT / "tools" / "preflight.py"
        self.assertTrue(p.is_file(), "缺少 Windows 可用的 tools/preflight.py")
        text = p.read_text(encoding="utf-8")
        self.assertIn("sys.executable", text, "跨平台预检必须用当前解释器，不能硬编码 python3")
        self.assertIn("reconfigure", text, "需处理 Windows 控制台编码")

    def test_gitattributes_normalizes_line_endings(self):
        p = ROOT / ".gitattributes"
        self.assertTrue(p.is_file(), "缺 .gitattributes，Windows 检出 CRLF 会导致脚本失败")
        text = p.read_text(encoding="utf-8")
        self.assertIn("*.sh text eol=lf", text)
        self.assertIn("*.ps1 text eol=crlf", text)

    def test_cross_platform_doc_covers_both_os(self):
        p = ROOT / "docs" / "cross-platform-setup.md"
        self.assertTrue(p.is_file())
        text = p.read_text(encoding="utf-8")
        for kw in ("Windows", "macOS", "preflight.py", "PYTHONUTF8"):
            self.assertIn(kw, text)

    def test_fresh_computer_checklist_exists_and_linked(self):
        p = ROOT / "docs" / "fresh-computer-checklist.md"
        self.assertTrue(p.is_file(), "缺全新电脑检查清单 docs/fresh-computer-checklist.md")
        text = p.read_text(encoding="utf-8")
        for kw in ("Windows", "macOS", "preflight.py", "不用敲命令", "PREFLIGHT PASS",
                   "退出码 0", "不能跳过", "core.longpaths"):
            self.assertIn(kw, text, f"检查清单缺关键内容：{kw}")
        self.assertNotIn("tools\\", text, "Windows 命令用正斜杠，避免 Git Bash 吞反斜杠")
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn("fresh-computer-checklist.md", readme, "README 快速入口应链接全新电脑检查清单")
        index = (ROOT / "docs" / "INDEX.md").read_text(encoding="utf-8")
        self.assertIn("fresh-computer-checklist.md", index, "docs/INDEX 应登记全新电脑检查清单")

    def test_preflight_gate_detects_fail_text_even_when_rc_zero(self):
        """行为测试：check_rules.sh 曾出现 [FAIL] 但 exit 0，preflight 必须判失败。"""
        spec = importlib.util.spec_from_file_location(
            "preflight_mod", ROOT / "tools" / "preflight.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        import contextlib
        fail_cmd = [sys.executable, "-c", "print('[FAIL] RULE-FILE-MISSING')"]
        ok_cmd = [sys.executable, "-c", "print('check ok')"]
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):  # 别污染 preflight 输出
            self.assertFalse(mod._run_gate("gate-fail", fail_cmd),
                             "rc=0 但输出含 [FAIL] 时必须判失败")
            self.assertTrue(mod._run_gate("gate-ok", ok_cmd),
                            "rc=0 且无 [FAIL] 时应判通过")
        self.assertIn("[FAIL]", buf.getvalue(),
                      "必须真实打印 [FAIL]（纯 ASCII，Windows 管道不会编码崩溃）")

    @unittest.skipUnless(shutil.which("bash"), "需要 bash 才能验证 check_rules.sh 行为")
    def test_check_rules_exits_nonzero_on_missing_file(self):
        """行为测试：把脚本复制到空目录（规则文件全缺）必须非零退出。"""
        with tempfile.TemporaryDirectory() as td:
            script = Path(td) / "check_rules.sh"
            shutil.copy2(ROOT / "tools" / "check_rules.sh", script)
            proc = subprocess.run(["bash", str(script)], cwd=td,
                                  capture_output=True, text=True, timeout=120)
            self.assertNotEqual(proc.returncode, 0,
                                "规则文件缺失时 check_rules.sh 必须非零退出")
            out = (proc.stdout or "") + (proc.stderr or "")
            self.assertIn("缺失", out, "缺规则文件时应给出中文缺失提示")

    def test_preflight_sh_autodetects_python(self):
        text = (ROOT / "tools" / "preflight.sh").read_text(encoding="utf-8")
        for kw in ("command -v python3", "command -v py", "PY="):
            self.assertIn(kw, text, f"preflight.sh 缺解释器探测：{kw}")

    @unittest.skipUnless(shutil.which("bash"), "需要 bash")
    def test_gate_check_missing_interpreter_is_env_not_login(self):
        """Windows 商店占位符 python3（退出码 49）且无其他解释器时：
        必须报「准备工作还差一点」，不得误报「账号钥匙失效」（2026-10-25 Windows 实机回归）。"""
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            tools_dir = root / "tools"
            tools_dir.mkdir()
            shutil.copy2(ROOT / "tools" / "gate_check.sh", tools_dir / "gate_check.sh")
            bin_dir = root / "bin"
            bin_dir.mkdir()
            uname = bin_dir / "uname"
            uname.write_text("#!/bin/sh\necho MINGW64_NT\n", encoding="utf-8")
            uname.chmod(0o755)
            for name in ("python3", "python", "py"):
                p = bin_dir / name
                p.write_text("#!/bin/sh\nexit 49\n", encoding="utf-8")
                p.chmod(0o755)
            env = dict(os.environ)
            env["PATH"] = f"{bin_dir}:/usr/bin:/bin"
            proc = subprocess.run(["bash", str(tools_dir / "gate_check.sh")],
                                  input="", text=True, capture_output=True,
                                  env=env, timeout=30)
            out = (proc.stdout or "") + (proc.stderr or "")
            self.assertNotEqual(proc.returncode, 0)
            self.assertIn("准备工作还差一点", out)
            self.assertNotIn("钥匙失效", out)

    @unittest.skipUnless(shutil.which("bash"), "需要 bash")
    def test_gate_check_skips_store_stub_and_picks_py(self):
        """主路径：占位符 python3（退出码 49）被跳过，选中可用的 py。"""
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            tools_dir = root / "tools"
            tools_dir.mkdir()
            shutil.copy2(ROOT / "tools" / "gate_check.sh", tools_dir / "gate_check.sh")
            bin_dir = root / "bin"
            bin_dir.mkdir()
            log = root / "py.log"
            (bin_dir / "uname").write_text("#!/bin/sh\necho MINGW64_NT\n", encoding="utf-8")
            (bin_dir / "python3").write_text(
                "#!/bin/sh\necho 'Python was not found'\nexit 49\n", encoding="utf-8")
            (bin_dir / "py").write_text(
                "#!/bin/sh\necho called >> \"$PY_LOG\"\nexec \"$REAL_PYTHON\" \"$@\"\n",
                encoding="utf-8")
            for name in ("uname", "python3", "py"):
                (bin_dir / name).chmod(0o755)
            env = dict(os.environ)
            env["PATH"] = f"{bin_dir}:/usr/bin:/bin"
            env["REAL_PYTHON"] = sys.executable
            env["PY_LOG"] = str(log)
            proc = subprocess.run(["bash", str(tools_dir / "gate_check.sh"), "--credentials-stdin"],
                                  input=b"", capture_output=True, env=env, timeout=30)
            self.assertNotEqual(0, proc.returncode)  # 临时目录缺必读文档，应失败
            self.assertTrue(log.is_file() and log.read_text().strip(), "应回退到可用的 py")

    def test_onboard_check_reads_docs_with_explicit_utf8(self):
        """Windows 默认编码是 GBK：安装门读 README/RULES 必须显式 UTF-8，
        否则中文文档直接 UnicodeDecodeError（2026-10-25 Windows 实机：ONBOARD_EXIT=1）。"""
        import ast
        tree = ast.parse((ROOT / "tools" / "onboard_check.py").read_text(encoding="utf-8"))
        show = next(n for n in ast.walk(tree)
                    if isinstance(n, ast.FunctionDef) and n.name == "show")
        calls = [n for n in ast.walk(show)
                 if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                 and n.func.attr == "read_text"]
        self.assertTrue(calls, "show() 应通过 read_text 读文档")
        for call in calls:
            enc = [kw.value for kw in call.keywords if kw.arg == "encoding"]
            self.assertTrue(enc and isinstance(enc[0], ast.Constant) and enc[0].value == "utf-8",
                            "show() 的 read_text 必须显式 encoding='utf-8'（Windows 按 ANSI 代码页会崩）")

    def test_onboard_check_survives_non_utf8_default_encoding(self):
        """把默认编码压成 ASCII（≈Windows GBK 场景）后，安装门仍须整段跑完、不得解码崩溃。"""
        env = dict(os.environ)
        # 严格 ascii 输出 + C locale：不显式切 UTF-8 时，read_text 与 emoji 打印都会崩
        env.update({"PYTHONUTF8": "0", "PYTHONCOERCECLOCALE": "0",
                    "LC_ALL": "C", "PYTHONIOENCODING": "utf-8"})
        proc = subprocess.run([sys.executable, str(ROOT / "tools" / "onboard_check.py")],
                              capture_output=True, env=env, timeout=120)
        out = (proc.stdout or b"").decode("utf-8", "replace")
        self.assertEqual(0, proc.returncode, out[-800:])
        self.assertNotIn("UnicodeDecodeError", out)
        self.assertNotIn("Traceback", out)
        self.assertIn("🛰", out, "输出必须显式切 UTF-8（否则 GBK/ascii 控制台下 emoji 会崩）")

    def test_check_login_stdout_is_forced_utf8(self):
        """gate_check 会把 check_login 的原始输出转给 AI；Windows 管道默认 GBK 会变乱码，
        所以脚本必须自己切 UTF-8。这里把默认输出编码压成 ascii 来验证。"""
        env = dict(os.environ)
        env["PYTHONIOENCODING"] = "ascii"
        proc = subprocess.run(
            [sys.executable, str(ROOT / "tools" / "check_login.py"),
             "--credentials-stdin", "--gate-mode"],
            input=b"accesstoken=x\norgId=y\n", capture_output=True, env=env, timeout=60)
        self.assertEqual(2, proc.returncode, "凭据格式不对应返回 2（不是崩溃）")
        self.assertNotIn(b"UnicodeEncodeError", proc.stderr)
        decoded = proc.stderr.decode("utf-8")  # 非 UTF-8 会直接抛错，即为回归
        self.assertNotIn("Traceback", decoded)
        self.assertTrue(decoded.strip(), "应给出可读的中文提示")

    def test_gate_check_forces_utf8_for_python_children(self):
        text = (ROOT / "tools" / "gate_check.sh").read_text(encoding="utf-8")
        self.assertRegex(text, r"(?m)^export PYTHONIOENCODING=utf-8$",
                         "gate_check 必须真的 export（注释不算），让 python 子进程输出 UTF-8")

    @unittest.skipUnless(shutil.which("bash"), "需要 bash")
    def test_gate_check_python_child_really_sees_utf8(self):
        """行为验证：真正被调用的 python 子进程能读到 PYTHONIOENCODING=utf-8。"""
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            tools_dir = root / "tools"
            tools_dir.mkdir()
            shutil.copy2(ROOT / "tools" / "gate_check.sh", tools_dir / "gate_check.sh")
            specs = root / "specs"
            specs.mkdir()
            for name in ("environment-setup.md", "migration-handoff.md",
                         "operator-profile-sop.md", "product-profile-sop.md",
                         "threshold-method.md", "domain-scale-sop.md", "sequence-config.md"):
                shutil.copy2(ROOT / "specs" / name, specs / name)
            for name in ("RULES.md", "INDEX.md"):
                shutil.copy2(ROOT / name, root / name)
            bin_dir = root / "bin"
            bin_dir.mkdir()
            log = root / "env.log"
            (bin_dir / "uname").write_text("#!/bin/sh\necho MINGW64_NT\n", encoding="utf-8")
            (bin_dir / "python3").write_text("#!/bin/sh\nexit 49\n", encoding="utf-8")
            (bin_dir / "py").write_text(
                "#!/bin/sh\necho $PYTHONIOENCODING > $ENV_LOG\nexit 0\n",
                encoding="utf-8")
            for name in ("uname", "python3", "py"):
                (bin_dir / name).chmod(0o755)
            env = dict(os.environ)
            env["PATH"] = f"{bin_dir}:/usr/bin:/bin"
            env["ENV_LOG"] = str(log)
            subprocess.run(["bash", str(tools_dir / "gate_check.sh"), "--credentials-stdin"],
                           input=b"accesstoken=x\norgId=y\n", capture_output=True, env=env, timeout=30)
            seen = log.read_text(encoding="utf-8").strip() if log.is_file() else ""
        self.assertEqual("utf-8", seen,
                         "gate_check 调 python 前必须 export PYTHONIOENCODING=utf-8")

    @staticmethod
    def _load_approval_module():
        spec = importlib.util.spec_from_file_location("approval_under_test", ROOT / "tools" / "approval.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    def test_approvals_reads_utf8_chinese(self):
        """正常路径：UTF-8 账本里的中文原话必须原样读回。"""
        mod = self._load_approval_module()
        with tempfile.TemporaryDirectory() as td:
            target = Path(td) / "approvals.tsv"
            header = "\t".join(mod.COLUMNS) + "\n"
            row = "ap-1\tproj\tS5\tconfirm\t可以保存\tparams\t2026-10-25 10:00:00\tconfirmed\n"
            target.write_text(header + row, encoding="utf-8-sig")
            original = mod.APPROVALS
            mod.APPROVALS = target
            try:
                rows = mod._rows()
            finally:
                mod.APPROVALS = original
        self.assertEqual("可以保存", rows[0]["user_quote"])

    def test_approvals_rejects_non_utf8_without_rewriting(self):
        """旧 GBK 账本：不猜编码、不静默损坏，明确报错且一个字节都不改（防 demote 永久写坏）。"""
        mod = self._load_approval_module()
        with tempfile.TemporaryDirectory() as td:
            target = Path(td) / "approvals.tsv"
            header = "\t".join(mod.COLUMNS) + "\n"
            # GBK 的“可以保存”不是合法 UTF-8：必须拒绝猜，而不是解码成乱码或写回
            row = "ap-1\tproj\tS5\tconfirm\t可以保存\tparams\t2026-10-25 10:00:00\tconfirmed\n"
            raw = (header + row).encode("gbk")
            target.write_bytes(raw)
            original = mod.APPROVALS
            mod.APPROVALS = target
            try:
                with self.assertRaises(ValueError) as ctx:
                    mod._rows()
            finally:
                mod.APPROVALS = original
            self.assertEqual(raw, target.read_bytes(), "解码失败时不得改写账本")
        self.assertIn("UTF-8", str(ctx.exception))

    def test_approvals_ambiguous_utf8_read_ok_but_rewrite_refused(self):
        """无 BOM 中文：读来显示可以，但任何重写（demote/升级）必须拒绝，防止永久写坏。"""
        mod = self._load_approval_module()
        with tempfile.TemporaryDirectory() as td:
            target = Path(td) / "approvals.tsv"
            header = "\t".join(mod.COLUMNS) + "\n"
            row = "ap-1\tproj\tS5\tconfirm\t可以保存\tparams\t2026-10-25 10:00:00\tconfirmed\n"
            target.write_text(header + row, encoding="utf-8")  # 合法 UTF-8，但没有 BOM
            original = mod.APPROVALS
            mod.APPROVALS = target
            try:
                self.assertEqual("可以保存", mod._rows()[0]["user_quote"])
                with self.assertRaises(ValueError) as ctx:
                    mod._rows(require_marked=True)
            finally:
                mod.APPROVALS = original
        self.assertIn("BOM", str(ctx.exception))

    def test_approvals_ascii_legacy_is_readable(self):
        """纯 ASCII 旧账本没有二义性，仍可直接读（下次写入会自动补 BOM）。"""
        mod = self._load_approval_module()
        with tempfile.TemporaryDirectory() as td:
            target = Path(td) / "approvals.tsv"
            header = "\t".join(mod.COLUMNS) + "\n"
            row = "ap-1\tproj\tS5\tconfirm\tok\tparams\t2026-10-25 10:00:00\tconfirmed\n"
            target.write_text(header + row, encoding="utf-8")
            original = mod.APPROVALS
            mod.APPROVALS = target
            try:
                rows = mod._rows()
            finally:
                mod.APPROVALS = original
        self.assertEqual("ok", rows[0]["user_quote"])

    def test_demote_migrated_keeps_bom_marker(self):
        """demote-migrated 重写账本后仍须带 BOM，否则中文文件变二义性、下次迁移被自己拒绝。"""
        mod = self._load_approval_module()
        with tempfile.TemporaryDirectory() as td:
            target = Path(td) / "approvals.tsv"
            header = "\t".join(mod.COLUMNS) + "\n"
            row = "ap-1\tproj\tS12_激活\tconfirm\t确认激活 皮筏艇\tparams\t2026-10-25 10:00:00\tconfirmed\n"
            target.write_text(header + row, encoding="utf-8-sig")
            original = mod.APPROVALS
            mod.APPROVALS = target
            try:
                with contextlib.redirect_stdout(io.StringIO()):
                    mod.main(["demote-migrated", "--confirm", "MIGRATION-DEMOTE"])
                raw = target.read_bytes()
            finally:
                mod.APPROVALS = original
        self.assertTrue(raw.startswith(b"\xef\xbb\xbf"), "重写后必须保留 BOM")
        self.assertIn("backfilled", raw.decode("utf-8-sig"))

    def test_demote_refuses_ambiguous_utf8_and_keeps_bytes(self):
        """真正走 demote-migrated：无 BOM 中文账本必须 exit 1 且一个字节都不改（P1 回归保险）。"""
        mod = self._load_approval_module()
        with tempfile.TemporaryDirectory() as td:
            target = Path(td) / "approvals.tsv"
            header = "\t".join(mod.COLUMNS) + "\n"
            row = "ap-1\tproj\tS12_激活\tconfirm\t确认激活 皮筏艇\tparams\t2026-10-25 10:00:00\tconfirmed\n"
            raw = (header + row).encode("utf-8")
            target.write_bytes(raw)
            original = mod.APPROVALS
            mod.APPROVALS = target
            try:
                buf = io.StringIO()
                with contextlib.redirect_stdout(buf):
                    with self.assertRaises(SystemExit) as ctx:
                        mod.main(["demote-migrated", "--confirm", "MIGRATION-DEMOTE"])
                after = target.read_bytes()
            finally:
                mod.APPROVALS = original
        self.assertEqual(1, ctx.exception.code)
        self.assertIn("BOM", buf.getvalue())
        self.assertEqual(raw, after, "拒绝时必须一个字节都不改")

    def test_record_writes_bom_for_new_ledger(self):
        """新账本一律写 BOM；否则之后 demote 会把自己的文件当二义性拒绝。"""
        mod = self._load_approval_module()
        with tempfile.TemporaryDirectory() as td:
            target = Path(td) / "approvals.tsv"
            original = mod.APPROVALS
            mod.APPROVALS = target
            try:
                mod.record("proj", "S5", "confirm", "可以保存", "sha256:abc")
                raw = target.read_bytes()
            finally:
                mod.APPROVALS = original
        self.assertTrue(raw.startswith(b"\xef\xbb\xbf"))
        self.assertIn("可以保存", raw.decode("utf-8-sig"))

    def test_record_upgrades_ascii_ledger_preserving_bytes(self):
        """旧纯 ASCII 账本补 BOM 时，原有字节必须逐字节保留。"""
        mod = self._load_approval_module()
        header = "\t".join(mod.COLUMNS) + "\n"
        row = "ap-1\tproj\tS5\tconfirm\tok\tparams\t2026-10-25 10:00:00\tconfirmed\n"
        with tempfile.TemporaryDirectory() as td:
            target = Path(td) / "approvals.tsv"
            target.write_text(header + row, encoding="utf-8")
            before = target.read_bytes()
            original = mod.APPROVALS
            mod.APPROVALS = target
            try:
                mod.record("proj2", "S6", "confirm", "second", "sha256:def")
                raw = target.read_bytes()
            finally:
                mod.APPROVALS = original
        self.assertTrue(raw.startswith(b"\xef\xbb\xbf" + before))

    @unittest.skipUnless(os.name == "posix", "需要可执行 shell 脚本充当 curl")
    def test_version_check_decodes_github_json_as_utf8(self):
        """GitHub 返回 UTF-8 JSON：父进程若按 ANSI/ASCII 解码，会在 reader 线程抛 UnicodeDecodeError（Windows 实踩）。"""
        with tempfile.TemporaryDirectory() as td:
            bin_dir = Path(td) / "bin"
            bin_dir.mkdir()
            fake = bin_dir / "curl"
            fake.write_text(
                "#!/bin/sh\nprintf '%s' '{\"tag_name\":\"v9.9.9\",\"body\":\"中文发行说明\"}'\n",
                encoding="utf-8")
            fake.chmod(0o755)
            script = (
                "import importlib.util, tempfile\n"
                "from pathlib import Path\n"
                f"spec = importlib.util.spec_from_file_location('vc', r'{ROOT / 'tools' / 'version_check.py'}')\n"
                "m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)\n"
                f"m.CACHE = Path(r'{td}') / 'vc.json'\n"
                "print('REMOTE=' + str(m._remote_version_cached()))\n"
            )
            env = dict(os.environ)
            env["PATH"] = str(bin_dir) + os.pathsep + env.get("PATH", "")
            env.update({"PYTHONUTF8": "0", "PYTHONCOERCECLOCALE": "0",
                        "LC_ALL": "C", "PYTHONIOENCODING": "utf-8"})
            proc = subprocess.run([sys.executable, "-c", script], capture_output=True,
                                  text=True, encoding="utf-8", errors="replace",
                                  env=env, timeout=120)
        self.assertNotIn("Traceback", proc.stderr, proc.stderr[-800:])
        self.assertIn("REMOTE=9.9.9", proc.stdout)

    @unittest.skipUnless(os.name == "posix", "需要可执行 shell 脚本充当 curl")
    def test_workspace_guard_decodes_probe_as_utf8(self):
        """平台返回 UTF-8 JSON：父进程若按 ANSI/ASCII 解码，会在 reader 线程抛 UnicodeDecodeError（同 version_check）。"""
        with tempfile.TemporaryDirectory() as td:
            bin_dir = Path(td) / "bin"
            bin_dir.mkdir()
            fake = bin_dir / "curl"
            fake.write_text(
                "#!/bin/sh\nprintf '%s' '{\"isOrg\": true, \"note\": \"中文工作空间\"}'\n",
                encoding="utf-8")
            fake.chmod(0o755)
            script = (
                "import importlib.util, sys\n"
                f"sys.path.insert(0, r'{ROOT / 'tools'}')\n"
                f"spec = importlib.util.spec_from_file_location('wg', r'{ROOT / 'tools' / 'workspace_guard.py'}')\n"
                "m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)\n"
                "print('PROBE=' + repr(m._probe('a&b&c', 'uid')))\n"
            )
            env = dict(os.environ)
            env["PATH"] = str(bin_dir) + os.pathsep + env.get("PATH", "")
            env.update({"PYTHONUTF8": "0", "PYTHONCOERCECLOCALE": "0",
                        "LC_ALL": "C", "PYTHONIOENCODING": "utf-8"})
            proc = subprocess.run([sys.executable, "-c", script], capture_output=True,
                                  text=True, encoding="utf-8", errors="replace",
                                  env=env, timeout=120)
        self.assertNotIn("Traceback", proc.stderr, proc.stderr[-800:])
        self.assertIn("'isOrg': True", proc.stdout)
        self.assertIn("中文工作空间", proc.stdout)

    def test_tools_with_unicode_output_enable_utf8_stdout(self):
        """含 GBK 不可编码字符的工具，必须定义并调用 _utf8_stdout（AST 检测，覆盖 print/out/别名等任意输出写法）。"""
        offenders = []
        for path in sorted((ROOT / "tools").glob("*.py")):
            text = path.read_text(encoding="utf-8")
            unencodable = False
            for ch in set(text):
                if ord(ch) <= 127:
                    continue
                try:
                    ch.encode("gbk")
                except UnicodeEncodeError:
                    unencodable = True
                    break
            if not unencodable:
                continue
            tree = ast.parse(text)
            is_entry = any(
                isinstance(node, ast.If)
                and isinstance(node.test, ast.Compare)
                and isinstance(node.test.left, ast.Name)
                and node.test.left.id == "__name__"
                for node in tree.body
            )
            has_output = any(
                isinstance(node, ast.Call)
                and (
                    (isinstance(node.func, ast.Name)
                     and node.func.id in {"print", "out", "emit", "log"})
                    or (isinstance(node.func, ast.Attribute)
                        and node.func.attr == "write"
                        and isinstance(node.func.value, ast.Attribute)
                        and node.func.value.attr in {"stdout", "stderr"})
                )
                for node in ast.walk(tree)
            )
            if not (is_entry or has_output):
                continue
            has_def = any(
                isinstance(node, ast.FunctionDef) and node.name == "_utf8_stdout"
                for node in tree.body
            )
            called = any(
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "_utf8_stdout"
                for node in ast.walk(tree)
            )
            if not (has_def and called):
                offenders.append(path.name)
        self.assertEqual(offenders, [], "缺少 _utf8_stdout 定义或调用：%s" % ", ".join(offenders))

    def test_version_notice_prints_under_ascii_pipe(self):
        """Windows 管道（ASCII 默认编码）下版本提示必须能打印，不得 UnicodeEncodeError。"""
        script = (
            "import importlib.util, sys\n"
            f"spec = importlib.util.spec_from_file_location('vc', r'{ROOT / 'tools' / 'version_check.py'}')\n"
            "m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)\n"
            "m.check_update = lambda force=False: ('0.1.0', '0.2.0', True)\n"
            "m.print_notice_if_newer()\n"
        )
        env = dict(os.environ)
        env.update({"PYTHONUTF8": "0", "PYTHONCOERCECLOCALE": "0",
                    "LC_ALL": "C", "PYTHONIOENCODING": "ascii"})
        proc = subprocess.run([sys.executable, "-c", script], capture_output=True,
                              text=True, encoding="utf-8", errors="replace",
                              env=env, timeout=60)
        self.assertEqual(proc.returncode, 0, proc.stderr[-800:])
        self.assertNotIn("Traceback", proc.stderr)
        self.assertIn("有新版本", proc.stdout)

    def test_readme_install_prompt_has_windows_command(self):
        text = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn("py tools\\startup_gate.py", text)
        self.assertIn("python3 tools/startup_gate.py", text)


if __name__ == "__main__":
    unittest.main()
