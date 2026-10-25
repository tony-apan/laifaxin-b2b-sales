"""跨平台一致性测试：Windows/macOS 通用入口、行尾、文案与自检行为。"""
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

    def test_readme_install_prompt_has_windows_command(self):
        text = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn("py tools\\startup_gate.py", text)
        self.assertIn("python3 tools/startup_gate.py", text)


if __name__ == "__main__":
    unittest.main()
