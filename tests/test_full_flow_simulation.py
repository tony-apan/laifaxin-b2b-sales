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
        fake = cls.fake_bin / "curl"
        fake.write_text(FAKE_CURL, encoding="utf-8")
        fake.chmod(fake.stat().st_mode | stat.S_IXUSR)
        cls.env = os.environ.copy()
        cls.env.update({
            "PATH": str(cls.fake_bin) + os.pathsep + cls.env.get("PATH", ""),
            "LFX_FAKE_CURL_LOG": str(cls.curl_log),
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
        )
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
        s5_binding = {
            "project": PROJECT, "org_sha256": org_sha, "profile": pmeta, "keyword": SEED,
            "n": 8, "company_tag": COMPANY_TAG, "contact_tag": CONTACT_TAG, "max": 3,
            "exclude": ["CN", "HK", "MO", "TW"], "verify_status": ["valid", "unkown"],
        }
        s5 = self.approval("S5_保存参数", s5_binding)
        self.run_tool(
            "save_first_n.py", "--token", TOKEN, "--org", ORG, "--keyword", SEED, "--n", 8,
            "--company-tag", COMPANY_TAG, "--contact-tag", CONTACT_TAG, "--max", 3,
            "--profile", self.profile, "--record", self.record, "--approval", s5, "--project", PROJECT,
        )
        self.run_tool(
            "wait_save_done.py", "--token", TOKEN, "--org", ORG, "--task", TASK,
            "--tag", CONTACT_TAG, "--record", self.record, "--timeout", 2,
        )

        directions = []
        for i, word in enumerate(("orbit", "harbor", "cedar", "quartz", "maple", "signal", "velvet", "anchor", "cobalt", "meadow", "summit", "willow"), 1):
            angle = " ".join(word + suffix for suffix in ("lane", "crest", "field", "point", "mark", "path", "view", "work", "craft", "scope"))
            # 轮次句含加粗产品词+实体优势（四要素：整封 2-4 处加粗、优势具体化；不用数字避免触发事实闸门）
            directions.append([f"R{i:02d}", f"方向{i}", f"{word} packaging discussion",
                               f"Are your <b>packaging</b> SKUs locked in? We build <b>seam</b> construction. {angle}"])
        variants = []
        claims = []
        for word in ("amber", "birch", "coral", "delta", "ember", "frost", "grove", "heath", "ivory", "juniper"):
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
        self.assertEqual(120, len(mapping))
        self.assertEqual(120, len(set(mapping.values())))
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
        s10_binding = {"project": PROJECT, "org_sha256": org_sha, "seq": SEQUENCE, "tags": [CONTACT_TAG], "task": TASK}
        s10 = self.approval("S10_加联系人", s10_binding)
        self.run_tool(
            "contact_add.py", "--token", TOKEN, "--org", ORG, "--seq", SEQUENCE,
            "--tags", CONTACT_TAG, "--task", TASK, "--record", self.record,
            "--approval", s10, "--project", PROJECT, "--timeout", 2,
        )
        self.assertIn("status: S10", self.record.read_text(encoding="utf-8"))

    def phase_verification_s11_and_no_activation(self):
        verify_seq = self.project_dir / "verify-seq.txt"
        verify_exclude = self.project_dir / "verify-exclude.txt"
        verify_diff = self.project_dir / "verify-diff.txt"
        panel = self.project_dir / "verification-panel.md"
        self.run_tool("verify_sequence.py", "--token", TOKEN, "--org", ORG, "--seq", SEQUENCE, output=verify_seq)
        self.run_tool("verify_exclude.py", "--token", TOKEN, "--org", ORG, "--keyword", SEED, output=verify_exclude)
        self.run_tool("check_template_diff.py", "--token", TOKEN, "--org", ORG, "--prefix", "英语-宠物食品包装-", "--limit", 120, output=verify_diff, timeout=180)
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
        save = [c["payload"] for c in calls if c["path"] == "/api/refine/company-save"]
        self.assertEqual(1, len(save))
        self.assertEqual("front", save[0]["selectOption"])
        self.assertEqual([], save[0]["selectKeys"])
        contact_add = [c["payload"] for c in calls if c["path"] == "/api/sequences/contact-add"]
        self.assertEqual([{"seqId": SEQUENCE, "tags": [CONTACT_TAG], "views": []}], contact_add)
        self.assertEqual(120, len([c for c in calls if c["path"] == "/api/mailbox/template-add"]))
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
