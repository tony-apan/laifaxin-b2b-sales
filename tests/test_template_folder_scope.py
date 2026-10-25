#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""模板分组（folder）不得把已分组模板排除（任务C）。

缺陷：check_template_diff.py / rebuild_templates.py 旧代码用 `if t.get("folder"): continue`
把 templates-list 里带 folder 字段（已归组）的模板跳过——gen_templates 创建模板时会自动分组，
于是"本批 48 个模板"只统计到未分组的那部分：差异检查报"模板数量不符"、重建收集不全。
修复：全部模板按名称前缀识别，分组/未分组都计入。本测试用 folder=true fixture 端到端锁死。
"""
import ast
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"

FAKE_CURL = r'''#!/usr/bin/env python3
import json, os, sys
argv = sys.argv[1:]
url = ""
payload = {}
for i, a in enumerate(argv):
    if "/api/" in a:
        url = a
    if a == "-d" and i + 1 < len(argv):
        try:
            payload = json.loads(argv[i + 1])
        except Exception:
            payload = {}
path = url.split("/api/", 1)[1] if "/api/" in url else ""
log = os.environ.get("CURL_LOG", "")
if log:
    with open(log, "a", encoding="utf-8") as f:
        f.write(path + "\n")
if path == "mailbox/templates-list":
    data = {"list": [
        {"_id": "tpl-a", "name": "英-demo-R01-V01", "folder": True},
        {"_id": "tpl-b", "name": "英-demo-R01-V02", "folder": False},
        {"_id": "tpl-c", "name": "其他-模板", "folder": True},
    ]}
    print(json.dumps({"success": True, "data": data}))
elif path == "mailbox/template-info":
    tid = str(payload.get("id") or "")
    html = {"tpl-a": "<p>unique1 common alpha</p>",
            "tpl-b": "<p>unique2 common alpha</p>"}.get(tid, "<p>other</p>")
    subject = {"tpl-a": "Subject one", "tpl-b": "Subject two"}.get(tid, "Subject other")
    print(json.dumps({"success": True, "data": {"subject": subject, "html": html}}))
else:
    print(json.dumps({"success": False, "message": "unexpected " + path}))
'''



try:
    from gate_env import gate_test_env
except ImportError:
    from tests.gate_env import gate_test_env

class FolderTemplateCountedTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.bin = Path(self.tmp.name) / "bin"
        self.bin.mkdir()
        self.log = Path(self.tmp.name) / "curl.log"
        fake = self.bin / "curl"
        if os.name == "nt":
            raise unittest.SkipTest("Windows 无扩展名 fake curl（离线平台仿真仅 POSIX）；Windows 用真机 smoke 覆盖")
        fake.write_text(FAKE_CURL, encoding="utf-8")
        fake.chmod(0o755)
        self.env = os.environ.copy()
        self.env.update(gate_test_env())
        self.env["PATH"] = str(self.bin) + os.pathsep + self.env.get("PATH", "")
        self.env["CURL_LOG"] = str(self.log)

    def tearDown(self):
        self.tmp.cleanup()

    def test_check_template_diff_counts_folder_true(self):
        r = subprocess.run(
            [sys.executable, str(TOOLS / "check_template_diff.py"),
             "--token", "x", "--org", "1", "--prefix", "英-demo-", "--limit", "2"],
            capture_output=True, text=True, cwd=ROOT, env=self.env, timeout=120, encoding="utf-8", errors="replace")
        out = r.stdout + r.stderr
        self.assertEqual(0, r.returncode, out)
        self.assertIn("模板数: 2", out, "folder=true 的模板被漏掉（旧缺陷）")
        self.assertIn("两两相似度均≤0.70", out)

    def test_scripts_do_not_skip_grouped_templates(self):
        for name in ("check_template_diff.py", "rebuild_templates.py"):
            src = (TOOLS / name).read_text(encoding="utf-8")
            with self.subTest(tool=name):
                self.assertNotIn('if t.get("folder"): continue', src,
                                 "仍在用 folder 字段排除已分组模板")
                self.assertIn('startswith(args.prefix)', src,
                              "应按名称前缀识别本批模板（分组/未分组都计入）")


class RebuildCollectOldTest(unittest.TestCase):
    """直接执行 rebuild_templates.collect_old（避免跑完整重建链）：folder=true 必须计入。"""

    def _load_collect_old(self, api, prefix):
        path = TOOLS / "rebuild_templates.py"
        tree = ast.parse(path.read_text(encoding="utf-8"))
        fn = next((n for n in tree.body
                   if isinstance(n, ast.FunctionDef) and n.name == "collect_old"), None)
        self.assertIsNotNone(fn, "rebuild_templates 缺 collect_old")
        module = ast.Module(body=[fn], type_ignores=[])
        ast.fix_missing_locations(module)
        ns = {"api": api, "args": SimpleNamespace(prefix=prefix)}
        exec(compile(module, str(path), "exec"), ns)
        return ns["collect_old"]

    def test_collect_old_includes_folder_true(self):
        templates = [
            {"_id": "tpl-a", "name": "英-demo-R01-V01", "folder": True},
            {"_id": "tpl-b", "name": "英-demo-R01-V02", "folder": False},
            {"_id": "tpl-c", "name": "其他-模板", "folder": True},
        ]

        def api(path, payload, t=60):
            if path != "mailbox/templates-list":
                return {"success": False}
            page = payload.get("current", 1)
            return {"success": True,
                    "data": {"list": templates if page == 1 else []}}

        collect_old = self._load_collect_old(api, "英-demo-")
        got = collect_old()
        names = [n for n, _ in got]
        self.assertEqual(["英-demo-R01-V01", "英-demo-R01-V02"], names,
                         "collect_old 漏掉 folder=true 的已分组模板或混入非本批模板")


if __name__ == "__main__":
    unittest.main()
