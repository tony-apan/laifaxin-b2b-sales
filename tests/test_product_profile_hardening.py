import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "tools" / "product_profile.py"


class ProductProfileHardeningTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.profile = Path(self.tmp.name) / "product-profile.md"
        self.record = self.profile.parent / "operation-record.md"
        result = self.run_cli(
            "init", "--profile", self.profile,
            "--operator-key", "acme", "--product-key", "widget",
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def tearDown(self):
        self.tmp.cleanup()

    def run_cli(self, *args):
        return subprocess.run(
            [sys.executable, str(CLI), *map(str, args)],
            cwd=ROOT,
            text=True,
            capture_output=True,
        )

    def test_confirmed_validation_requires_confirm_quote(self):
        result = self.run_cli(
            "confirm", "--profile", self.profile,
            "--by", "Tony", "--quote", "确认当前档案",
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        text = self.profile.read_text(encoding="utf-8")
        self.profile.write_text(
            re.sub(r"(?m)^confirm_quote:.*$", "confirm_quote:", text, count=1),
            encoding="utf-8",
        )
        result = self.run_cli("validate", "--profile", self.profile, "--require-confirmed")
        self.assertEqual(result.returncode, 2)
        self.assertIn("缺 confirm_quote", result.stdout)

    def test_declined_to_confirmed_increments_version(self):
        result = self.run_cli("decline", "--profile", self.profile, "--quote", "暂不提供")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("profile_version: 1", self.profile.read_text(encoding="utf-8"))
        result = self.run_cli(
            "confirm", "--profile", self.profile,
            "--by", "Tony", "--quote", "确认重新启用档案",
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("profile_version: 2", self.profile.read_text(encoding="utf-8"))

    def test_s12_rejects_confirm_and_decline_without_profile_write(self):
        result = self.run_cli(
            "confirm", "--profile", self.profile,
            "--by", "Tony", "--quote", "确认当前档案",
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        record_text = self.record.read_text(encoding="utf-8")
        self.record.write_text(
            re.sub(r"(?m)^status:.*$", "status: S12", record_text, count=1),
            encoding="utf-8",
        )
        before = self.profile.read_bytes()
        mtime = self.profile.stat().st_mtime_ns
        for args in (
            ("confirm", "--profile", self.profile, "--by", "Tony", "--quote", "确认修改"),
            ("decline", "--profile", self.profile, "--quote", "暂不提供"),
        ):
            result = self.run_cli(*args)
            self.assertEqual(result.returncode, 2)
            self.assertIn("S12/ACTIVE", result.stdout)
            self.assertEqual(self.profile.read_bytes(), before)
            self.assertEqual(self.profile.stat().st_mtime_ns, mtime)


if __name__ == "__main__":
    unittest.main()
