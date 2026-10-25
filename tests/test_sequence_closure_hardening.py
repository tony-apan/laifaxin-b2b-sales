#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""任务A 回归测试：闭合序列 / 激活 / verify 三处加固（2026-10-23）。

覆盖契约：
  A1 build_sequence: tmap 分组 exact=False / 总数非 12 倍数 → 任何平台调用之前中文报错 exit 2；
                     建完自动终检失败 → exit 2 且不推进 S9；成功则推进 S9。
  A2 verify_sequence: 分组(folder)模板必须计入（旧 `not t.get("folder")` 会误判失败）；
                      模板库为空 / 步骤未绑定模板 → 中文报错，不得静默通过。
  A3 activate_sequence: 激活写之前只读校验 sequence-details(rules/notSentTags) + step-list(12步都绑模板)；
                      不满足 exit 2，不发起 sequence-active、不推进状态；满足时正常激活。

全部用 PATH 注入的假 curl 截获，零真实网络。
"""
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

NOW_ISO = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
ROOT = Path(__file__).resolve().parents[1]
PROJECT = "tony/pet-pack"
OPERATOR, PRODUCT = "tony", "pet-pack"
ORG = "fake-org-for-offline-test"
TOKEN = "web.laifaxin.com&fake-user-uid&fake-token-for-offline-test"
SEQ = "000000000000000000000047"
INQUIRY_TAG = "000000000000000000000043"
STOP_TAG = "000000000000000000000044"
SEQ_NAME = "英语-宠物食品包装-12轮4封-多轮开发"


# 最小合法产品档案（status=declined = 用户明确跳过资料，仍可继续；过 profile_gate）
PROFILE_FIXTURE = """---
profile_version: 1
status: declined
operator_key: tony
product_key: pet-pack
created_at: 2026-09-17T00:00:00
updated_at: 2026-09-17T00:00:00
confirmed_at:
confirmed_by:
confirm_quote:
content_sha256:
sources_status: declined
sources_present: no
---

# 产品知识档案

## ① 产品定位（卖给谁/解决什么）
- 内容：（待补）
- source: none
- confidence: low

## ② 产品线（品类/子品类/SKU/成分配比）
- 内容：（待补）
- source: none
- confidence: low

## ③ 核心卖点（≤5 条，每条一句：为什么买你）
- 内容：（待补）
- source: none
- confidence: low

## ④ 目标客群+市场（国家/语言/渠道角色）
- 内容：（待补）
- source: none
- confidence: low

## ⑤ 规格/认证（型号/标准号/证书/参数——有来源才写）
- 内容：（待补）
- source: none
- confidence: low

## ⑥ 差异化（vs 竞品强在哪）
- 内容：（待补）
- source: none
- confidence: low

## ⑦ 合规/禁忌（禁运区/受管制品类/环保声明——有依据才写）
- 内容：（待补）
- source: none
- confidence: low

## ⑧ 可引用数字（产能/MOQ/交期/价格带——用户给或官网可查才写，没有不编）
- 内容：（待补）
- source: none
- confidence: low
"""


# 假 curl：按配置文件回放平台响应；写调用（sequence-active）会让后续 sequence-list 变成 active。
FAKE_CURL = r'''#!/usr/bin/env python3
import json, os, sys
from pathlib import Path
from urllib.parse import urlparse

log = Path(os.environ["LFX_FAKE_CURL_LOG"])
cfg = json.loads(Path(os.environ["LFX_FAKE_CURL_CONFIG"]).read_text(encoding="utf-8"))
args = sys.argv[1:]
url = next((a for a in args if a.startswith("http")), "")
path = urlparse(url).path
payload = {}
if "-d" in args:
    try:
        payload = json.loads(args[args.index("-d") + 1])
    except Exception:
        payload = {}
entry = {"path": path, "payload": payload}
with log.open("a", encoding="utf-8") as f:
    f.write(json.dumps(entry, ensure_ascii=False) + "\n")
prior = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines() if line]

def seen(p):
    return [r for r in prior if r.get("path") == p]

def data_list(items):
    return {"success": True, "data": {"list": items}}

def data_value(value):
    return {"success": True, "data": value}

seq = cfg.get("seq", "000000000000000000000047")
status = "active" if seen("/api/sequences/sequence-active") else cfg.get("status", "inactive")
created = bool(seen("/api/sequences/sequence-create")) or cfg.get("sequence_exists", False)
templates = [] if cfg.get("templates_empty") else cfg.get("templates", [])
steps = cfg.get("steps")
if cfg.get("steps_from_create"):
    steps = [dict(r["payload"]) for r in seen("/api/sequences/step-create")]
for no in cfg.get("drop_step_templates", []):
    for s in (steps or []):
        if s.get("step") == no:
            s.pop("template_ids", None)

if path == "/api/benefits/refine-data":
    out = {"success": True, "data": {"isOrg": True, "vip": 2, "dailyLimit": 500,
                                     "monthlyLimit": 10000, "dailyUsed": 1, "monthlyUsed": 2}}
elif path == "/api/settings/sequence/schedule-list":
    out = data_list([{"id": "000000000000000000000045", "name": "US work hours",
                      "time_zone": "America/New_York", "isDefault": True}])
elif path == "/api/contacts/tags-list":
    created = {r.get("payload", {}).get("name") for r in prior
               if r.get("path") == "/api/contacts/tags-add"}
    _all = [{"id": cfg.get("inquiry_tag", "000000000000000000000043"), "name": "询盘"},
            {"id": cfg.get("stop_tag", "000000000000000000000044"), "name": "不发"}]
    out = data_list([t for t in _all if t["name"] not in cfg.get("missing_tags", []) or t["name"] in created])
elif path == "/api/contacts/tags-add":
    out = ({"success": False, "message": "no permission"} if cfg.get("tag_add_fail")
           else data_value({"id": "%024x" % (900 + len(seen("/api/contacts/tags-add")))}))
elif path == "/api/sequences/sequence-list":
    items = [{"id": seq, "name": cfg.get("name", "英语-测试-12轮4封-x"),
              "status": status, "active": status == "active"}] if created else []
    out = data_list(items)
elif path == "/api/sequences/sequence-create":
    out = data_value({"id": seq})
elif path == "/api/sequences/sequence-save":
    out = data_value({})
elif path == "/api/sequences/sequence-details":
    default_rules = {"otherReplayValue": "nothing",
                     "max_emails_per_day": 30000, "domain_emails_per_day": 5,
                     "notSentTags": [cfg.get("inquiry_tag", "000000000000000000000043"),
                                     cfg.get("stop_tag", "000000000000000000000044")]}
    out = data_value(cfg.get("sequence_details", {"rules": default_rules}))
elif path == "/api/sequences/step-create":
    out = data_value({"id": "%024x" % (int(payload.get("step", 0)) + 512)})
elif path == "/api/sequences/step-list":
    # 平台 step-list 的 data 直接是步骤数组（verify/activate 都按数组消费）
    out = {"success": True, "data": steps if steps is not None else []}
elif path == "/api/mailbox/templates-list":
    out = data_list(templates)
elif path == "/api/sequences/sequence-active":
    out = data_value({})
else:
    with log.open("a", encoding="utf-8") as f:
        f.write(json.dumps({"unknown": path}, ensure_ascii=False) + "\n")
    out = {"success": False, "message": "unknown fake path: " + path}
print(json.dumps(out, ensure_ascii=False))
'''


def _steps_fixture(template_ids):
    steps = []
    for no in range(1, 13):
        wait = ("minute", 30) if no == 1 else ("day", 5) if no == 2 else ("day", 15) if no == 3 else ("day", 30)
        steps.append({"step": no, "template_ids": template_ids[(no - 1) * 4:no * 4],
                      "wait_mode": wait[0], "wait_time": wait[1]})
    return steps


def _install_curl(bin_dir, cwd_dir, body):
    """POSIX 用 sh 壳；Windows 编译 curl.exe 到工具 cwd（CreateProcess 先查当前目录）。"""
    bin_dir = Path(bin_dir)
    cwd_dir = Path(cwd_dir)
    fake_py = cwd_dir / "fake_curl.py"
    fake_py.write_text(body, encoding="utf-8")
    if os.name != "nt":
        curl = bin_dir / "curl"
        curl.write_text('#!/bin/sh\nexec "%s" "%s" "$@"\n' % (sys.executable, fake_py), encoding="utf-8")
        curl.chmod(0o755)
        return
    try:
        from test_cross_platform import _WIN_CURL_SHIM_CS
    except ImportError:
        from tests.test_cross_platform import _WIN_CURL_SHIM_CS
    win = Path(os.environ.get("WINDIR", r"C:\Windows"))
    csc = next((q for q in (
        win / "Microsoft.NET" / "Framework64" / "v4.0.30319" / "csc.exe",
        win / "Microsoft.NET" / "Framework" / "v4.0.30319" / "csc.exe",
    ) if q.exists()), None)
    if csc is None:
        raise unittest.SkipTest("Windows 需要 .NET Framework csc.exe 编译 curl 影子")
    src = cwd_dir / "curl_shim.cs"
    src.write_text(_WIN_CURL_SHIM_CS, encoding="utf-8")
    exe = cwd_dir / "curl.exe"
    subprocess.run([str(csc), "/nologo", "/out:" + str(exe), str(src)],
                   capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120, check=True)

class _RepoCase(unittest.TestCase):
    """隔离仓库副本 + 假 curl + 项目夹具。"""

    maxDiff = None

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="seqgate-"))
        self.repo = self.tmp / "repo"
        shutil.copytree(ROOT, self.repo, ignore=shutil.ignore_patterns(
            ".git", ".local", "runs", "__pycache__", ".pytest_cache"))
        self.bin = self.tmp / "bin"
        self.bin.mkdir()
        _install_curl(self.bin, self.repo, FAKE_CURL)
        self.log = self.tmp / "curl.jsonl"
        self.config = self.tmp / "curl-config.json"
        self.project_dir = self.repo / "runs" / OPERATOR / PRODUCT
        self.project_dir.mkdir(parents=True)
        self.profile = self.project_dir / "product-profile.md"
        self.profile.write_text(PROFILE_FIXTURE, encoding="utf-8")
        self.record = self.project_dir / "operation-record.md"
        self.write_record("S8")
        self.env = os.environ.copy()
        self.env.update({
            "PATH": str(self.bin) + os.pathsep + self.env.get("PATH", ""),
            "LFX_GATE_TEST_MODE": "1",
            "LFX_FAKE_CURL_LOG": str(self.log),
            "LFX_FAKE_CURL_CONFIG": str(self.config),
            "PYTHONDONTWRITEBYTECODE": "1",
            "LFX_FAKE_PYTHON": sys.executable,
            "PYTHONIOENCODING": "utf-8",
        })
        self.set_config()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    # ---------- 夹具 ----------
    def write_record(self, status):
        self.record.write_text(
            f"---\noperator_key: {OPERATOR}\nproduct_key: {PRODUCT}\nproject: {PROJECT}\n"
            f"status: {status}\nsequence_id: {SEQ}\n"
            f"next_state: {'S9' if status == 'S8' else ''}\n"
            + (f's11_finalized_at: "{NOW_ISO}"\ns11_manifest_sha256: "{"a" * 64}"\n' if status == "S11" else "")
            + "---\n",
            encoding="utf-8")

    def record_status(self):
        for line in self.record.read_text(encoding="utf-8").splitlines():
            if line.startswith("status:"):
                return line.split(":", 1)[1].strip()
        return ""

    def set_config(self, **cfg):
        self.config.write_text(json.dumps(cfg, ensure_ascii=False), encoding="utf-8")

    def run_tool(self, tool, *args, timeout=180):
        return subprocess.run(
            [sys.executable, str(self.repo / "tools" / tool), *map(str, args)],
            cwd=self.repo, env=self.env, text=True, capture_output=True, timeout=timeout, encoding="utf-8", errors="replace")

    def calls(self, path=None):
        if not self.log.exists():
            return []
        rows = [json.loads(line) for line in self.log.read_text(encoding="utf-8").splitlines() if line]
        return [r for r in rows if path is None or r.get("path") == path]

    def assert_no_write_calls(self):
        """只读链路里不得出现任何平台写接口。"""
        writes = [c for c in self.calls() if c.get("path") in (
            "/api/sequences/sequence-create", "/api/sequences/sequence-save",
            "/api/sequences/sequence-active", "/api/sequences/step-create")]
        self.assertEqual([], writes, "不得发起平台写请求")

    # ---------- 产品档案 / 审批 / 合规 ----------
    def mint_s9(self, mapping):
        self.set_config(templates=[{"_id": v, "name": k, "folder": "英语分组"}
                                   for k, v in mapping.items()])
        binding = {
            "project": PROJECT,
            "org_sha256": hashlib.sha256(ORG.encode("utf-8")).hexdigest(),
            "name": SEQ_NAME, "from_name": "Tony",
            "profile": {"sha256": hashlib.sha256(self.profile.read_bytes()).hexdigest(),
                        "status": "declined", "version": "1"},
            "tmap": {"sha256": hashlib.sha256(self.tmap.read_bytes()).hexdigest()},
            "rules": {"steps": 12, "waits": "step1=30分,step2=5天,step3=15天,step4-12=30天",
                      "tz": "America/New_York", "daily_limit": "30000/5", "not_sent_tags": "询盘/不发"},
        }
        params = self.project_dir / "s9-params.json"
        params.write_text(json.dumps(binding, ensure_ascii=False), encoding="utf-8")
        result = self.run_tool("approval.py", "grant", "--project", PROJECT,
                               "--state", "S9_序列配置", "--quote", "确认执行当前参数",
                               "--params-file", params)
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        return [r for r in self.approval_rows() if r["state"].startswith("S9")][-1]["id"]

    def write_tmap(self, mode="grid", total=48):
        mapping, index = {}, 1
        if mode == "grid":
            for rnd in range(1, 13):
                for var in range(1, total // 12 + 1):
                    mapping[f"英语-宠物食品包装-R{rnd:02d}-方向-V{var:02d}-PF"] = "%024x" % index
                    index += 1
        else:
            for k in range(total):
                mapping[f"英语-宠物食品包装-模板{k + 1:03d}-PF"] = "%024x" % index
                index += 1
        self.tmap = self.project_dir / "tmap.json"
        self.tmap.write_text(json.dumps(mapping, ensure_ascii=False, indent=2), encoding="utf-8")
        meta = {
            "tmap_sha256": hashlib.sha256(self.tmap.read_bytes()).hexdigest(),
            "project_key": PROJECT,
            "org_sha256": hashlib.sha256(ORG.encode("utf-8")).hexdigest(),
            "profile_path_rel": f"runs/{OPERATOR}/{PRODUCT}/product-profile.md",
            "profile_sha256": hashlib.sha256(self.profile.read_bytes()).hexdigest(),
            "profile_status": "declined",
        }
        Path(str(self.tmap) + ".meta.json").write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")
        return mapping

    def build(self, *extra):
        return self.run_tool("build_sequence.py", "--token", TOKEN, "--org", ORG,
                             "--name", SEQ_NAME, "--tmap", self.tmap,
                             "--profile", self.profile, "--from-name", "Tony",
                             "--record", self.record, "--approval", self.ap,
                             "--project", PROJECT, *extra)

    def approval_rows(self):
        path = self.repo / ".local" / "approvals.tsv"
        if not path.exists():
            return []
        lines = path.read_text(encoding="utf-8-sig").splitlines()
        header = lines[0].split("\t")
        return [dict(zip(header, line.split("\t"))) for line in lines[1:] if line.strip()]


class BuildSequenceGridGateTest(_RepoCase):
    """A1: tmap 网格不可信 → 平台调用之前中文报错 exit 2；建完自动终检失败 → exit 2 不推进。"""

    def test_non_grid_names_rejected_before_any_platform_call(self):
        mapping = self.write_tmap(mode="flat", total=48)
        self.ap = self.mint_s9(mapping)
        self.log.unlink(missing_ok=True)
        result = self.build()
        self.assertEqual(2, result.returncode, result.stdout + result.stderr)
        self.assertIn("tmap 分组不可信", result.stdout, "必须中文说明分组不可信（禁止顺序切分）")
        self.assertEqual([], self.calls(), "★网格校验必须在任何平台调用之前完成")
        self.assertEqual("S8", self.record_status(), "失败不得推进状态")

    def test_total_not_multiple_of_twelve_rejected_before_network(self):
        mapping = self.write_tmap(mode="flat", total=47)
        self.ap = self.mint_s9(mapping)
        self.log.unlink(missing_ok=True)
        result = self.build()
        self.assertEqual(2, result.returncode, result.stdout + result.stderr)
        self.assertIn("tmap 网格异常", result.stdout)
        self.assertIn("12", result.stdout)
        self.assertEqual([], self.calls(), "★轮数异常必须在任何平台调用之前报错")
        self.assertEqual("S8", self.record_status())

    def test_auto_verify_failure_exits_2_and_keeps_state(self):
        mapping = self.write_tmap()
        self.ap = self.mint_s9(mapping)
        self.set_config(templates=[{"_id": v, "name": k, "folder": "英语分组"} for k, v in mapping.items()],
                        steps_from_create=True, drop_step_templates=[5])
        self.log.unlink(missing_ok=True)
        result = self.build()
        self.assertEqual(2, result.returncode, result.stdout + result.stderr)
        out = result.stdout + result.stderr
        self.assertIn("建完自动终检未通过", out, "建完必须自动终检并中文报错")
        self.assertIn("step5", out)
        self.assertIn("未绑定", out)
        self.assertEqual(12, len(self.calls("/api/sequences/step-create")), "12 步已建（半成品）")
        self.assertEqual([], self.calls("/api/sequences/sequence-active"), "自动终检失败不得激活")
        self.assertEqual("S8", self.record_status(), "★终检失败不得推进 S9")

    def test_missing_notsent_tags_autocreated_then_sequence_built(self):
        mapping = self.write_tmap()
        self.ap = self.mint_s9(mapping)
        self.set_config(templates=[{"_id": v, "name": k, "folder": "英语分组"} for k, v in mapping.items()],
                        steps_from_create=True, missing_tags=["询盘"])
        self.log.unlink(missing_ok=True)
        result = self.build()
        out = result.stdout + result.stderr
        self.assertEqual(0, result.returncode, out)
        self.assertIn("自动创建", out)
        self.assertIn("已自动创建并解析 notSentTags", out)
        self.assertEqual(1, len(self.calls("/api/contacts/tags-add")), "缺一个标签只建一次")
        self.assertIn("询盘", self.calls("/api/contacts/tags-add")[0]["payload"].get("name"))
        self.assertEqual("S9", self.record_status())

    def test_tag_autocreate_failure_blocks_sequence(self):
        mapping = self.write_tmap()
        self.ap = self.mint_s9(mapping)
        self.set_config(templates=[{"_id": v, "name": k, "folder": "英语分组"} for k, v in mapping.items()],
                        steps_from_create=True, missing_tags=["询盘"], tag_add_fail=True)
        self.log.unlink(missing_ok=True)
        result = self.build()
        out = result.stdout + result.stderr
        self.assertEqual(2, result.returncode, out)
        self.assertIn("自动创建标签", out)
        self.assertEqual([], self.calls("/api/sequences/sequence-create"), "建标签失败不得建序列")
        self.assertEqual("S8", self.record_status())

    def test_auto_verify_success_advances_to_s9(self):
        mapping = self.write_tmap()
        self.ap = self.mint_s9(mapping)
        self.set_config(templates=[{"_id": v, "name": k, "folder": "英语分组"} for k, v in mapping.items()],
                        steps_from_create=True)
        self.log.unlink(missing_ok=True)
        result = self.build()
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertIn("建完自动终检通过", result.stdout)
        self.assertIn("12 步均绑定模板", result.stdout)
        self.assertEqual("S9", self.record_status(), "终检通过才推进 S9")
        self.assertEqual([], self.calls("/api/sequences/sequence-active"), "建序列不得激活")


class VerifySequenceGateTest(_RepoCase):
    """A2: verify_sequence 识别分组模板；模板缺失必须中文报错，不得静默通过。"""

    def verify(self):
        return self.run_tool("verify_sequence.py", "--token", TOKEN, "--org", ORG, "--seq", SEQ)

    def template_pool(self, count=48, folder="英语分组"):
        return [{"_id": "%024x" % (i + 1), "name": f"模板{i + 1}", "folder": folder}
                for i in range(count)]

    def test_grouped_templates_are_counted(self):
        """★旧实现 `not t.get("folder")` 会把已分组模板当成不存在 → 正确序列被误判失败。"""
        pool = self.template_pool(folder="英语分组")
        self.set_config(sequence_exists=True, status="inactive", name=SEQ_NAME,
                        templates=pool, steps=_steps_fixture([t["_id"] for t in pool]))
        result = self.verify()
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertIn("全部12步", result.stdout)
        self.assertNotIn("❌", result.stdout)

    def test_empty_template_library_fails_with_chinese_error(self):
        self.set_config(sequence_exists=True, status="inactive", name=SEQ_NAME,
                        templates_empty=True, steps=_steps_fixture(["%024x" % (i + 1) for i in range(48)]))
        result = self.verify()
        self.assertNotEqual(0, result.returncode)
        out = result.stdout + result.stderr
        self.assertIn("邮件模板库为空", out, "模板库查不到必须中文报错")
        self.assertNotIn("✅ 全部", out, "★不得静默通过")
        self.assertEqual([], [c for c in self.calls() if c.get("path") in (
            "/api/sequences/sequence-active", "/api/sequences/sequence-create")], "终检只读")

    def test_step_without_template_binding_fails(self):
        """★旧缺陷：template_ids=[] 且 wait 正确时，旧实现会打印「✅ 全部12步」静默通过。"""
        pool = self.template_pool()
        steps = _steps_fixture([t["_id"] for t in pool])
        steps[4]["template_ids"] = []
        self.set_config(sequence_exists=True, status="inactive", name=SEQ_NAME,
                        templates=pool, steps=steps)
        result = self.verify()
        self.assertNotEqual(0, result.returncode)
        out = result.stdout + result.stderr
        self.assertIn("step5", out)
        self.assertIn("未绑定任何邮件模板", out)
        self.assertIn("终检失败", out)

    def test_missing_template_id_fails_with_chinese_error(self):
        pool = self.template_pool()
        steps = _steps_fixture([t["_id"] for t in pool])
        steps[0]["template_ids"][0] = "deadbeefdeadbeefdeadbeef"
        self.set_config(sequence_exists=True, status="inactive", name=SEQ_NAME,
                        templates=pool, steps=steps)
        result = self.verify()
        self.assertNotEqual(0, result.returncode)
        self.assertIn("不在邮件模板库", result.stdout)

    def test_wrong_step_count_fails(self):
        pool = self.template_pool()
        steps = _steps_fixture([t["_id"] for t in pool])[:11]
        self.set_config(sequence_exists=True, status="inactive", name=SEQ_NAME,
                        templates=pool, steps=steps)
        result = self.verify()
        self.assertNotEqual(0, result.returncode)
        self.assertIn("11≠12", result.stdout)


class ActivateSequenceStructureGateTest(_RepoCase):
    """A3: 激活写之前只读校验 rules/notSentTags + 12 步模板绑定；不满足 exit 2 不激活。"""

    def setUp(self):
        super().setUp()
        self.write_record("S11")
        self.compliance = self.project_dir / "compliance-check.json"
        now = datetime.now(timezone.utc).isoformat()
        doc = {"evidence_mode": "live", "project": PROJECT, "seq": SEQ, "checked_at": now,
               "profile_sha256": hashlib.sha256(self.profile.read_bytes()).hexdigest()}
        for key in ("market", "list_source", "sender_identity", "unsubscribe", "suppression"):
            doc[key] = {"status": "pass", "evidence": {"source": "平台后台 + 人工逐项核对确认",
                                                        "detail": "已逐项核验通过（详细说明）",
                                                        "checked_at": now}}
        self.compliance.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
        issue = self.run_tool("flow_orchestrator.py", "--resume-s12", "--org", ORG,
                              "--profile", self.profile, "--seq", SEQ,
                              "--compliance-file", self.compliance,
                              "--confirm", "确认激活 皮筏艇找客户")
        self.assertEqual(0, issue.returncode, issue.stdout + issue.stderr)
        self.ap = [r for r in self.approval_rows() if r["state"].startswith("S12")][-1]["id"]

    def activate(self):
        return self.run_tool(
            "activate_sequence.py", "--token", TOKEN, "--org", ORG, "--seq", SEQ,
            "--project", PROJECT, "--profile", self.profile,
            "--compliance-file", self.compliance, "--record", self.record,
            "--confirm", "确认激活 皮筏艇找客户", "--approval", self.ap)

    def pool(self):
        return ["%024x" % (i + 1) for i in range(48)]

    def test_valid_sequence_activates_and_advances_s12(self):
        tids = self.pool()
        self.set_config(sequence_exists=True, status="inactive", name=SEQ_NAME,
                        templates=[{"_id": t, "folder": "英语分组"} for t in tids],
                        steps=_steps_fixture(tids))
        result = self.activate()
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertIn("激活前只读校验", result.stdout)
        self.assertEqual(1, len(self.calls("/api/sequences/sequence-active")))
        self.assertEqual("S12", self.record_status())

    def test_missing_not_sent_tags_blocks_before_activation(self):
        tids = self.pool()
        self.set_config(sequence_exists=True, status="inactive", name=SEQ_NAME,
                        templates=[{"_id": t} for t in tids],
                        steps=_steps_fixture(tids),
                        sequence_details={"rules": {"otherReplayValue": "nothing"}})
        result = self.activate()
        self.assertEqual(2, result.returncode, result.stdout + result.stderr)
        out = result.stdout + result.stderr
        self.assertIn("notSentTags", out)
        self.assertIn("不发起激活请求", out)
        self.assertEqual([], self.calls("/api/sequences/sequence-active"),
                         "★校验失败不得发起激活写")
        self.assertEqual("S11", self.record_status(), "★不得推进状态")

    def test_eleven_steps_blocks_before_activation(self):
        tids = self.pool()
        self.set_config(sequence_exists=True, status="inactive", name=SEQ_NAME,
                        templates=[{"_id": t} for t in tids],
                        steps=_steps_fixture(tids)[:11])
        result = self.activate()
        self.assertEqual(2, result.returncode, result.stdout + result.stderr)
        self.assertIn("11≠12", result.stdout + result.stderr)
        self.assertEqual([], self.calls("/api/sequences/sequence-active"))
        self.assertEqual("S11", self.record_status())

    def test_step_without_template_blocks_before_activation(self):
        tids = self.pool()
        steps = _steps_fixture(tids)
        steps[6]["template_ids"] = []
        self.set_config(sequence_exists=True, status="inactive", name=SEQ_NAME,
                        templates=[{"_id": t} for t in tids], steps=steps)
        result = self.activate()
        self.assertEqual(2, result.returncode, result.stdout + result.stderr)
        out = result.stdout + result.stderr
        self.assertIn("step7", out)
        self.assertIn("未绑定任何邮件模板", out)
        self.assertEqual([], self.calls("/api/sequences/sequence-active"))
        self.assertEqual("S11", self.record_status())

    def test_local_gates_still_precede_any_network(self):
        """保留原有契约：本地审批链不过时零网络。"""
        self.ap = "ap-does-not-exist"
        self.set_config(sequence_exists=True, status="inactive", name=SEQ_NAME)
        result = self.activate()
        self.assertNotEqual(0, result.returncode)
        self.assertEqual([], self.calls(), "本地审批闸门必须早于任何联网")


if __name__ == "__main__":
    unittest.main()
