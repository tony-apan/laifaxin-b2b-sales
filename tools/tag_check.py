#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Only-read: check whether a contact tag already has contacts before saving."""
from __future__ import annotations
import argparse, json, os, subprocess, sys
from pathlib import Path
TOOLS = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS))
def _cred(args):
    if args.token and args.org:
        return args.token, args.org
    from session_store import load_ready
    _h, t, o = load_ready(TOOLS.parent)
    return t, o
def _api(path, payload, token, org):
    from tag_write_guard import check_send
    check_send(path, payload)
    cmd = ["curl", "-sSL", "-m", "30", "-X", "POST",
           "https://web.laifaxin.com/api/" + path,
           "-H", "Content-Type: application/json",
           "-H", "accesstoken: " + token, "-H", "uid: " + org,
           "-d", json.dumps(payload)]
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    try:
        return json.loads(r.stdout)
    except Exception:
        return {"success": False, "_raw": (r.stdout or r.stderr)[:300]}
def main(argv=None):
    ap = argparse.ArgumentParser(description="only-read tag freshness check")
    ap.add_argument("--contact-tag", required=True)
    ap.add_argument("--token", default=os.environ.get("LFX_TOKEN", ""))
    ap.add_argument("--org", default=os.environ.get("LFX_ORG", ""))
    ap.add_argument("--from-session", action="store_true")
    ap.add_argument("--max-existing", type=int, default=0)
    args = ap.parse_args(argv)
    token, org = _cred(args)
    filt = {"property": "tags", "operator": "include", "value": args.contact_tag,
            "values": [args.contact_tag], "valueType": "select"}
    d = _api("contacts/contacts/show",
             {"current": 1, "pageSize": 100, "filters": [filt], "viewId": "all"}, token, org)
    data = d.get("data") or {}
    total = data.get("total")
    print(json.dumps({"success": d.get("success"), "tag": args.contact_tag,
                      "existing": total, "max_existing": args.max_existing},
                     ensure_ascii=False, indent=2))
    if not d.get("success") or not isinstance(total, int):
        print("DENY E_TAG_COUNT_UNKNOWN: cannot confirm tag count", file=sys.stderr)
        return 2
    if total > args.max_existing:
        print("DENY E_TAG_NOT_EMPTY: tag has %d contacts; create a new test tag" % total,
              file=sys.stderr)
        return 3
    print("OK: tag is empty")
    return 0
if __name__ == "__main__":
    raise SystemExit(main())
