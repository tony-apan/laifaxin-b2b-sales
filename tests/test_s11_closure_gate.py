#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""S11 收口证明闸门（三审 S1-8/S2-4）单元回归。

只认 finalize_run 写的 s11_finalized_at + s11_manifest_sha256；
手写 status: S11、过期收口、缺字段、坏 sha 一律判无效。
"""
import datetime
import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("_s11_closure", ROOT / "tools" / "s11_closure.py")


class S11ClosureGateTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.mod = importlib.util.module_from_spec(SPEC)
        SPEC.loader.exec_module(cls.mod)
        cls.sha = "a" * 64

    def _meta(self, **overrides):
        meta = {
            "status": "S11",
            "s11_finalized_at": datetime.datetime.now().isoformat(timespec="seconds"),
            "s11_manifest_sha256": self.sha,
        }
        meta.update(overrides)
        return meta

    def test_fresh_finalized_record_passes(self):
        self.assertEqual([], self.mod.check_s11_closure(self._meta()))

    def test_hand_written_status_only_is_rejected(self):
        issues = self.mod.check_s11_closure({"status": "S11"})
        self.assertTrue(any("s11_finalized_at" in i for i in issues), issues)
        self.assertTrue(any("s11_manifest_sha256" in i for i in issues), issues)

    def test_stale_finalize_is_rejected(self):
        old = (datetime.datetime.now() - datetime.timedelta(hours=25)).isoformat(timespec="seconds")
        issues = self.mod.check_s11_closure(self._meta(s11_finalized_at=old), max_age_hours=24)
        self.assertTrue(any("超过 24 小时" in i for i in issues), issues)

    def test_bad_time_or_sha_shape_is_rejected(self):
        self.assertTrue(self.mod.check_s11_closure(self._meta(s11_finalized_at="not-a-date")))
        self.assertTrue(self.mod.check_s11_closure(self._meta(s11_manifest_sha256="abc")))

    def test_future_time_is_rejected(self):
        future = (datetime.datetime.now() + datetime.timedelta(hours=2)).isoformat(timespec="seconds")
        issues = self.mod.check_s11_closure(self._meta(s11_finalized_at=future))
        self.assertTrue(any("未来" in i for i in issues), issues)


if __name__ == "__main__":
    unittest.main()
