import hashlib
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "tools" / "website_profile.py"
UTILS = ROOT / "tools" / "website_profile_utils.py"
PROTECTED = [ROOT / "tools" / name for name in (
    "operator_profile.py", "product_profile.py", "profile_utils.py")]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(ROOT / "tools"))
    try:
        spec.loader.exec_module(module)
    finally:
        sys.path.pop(0)
    return module


def load_utils():
    return load_module("website_profile_utils", UTILS)


def load_cli():
    return load_module("website_profile_cli", CLI)


class WebsiteProfileTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.protected_before = {p: sha(p) for p in PROTECTED}

    @classmethod
    def tearDownClass(cls):
        assert {p: sha(p) for p in PROTECTED} == cls.protected_before

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.project = "acme/widget"
        self.project_dir = self.root / "runs" / "acme" / "widget"
        self.project_dir.mkdir(parents=True)
        self.product = self.project_dir / "product-profile.md"
        template = (ROOT / "runs" / "_template" / "product-profile.md").read_text()
        for old, new in (("${OPERATOR_KEY}", "acme"), ("${PRODUCT_KEY}", "widget"),
                         ("${CREATED_AT}", "2026-09-07T00:00:00"),
                         ("${UPDATED_AT}", "2026-09-07T00:00:00"),
                         ("${STATUS}", "draft"), ("${SOURCES_STATUS}", "requested")):
            template = template.replace(old, new)
        self.product.write_text(template)
        self.operator = self.root / ".local" / "operators" / "acme.md"
        self.operator.parent.mkdir(parents=True)
        self.operator.write_text(
            "# operator\noperator_key: acme\nnickname: Tony\ncompany_name: Old Co\n"
            "website: https://acme.example\ncontact_email: hello@acme.example\n"
            "target_markets: EU\ndefault_languages: en\nupdated_at: old\n")
        self.candidate = self.root / "candidate.json"

    def tearDown(self):
        self.tmp.cleanup()

    def run_cli(self, *args):
        return subprocess.run([sys.executable, str(CLI), *map(str, args)], cwd=self.root,
                              text=True, capture_output=True)

    def item(self, item_id="f1", target_profile="product", target_field="1",
             text="Industrial widget", source_url="https://acme.example/about",
             evidence="Industrial widget", confidence="high"):
        return {"id": item_id, "text": text, "source_url": source_url,
                "evidence_text": evidence, "confidence": confidence,
                "confirmation_status": "pending", "target_profile": target_profile,
                "target_field": target_field}

    def candidate_data(self, item=None):
        sections = {k: [] for k in (
            "facts", "company_claims", "ai_analysis", "recommendations", "conflicts", "unverified")}
        if item:
            sections["facts"].append(item)
        return {"schema_version": 1, "kind": "website-profile-candidate",
                "candidate_id": "cand-001", "project": self.project, "status": "candidate",
                "created_at": "2026-09-07T00:00:00Z", "confirmed_own_hosts": ["acme.example"],
                "source_documents": [{"url": "https://acme.example/about", "sha256": "a" * 64,
                                      "role": "OWN_COMPANY_SITE", "role_confirmed": True}],
                "sections": sections}

    def write_candidate(self, data=None):
        self.candidate.write_text(json.dumps(data or self.candidate_data(self.item())))

    def make_patch(self, target="product", selected="f1", base=None, name="patch.json"):
        self.write_candidate()
        patch = self.root / name
        r = self.run_cli("prepare-patch", "--candidate", self.candidate, "--target", target,
                         "--select", selected, "--base-profile", base or self.product,
                         "--out", patch)
        self.assertEqual(r.returncode, 0, r.stderr + r.stdout)
        return patch

    def approve(self, patch, quote="确认应用", by="Tony", ack=None):
        patch_id = json.loads(Path(patch).read_text())["patch_id"]
        return self.run_cli("approve-patch", "--patch", patch, "--ack-patch",
                            patch_id if ack is None else ack, "--by", by, "--quote", quote)

    def apply_direct(self, patch, profile=None, project=None, record="", dry_run=False,
                     replace_side_effect=None):
        module = load_cli()
        args = SimpleNamespace(patch=str(patch), profile=str(profile or self.product),
                               project=project or self.project, record=str(record) if record else "",
                               dry_run=dry_run)
        patches = [mock.patch.object(module, "KB", self.root)]
        if replace_side_effect is not None:
            real_atomic = module.atomic_write_bytes

            def fail_profile(path, data):
                if Path(path) == Path(args.profile):
                    raise OSError(replace_side_effect)
                return real_atomic(path, data)

            patches.append(mock.patch.object(module, "atomic_write_bytes", side_effect=fail_profile))
        with patches[0]:
            context = patches[1] if len(patches) > 1 else mock.patch.object(module, "EXIT_IO", module.EXIT_IO)
            with context:
                try:
                    return module.cmd_apply_patch(args)
                except SystemExit as exc:
                    return exc.code

    def test_classify_default_own_and_marketplace_conflict(self):
        r = self.run_cli("classify", "--url", "https://acme.example/products/x")
        self.assertEqual(json.loads(r.stdout)["role"], "UNKNOWN")
        r = self.run_cli("classify", "--url", "https://acme.example", "--declared-role", "OWN_COMPANY_SITE")
        self.assertEqual(json.loads(r.stdout)["role"], "OWN_COMPANY_SITE")
        r = self.run_cli("classify", "--url", "https://www.alibaba.com/x", "--declared-role", "OWN_PRODUCT_PAGE")
        self.assertEqual(r.returncode, 7)
        self.assertTrue(json.loads(r.stdout)["conflict"])
        for host in ("aliexpress.com", "1688.com", "globalsources.com", "amazon.de", "amazon.co.uk", "amazon.co.jp"):
            r = self.run_cli("classify", "--url", f"https://shop.{host}/x",
                             "--declared-role", "OWN_COMPANY_SITE")
            self.assertEqual(r.returncode, 7, host)
            self.assertEqual(json.loads(r.stdout)["role"], "UNKNOWN")
        r = self.run_cli("classify", "--url", "https://amazon.evil.example/x",
                         "--declared-role", "OWN_COMPANY_SITE")
        self.assertEqual(r.returncode, 0)
        self.assertEqual(json.loads(r.stdout)["role"], "OWN_COMPANY_SITE")

    def test_candidate_six_sections_and_unknown_key_fail_closed(self):
        data = self.candidate_data()
        del data["sections"]["unverified"]
        self.write_candidate(data)
        self.assertEqual(self.run_cli("validate-candidate", "--candidate", self.candidate).returncode, 2)
        data = self.candidate_data(); data["surprise"] = 1
        self.write_candidate(data)
        self.assertEqual(self.run_cli("validate-candidate", "--candidate", self.candidate).returncode, 2)
        data = self.candidate_data(); data["project"] = "../widget"
        self.write_candidate(data)
        self.assertEqual(self.run_cli("validate-candidate", "--candidate", self.candidate).returncode, 2)

    def test_candidate_section_statuses_and_safe_project_slugs(self):
        cases = []
        for section, wrong in (("facts", "conflict"), ("company_claims", "unverified"),
                               ("ai_analysis", "conflict"), ("recommendations", "unverified"),
                               ("conflicts", "pending"), ("unverified", "pending")):
            data = self.candidate_data()
            item = self.item()
            if section in ("ai_analysis", "recommendations"):
                item["target_profile"] = ""; item["target_field"] = ""
            item["confirmation_status"] = wrong
            data["sections"][section].append(item)
            cases.append(data)
        for data in cases:
            self.write_candidate(data)
            self.assertEqual(self.run_cli("validate-candidate", "--candidate", self.candidate).returncode, 2)
        for project in ("acme\\evil/widget", "acme:evil/widget", "acme/..", "acme/evil\nkey"):
            data = self.candidate_data(); data["project"] = project
            self.write_candidate(data)
            self.assertEqual(self.run_cli("validate-candidate", "--candidate", self.candidate).returncode, 2)

    def test_prepare_defensively_rechecks_selected_pending_status(self):
        module = load_cli()
        data = self.candidate_data(self.item()); data["sections"]["facts"][0]["confirmation_status"] = "conflict"
        self.write_candidate(data)
        args = SimpleNamespace(candidate=str(self.candidate), target="product", select="f1",
                               base_profile=str(self.product), out=str(self.root / "defense.json"))
        with mock.patch.object(module, "validate_candidate", return_value=data):
            with self.assertRaises(SystemExit) as raised:
                module.cmd_prepare_patch(args)
        self.assertEqual(raised.exception.code, 2)
        self.assertFalse(Path(args.out).exists())

    def test_candidate_rejects_third_party_role_and_source_host(self):
        data = self.candidate_data(self.item())
        data["source_documents"][0]["role"] = "THIRD_PARTY_REFERENCE"
        self.write_candidate(data)
        self.assertEqual(self.run_cli("validate-candidate", "--candidate", self.candidate).returncode, 2)
        data = self.candidate_data(self.item(source_url="https://other.example/a"))
        self.write_candidate(data)
        self.assertEqual(self.run_cli("validate-candidate", "--candidate", self.candidate).returncode, 2)

    def test_candidate_rejects_hard_fact_without_evidence_and_ai_target(self):
        data = self.candidate_data(self.item(text="MOQ 500 units", evidence=""))
        self.write_candidate(data)
        self.assertEqual(self.run_cli("validate-candidate", "--candidate", self.candidate).returncode, 2)
        data = self.candidate_data(); data["sections"]["recommendations"].append(self.item(target_field="2"))
        self.write_candidate(data)
        self.assertEqual(self.run_cli("validate-candidate", "--candidate", self.candidate).returncode, 2)

    def test_candidate_contact_email_rules(self):
        data = self.candidate_data(self.item(target_profile="operator", target_field="contact_email",
                                             text="sales@other.example", evidence="sales@other.example"))
        self.write_candidate(data)
        self.assertEqual(self.run_cli("validate-candidate", "--candidate", self.candidate).returncode, 2)
        data = self.candidate_data(self.item(target_profile="operator", target_field="contact_email",
                                             text="sales@acme.example and ceo@acme.example",
                                             evidence="sales@acme.example and ceo@acme.example"))
        self.write_candidate(data)
        self.assertEqual(self.run_cli("validate-candidate", "--candidate", self.candidate).returncode, 2)

    def test_hardened_contact_detection_allows_capacity_and_rejects_phone(self):
        data = self.candidate_data(self.item(text="capacity 1000000 pcs/year",
                                             evidence="capacity 1000000 pcs/year"))
        self.write_candidate(data)
        self.assertEqual(self.run_cli("validate-candidate", "--candidate", self.candidate).returncode, 0)
        data = self.candidate_data(self.item(text="Call +1 212 555 0199",
                                             evidence="Call +1 212 555 0199"))
        self.write_candidate(data)
        self.assertEqual(self.run_cli("validate-candidate", "--candidate", self.candidate).returncode, 2)
        data = self.candidate_data(); data["sections"]["facts"].append(self.item(evidence=123))
        self.write_candidate(data)
        self.assertEqual(self.run_cli("validate-candidate", "--candidate", self.candidate).returncode, 2)

    def test_patch_id_binds_candidate_content_and_is_stable(self):
        def prepare(data, name):
            self.write_candidate(data)
            path = self.root / name
            result = self.run_cli("prepare-patch", "--candidate", self.candidate, "--target", "product",
                                  "--select", "f1", "--base-profile", self.product, "--out", path)
            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            return json.loads(path.read_text())["patch_id"]

        original = self.candidate_data(self.item())
        first = prepare(original, "stable-1.json")
        second = prepare(original, "stable-2.json")
        self.assertEqual(first, second)

        changed_text = self.candidate_data(self.item(text="Different widget"))
        changed_evidence = self.candidate_data(self.item(evidence="Different evidence"))
        changed_source = self.candidate_data(self.item(source_url="https://acme.example/other"))
        changed_source["source_documents"][0]["url"] = "https://acme.example/other"
        ids = {first, prepare(changed_text, "changed-text.json"),
               prepare(changed_evidence, "changed-evidence.json"),
               prepare(changed_source, "changed-source.json")}
        self.assertEqual(len(ids), 4)

    def test_prepare_does_not_change_base_and_conflict_rejects_whole_patch(self):
        before = self.product.read_bytes()
        self.make_patch()
        self.assertEqual(self.product.read_bytes(), before)
        data = self.candidate_data(self.item())
        conflict = self.item("f1"); conflict["confirmation_status"] = "conflict"
        data["sections"]["conflicts"].append(conflict)
        self.write_candidate(data)
        r = self.run_cli("prepare-patch", "--candidate", self.candidate, "--target", "product",
                         "--select", "f1", "--base-profile", self.product, "--out", self.root / "bad.json")
        self.assertEqual(r.returncode, 6)

    def test_negative_approval_bad_nickname_and_ack_leave_patch_unchanged(self):
        patch = self.make_patch()
        before = patch.read_bytes(); mtime = patch.stat().st_mtime_ns
        self.assertEqual(self.approve(patch, "先不要确认").returncode, 4)
        self.assertEqual((patch.read_bytes(), patch.stat().st_mtime_ns), (before, mtime))
        self.assertEqual(self.approve(patch, by="Sales Team").returncode, 4)
        self.assertEqual((patch.read_bytes(), patch.stat().st_mtime_ns), (before, mtime))
        self.assertEqual(self.approve(patch, ack="wpp-wrong").returncode, 4)
        self.assertEqual((patch.read_bytes(), patch.stat().st_mtime_ns), (before, mtime))
        for quote in ("确认，联系 sales@acme.example", "确认，电话 +1 212 555 0199", "确认，客户名单如下"):
            self.assertEqual(self.approve(patch, quote).returncode, 4)
            self.assertEqual((patch.read_bytes(), patch.stat().st_mtime_ns), (before, mtime))
        before_profile = self.product.read_bytes()
        self.assertEqual(self.apply_direct(patch), 4)
        self.assertEqual(self.product.read_bytes(), before_profile)

    def test_base_hash_drift(self):
        patch = self.make_patch(); self.assertEqual(self.approve(patch).returncode, 0)
        self.product.write_text(self.product.read_text() + "\nexternal change\n")
        before = self.product.read_bytes()
        self.assertEqual(self.apply_direct(patch), 4)
        self.assertEqual(self.product.read_bytes(), before)

    def test_product_precise_change_draft_version_and_impact(self):
        patch = self.make_patch(); self.assertEqual(self.approve(patch).returncode, 0)
        self.assertEqual(self.apply_direct(patch), 0)
        text = self.product.read_text()
        self.assertIn("- 内容：Industrial widget", text)
        self.assertIn("- source: URL:https://acme.example/about", text)
        self.assertIn("status: draft", text); self.assertIn("profile_version: 2", text)
        self.assertIn("## ②", text); self.assertIn("- 内容：（待补）", text)
        approved_hash = json.loads(patch.read_text())["canonical_patch_sha256"]
        self.assertRegex(text, rf"(?m)^\| .+ \| website-profile v2 \| patch sha256:{approved_hash} \|$")
        approved_dir = self.project_dir / "website-profile" / "approved"
        impacts = list(approved_dir.glob("*-impact.json"))
        archives = list(approved_dir.glob("*-patch.json"))
        self.assertEqual(len(impacts), 1)
        self.assertEqual(len(archives), 1)
        self.assertEqual(archives[0].read_bytes(), patch.read_bytes())
        self.assertEqual(json.loads(archives[0].read_text()), json.loads(patch.read_text()))
        load_utils().validate_patch(json.loads(archives[0].read_text()), require_approved=True)
        self.assertEqual(json.loads(impacts[0].read_text())["earliest_affected_state"], "S2")

    def write_matching_sidecars(self, patch, include=("patch", "impact")):
        value = json.loads(Path(patch).read_text())
        approved = self.project_dir / "website-profile" / "approved"
        approved.mkdir(parents=True, exist_ok=True)
        paths = {}
        if "patch" in include:
            paths["patch"] = approved / f"{value['patch_id']}-patch.json"
            paths["patch"].write_bytes(Path(patch).read_bytes())
        if "impact" in include:
            paths["impact"] = approved / f"{value['patch_id']}-impact.json"
            paths["impact"].write_text(json.dumps({
                "patch_id": value["patch_id"], "patch_sha256": value["canonical_patch_sha256"],
                "project": value["project"], "target_profile": value["target_profile"]}))
        return paths

    def test_matching_sidecars_recover_after_interrupted_apply(self):
        original = self.product.read_bytes()
        for index, include in enumerate((("patch", "impact"), ("patch",), ("impact",))):
            with self.subTest(include=include):
                self.product.write_bytes(original)
                approved = self.project_dir / "website-profile" / "approved"
                if approved.is_dir():
                    for old in approved.iterdir():
                        old.unlink()
                patch = self.make_patch(name=f"recover-{index}.json")
                self.assertEqual(self.approve(patch).returncode, 0)
                self.write_matching_sidecars(patch, include)
                self.assertEqual(self.apply_direct(patch), 0)
                self.assertEqual(len(list(approved.glob("*-patch.json"))), 1)
                self.assertEqual(len(list(approved.glob("*-impact.json"))), 1)

    def test_foreign_sidecar_is_preserved_and_rejected(self):
        patch = self.make_patch(name="foreign-sidecar.json")
        self.assertEqual(self.approve(patch).returncode, 0)
        patch_id = json.loads(patch.read_text())["patch_id"]
        approved = self.project_dir / "website-profile" / "approved"
        approved.mkdir(parents=True, exist_ok=True)
        artifact = approved / f"{patch_id}-impact.json"
        artifact.write_text('{"patch_id":"foreign"}\n')
        before = self.product.read_bytes(); mtime = self.product.stat().st_mtime_ns
        self.assertEqual(self.apply_direct(patch), 3)
        self.assertEqual((self.product.read_bytes(), self.product.stat().st_mtime_ns), (before, mtime))
        self.assertEqual(artifact.read_text(), '{"patch_id":"foreign"}\n')

    def test_product_replacement_preserves_literal_backslashes(self):
        source_url = "https://acme.example/docs/%5Cspec"
        item = self.item(text=r"Size chart C:\docs\spec", source_url=source_url,
                         evidence=r"Size chart C:\docs\spec")
        data = self.candidate_data(item)
        data["source_documents"][0]["url"] = source_url
        self.write_candidate(data)
        patch = self.root / "backslash-patch.json"
        r = self.run_cli("prepare-patch", "--candidate", self.candidate, "--target", "product",
                         "--select", "f1", "--base-profile", self.product, "--out", patch)
        self.assertEqual(r.returncode, 0, r.stderr + r.stdout)
        self.assertEqual(self.approve(patch).returncode, 0)
        self.assertEqual(self.apply_direct(patch), 0)
        rendered = self.product.read_text()
        self.assertIn(r"- 内容：Size chart C:\docs\spec", rendered)
        self.assertIn("- source: URL:https://acme.example/docs/%5Cspec", rendered)

    def test_company_claim_remains_attributed(self):
        data = self.candidate_data(self.item()); data["sections"]["facts"].clear()
        data["sections"]["company_claims"].append(self.item())
        self.write_candidate(data)
        patch = self.root / "claim.json"
        r = self.run_cli("prepare-patch", "--candidate", self.candidate, "--target", "product",
                         "--select", "f1", "--base-profile", self.product, "--out", patch)
        self.assertEqual(r.returncode, 0, r.stderr + r.stdout)
        self.assertEqual(self.approve(patch).returncode, 0)
        self.assertEqual(self.apply_direct(patch), 0)
        self.assertIn("- 内容：企业官网自述：Industrial widget", self.product.read_text())

    def test_operator_nickname_forbidden(self):
        data = self.candidate_data(self.item(target_profile="operator", target_field="nickname"))
        self.write_candidate(data)
        r = self.run_cli("prepare-patch", "--candidate", self.candidate, "--target", "operator",
                         "--select", "f1", "--base-profile", self.operator, "--out", self.root / "p.json")
        self.assertEqual(r.returncode, 2)

    def test_s12_rejects_without_changes_or_record_argument(self):
        patch = self.make_patch(); self.assertEqual(self.approve(patch).returncode, 0)
        record = self.project_dir / "operation-record.md"
        record.write_text("---\nstatus: S12\n---\nACTIVE\n")
        before = self.product.read_bytes(); mtime = self.product.stat().st_mtime_ns
        self.assertEqual(self.apply_direct(patch), 6)
        self.assertEqual((self.product.read_bytes(), self.product.stat().st_mtime_ns), (before, mtime))

    def test_dry_run_and_metadata_noop(self):
        patch = self.make_patch(); self.assertEqual(self.approve(patch).returncode, 0)
        before = self.product.read_bytes()
        self.assertEqual(self.apply_direct(patch, dry_run=True), 0)
        self.assertEqual(self.product.read_bytes(), before)
        self.assertEqual(self.apply_direct(patch), 0)
        patch2 = self.make_patch(name="patch-2.json"); self.assertEqual(self.approve(patch2).returncode, 0)
        before = self.product.read_bytes(); mtime = self.product.stat().st_mtime_ns
        self.assertEqual(self.apply_direct(patch2), 5)
        self.assertEqual((self.product.read_bytes(), self.product.stat().st_mtime_ns), (before, mtime))

    def test_live_and_stale_project_locks(self):
        patch = self.make_patch(); self.assertEqual(self.approve(patch).returncode, 0)
        lock = self.product.parent / ".website-profile.lock"
        lock.write_text(json.dumps({"pid": __import__("os").getpid(), "project": self.project}) + "\n")
        before = self.product.read_bytes(); mtime = self.product.stat().st_mtime_ns
        self.assertEqual(self.apply_direct(patch), 6)
        self.assertEqual((self.product.read_bytes(), self.product.stat().st_mtime_ns), (before, mtime))
        self.assertTrue(lock.exists())
        lock.write_text(json.dumps({"pid": 99999999, "project": self.project}) + "\n")
        self.assertEqual(self.apply_direct(patch), 0)
        self.assertFalse(lock.exists())

    def test_main_lock_fresh_corrupt_rejects_and_old_corrupt_recovers(self):
        import os
        import time
        patch = self.make_patch(); self.assertEqual(self.approve(patch).returncode, 0)
        lock = self.product.parent / ".website-profile.lock"
        lock.write_bytes(b"")
        before = self.product.read_bytes(); mtime = self.product.stat().st_mtime_ns
        self.assertEqual(self.apply_direct(patch), 6)
        self.assertEqual((self.product.read_bytes(), self.product.stat().st_mtime_ns), (before, mtime))
        self.assertTrue(lock.exists()); self.assertEqual(lock.read_bytes(), b"")
        old = time.time() - 301
        os.utime(lock, (old, old))
        self.assertEqual(self.apply_direct(patch), 0)
        self.assertFalse(lock.exists())
        self.assertNotEqual(self.product.read_bytes(), before)

    def test_cleanup_guard_live_stale_and_corrupt_recovery(self):
        import os
        import time
        module = load_cli()
        lock = self.product.parent / ".website-profile.lock"
        guard = lock.with_name(lock.name + ".cleanup")

        guard.write_text(json.dumps({"pid": os.getpid(), "project": self.project}) + "\n")
        with self.assertRaises(SystemExit) as raised:
            with module.lock_cleanup_guard(lock, self.project):
                pass
        self.assertEqual(raised.exception.code, 6); self.assertTrue(guard.exists())

        guard.write_text(json.dumps({"pid": 99999999, "project": self.project}) + "\n")
        with module.lock_cleanup_guard(lock, self.project):
            owner = json.loads(guard.read_text())
            self.assertEqual((owner["pid"], owner["project"]), (os.getpid(), self.project))
        self.assertFalse(guard.exists())

        guard.write_bytes(b"")
        with self.assertRaises(SystemExit) as raised:
            with module.lock_cleanup_guard(lock, self.project):
                pass
        self.assertEqual(raised.exception.code, 6); self.assertTrue(guard.exists())

        old = time.time() - 301
        os.utime(guard, (old, old))
        with module.lock_cleanup_guard(lock, self.project):
            self.assertEqual(json.loads(guard.read_text())["project"], self.project)
        self.assertFalse(guard.exists())

    def test_operator_rejects_when_any_product_record_exists(self):
        data = self.candidate_data(self.item(target_profile="operator", target_field="company_name",
                                             text="New Co"))
        self.write_candidate(data)
        patch = self.root / "operator-blocked-patch.json"
        r = self.run_cli("prepare-patch", "--candidate", self.candidate, "--target", "operator",
                         "--select", "f1", "--base-profile", self.operator, "--out", patch)
        self.assertEqual(r.returncode, 0, r.stderr + r.stdout)
        self.assertEqual(self.approve(patch).returncode, 0)
        other_project = self.root / "runs" / "acme" / "other-product"
        other_project.mkdir(parents=True)
        (other_project / "operation-record.md").write_text("---\nstatus: S1\n---\n")
        before = self.operator.read_bytes(); mtime = self.operator.stat().st_mtime_ns
        self.assertEqual(self.apply_direct(patch, profile=self.operator), 6)
        self.assertEqual((self.operator.read_bytes(), self.operator.stat().st_mtime_ns), (before, mtime))
        self.assertFalse((self.project_dir / "website-profile").exists())
        self.assertFalse((other_project / "website-profile").exists())

    def test_canonical_profile_paths_reject_copies_with_matching_meta(self):
        patch = self.make_patch(); self.assertEqual(self.approve(patch).returncode, 0)
        product_copy = self.root / "copied-product-profile.md"
        product_copy.write_bytes(self.product.read_bytes())
        copy_patch = self.make_patch(base=product_copy, name="copy-patch.json")
        self.assertEqual(self.approve(copy_patch).returncode, 0)
        before = product_copy.read_bytes(); mtime = product_copy.stat().st_mtime_ns
        self.assertEqual(self.apply_direct(copy_patch, profile=product_copy), 6)
        self.assertEqual((product_copy.read_bytes(), product_copy.stat().st_mtime_ns), (before, mtime))

        data = self.candidate_data(self.item(target_profile="operator", target_field="company_name", text="New Co"))
        self.write_candidate(data)
        operator_copy = self.root / "copied-operator.md"
        operator_copy.write_bytes(self.operator.read_bytes())
        operator_patch = self.root / "copied-operator-patch.json"
        r = self.run_cli("prepare-patch", "--candidate", self.candidate, "--target", "operator",
                         "--select", "f1", "--base-profile", operator_copy, "--out", operator_patch)
        self.assertEqual(r.returncode, 0, r.stderr + r.stdout)
        self.assertEqual(self.approve(operator_patch).returncode, 0)
        before = operator_copy.read_bytes(); mtime = operator_copy.stat().st_mtime_ns
        self.assertEqual(self.apply_direct(operator_patch, profile=operator_copy), 6)
        self.assertEqual((operator_copy.read_bytes(), operator_copy.stat().st_mtime_ns), (before, mtime))

    def test_project_binding_and_profile_failure_are_transactional(self):
        patch = self.make_patch(); self.assertEqual(self.approve(patch).returncode, 0)
        before = self.product.read_bytes(); mtime = self.product.stat().st_mtime_ns
        self.assertEqual(self.apply_direct(patch, project="other/widget"), 4)
        self.assertEqual((self.product.read_bytes(), self.product.stat().st_mtime_ns), (before, mtime))
        text = self.product.read_text().replace("operator_key: acme", "operator_key: other", 1)
        other = self.root / "other-product.md"; other.write_text(text)
        other_patch = self.make_patch(base=other, name="other-patch.json")
        self.assertEqual(self.approve(other_patch).returncode, 0)
        before_other = other.read_bytes(); other_mtime = other.stat().st_mtime_ns
        self.assertEqual(self.apply_direct(other_patch, profile=other), 6)
        self.assertEqual((other.read_bytes(), other.stat().st_mtime_ns), (before_other, other_mtime))
        self.assertEqual(self.apply_direct(patch, replace_side_effect="injected profile failure"), 1)
        self.assertEqual((self.product.read_bytes(), self.product.stat().st_mtime_ns), (before, mtime))
        self.assertEqual(list((self.project_dir / "website-profile" / "approved").glob("*.json")), [])

    def make_operator_patch(self, name="operator-patch.json", text="New Co"):
        data = self.candidate_data(self.item(target_profile="operator", target_field="company_name",
                                             text=text))
        self.write_candidate(data)
        patch = self.root / name
        r = self.run_cli("prepare-patch", "--candidate", self.candidate, "--target", "operator",
                         "--select", "f1", "--base-profile", self.operator, "--out", patch)
        self.assertEqual(r.returncode, 0, r.stderr + r.stdout)
        self.assertEqual(self.approve(patch).returncode, 0)
        return patch

    def test_operator_preserves_extensions_and_rejects_missing_or_duplicate_target(self):
        base = self.operator.read_text()
        self.operator.write_text("# custom comment\nunknown_future_key: preserve: exactly\n" + base)
        patch = self.make_operator_patch(name="operator-preserve.json")
        self.assertEqual(self.apply_direct(patch, profile=self.operator), 0)
        rendered = self.operator.read_text()
        self.assertIn("# custom comment\n", rendered)
        self.assertIn("unknown_future_key: preserve: exactly\n", rendered)
        self.assertIn("company_name: New Co\n", rendered)

        for mode in ("duplicate", "missing"):
            with self.subTest(mode=mode):
                original = base
                if mode == "duplicate":
                    original += "company_name: Duplicate Co\n"
                else:
                    original = original.replace("company_name: Old Co\n", "")
                self.operator.write_text(original)
                approved = self.project_dir / "website-profile" / "approved"
                if approved.is_dir():
                    for old in approved.iterdir():
                        old.unlink()
                patch = self.make_operator_patch(name=f"operator-{mode}.json")
                before = self.operator.read_bytes(); mtime = self.operator.stat().st_mtime_ns
                self.assertEqual(self.apply_direct(patch, profile=self.operator), 2)
                self.assertEqual((self.operator.read_bytes(), self.operator.stat().st_mtime_ns),
                                 (before, mtime))

    def test_operator_impact_uses_project_run_directory(self):
        data = self.candidate_data(self.item(target_profile="operator", target_field="company_name",
                                             text="New Co"))
        self.write_candidate(data)
        patch = self.root / "operator-patch.json"
        r = self.run_cli("prepare-patch", "--candidate", self.candidate, "--target", "operator",
                         "--select", "f1", "--base-profile", self.operator, "--out", patch)
        self.assertEqual(r.returncode, 0, r.stderr + r.stdout)
        self.assertEqual(self.approve(patch).returncode, 0)
        self.assertEqual(self.apply_direct(patch, profile=self.operator), 0)
        impacts = list((self.project_dir / "website-profile" / "approved").glob("*-impact.json"))
        self.assertEqual(len(impacts), 1)
        self.assertFalse((self.operator.parent / "website-profile").exists())

    def test_user_source_count_and_product_impact_mapping(self):
        text = self.product.read_text()
        text = text.replace("## ② 产品线（品类/子品类/SKU/成分配比）\n- 内容：（待补）\n- source: none",
                            "## ② 产品线（品类/子品类/SKU/成分配比）\n- 内容：User supplied line\n- source: 用户")
        self.product.write_text(text)
        patch = self.make_patch(base=self.product); self.assertEqual(self.approve(patch).returncode, 0)
        self.assertEqual(self.apply_direct(patch), 0)
        rendered = self.product.read_text()
        self.assertIn("- 内容：User supplied line\n- source: 用户", rendered)
        self.assertIn("sources_present: partial", rendered)
        self.assertIn("sources_status: partial", rendered)
        module = load_cli()
        expected = {"1": "S2", "2": "S2", "3": "S4", "4": "S2",
                    "5": "S7", "6": "S7", "7": "S4", "8": "S7"}
        self.assertEqual(module.FIELD_STATES, expected)

    def test_schema_and_templates_parse_and_required_keys_match_runtime(self):
        utils = load_utils()
        candidate_schema = json.loads((ROOT / "website-profile" / "schema-candidate.json").read_text())
        patch_schema = json.loads((ROOT / "website-profile" / "schema-patch.json").read_text())
        self.assertEqual(set(candidate_schema["required"]), set(utils.CANDIDATE_KEYS))
        self.assertEqual(set(patch_schema["required"]), set(utils.PATCH_KEYS))
        for name in ("website-profile-candidate.json", "website-profile-patch.json"):
            self.assertIsInstance(json.loads((ROOT / "runs" / "_template" / name).read_text()), dict)

    def test_atomic_replace_failure_preserves_bytes_and_mtime(self):
        utils = load_utils()
        before = self.product.read_bytes(); mtime = self.product.stat().st_mtime_ns
        with mock.patch.object(utils.os, "replace", side_effect=OSError("injected replace failure")):
            with self.assertRaises(OSError):
                utils.atomic_write_bytes(self.product, b"changed")
        self.assertEqual((self.product.read_bytes(), self.product.stat().st_mtime_ns), (before, mtime))


if __name__ == "__main__":
    unittest.main()
