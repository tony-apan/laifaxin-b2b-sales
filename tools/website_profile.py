#!/usr/bin/env python3
"""Optional stdlib-only import path from AI-generated website candidates to profiles."""
import argparse
import contextlib
import json
import os
import re
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import operator_profile
from approval import confirm_quote_ok
from profile_utils import detect_third_party_contact, find_list_markers, parse_frontmatter, profile_field_facts, split_markdown, validate_nickname, validate_product_profile
from website_profile_utils import (
    Invalid, OPERATOR_FIELDS, PRODUCT_FIELDS, SECTIONS, approved_payload, atomic_write_bytes,
    atomic_write_json, classify_url, file_sha256, load_json, object_sha256, patch_payload,
    validate_candidate, validate_patch,
)

KB = Path(__file__).resolve().parent.parent
EXIT_IO = 1
EXIT_INVALID = 2
EXIT_EXISTS = 3
EXIT_NOT_APPROVED = 4
EXIT_SKIPPED = 5
EXIT_CONFLICT = 6
EXIT_ROLE = 7
FIELD_STATES = {"1": "S2", "2": "S2", "3": "S4", "4": "S2", "5": "S7", "6": "S7", "7": "S4", "8": "S7"}
OPERATOR_STATES = {"company_name": "S7", "website": "S4", "contact_email": "S7",
                   "target_markets": "S2", "default_languages": "S9"}
STATE_ORDER = ("S2", "S4", "S7", "S9")


def now():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def fail(code, message):
    print(message, file=sys.stderr)
    raise SystemExit(code)


def safe_line(value, limit=1000):
    return " ".join(str(value).replace("\r", " ").replace("\n", " ").split())[:limit]


def load_or_fail(path, label):
    try:
        return load_json(path)
    except (OSError, json.JSONDecodeError, Invalid) as exc:
        fail(EXIT_IO if isinstance(exc, OSError) else EXIT_INVALID, f"{label}: {exc}")


def write_json_or_fail(path, value, exists_is_error=False):
    path = Path(path)
    if exists_is_error and path.exists():
        fail(EXIT_EXISTS, f"output already exists: {path}")
    try:
        atomic_write_json(path, value)
    except OSError as exc:
        fail(EXIT_IO, f"write failed: {exc}")


def cmd_classify(args):
    try:
        result = classify_url(args.url, args.declared_role)
    except Invalid as exc:
        fail(EXIT_INVALID, str(exc))
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return EXIT_ROLE if result["conflict"] else 0


def cmd_validate_candidate(args):
    data = load_or_fail(args.candidate, "candidate read failed")
    try:
        validate_candidate(data)
    except Invalid as exc:
        fail(EXIT_INVALID, str(exc))
    print(f"candidate valid: {data['candidate_id']}")
    return 0


def selected_ids(raw):
    values = [part.strip() for part in raw.split(",") if part.strip()]
    if not values or len(values) != len(set(values)):
        fail(EXIT_INVALID, "--select must contain unique comma-separated ids")
    return values


def cmd_prepare_patch(args):
    candidate = load_or_fail(args.candidate, "candidate read failed")
    try:
        validate_candidate(candidate)
    except Invalid as exc:
        fail(EXIT_INVALID, str(exc))
    base = Path(args.base_profile)
    try:
        base_hash = file_sha256(base)
    except OSError as exc:
        fail(EXIT_IO, f"base profile read failed: {exc}")
    wanted = selected_ids(args.select)
    blocked = [item for section in ("conflicts", "unverified") for item in candidate["sections"][section]]
    if blocked:
        fail(EXIT_CONFLICT, "candidate contains conflicts/unverified; whole patch rejected")
    available = {}
    for section in ("facts", "company_claims"):
        for item in candidate["sections"][section]:
            available[item["id"]] = (section, item)
    if any(item_id not in available for item_id in wanted):
        fail(EXIT_INVALID, "selected ids must all belong to facts/company_claims")
    changes = []
    for item_id in wanted:
        section, item = available[item_id]
        if item["confirmation_status"] != "pending":
            fail(EXIT_INVALID, "selected facts/company_claims item must have confirmation_status=pending")
        if item["target_profile"] != args.target:
            fail(EXIT_INVALID, "selected item target_profile differs from --target")
        if args.target == "operator" and item["target_field"] not in OPERATOR_FIELDS:
            fail(EXIT_INVALID, "operator field is forbidden")
        if args.target == "product" and item["target_field"] not in PRODUCT_FIELDS:
            fail(EXIT_INVALID, "product field must be 1..8")
        changes.append({"id": item_id, "section": section, "text": item["text"],
                        "source_url": item["source_url"], "evidence_text": item["evidence_text"],
                        "confidence": item["confidence"], "target_field": item["target_field"]})
    candidate_hash = object_sha256(candidate)
    core = {"schema_version": 1, "kind": "website-profile-patch",
            "patch_id": "wpp-" + object_sha256({"candidate_sha256": candidate_hash, "target": args.target,
                                                  "base": base_hash, "ids": wanted})[:16],
            "candidate_id": candidate["candidate_id"], "project": candidate["project"],
            "target_profile": args.target, "created_at": now(), "base_profile_sha256": base_hash,
            "candidate_sha256": candidate_hash, "selected_ids": wanted, "changes": changes}
    patch = dict(core, status="candidate", patch_sha256=object_sha256(core), approval=None,
                 canonical_patch_sha256="")
    try:
        validate_patch(patch)
    except Invalid as exc:
        fail(EXIT_INVALID, f"internal patch validation failed: {exc}")
    write_json_or_fail(args.out, patch, exists_is_error=True)
    print(f"patch prepared: {args.out}")
    return 0


def cmd_approve_patch(args):
    patch = load_or_fail(args.patch, "patch read failed")
    try:
        validate_patch(patch)
    except Invalid as exc:
        fail(EXIT_NOT_APPROVED, str(exc))
    if patch["status"] != "candidate" or args.ack_patch != patch["patch_id"] or not confirm_quote_ok(args.quote):
        fail(EXIT_NOT_APPROVED, "patch is not an unapproved candidate, --ack-patch mismatches patch_id, or quote is not affirmative")
    quote_contact_issues = detect_third_party_contact(args.quote, label="--quote")
    if quote_contact_issues or find_list_markers(args.quote):
        fail(EXIT_NOT_APPROVED, "--quote contains contact data/list markers")
    ok, reason = validate_nickname(args.by)
    if not ok:
        fail(EXIT_NOT_APPROVED, f"--by is not a personal nickname: {reason}")
    patch["status"] = "approved"
    patch["approval"] = {"approved_by": safe_line(args.by, 200),
                         "approved_quote": safe_line(args.quote), "approved_at": now()}
    patch["canonical_patch_sha256"] = object_sha256(approved_payload(patch))
    try:
        validate_patch(patch, require_approved=True)
        atomic_write_json(args.patch, patch)
    except Invalid as exc:
        fail(EXIT_NOT_APPROVED, str(exc))
    except OSError as exc:
        fail(EXIT_IO, f"approval write failed: {exc}")
    print(f"patch approved: {patch['patch_id']}")
    return 0


def pid_is_alive(pid):
    if not isinstance(pid, int) or pid <= 0:
        return True
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def unlink_if_unchanged(path, expected, expected_stat):
    try:
        current_stat = path.stat()
        if (path.read_bytes() != expected or current_stat.st_ino != expected_stat.st_ino
                or current_stat.st_mtime_ns != expected_stat.st_mtime_ns):
            return False
        path.unlink()
        return True
    except FileNotFoundError:
        return False


def lock_owner_state(path, stale_after=300):
    try:
        raw = path.read_bytes()
        stat = path.stat()
    except OSError as exc:
        fail(EXIT_CONFLICT, f"cannot inspect lock owner: {path}: {exc}")
    try:
        owner = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        if time.time() - stat.st_mtime <= stale_after:
            fail(EXIT_CONFLICT, f"fresh corrupt lock fails closed: {path}")
        return raw, stat, False
    if not isinstance(owner, dict) or set(owner) != {"pid", "project"} or not isinstance(owner.get("project"), str):
        if time.time() - stat.st_mtime <= stale_after:
            fail(EXIT_CONFLICT, f"fresh invalid lock owner fails closed: {path}")
        return raw, stat, False
    return raw, stat, pid_is_alive(owner.get("pid"))


@contextlib.contextmanager
def lock_cleanup_guard(lock, project):
    guard = lock.with_name(lock.name + ".cleanup")
    owner = json.dumps({"pid": os.getpid(), "project": project}, sort_keys=True).encode("utf-8") + b"\n"
    for attempt in range(2):
        try:
            fd = os.open(guard, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            with os.fdopen(fd, "wb") as handle:
                handle.write(owner)
                handle.flush()
                os.fsync(handle.fileno())
            break
        except FileExistsError:
            raw, stat, alive = lock_owner_state(guard)
            if alive:
                fail(EXIT_CONFLICT, f"project lock cleanup is already in progress: {guard}")
            if attempt or not unlink_if_unchanged(guard, raw, stat):
                fail(EXIT_CONFLICT, f"stale cleanup guard changed during recovery: {guard}")
        except OSError as exc:
            fail(EXIT_IO, f"cannot acquire project lock cleanup guard: {exc}")
    try:
        yield
    finally:
        try:
            if guard.read_bytes() == owner:
                guard.unlink()
        except FileNotFoundError:
            pass


@contextlib.contextmanager
def project_lock(profile, project):
    lock = Path(profile).parent / ".website-profile.lock"
    owner = json.dumps({"pid": os.getpid(), "project": project}, sort_keys=True).encode("utf-8") + b"\n"
    with lock_cleanup_guard(lock, project):
        if lock.exists():
            raw, stat, alive = lock_owner_state(lock)
            if alive:
                fail(EXIT_CONFLICT, f"project is locked: {lock}")
            if not unlink_if_unchanged(lock, raw, stat):
                fail(EXIT_CONFLICT, f"stale project lock changed during recovery: {lock}")
        try:
            fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            with os.fdopen(fd, "wb") as handle:
                handle.write(owner)
                handle.flush()
                os.fsync(handle.fileno())
        except FileExistsError:
            fail(EXIT_CONFLICT, f"project lock was concurrently acquired: {lock}")
        except OSError as exc:
            fail(EXIT_IO, f"cannot acquire project lock: {exc}")
    try:
        yield
    finally:
        try:
            if lock.read_bytes() == owner:
                lock.unlink()
        except FileNotFoundError:
            pass


def resolve_record(profile, target_profile, explicit_record):
    if target_profile == "product":
        automatic = Path(profile).resolve().parent / "operation-record.md"
        if explicit_record and Path(explicit_record).resolve() != automatic:
            fail(EXIT_CONFLICT, "explicit record differs from product profile operation-record.md")
        return automatic if automatic.is_file() else ""
    return explicit_record


def record_is_active(path):
    if not path:
        return False
    path = Path(path)
    if not path.is_file():
        fail(EXIT_INVALID, f"record does not exist: {path}")
    meta = parse_frontmatter(path)
    text = path.read_text(encoding="utf-8", errors="replace")
    return meta.get("status", "").upper().startswith("S12") or bool(re.search(r"(?im)^\s*(?:status\s*:\s*)?ACTIVE\s*$", text))


def import_text(change):
    text = safe_line(change["text"])
    return "企业官网自述：" + text if change["section"] == "company_claims" else text


def replace_product_fields(text, changes, patch_hash):
    meta_lines, body = split_markdown(text)
    if not meta_lines:
        raise Invalid("product profile lacks frontmatter")
    facts = {}
    for number, fact in profile_field_facts_from_text(text).items():
        facts[str(number)] = fact
    changed = []
    for change in changes:
        field = change["target_field"]
        current = facts.get(field)
        wanted = {"content": import_text(change), "source": "URL:" + change["source_url"],
                  "confidence": change["confidence"]}
        if current != wanted:
            changed.append(change)
    if not changed:
        return text, []
    for change in changed:
        circled = "①②③④⑤⑥⑦⑧"[int(change["target_field"]) - 1]
        pattern = re.compile(
            r"(?m)(^##\s*" + re.escape(circled) + r"[^\n]*\n)- 内容：[^\n]*\n- source:[^\n]*\n- confidence:[^\n]*")
        literal = ("- 内容：" + import_text(change) + "\n- source: URL:" + change["source_url"]
                   + "\n- confidence: " + change["confidence"])
        body, count = pattern.subn(lambda match, value=literal: match.group(1) + value, body, count=1)
        if count != 1:
            raise Invalid(f"cannot locate product field {change['target_field']}")
    meta = {}
    for line in meta_lines:
        if ":" in line:
            key, _, value = line.partition(":"); meta[key.strip()] = value.strip()
    try:
        version = int(meta.get("profile_version", "")) + 1
    except ValueError:
        raise Invalid("profile_version is not an integer")
    provided, inferred = set(), set()
    for number, fact in profile_field_facts_from_text("---\n" + "\n".join(meta_lines) + "\n---\n" + body).items():
        if fact["content"] in ("", "（待补）", "待补"):
            continue
        source = fact["source"].strip().lower()
        if source == "用户" or source.startswith("url:https://"):
            provided.add(number)
        elif source == "推断":
            inferred.add(number)
    sourced = provided | inferred
    updates = {"profile_version": str(version), "status": "draft", "updated_at": now(),
               "confirmed_at": "", "confirmed_by": "", "confirm_quote": "", "content_sha256": "",
               "sources_present": "yes" if len(provided) == 8 else ("partial" if sourced else "no"),
               "sources_status": "provided" if len(provided) == 8 else ("partial" if sourced else "requested")}
    new_meta = []
    for line in meta_lines:
        key = line.partition(":")[0].strip() if ":" in line else ""
        if key in updates:
            new_meta.append(f"{key}: {updates.pop(key)}")
        else:
            new_meta.append(line)
    new_meta.extend(f"{key}: {value}" for key, value in updates.items())
    if "## 变更记录" not in body:
        raise Invalid("product profile lacks append-only change record section")
    if not body.endswith("\n"):
        body += "\n"
    body += f"| {now()} | website-profile v{version} | patch sha256:{patch_hash} |\n"
    return "---\n" + "\n".join(new_meta) + "\n---\n" + body, changed


def profile_field_facts_from_text(text):
    _meta, body = {}, split_markdown(text)[1]
    facts, current = {}, None
    for raw in body.splitlines():
        line = raw.strip()
        match = re.match(r"^##\s*([①②③④⑤⑥⑦⑧])", line)
        if match:
            current = "①②③④⑤⑥⑦⑧".index(match.group(1)) + 1
            facts[current] = {"content": "", "source": "", "confidence": ""}
        elif current and line.startswith("- 内容："):
            facts[current]["content"] = line.split("：", 1)[1].strip()
        elif current and line.lower().startswith("- source:"):
            facts[current]["source"] = line.split(":", 1)[1].strip()
        elif current and line.lower().startswith("- confidence:"):
            facts[current]["confidence"] = line.split(":", 1)[1].strip()
    return facts


def parse_operator_allowed_fields(text):
    fields = {}
    for line in text.splitlines():
        if ":" in line and not line.lstrip().startswith(("#", ">")):
            key, _, value = line.partition(":")
            if key.strip() in operator_profile.ALLOWED_KEYS:
                fields[key.strip()] = value.strip()
    return fields


def replace_operator_fields(text, changes):
    fields = parse_operator_allowed_fields(text)
    if not fields:
        raise Invalid("operator profile is empty or invalid")
    replacements, changed = {}, []
    for change in changes:
        field, value = change["target_field"], operator_profile.safe(import_text(change), 500)
        if field not in OPERATOR_FIELDS:
            raise Invalid("forbidden operator field")
        if fields.get(field, "") != value:
            replacements[field] = value
            changed.append(change)
    if not changed:
        return text, []
    lines = text.splitlines(keepends=True)
    occurrences = {field: 0 for field in replacements}
    for line in lines:
        if ":" not in line or line.lstrip().startswith(("#", ">")):
            continue
        key = line.partition(":")[0].strip()
        if key in occurrences:
            occurrences[key] += 1
    invalid = {key: count for key, count in occurrences.items() if count != 1}
    if invalid:
        raise Invalid(f"selected operator keys must occur exactly once: {invalid}")
    updated_seen = 0
    new_lines = []
    timestamp = now()
    for line in lines:
        ending = "\n" if line.endswith("\n") else ""
        raw = line[:-1] if ending else line
        key = raw.partition(":")[0].strip() if ":" in raw and not raw.lstrip().startswith(("#", ">")) else ""
        if key in replacements:
            prefix = raw[:raw.index(key)]
            new_lines.append(f"{prefix}{key}: {replacements[key]}{ending}")
        elif key == "updated_at":
            updated_seen += 1
            new_lines.append(f"updated_at: {timestamp}{ending}")
        else:
            new_lines.append(line)
    if updated_seen > 1:
        raise Invalid("updated_at must occur at most once")
    if not updated_seen:
        if new_lines and not new_lines[-1].endswith("\n"):
            new_lines[-1] += "\n"
        new_lines.append(f"updated_at: {timestamp}\n")
    rendered = "".join(new_lines)
    validated_fields = parse_operator_allowed_fields(rendered)
    issues = operator_profile.validate(validated_fields)
    if issues:
        raise Invalid("; ".join(issues))
    return rendered, changed


def validate_product_candidate_bytes(profile, data):
    profile = Path(profile)
    fd, name = tempfile.mkstemp(prefix="." + profile.name + ".validate.", suffix=".tmp", dir=str(profile.parent))
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
        issues = validate_product_profile(name, require_confirmed=False)
    finally:
        try:
            os.unlink(name)
        except FileNotFoundError:
            pass
    if issues:
        raise Invalid("product candidate failed existing validator: " + "; ".join(issues))


def impact_for(patch, changes):
    mapping = FIELD_STATES if patch["target_profile"] == "product" else OPERATOR_STATES
    fields = [change["target_field"] for change in changes]
    states = sorted({mapping[field] for field in fields}, key=STATE_ORDER.index)
    return {"schema_version": 1, "kind": "website-profile-impact", "patch_id": patch["patch_id"],
            "project": patch["project"], "target_profile": patch["target_profile"],
            "patch_sha256": patch["canonical_patch_sha256"], "applied_at": now(),
            "changed_fields": fields, "affected_states": states, "earliest_affected_state": states[0]}


def validate_profile_path(profile, target_profile, project):
    operator_key, product_key = project.split("/", 1)
    expected = (KB / "runs" / operator_key / product_key / "product-profile.md"
                if target_profile == "product"
                else KB / ".local" / "operators" / (operator_key + ".md"))
    if Path(profile).resolve() != expected.resolve():
        raise Invalid(f"{target_profile} profile must use canonical path: {expected}")


def validate_profile_project(text, target_profile, project):
    operator_key, product_key = project.split("/", 1)
    if target_profile == "product":
        meta_lines, _body = split_markdown(text)
        meta = {}
        for line in meta_lines:
            if ":" in line:
                key, _, value = line.partition(":")
                meta[key.strip()] = value.strip()
        if meta.get("operator_key") != operator_key or meta.get("product_key") != product_key:
            raise Invalid("product profile project keys do not match --project")
    else:
        fields = {}
        for line in text.splitlines():
            if ":" in line and not line.lstrip().startswith(("#", ">")):
                key, _, value = line.partition(":")
                fields[key.strip()] = value.strip()
        if fields.get("operator_key") != operator_key:
            raise Invalid("operator profile operator_key does not match --project")


def operator_has_project_records(operator_key):
    operator_runs = KB / "runs" / operator_key
    if not operator_runs.is_dir():
        return False
    return any(path.is_file() for path in operator_runs.glob("**/operation-record.md"))


def recoverable_sidecar(path, kind, patch, patch_bytes):
    if not path.exists():
        return True
    try:
        raw = path.read_bytes()
        value = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return False
    if kind == "patch":
        return raw == patch_bytes and value == patch
    required = {"patch_id": patch["patch_id"], "patch_sha256": patch["canonical_patch_sha256"],
                "project": patch["project"], "target_profile": patch["target_profile"]}
    return isinstance(value, dict) and all(value.get(key) == expected for key, expected in required.items())


def cmd_apply_patch(args):
    patch = load_or_fail(args.patch, "patch read failed")
    try:
        validate_patch(patch, require_approved=True)
    except Invalid as exc:
        fail(EXIT_NOT_APPROVED, str(exc))
    if patch["project"] != args.project:
        fail(EXIT_NOT_APPROVED, "project binding mismatch")
    profile = Path(args.profile)
    try:
        before = profile.read_bytes()
    except OSError as exc:
        fail(EXIT_IO, f"profile read failed: {exc}")
    if file_sha256(profile) != patch["base_profile_sha256"]:
        fail(EXIT_NOT_APPROVED, "base profile hash mismatch")
    record = resolve_record(profile, patch["target_profile"], args.record)
    if record_is_active(record):
        fail(EXIT_CONFLICT, "S12/ACTIVE project cannot accept website profile changes")
    with project_lock(profile, args.project):
        try:
            current = profile.read_bytes()
            if current != before or file_sha256(profile) != patch["base_profile_sha256"]:
                fail(EXIT_NOT_APPROVED, "base profile changed while acquiring lock")
            text = current.decode("utf-8")
            try:
                validate_profile_path(profile, patch["target_profile"], args.project)
                validate_profile_project(text, patch["target_profile"], args.project)
            except Invalid as exc:
                fail(EXIT_CONFLICT, str(exc))
            operator_key, product_key = patch["project"].split("/", 1)
            if patch["target_profile"] == "operator" and operator_has_project_records(operator_key):
                fail(EXIT_CONFLICT, "operator already has project operation records; use operator_profile.py update and evaluate each project")
            approved_dir = KB / "runs" / operator_key / product_key / "website-profile" / "approved"
            archive_path = approved_dir / (patch["patch_id"] + "-patch.json")
            impact_path = approved_dir / (patch["patch_id"] + "-impact.json")
            try:
                patch_bytes = Path(args.patch).read_bytes()
                if json.loads(patch_bytes.decode("utf-8")) != patch:
                    fail(EXIT_NOT_APPROVED, "patch changed after validation")
            except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
                fail(EXIT_IO if isinstance(exc, OSError) else EXIT_NOT_APPROVED,
                     f"patch reread failed: {exc}")
            existing = [path for path in (archive_path, impact_path) if path.exists()]
            if existing:
                checks = ((archive_path, "patch"), (impact_path, "impact"))
                if not all(recoverable_sidecar(path, kind, patch, patch_bytes)
                           for path, kind in checks if path.exists()):
                    fail(EXIT_EXISTS, "approved artifact exists but does not match this patch; preserved")
                if not args.dry_run:
                    for derived in existing:
                        try:
                            derived.unlink()
                        except OSError as exc:
                            fail(EXIT_EXISTS, f"recoverable approved artifact cleanup failed: {exc}")
            if patch["target_profile"] == "product":
                rendered, changes = replace_product_fields(text, patch["changes"], patch["canonical_patch_sha256"])
            else:
                rendered, changes = replace_operator_fields(text, patch["changes"])
            if not changes:
                fail(EXIT_SKIPPED, "no semantic profile change")
            rendered_bytes = rendered.encode("utf-8")
            if patch["target_profile"] == "product":
                validate_product_candidate_bytes(profile, rendered_bytes)
            impact = impact_for(patch, changes)
            if args.dry_run:
                print(json.dumps(impact, ensure_ascii=False, sort_keys=True))
                return 0
            created = []
            try:
                atomic_write_bytes(archive_path, patch_bytes)
                created.append(archive_path)
                atomic_write_json(impact_path, impact)
                created.append(impact_path)
                atomic_write_bytes(profile, rendered_bytes)
            except BaseException:
                for derived in reversed(created):
                    try:
                        derived.unlink()
                    except FileNotFoundError:
                        pass
                raise
        except Invalid as exc:
            fail(EXIT_INVALID, str(exc))
        except OSError as exc:
            fail(EXIT_IO, f"atomic apply failed: {exc}")
    print(f"patch applied: {patch['patch_id']}")
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description="Optional website-profile candidate import (stdlib only, no network)")
    sub = parser.add_subparsers(dest="command", required=True)
    command = sub.add_parser("classify")
    command.add_argument("--url", required=True)
    command.add_argument("--declared-role", choices=("OWN_COMPANY_SITE", "OWN_PRODUCT_PAGE", "OWN_CATALOG", "BUYER_SEED", "THIRD_PARTY_REFERENCE", "UNKNOWN"), default="")
    command.set_defaults(function=cmd_classify)
    command = sub.add_parser("validate-candidate")
    command.add_argument("--candidate", required=True)
    command.set_defaults(function=cmd_validate_candidate)
    command = sub.add_parser("prepare-patch")
    command.add_argument("--candidate", required=True); command.add_argument("--target", choices=("product", "operator"), required=True)
    command.add_argument("--select", required=True); command.add_argument("--base-profile", required=True); command.add_argument("--out", required=True)
    command.set_defaults(function=cmd_prepare_patch)
    command = sub.add_parser("approve-patch")
    command.add_argument("--patch", required=True); command.add_argument("--ack-patch", required=True)
    command.add_argument("--by", required=True); command.add_argument("--quote", required=True)
    command.set_defaults(function=cmd_approve_patch)
    command = sub.add_parser("apply-patch")
    command.add_argument("--patch", required=True); command.add_argument("--profile", required=True); command.add_argument("--project", required=True)
    command.add_argument("--record", default=""); command.add_argument("--dry-run", action="store_true")
    command.set_defaults(function=cmd_apply_patch)
    args = parser.parse_args(argv)
    return args.function(args)


if __name__ == "__main__":
    try:
        raise SystemExit(main() or 0)
    except KeyboardInterrupt:
        raise SystemExit(EXIT_IO)
