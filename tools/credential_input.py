#!/usr/bin/env python3
"""Strict parser for the two-line credential handoff format."""

import unicodedata


class Invalid(ValueError):
    """Credential input violates the accepted format."""


_ALIASES = {
    "accesstoken": "token",
    "TOKEN": "token",
    "orgId": "org",
    "ORG": "org",
}


def _decode(blob, max_bytes):
    if isinstance(blob, str):
        try:
            raw = blob.encode("utf-8")
        except UnicodeEncodeError as exc:
            raise Invalid("credentials are not valid UTF-8") from exc
    elif isinstance(blob, (bytes, bytearray)):
        raw = bytes(blob)
    else:
        raise Invalid("credentials must be bytes or text")
    if len(raw) > max_bytes:
        raise Invalid("credentials exceed the byte limit")
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise Invalid("credentials are not valid UTF-8") from exc


def _valid_value(value):
    return bool(value) and value.lower() != "null" and all(
        not char.isspace() and not unicodedata.category(char).startswith("C")
        for char in value
    )


def parse_credentials(blob, max_bytes=8192):
    """Return ``(token, org_id)`` from exactly one token/org key pair."""
    text = _decode(blob, max_bytes)
    found = {}
    for line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        if not line:
            continue
        if "=" not in line:
            raise Invalid("unknown non-empty credential line")
        key, value = line.split("=", 1)
        canonical = _ALIASES.get(key)
        if canonical is None:
            raise Invalid("unknown credential key")
        if canonical in found:
            raise Invalid("duplicate credential key")
        if not _valid_value(value):
            raise Invalid("credential value is empty, null, or contains whitespace/control characters")
        found[canonical] = value
    if set(found) != {"token", "org"}:
        raise Invalid("exactly one token and one org key are required")
    segments = found["token"].split("&")
    if len(segments) != 3 or not all(segments):
        raise Invalid("token must have exactly three non-empty segments")
    return found["token"], found["org"]
