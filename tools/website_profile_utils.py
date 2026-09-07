#!/usr/bin/env python3
"""Validation and transactional helpers for the optional website-profile CLI."""
import hashlib
import json
import os
import re
import tempfile
from pathlib import Path
from urllib.parse import urlsplit

from profile_utils import find_emails, find_list_markers, find_phones


ROLES = (
    "OWN_COMPANY_SITE", "OWN_PRODUCT_PAGE", "OWN_CATALOG", "BUYER_SEED",
    "THIRD_PARTY_REFERENCE", "UNKNOWN",
)
OWN_ROLES = frozenset(("OWN_COMPANY_SITE", "OWN_PRODUCT_PAGE", "OWN_CATALOG"))
NON_IMPORTABLE_ROLES = frozenset(("BUYER_SEED", "THIRD_PARTY_REFERENCE", "UNKNOWN"))
SECTIONS = ("facts", "company_claims", "ai_analysis", "recommendations", "conflicts", "unverified")
CONFIDENCES = frozenset(("low", "medium", "high"))
OPERATOR_FIELDS = frozenset(("company_name", "website", "contact_email", "target_markets", "default_languages"))
PRODUCT_FIELDS = frozenset(str(i) for i in range(1, 9))
MARKETPLACE_SOCIAL_HOSTS = (
    "1688.com", "alibaba.com", "aliexpress.com", "amazon.ae", "amazon.ca",
    "amazon.co.jp", "amazon.co.uk", "amazon.com", "amazon.com.au", "amazon.com.br",
    "amazon.com.mx", "amazon.de", "amazon.es", "amazon.fr", "amazon.in", "amazon.it",
    "amazon.nl", "amazon.pl", "amazon.sa", "amazon.se", "amazon.sg", "facebook.com",
    "globalsources.com", "instagram.com", "linkedin.com", "made-in-china.com",
    "pinterest.com", "tiktok.com", "x.com", "youtube.com",
)
CANDIDATE_KEYS = frozenset((
    "schema_version", "kind", "candidate_id", "project", "status", "created_at",
    "confirmed_own_hosts", "source_documents", "sections",
))
SOURCE_KEYS = frozenset(("url", "sha256", "role", "role_confirmed"))
ITEM_KEYS = frozenset((
    "id", "text", "source_url", "evidence_text", "confidence", "confirmation_status",
    "target_profile", "target_field",
))
PATCH_KEYS = frozenset((
    "schema_version", "kind", "patch_id", "candidate_id", "project", "target_profile",
    "status", "created_at", "base_profile_sha256", "candidate_sha256", "selected_ids",
    "changes", "patch_sha256", "approval", "canonical_patch_sha256",
))
CHANGE_KEYS = frozenset((
    "id", "section", "text", "source_url", "evidence_text", "confidence", "target_field",
))
APPROVAL_KEYS = frozenset(("approved_by", "approved_quote", "approved_at"))
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
PROJECT_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*/[A-Za-z0-9][A-Za-z0-9._-]*$")
HARD_FACT_RE = re.compile(
    r"[0-9０-９%％]|\b(?:MOQ|ISO\s*\d*|CE|FDA|UL|SGS|RoHS|BPA|LFGB)\b|"
    r"认证|证书|产能|交期|最小起订|capacity|lead\s*time|certif",
    re.IGNORECASE,
)
CONTACT_MARKER_RE = re.compile(
    r"customer[_ ]?(?:list|email)|buyer[_ ]?(?:list|email)|contact[_ ]?list|"
    r"客户名单|买家名单|联系人清单|客户邮箱|买家邮箱|联系人邮箱", re.IGNORECASE,
)


class Invalid(ValueError):
    pass


def canonical_json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def object_sha256(value):
    return hashlib.sha256(canonical_json(value)).hexdigest()


def bytes_sha256(data):
    return hashlib.sha256(data).hexdigest()


def file_sha256(path):
    return bytes_sha256(Path(path).read_bytes())


def load_json(path):
    with Path(path).open("r", encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise Invalid("JSON root must be an object")
    return value


def https_url(value, label):
    if not isinstance(value, str):
        raise Invalid(f"{label} must be a string")
    parsed = urlsplit(value)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise Invalid(f"{label} must be an HTTPS URL without credentials")
    return parsed


def normalize_host(host):
    if not isinstance(host, str) or not host.strip():
        raise Invalid("confirmed own host must be a non-empty hostname")
    host = host.strip().lower().rstrip(".")
    if "://" in host or "/" in host or "@" in host or not re.match(r"^[a-z0-9.-]+$", host):
        raise Invalid(f"invalid confirmed own host: {host!r}")
    return host[4:] if host.startswith("www.") else host


def same_host(left, right):
    return normalize_host(left) == normalize_host(right)


def known_marketplace_social(host):
    host = normalize_host(host)
    return any(host == known or host.endswith("." + known) for known in MARKETPLACE_SOCIAL_HOSTS)


def classify_url(url, declared_role=""):
    parsed = https_url(url, "url")
    if declared_role and declared_role not in ROLES:
        raise Invalid(f"unknown declared role: {declared_role}")
    if declared_role in OWN_ROLES and known_marketplace_social(parsed.hostname):
        return {"url": url, "role": "UNKNOWN", "declared_role": declared_role,
                "conflict": True, "reason": "known marketplace/social host conflicts with own role"}
    return {"url": url, "role": declared_role or "UNKNOWN", "declared_role": declared_role or None,
            "conflict": False, "reason": "user declaration" if declared_role else "no role declared"}


def _exact_keys(obj, expected, label):
    if not isinstance(obj, dict):
        raise Invalid(f"{label} must be an object")
    actual = frozenset(obj)
    if actual != expected:
        extra = sorted(actual - expected)
        missing = sorted(expected - actual)
        raise Invalid(f"{label} keys invalid; missing={missing}, unknown={extra}")


def _nonempty_string(value, label):
    if not isinstance(value, str) or not value.strip():
        raise Invalid(f"{label} must be a non-empty string")


def _detect_contacts(text):
    text = text or ""
    return find_emails(text), find_phones(text), find_list_markers(text)


def validate_candidate(data):
    _exact_keys(data, CANDIDATE_KEYS, "candidate")
    if data["schema_version"] != 1 or data["kind"] != "website-profile-candidate" or data["status"] != "candidate":
        raise Invalid("candidate discriminator/status invalid")
    _nonempty_string(data["candidate_id"], "candidate_id")
    _nonempty_string(data["created_at"], "created_at")
    if not isinstance(data["project"], str) or not PROJECT_RE.match(data["project"]):
        raise Invalid("project must be <operator_key>/<product_key>")
    if not isinstance(data["confirmed_own_hosts"], list) or not data["confirmed_own_hosts"]:
        raise Invalid("confirmed_own_hosts must be a non-empty array")
    own_hosts = {normalize_host(host) for host in data["confirmed_own_hosts"]}
    if any(known_marketplace_social(host) for host in own_hosts):
        raise Invalid("known marketplace/social host cannot be a confirmed own host")
    if len(own_hosts) != len(data["confirmed_own_hosts"]):
        raise Invalid("confirmed_own_hosts contains duplicates")
    if not isinstance(data["source_documents"], list) or not data["source_documents"]:
        raise Invalid("source_documents must be a non-empty array")
    documents = {}
    for index, doc in enumerate(data["source_documents"]):
        label = f"source_documents[{index}]"
        _exact_keys(doc, SOURCE_KEYS, label)
        parsed = https_url(doc["url"], label + ".url")
        if not isinstance(doc["sha256"], str) or not SHA256_RE.match(doc["sha256"]):
            raise Invalid(label + ".sha256 must be 64 lowercase hex characters")
        if doc["role"] not in ROLES or type(doc["role_confirmed"]) is not bool:
            raise Invalid(label + " role/role_confirmed invalid")
        if doc["role"] in OWN_ROLES and (not doc["role_confirmed"] or normalize_host(parsed.hostname) not in own_hosts):
            raise Invalid(label + " own role is not confirmed against confirmed_own_hosts")
        if doc["role"] in OWN_ROLES and known_marketplace_social(parsed.hostname):
            raise Invalid(label + " marketplace/social conflict")
        if doc["url"] in documents:
            raise Invalid("duplicate source document URL")
        documents[doc["url"]] = doc
    _exact_keys(data["sections"], frozenset(SECTIONS), "sections")
    seen_ids = {}
    for section in SECTIONS:
        entries = data["sections"][section]
        if not isinstance(entries, list):
            raise Invalid(f"sections.{section} must be an array")
        for index, item in enumerate(entries):
            label = f"sections.{section}[{index}]"
            _exact_keys(item, ITEM_KEYS, label)
            for key in ("id", "text", "source_url", "evidence_text", "confidence", "confirmation_status",
                        "target_profile", "target_field"):
                if not isinstance(item[key], str):
                    raise Invalid(f"{label}.{key} must be a string")
            _nonempty_string(item["id"], label + ".id")
            _nonempty_string(item["text"], label + ".text")
            if item["id"] in seen_ids and section not in ("conflicts", "unverified"):
                raise Invalid(f"duplicate item id outside conflict markers: {item['id']}")
            seen_ids.setdefault(item["id"], []).append(section)
            https_url(item["source_url"], label + ".source_url")
            if item["confidence"] not in CONFIDENCES:
                raise Invalid(label + ".confidence invalid")
            expected_status = "conflict" if section == "conflicts" else ("unverified" if section == "unverified" else "pending")
            if item["confirmation_status"] != expected_status:
                raise Invalid(f"{label}.confirmation_status must be {expected_status}")
            if section in ("ai_analysis", "recommendations"):
                if item["target_profile"] or item["target_field"]:
                    raise Invalid(label + " cannot target a formal profile")
            else:
                if item["target_profile"] not in ("product", "operator"):
                    raise Invalid(label + ".target_profile invalid")
                allowed = PRODUCT_FIELDS if item["target_profile"] == "product" else OPERATOR_FIELDS
                if item["target_field"] not in allowed:
                    raise Invalid(label + ".target_field invalid")
            if section in ("facts", "company_claims"):
                doc = documents.get(item["source_url"])
                parsed = urlsplit(item["source_url"])
                if (not doc or doc["role"] not in OWN_ROLES or not doc["role_confirmed"]
                        or normalize_host(parsed.hostname) not in own_hosts):
                    raise Invalid(label + " source is not a confirmed own document/host")
                if HARD_FACT_RE.search(item["text"]) and not str(item["evidence_text"]).strip():
                    raise Invalid(label + " hard fact requires evidence_text")
            emails, phones, marker = _detect_contacts("\n".join((item["text"], str(item["evidence_text"]))))
            is_own_email = item["target_profile"] == "operator" and item["target_field"] == "contact_email"
            if is_own_email:
                if len(emails) != 1 or item["text"].strip() != emails[0]:
                    raise Invalid(label + " contact_email must be exactly one email")
                if normalize_host(emails[0].rsplit("@", 1)[1]) not in own_hosts:
                    raise Invalid(label + " contact_email domain must equal a confirmed own host")
                evidence_emails = find_emails(item["evidence_text"])
                if any(email != emails[0] for email in evidence_emails):
                    raise Invalid(label + " evidence contains another email")
            elif emails:
                raise Invalid(label + " contains an email outside operator contact_email")
            if phones or marker:
                raise Invalid(label + " contains third-party contact data/list markers")
    return data


def patch_payload(data):
    return {key: data[key] for key in PATCH_KEYS
            if key not in ("status", "approval", "canonical_patch_sha256", "patch_sha256")}


def approved_payload(data):
    return {key: data[key] for key in PATCH_KEYS if key != "canonical_patch_sha256"}


def validate_patch(data, require_approved=False):
    _exact_keys(data, PATCH_KEYS, "patch")
    if data["schema_version"] != 1 or data["kind"] != "website-profile-patch":
        raise Invalid("patch discriminator invalid")
    for key in ("patch_id", "candidate_id", "created_at"):
        _nonempty_string(data[key], key)
    if not isinstance(data["project"], str) or not PROJECT_RE.match(data["project"]):
        raise Invalid("patch project invalid")
    if data["target_profile"] not in ("product", "operator"):
        raise Invalid("patch target_profile invalid")
    for key in ("base_profile_sha256", "candidate_sha256", "patch_sha256"):
        if not isinstance(data[key], str) or not SHA256_RE.match(data[key]):
            raise Invalid(key + " invalid")
    if data["patch_sha256"] != object_sha256(patch_payload(data)):
        raise Invalid("patch_sha256 mismatch")
    if not isinstance(data["selected_ids"], list) or not data["selected_ids"] or len(set(data["selected_ids"])) != len(data["selected_ids"]):
        raise Invalid("selected_ids must be a non-empty unique array")
    if not isinstance(data["changes"], list) or len(data["changes"]) != len(data["selected_ids"]):
        raise Invalid("changes do not match selected_ids")
    ids, targets = [], set()
    for index, change in enumerate(data["changes"]):
        _exact_keys(change, CHANGE_KEYS, f"changes[{index}]")
        if change["section"] not in ("facts", "company_claims"):
            raise Invalid("patch can only contain facts/company_claims")
        for key in ("id", "text", "source_url", "evidence_text", "confidence", "target_field"):
            if not isinstance(change[key], str):
                raise Invalid(f"changes[{index}].{key} must be a string")
        https_url(change["source_url"], f"changes[{index}].source_url")
        if change["confidence"] not in CONFIDENCES:
            raise Invalid("change confidence invalid")
        allowed = PRODUCT_FIELDS if data["target_profile"] == "product" else OPERATOR_FIELDS
        if change["target_field"] not in allowed or change["target_field"] in targets:
            raise Invalid("change target field invalid or duplicated")
        ids.append(change["id"]); targets.add(change["target_field"])
    if ids != data["selected_ids"]:
        raise Invalid("changes order/ids do not match selected_ids")
    if data["status"] == "candidate":
        if data["approval"] is not None or data["canonical_patch_sha256"] != "":
            raise Invalid("candidate patch cannot contain approval")
    elif data["status"] == "approved":
        _exact_keys(data["approval"], APPROVAL_KEYS, "approval")
        for key in APPROVAL_KEYS:
            _nonempty_string(data["approval"][key], "approval." + key)
        if not isinstance(data["canonical_patch_sha256"], str) or not SHA256_RE.match(data["canonical_patch_sha256"]):
            raise Invalid("canonical_patch_sha256 invalid")
        if data["canonical_patch_sha256"] != object_sha256(approved_payload(data)):
            raise Invalid("canonical approved patch hash mismatch")
    else:
        raise Invalid("patch status invalid")
    if require_approved and data["status"] != "approved":
        raise Invalid("patch is not approved")
    return data


def atomic_write_bytes(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix="." + path.name + ".", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(name, path)
    except BaseException:
        try:
            os.unlink(name)
        except FileNotFoundError:
            pass
        raise


def atomic_write_json(path, value):
    atomic_write_bytes(path, json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8") + b"\n")
