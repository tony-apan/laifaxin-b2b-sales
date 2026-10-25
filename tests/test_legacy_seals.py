# -*- coding: utf-8 -*-
"""旧脚本物理封条 + 安装自检退出码回归（2026-10-23）。

封条语义（RULES「🧱 脚本使用边界」）：
  * save_first_n / contact_add / delete_all_products / wait_save_done 在最早可执行
    位置调用 save_guard.require()；任何写/推进路径（含 dry-run）一律
    SystemExit("DEPRECATED: use save_guard")，无环境变量可绕过；
  * --help 在 argparse 内提前返回，仍为 0；import save_first_n 不受影响；
  * onboard_check.py 环境自检失败 exit 2、成功 exit 0（AGENTS「未通过不得开始」真实门）。
"""
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
SEAL_MSG = "DEPRECATED: use save_guard"

RECORD = "runs/tony/pet-food-packaging/operation-record.md"
PROFILE = "runs/tony/pet-food-packaging/product-profile.md"

SAVE_ARGS = ("--token", "t", "--org", "o", "--keyword", "seed.example", "--n", "8",
             "--company-tag", "c", "--contact-tag", "ct", "--profile", PROFILE,
             "--record", RECORD, "--project", "tony/pet-food-packaging")
CONTACT_ARGS = ("--token", "t", "--org", "o", "--seq", "s", "--tags", "c", "--task", "k",
                "--record", RECORD, "--project", "tony/pet-food-packaging")
DELETE_ARGS = ("--token", "t", "--org", "o")
DELETE_EXEC_ARGS = ("--token", "t", "--org", "o", "--execute", "--confirm", "DELETE-ALL")
WAIT_ARGS = ("--token", "t", "--org", "o", "--task", "k", "--tag", "c", "--record", RECORD)


def run_tool(script, *args, env_extra=None, timeout=120):
    """子进程跑工具；剔除 LFX_GATE_*，确保封条与开工门/测试放行环境无关。"""
    env = {k: v for k, v in os.environ.items()
           if not k.startswith("LFX_GATE_") and not k.startswith("STEP_GATE_")}
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    if env_extra:
        env.update(env_extra)
    return subprocess.run(
        [sys.executable, str(TOOLS / script), *[str(a) for a in args]],
        cwd=str(ROOT), capture_output=True, text=True,
        encoding="utf-8", errors="replace", env=env, timeout=timeout)


class LegacyScriptSealTest(unittest.TestCase):
    """4 个旧脚本：写/推进一律封死，--help 仍可用。"""

    SCRIPTS = ("save_first_n.py", "contact_add.py", "delete_all_products.py", "wait_save_done.py")

    def test_help_still_exits_zero(self):
        for script in self.SCRIPTS:
            with self.subTest(script=script):
                r = run_tool(script, "--help")
                self.assertEqual(0, r.returncode, f"{script} --help 应仍为 0\n{r.stdout}\n{r.stderr}")
                self.assertIn("usage", (r.stdout + r.stderr).lower())

    def test_write_paths_are_sealed(self):
        cases = (
            ("save_first_n.py", SAVE_ARGS),
            ("contact_add.py", CONTACT_ARGS),
            ("contact_add.py", CONTACT_ARGS + ("--dry-run",)),
            ("delete_all_products.py", DELETE_ARGS),               # 默认 dry-run 也不得放行
            ("delete_all_products.py", DELETE_EXEC_ARGS),          # 真删路径
            ("wait_save_done.py", WAIT_ARGS),
        )
        for script, args in cases:
            with self.subTest(script=script, args=args):
                r = run_tool(script, *args)
                self.assertEqual(1, r.returncode,
                                 f"{script} 未按 SystemExit 退出：rc={r.returncode}\n{r.stdout}\n{r.stderr}")
                self.assertIn(SEAL_MSG, r.stdout + r.stderr,
                              f"{script} 缺少封条文案：\n{r.stdout}\n{r.stderr}")

    def test_seal_precedes_network_and_state_writes(self):
        """封条必须在主流程首次网络调用/状态推进之前（按真实调用点锁定，不按 import 行）。"""
        call_markers = {
            "save_first_n.py": ("require_state(", "update_frontmatter(", "api(args.org"),
            "contact_add.py": ("require_state(", "update_frontmatter(", 'api("sequences/contact-add"'),
            "delete_all_products.py": ("subprocess.run(", "Path(args.backup_manifest).write_text"),
            "wait_save_done.py": ("require_state(", "update_frontmatter("),
        }
        for script in self.SCRIPTS:
            source = (TOOLS / script).read_text(encoding="utf-8")
            with self.subTest(script=script):
                self.assertIn("from save_guard import require as _save_guard_require", source)
                self.assertIn("_save_guard_require()", source)
                seal_at = source.index("_save_guard_require()")
                for marker in call_markers[script]:
                    idx = source.find(marker)
                    self.assertNotEqual(-1, idx, f"{script}: 找不到调用点 {marker!r}")
                    self.assertLess(seal_at, idx, f"{script}: 封条须在 {marker!r} 之前")

    def test_import_save_first_n_unaffected(self):
        r = subprocess.run(
            [sys.executable, "-c", "import sys; sys.path.insert(0, 'tools'); import save_first_n; print('imported')"],
            cwd=str(ROOT), capture_output=True, text=True, timeout=60)
        self.assertEqual(0, r.returncode, r.stdout + r.stderr)
        self.assertIn("imported", r.stdout)

    def test_save_guard_require_is_unconditional(self):
        sys.path.insert(0, str(TOOLS))
        try:
            import save_guard
        finally:
            pass
        with self.assertRaises(SystemExit) as ctx:
            save_guard.require()
        self.assertIn(SEAL_MSG, str(ctx.exception))


class OnboardCheckExitCodeTest(unittest.TestCase):
    """onboard_check.py：env_ok=False → exit 2；成功 → exit 0。"""

    @staticmethod
    def _shim_bins(bin_dir, names):
        for name in names:
            p = Path(bin_dir) / name
            p.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            p.chmod(0o755)

    def test_env_ok_exits_zero(self):
        with tempfile.TemporaryDirectory() as tmp:
            self._shim_bins(tmp, ("curl", "bash", "grep", "awk"))
            r = run_tool("onboard_check.py", env_extra={"PATH": tmp})
            self.assertEqual(0, r.returncode,
                             "自检通过应 exit 0：\n" + r.stdout[-2000:] + "\n" + r.stderr[-2000:])

    def test_missing_dependency_exits_two(self):
        with tempfile.TemporaryDirectory() as tmp:
            # 空目录 PATH：python 由 sys.executable 兜底，curl/bash/grep/awk 全缺 → env_ok=False
            r = run_tool("onboard_check.py", env_extra={"PATH": tmp})
            self.assertEqual(2, r.returncode,
                             "自检失败应 exit 2：\n" + r.stdout[-2000:] + "\n" + r.stderr[-2000:])
            self.assertIn("缺环境依赖", r.stdout)


if __name__ == "__main__":
    unittest.main()
