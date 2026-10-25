import datetime
import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PROJECT = "tony/pet-food-packaging"
PRODUCT = "pet-food-packaging"
OPERATOR = "tony"
NICKNAME = "Tony"
TOKEN = "web.laifaxin.com&fake-user-uid&fake-token-for-offline-test"
ORG = "fake-org-for-offline-test"
SEED = "pet-packaging.example"
TASK = "fake-save-task"
COMPANY_TAG = "000000000000000000000041"
CONTACT_TAG = "000000000000000000000042"
INQUIRY_TAG = "000000000000000000000043"
STOP_TAG = "000000000000000000000044"
SEQUENCE = "000000000000000000000047"


FAKE_CURL = r'''#!/usr/bin/env python3
import json
import os
import sys
from pathlib import Path
from urllib.parse import urlparse
import os as _os
_os.environ.setdefault("LFX_GATE_TEST_MODE", "1")

log_path = Path(os.environ["LFX_FAKE_CURL_LOG"])
args = sys.argv[1:]
url = next((a for a in args if a.startswith("http://") or a.startswith("https://")), "")
path = urlparse(url).path
payload = {}
if "-d" in args:
    try:
        payload = json.loads(args[args.index("-d") + 1])
    except Exception:
        payload = {"_invalid": args[args.index("-d") + 1]}

def rows():
    if not log_path.exists():
        return []
    return [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines() if line]

prior = rows()
known = {
    "/api/refine/company-save", "/api/operation/backend-task-status",
    "/api/contacts/contacts/show", "/api/mailbox/templates-folder-list",
    "/api/mailbox/template-folder-add", "/api/mailbox/template-add",
    "/api/settings/sequence/schedule-list", "/api/contacts/tags-list",
    "/api/sequences/sequence-list", "/api/sequences/sequence-create",
    "/api/sequences/sequence-save", "/api/sequences/sequence-details",
    "/api/sequences/step-create", "/api/sequences/contact-add",
    "/api/sequences/step-list", "/api/mailbox/templates-list",
    "/api/mailbox/template-info", "/api/refine/company-list",
    "/api/benefits/refine-data",
}
entry = {"path": path, "payload": payload}
if path not in known:
    entry["unknown"] = True
    with log_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    print(json.dumps({"success": False, "message": "unknown fake path: " + path}))
    raise SystemExit(99)
with log_path.open("a", encoding="utf-8") as f:
    f.write(json.dumps(entry, ensure_ascii=False) + "\n")

template_rows = [r for r in prior if r["path"] == "/api/mailbox/template-add"]
created_sequence = any(r["path"] == "/api/sequences/sequence-create" for r in prior)

if path == "/api/refine/company-save":
    out = {"success": True, "data": {"id": "fake-save-task"}}
elif path == "/api/operation/backend-task-status":
    out = {"success": True, "data": {"status": "finished", "finished": 8, "total": 8, "contactSaveCount": 8}}
elif path == "/api/contacts/contacts/show":
    out = {"success": True, "data": {"total": 8, "list": []}}
elif path == "/api/mailbox/templates-folder-list":
    out = {"success": True, "data": []}
elif path == "/api/mailbox/template-folder-add":
    out = {"success": True, "data": {"id": "000000000000000000000046"}}
elif path == "/api/mailbox/template-add":
    out = {"success": True, "data": {"id": f"{len(template_rows) + 256:024x}"}}
elif path == "/api/settings/sequence/schedule-list":
    out = {"success": True, "data": {"list": [{"id": "000000000000000000000045", "name": "US work hours", "time_zone": "America/New_York", "isDefault": True}]}}
elif path == "/api/contacts/tags-list":
    out = {"success": True, "data": {"list": [
        {"id": "000000000000000000000042", "name": "英语-宠物食品包装"},
        {"id": "000000000000000000000043", "name": "询盘"},
        {"id": "000000000000000000000044", "name": "不发"},
    ]}}
elif path == "/api/sequences/sequence-list":
    items = [{"id": "000000000000000000000047", "name": "英语-宠物食品包装-12轮", "status": "inactive", "active": False}] if created_sequence else []
    out = {"success": True, "data": {"list": items}}
elif path == "/api/sequences/sequence-create":
    out = {"success": True, "data": {"id": "000000000000000000000047"}}
elif path == "/api/sequences/sequence-save":
    out = {"success": True, "data": {}}
elif path == "/api/sequences/sequence-details":
    out = {"success": True, "data": {"rules": {"otherReplayValue": "nothing"}}}
elif path == "/api/sequences/step-create":
    out = {"success": True, "data": {"id": f"{int(payload.get('step', 0)) + 512:024x}"}}
elif path == "/api/sequences/contact-add":
    out = {"success": True, "data": {"add": 8}}
elif path == "/api/sequences/step-list":
    steps = [r["payload"] for r in prior if r["path"] == "/api/sequences/step-create"]
    out = {"success": True, "data": steps}
elif path == "/api/mailbox/templates-list":
    page = int(payload.get("current", 1))
    size = int(payload.get("pageSize", 20))
    start = (page - 1) * size
    all_templates = [{"_id": f"{i + 256:024x}", "name": r["payload"]["name"], "folder": False}
                     for i, r in enumerate(template_rows)]
    out = {"success": True, "data": {"list": all_templates[start:start + size]}}
elif path == "/api/mailbox/template-info":
    wanted = payload.get("id")
    item = next((r["payload"] for i, r in enumerate(template_rows) if f"{i + 256:024x}" == wanted), {})
    out = {"success": True, "data": {"subject": item.get("subject", ""), "html": item.get("html", "")}}
elif path == "/api/refine/company-list":
    out = {"success": True, "data": {"list": [{"company_name": "Example Buyer", "country_code": "US"}]}}
elif path == "/api/benefits/refine-data":
    # 工作空间落点探测：token 中段=fake-user-uid ≠ ORG=fake-org-for-offline-test → 企业空间自洽
    out = {"success": True, "data": {"isOrg": True, "vip": 2, "dailyLimit": 500,
                                     "monthlyLimit": 10000, "dailyUsed": 1, "monthlyUsed": 2}}
else:
    raise AssertionError(path)
print(json.dumps(out, ensure_ascii=False))
'''


class _ShimUnavailable(RuntimeError):
    pass


def _install_curl_shim(bin_dir, cwd_dir=None):
    """装一个能被 CreateProcess 解析的 curl：POSIX 用无扩展名脚本；Windows 编译 curl.exe 转发到 fake_curl.py。

    Windows 的系统 curl.exe 在 System32，PATH 永远抢不过它；但 CreateProcess 会先查
    调用进程的当前目录，所以影子必须落到工具进程的 cwd（副本仓库根）。"""
    if os.name != "nt":
        fake = Path(bin_dir) / "curl"
        fake.write_text(FAKE_CURL, encoding="utf-8")
        fake.chmod(fake.stat().st_mode | stat.S_IXUSR)
        return
    target = Path(cwd_dir or bin_dir)
    (target / "fake_curl.py").write_text(FAKE_CURL, encoding="utf-8")
    win = Path(os.environ.get("WINDIR", r"C:\Windows"))
    csc = next((p for p in (
        win / "Microsoft.NET" / "Framework64" / "v4.0.30319" / "csc.exe",
        win / "Microsoft.NET" / "Framework" / "v4.0.30319" / "csc.exe",
    ) if p.exists()), None)
    if csc is None:
        raise _ShimUnavailable("Windows 离线仿真需要 .NET Framework csc.exe 编译 curl 影子；本机未找到，改由真机 curl 冒烟覆盖")
    src = target / "curl_shim.cs"
    src.write_text(SHIM_CS, encoding="utf-8")
    exe = target / "curl.exe"
    proc = subprocess.run(
        [str(csc), "/nologo", "/out:" + str(exe), str(src)],
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120,
    )
    if proc.returncode != 0 or not exe.exists():
        raise _ShimUnavailable("Windows curl 影子编译失败：" + (proc.stdout + proc.stderr)[-500:])


class FullFlowSimulationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.base = Path(cls.temp.name)
        cls.repo = cls.base / "repo"
        shutil.copytree(ROOT, cls.repo, ignore=shutil.ignore_patterns(".git", "__pycache__", ".pytest_cache", ".local"))
        cls.fake_bin = cls.base / "bin"
        cls.fake_bin.mkdir()
        cls.curl_log = cls.base / "curl.jsonl"
        try:
            _install_curl_shim(cls.fake_bin, cls.repo)
        except _ShimUnavailable as exc:
            raise unittest.SkipTest(str(exc))
        cls.env = os.environ.copy()
        cls.env.update({
            "PATH": str(cls.fake_bin) + os.pathsep + cls.env.get("PATH", ""),
            "LFX_FAKE_CURL_LOG": str(cls.curl_log),
            "LFX_FAKE_PYTHON": sys.executable,
            "PYTHONIOENCODING": "utf-8",
            "PYTHONDONTWRITEBYTECODE": "1",
        })
        cls.project_dir = cls.repo / "runs" / OPERATOR / PRODUCT
        cls.profile = cls.project_dir / "product-profile.md"
        cls.record = cls.project_dir / "operation-record.md"
        cls.results = []

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    @classmethod
    def run_tool(cls, tool, *args, expect=0, output=None, timeout=180):
        result = subprocess.run(
            [sys.executable, str(cls.repo / "tools" / tool), *map(str, args)],
            cwd=cls.repo,
            env=cls.env,
            text=True,
            capture_output=True,
            timeout=timeout,
        encoding="utf-8", errors="replace")
        cls.results.append((tool, result))
        if output is not None:
            Path(output).write_text(result.stdout + result.stderr, encoding="utf-8")
        if result.returncode != expect:
            raise AssertionError(
                f"{tool} returned {result.returncode}, expected {expect}\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
            )
        return result

    @staticmethod
    def sha(path):
        return hashlib.sha256(Path(path).read_bytes()).hexdigest()

    @classmethod
    def write_json(cls, path, doc):
        Path(path).write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")

    @classmethod
    def approval(cls, state, binding):
        params = cls.project_dir / f"{state}-params.json"
        cls.write_json(params, binding)
        result = cls.run_tool(
            "approval.py", "grant", "--project", PROJECT, "--state", state,
            "--quote", "确认执行当前参数", "--params-file", params,
        )
        match = re.search(r"凭证已铸造: (ap-[0-9a-f]+)", result.stdout)
        if not match:
            raise AssertionError(result.stdout)
        return match.group(1)

    @classmethod
    def evidence_item(cls, path):
        return {"status": "pass", "path": Path(path).name, "sha256": cls.sha(path)}

    @classmethod
    def set_record_field(cls, key, value):
        text = cls.record.read_text(encoding="utf-8")
        end = text.find("\n---", 4)
        cls.record.write_text(text[:end] + f"\n{key}: {value}" + text[end:], encoding="utf-8")

    def phase_profiles_state_and_audit_gate(self):
        operator_profile = self.repo / ".local" / "operators" / f"{OPERATOR}.md"
        self.run_tool("operator_profile.py", "--path", operator_profile, "init", "--operator-key", OPERATOR, "--nickname", NICKNAME)
        self.run_tool("product_profile.py", "init", "--profile", self.profile, "--operator-key", OPERATOR, "--product-key", PRODUCT)

        text = self.profile.read_text(encoding="utf-8")
        replacements = {
            "①": ("Pet food flexible packaging for brand owners", "用户"),
            "②": ("Pouches and rollstock", "用户"),
            "③": ("Custom barrier packaging", "用户"),
            "⑤": ("Material options documented by the operator", "用户"),
            "⑥": ("Flexible artwork and format choices", "用户"),
            "⑦": ("Claims require buyer-side review", "用户"),
            "⑧": ("MOQ options available", "用户"),
        }
        for marker, (content, source) in replacements.items():
            pattern = rf"(## {marker}[^\n]*\n)- 内容：[^\n]*\n- source: [^\n]*"
            text, count = re.subn(pattern, rf"\1- 内容：{content}\n- source: {source}", text)
            self.assertEqual(1, count, marker)
        self.profile.write_text(text, encoding="utf-8")
        self.run_tool("product_profile.py", "confirm", "--profile", self.profile, "--by", NICKNAME, "--quote", "确认当前产品档案")
        confirmed = self.profile.read_text(encoding="utf-8")
        section4 = re.search(r"## ④.*?(?=\n## ⑤)", confirmed, re.S).group(0)
        self.assertIn("内容：（待补）", section4)
        self.assertIn("source: none", section4)

        self.run_tool("update_run_state.py", "--record", self.record, "--expected-state", "S1", "--state", "S2", "--next-state", "S3")
        self.run_tool("update_run_state.py", "--record", self.record, "--expected-state", "S2", "--state", "S3", "--next-state", "S4")
        self.set_record_field("seed", SEED)

        audit = self.project_dir / "s4-audit.md"
        review = self.project_dir / "s4-review.md"
        audit.write_text("70% 临界 50页 三页平均 逐页 敏感性\n审计通过\n", encoding="utf-8")
        review.write_text("放行\nP0=0\nP1=0\n", encoding="utf-8")
        manifest = self.project_dir / "audit-manifest.json"
        doc = {
            "project": PROJECT, "profile_sha256": self.sha(self.profile), "seed": SEED,
            "generated_at": datetime.datetime.now().isoformat(timespec="seconds"),
            "evidence_mode": "simulation",
            "evidence": {"audit": self.evidence_item(audit), "review": self.evidence_item(review)},
        }
        self.write_json(manifest, doc)
        before = (self.record.read_bytes(), self.record.stat().st_mtime_ns)
        self.run_tool("finalize_audit.py", "--record", self.record, "--profile", self.profile, "--project", PROJECT, "--manifest", manifest, expect=2)
        self.assertEqual(before, (self.record.read_bytes(), self.record.stat().st_mtime_ns))

        # Test-only clean live fixture: this unit environment never contacts the platform.
        doc["evidence_mode"] = "live"
        self.write_json(manifest, doc)
        self.run_tool("finalize_audit.py", "--record", self.record, "--profile", self.profile, "--project", PROJECT, "--manifest", manifest)
        self.assertIn("status: S4", self.record.read_text(encoding="utf-8"))

    def phase_platform_toolchain_to_s10(self):
        psha = self.sha(self.profile)
        pmeta = {"sha256": psha, "status": "confirmed", "version": "1"}
        org_sha = hashlib.sha256(ORG.encode()).hexdigest()
        # 旧 S5 写脚本（save_first_n/wait_save_done）已加物理封条（save_guard.require，
        # 见 test_legacy_seals）；本仿真不再复制封条后门，只推进状态以验证 S6 之后的现役链路。
        self.run_tool(
            "update_run_state.py", "--record", self.record, "--expected-state", "S4",
            "--state", "S5", "--next-state", "S6",
        )
        self.run_tool(
            "update_run_state.py", "--record", self.record, "--expected-state", "S5",
            "--state", "S6", "--next-state", "S7",
        )

        directions = []
        for i, word in enumerate(("orbit", "harbor", "cedar", "quartz", "maple", "signal", "velvet", "anchor", "cobalt", "meadow", "summit", "willow"), 1):
            angle = " ".join(word + suffix for suffix in ("lane", "crest", "field", "point", "mark", "path", "view", "work", "craft", "scope"))
            # 轮次句含加粗产品词+实体优势（四要素：整封 2-4 处加粗、优势具体化；不用数字避免触发事实闸门）
            # ★2026-09-18：第 3 位改为**逐变体标题列表**（同轮 4 个变体标题必须互不相同，
            #   跨轮也不得重复——用户实测"同一个步骤，标题一致"是错的）
            subjects = [f"{word} packaging — {v} view".replace("view", v)
                        for v in ("sourcing", "quality", "leadtime", "design")]
            directions.append([f"R{i:02d}", f"方向{i}", subjects,
                               f"Are your <b>packaging</b> SKUs locked in? We build <b>seam</b> construction. {angle}"])
        variants = []
        claims = []
        # ★2026-09-11 每轮变体 10→4：整批 = 12 轮 × 4 = 48 个模板
        for word in ("amber", "birch", "coral", "delta"):
            detail = " ".join(word + suffix for suffix in ("tone", "shape", "blend", "frame", "line", "note", "mode", "route", "choice", "brief"))
            # 四要素+视觉扫读：独立 CTA 段 + 加粗回复关键词 + 加粗实体优势(MOQ)；detail 提供变体间差异化
            sentence = (f"Worth a look? Reply \"<b>{word.upper()}</b>\" and I will send our <b>MOQ</b> sheet "
                        f"covering {detail} — no commitment.")
            variants.append(sentence)
            claims.append({"exact_text": sentence, "source": "用户", "profile_field": "⑧", "evidence_text": "MOQ options available"})
        plan = self.project_dir / "plan.json"
        self.write_json(plan, {"profile_sha256": psha, "directions": directions, "variants": variants, "claims": claims})
        tmap = self.project_dir / "tmap.json"
        out_rel = str(tmap.relative_to(self.repo))
        s8_binding = {
            "project": PROJECT, "org_sha256": org_sha, "profile": pmeta,
            "plan": {"sha256": self.sha(plan)}, "name": NICKNAME, "prefix": "英语-宠物食品包装-",
            "suffix": "-PF", "foid": "auto", "out": out_rel,
        }
        s8 = self.approval("S8_批量模板", s8_binding)
        self.run_tool(
            "gen_templates.py", "--token", TOKEN, "--org", ORG, "--product", PRODUCT,
            "--prefix", "英语-宠物食品包装-", "--suffix=-PF", "--name", NICKNAME,
            "--profile", self.profile, "--plan", plan, "--out", tmap, "--record", self.record,
            "--approval", s8, "--project", PROJECT, timeout=240,
        )
        mapping = json.loads(tmap.read_text(encoding="utf-8"))
        self.assertEqual(48, len(mapping), '整批模板数 = 12轮×4变体 = 48')
        self.assertEqual(48, len(set(mapping.values())))
        self.assertTrue(all(re.fullmatch(r"[0-9a-f]{24}", item) for item in mapping.values()))
        self.assertTrue(Path(str(tmap) + ".meta.json").is_file())

        seq_name = "英语-宠物食品包装-12轮"
        s9_binding = {
            "project": PROJECT, "org_sha256": org_sha, "name": seq_name, "from_name": NICKNAME,
            "profile": pmeta, "tmap": {"sha256": self.sha(tmap)},
            "rules": {"steps": 12, "waits": "step1=30分,step2=5天,step3=15天,step4-12=30天", "tz": "America/New_York", "daily_limit": "30000/5", "not_sent_tags": "询盘/不发"},
        }
        s9 = self.approval("S9_序列配置", s9_binding)
        self.run_tool(
            "build_sequence.py", "--token", TOKEN, "--org", ORG, "--name", seq_name,
            "--tmap", tmap, "--profile", self.profile, "--from-name", NICKNAME,
            "--record", self.record, "--approval", s9, "--project", PROJECT,
        )
        # 旧 contact_add.py 已加物理封条（见 test_legacy_seals）；现役 contact_add_authorized
        # 需要开工门 + S10 票据，不在本仿真覆盖范围，这里只推进状态供 S11 收口验证。
        self.run_tool(
            "update_run_state.py", "--record", self.record, "--expected-state", "S9",
            "--state", "S10", "--next-state", "S11",
        )
        self.assertIn("status: S10", self.record.read_text(encoding="utf-8"))

    def phase_verification_s11_and_no_activation(self):
        verify_seq = self.project_dir / "verify-seq.txt"
        verify_exclude = self.project_dir / "verify-exclude.txt"
        verify_diff = self.project_dir / "verify-diff.txt"
        panel = self.project_dir / "verification-panel.md"
        self.run_tool("verify_sequence.py", "--token", TOKEN, "--org", ORG, "--seq", SEQUENCE, output=verify_seq)
        self.run_tool("verify_exclude.py", "--token", TOKEN, "--org", ORG, "--keyword", SEED, output=verify_exclude)
        self.run_tool("check_template_diff.py", "--token", TOKEN, "--org", ORG, "--prefix", "英语-宠物食品包装-", "--limit", 48, output=verify_diff, timeout=180)
        panel.write_text("标签 客群 保存 模板 配额 审查\n状态 inactive，等待人工决策。\n", encoding="utf-8")
        manifest = self.project_dir / "verification-manifest.json"
        doc = {
            "project": PROJECT, "org_sha256": hashlib.sha256(ORG.encode()).hexdigest(),
            "seq": SEQUENCE, "profile_sha256": self.sha(self.profile),
            "generated_at": datetime.datetime.now().isoformat(timespec="seconds"),
            "evidence_mode": "simulation",
            "evidence": {
                "sequence": self.evidence_item(verify_seq), "exclude": self.evidence_item(verify_exclude),
                "diff": self.evidence_item(verify_diff), "panel": self.evidence_item(panel),
            },
        }
        self.write_json(manifest, doc)
        before = (self.record.read_bytes(), self.record.stat().st_mtime_ns)
        self.run_tool(
            "finalize_run.py", "--record", self.record, "--profile", self.profile, "--project", PROJECT,
            "--org", ORG, "--seq", SEQUENCE, "--manifest", manifest, expect=2,
        )
        self.assertEqual(before, (self.record.read_bytes(), self.record.stat().st_mtime_ns))

        # Test-only clean live fixture: generated tool output is accepted only inside this isolated unit copy.
        doc["evidence_mode"] = "live"
        self.write_json(manifest, doc)
        self.run_tool(
            "finalize_run.py", "--record", self.record, "--profile", self.profile, "--project", PROJECT,
            "--org", ORG, "--seq", SEQUENCE, "--manifest", manifest,
        )
        record_text = self.record.read_text(encoding="utf-8")
        self.assertIn("status: S11", record_text)
        self.assertIn("next_state: S12", record_text)
        self.assertIn("inactive", record_text)

        now = datetime.datetime.now().isoformat(timespec="seconds")
        compliance = self.project_dir / "compliance-check.json"
        comp = {"project": PROJECT, "seq": SEQUENCE, "profile_sha256": self.sha(self.profile), "checked_at": now, "evidence_mode": "simulation"}
        for key in ("market", "list_source", "sender_identity", "unsubscribe", "suppression"):
            comp[key] = {"status": "pass", "evidence": {"source": "operator record", "detail": f"{key} control was checked", "checked_at": now}}
        self.write_json(compliance, comp)
        approvals = self.repo / ".local" / "approvals.tsv"
        approvals_before = approvals.read_bytes()
        self.run_tool(
            "flow_orchestrator.py", "--token", TOKEN, "--org", ORG, "--nickname", NICKNAME,
            "--product", PRODUCT, "--profile", self.profile, "--seq", SEQUENCE,
            "--compliance-file", compliance, "--resume-s12", expect=2,
        )
        self.assertEqual(approvals_before, approvals.read_bytes())
        self.run_tool(
            "approval.py", "grant", "--project", PROJECT, "--state", "S12_激活",
            "--quote", "确认激活", "--params", "{}", expect=2,
        )
        self.assertEqual(approvals_before, approvals.read_bytes())

        calls = [json.loads(line) for line in self.curl_log.read_text(encoding="utf-8").splitlines()]
        self.assertFalse(any(call.get("unknown") for call in calls))
        self.assertFalse(any("sequence-active" in call["path"] for call in calls))
        # 旧写入脚本已加物理封条（save_first_n/contact_add/wait_save_done）：
        # 本仿真不再产生 company-save / contact-add 平台写入。
        self.assertEqual([], [c for c in calls if c["path"] == "/api/refine/company-save"])
        self.assertEqual([], [c for c in calls if c["path"] == "/api/sequences/contact-add"])
        self.assertEqual(48, len([c for c in calls if c["path"] == "/api/mailbox/template-add"]))
        steps = [c["payload"] for c in calls if c["path"] == "/api/sequences/step-create"]
        self.assertEqual(list(range(1, 13)), [s["step"] for s in steps])
        sequence_save = next(c["payload"] for c in calls if c["path"] == "/api/sequences/sequence-save")
        self.assertEqual([INQUIRY_TAG, STOP_TAG], sequence_save["rules"]["notSentTags"])

    def test_full_flow_stops_at_s11_inactive(self):
        self.phase_profiles_state_and_audit_gate()
        self.phase_platform_toolchain_to_s10()
        self.phase_verification_s11_and_no_activation()


if __name__ == "__main__":
    unittest.main()


SHIM_CS = r'''using System;
using System.Diagnostics;
using System.Text;

// Windows 上 CreateProcess 只解析 .exe；本 shim 把 curl 调用转发给 fake_curl.py。
class FakeCurlShim {
    static string Q(string s) {
        var sb = new StringBuilder();
        sb.Append((char)34);
        int bs = 0;
        foreach (char c in s) {
            if (c == (char)92) { sb.Append(c); bs++; }
            else if (c == (char)34) { sb.Append((char)92, bs + 1); sb.Append((char)34); bs = 0; }
            else { sb.Append(c); bs = 0; }
        }
        sb.Append((char)92, bs);
        sb.Append((char)34);
        return sb.ToString();
    }

    static int Main(string[] args) {
        string dir = AppDomain.CurrentDomain.BaseDirectory;
        string py = Environment.GetEnvironmentVariable("LFX_FAKE_PYTHON");
        if (String.IsNullOrEmpty(py)) py = "py";
        var sb = new StringBuilder();
        sb.Append(Q(System.IO.Path.Combine(dir, "fake_curl.py")));
        foreach (var a in args) { sb.Append(' '); sb.Append(Q(a)); }
        var psi = new ProcessStartInfo();
        psi.FileName = py;
        psi.Arguments = sb.ToString();
        psi.UseShellExecute = false;
        var p = Process.Start(psi);
        p.WaitForExit();
        return p.ExitCode;
    }
}
'''
