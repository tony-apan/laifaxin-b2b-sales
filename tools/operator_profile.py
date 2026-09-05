#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""运营方档案 CLI（本地标准库，不调用平台、不保存 token）。

公司名/官网/联系邮箱等属于用户自己的公司级资料，AI 可主动索取并回落到
.local/operators/<operator_key>.md（多公司各一份），供跨产品复用。
旧版单运营方文件 .local/operator-profile.md 兼容读取（明确提示为旧格式）。
邮件签名始终只取 nickname。

第三方资料边界（静态红队P1）: contact_email 字段允许存运营方自己的邮箱;
其他任何字段值出现额外邮箱/电话号码/客户·买家·联系人清单标记 → 校验拒绝。
"""
import argparse
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from profile_utils import (
    find_emails, find_list_markers, find_phones, mask_email, mask_phone, validate_nickname,
)

KB = Path(__file__).resolve().parent.parent
OPERATORS_DIR = KB / ".local" / "operators"
LEGACY_PATH = KB / ".local" / "operator-profile.md"  # 旧版单运营方档案(兼容读取)
FORBIDDEN_FIELD_KEYS = {"token", "accesstoken", "customer_email", "customer_emails", "contact_list", "customer_list", "客户邮箱", "联系人邮箱"}
ALLOWED_KEYS = (
    "operator_key", "nickname", "company_name", "website", "contact_email",
    "target_markets", "default_languages", "updated_at",
)


def now():
    return time.strftime("%Y-%m-%dT%H:%M:%S")


def safe(value, limit=500):
    return " ".join(str(value or "").replace("\r", " ").replace("\n", " ").split())[:limit]


def default_path_for(operator_key):
    """多公司默认路径: .local/operators/<operator_key>.md"""
    return OPERATORS_DIR / f"{(operator_key or '').strip()}.md"


def resolve_path(path_arg, operator_key):
    """解析档案路径, 返回 (path, note)。
    优先级: 显式 --path > .local/operators/<operator_key>.md > 旧版 .local/operator-profile.md(兼容)。"""
    if path_arg:
        return Path(path_arg), ""
    key = (operator_key or "").strip()
    if key:
        return default_path_for(key), ""
    if LEGACY_PATH.is_file():
        return LEGACY_PATH, "旧版单运营方档案(.local/operator-profile.md)——多运营方请迁移到 .local/operators/<operator_key>.md(工具兼容读取本文件)"
    return OPERATORS_DIR, "未指定路径且找不到档案——传 --path, 或 --operator-key <运营方>(默认 .local/operators/<key>.md), 旧版文件 .local/operator-profile.md 也可显式指定"


def read_fields(path):
    p = Path(path)
    fields = {}
    if not p.is_file():
        return fields
    for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
        if ":" not in line or line.lstrip().startswith("#"):
            continue
        key, val = line.split(":", 1)
        if key.strip() in ALLOWED_KEYS:
            fields[key.strip()] = val.strip()
    return fields


def validate(fields):
    issues = []
    if not fields.get("operator_key"):
        issues.append("缺 operator_key")
    ok, reason = validate_nickname(fields.get("nickname", ""))
    if not ok:
        issues.append("nickname 非纯个人昵称: " + reason)
    website = fields.get("website", "")
    if website and not re.match(r"^https?://[^\s]+$", website):
        issues.append("website 须为完整 http/https URL")
    email = fields.get("contact_email", "")
    if email and not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email):
        issues.append("contact_email 格式无效")
    # 第三方资料边界(静态红队P1): 除 contact_email 外, 任何字段值不得含额外邮箱/电话/清单标记
    for key in ALLOWED_KEYS:
        if key == "contact_email":
            continue
        val = (fields.get(key) or "").strip()
        if not val:
            continue
        emails = find_emails(val)
        if emails:
            issues.append(f"{key} 含额外邮箱({mask_email(emails[0])})——运营方档案只有 contact_email 字段可存邮箱")
        phones = find_phones(val)
        if phones:
            issues.append(f"{key} 含疑似电话号码({mask_phone(phones[0])})——电话号码不入运营方档案")
        markers = find_list_markers(val)
        if markers:
            issues.append(f"{key} 含客户/买家/联系人清单标记({markers[0]})——第三方联系方式清单禁止写入")
    return issues


def write_fields(path, fields):
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# 运营方档案（本地，不入 Git；不含 token）",
        f"operator_key: {safe(fields.get('operator_key'))}",
        f"nickname: {safe(fields.get('nickname'))}",
        f"company_name: {safe(fields.get('company_name'))}",
        f"website: {safe(fields.get('website'))}",
        f"contact_email: {safe(fields.get('contact_email'))}",
        f"target_markets: {safe(fields.get('target_markets'))}",
        f"default_languages: {safe(fields.get('default_languages'))}",
        f"updated_at: {safe(fields.get('updated_at') or now())}",
        "",
        "> 邮件签名只读取 nickname；其他字段只供 AI 建档、读取官网、客群与产品分析，不进入签名区。",
        "> contact_email 只存运营方自己的联系邮箱；客户/买家/联系人等第三方邮箱、电话、清单一律禁止写入。",
    ]
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")


def cmd_init(args):
    p, _ = resolve_path(args.path, args.operator_key)
    if p.exists():
        print(f"❌ 档案已存在，不覆盖: {p}")
        return 3
    fields = {"operator_key": args.operator_key, "nickname": args.nickname, "updated_at": now()}
    issues = validate(fields)
    if issues:
        for issue in issues:
            print("❌ " + issue)
        return 2
    write_fields(p, fields)
    print(f"✅ 已初始化运营方档案: {p}（签名昵称={args.nickname}；不含 token）")
    return 0


def cmd_update(args):
    p, note = resolve_path(args.path, args.operator_key)
    fields = read_fields(p)
    if not fields:
        print(f"❌ 档案不存在或为空，先 init: {p}")
        print(f"   (默认路径: .local/operators/<operator_key>.md; 旧版 .local/operator-profile.md 需显式 --path 指定)")
        return 2
    if note:
        print(f"   ℹ️ {note}")
    for key in ("company_name", "website", "contact_email", "target_markets", "default_languages"):
        value = getattr(args, key)
        if value is not None:
            fields[key] = value
    if args.nickname is not None:
        fields["nickname"] = args.nickname
    fields["updated_at"] = now()
    issues = validate(fields)
    if issues:
        for issue in issues:
            print("❌ " + issue)
        return 2
    write_fields(p, fields)
    print(f"✅ 已更新运营方档案: {p}（公司资料仅供 AI 使用；邮件签名={fields['nickname']}）")
    return 0


def cmd_validate(args):
    p, note = resolve_path(args.path, args.operator_key)
    fields = read_fields(p)
    issues = validate(fields)
    text = p.read_text(encoding="utf-8", errors="replace") if p.is_file() else ""
    for line in text.splitlines():
        if ":" not in line or line.lstrip().startswith(("#", ">")):
            continue
        key = line.split(":", 1)[0].strip().lower()
        if key in FORBIDDEN_FIELD_KEYS:
            issues.append(f"发现禁止字段: {key}")
    if issues:
        for issue in issues:
            print("❌ " + issue)
        return 2
    if note:
        print(f"   ℹ️ {note}")
    print(f"✅ 运营方档案通过: {p}（nickname={fields.get('nickname')}；签名只用此字段）")
    return 0


def cmd_status(args):
    p, note = resolve_path(args.path, args.operator_key)
    fields = read_fields(p)
    if not fields:
        print(f"❌ 未找到运营方档案: {p}")
        print("   (默认路径: .local/operators/<operator_key>.md; 旧版 .local/operator-profile.md 兼容)")
        return 2
    if note:
        print(f"   ℹ️ {note}")
    for key in ("operator_key", "nickname", "company_name", "website", "target_markets", "default_languages", "updated_at"):
        print(f"{key}: {fields.get(key, '')}")
    print("contact_email: " + ("已记录" if fields.get("contact_email") else "未记录"))
    return 0


def main():
    parser = argparse.ArgumentParser(description="运营方档案管理（公司级资料跨产品复用；签名仅昵称；多运营方各一份 .local/operators/<operator_key>.md）")
    parser.add_argument("--path", default="", help="档案路径(默认 .local/operators/<operator_key>.md; 未给 operator_key 时回落旧版 .local/operator-profile.md)")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("init")
    p.add_argument("--operator-key", required=True)
    p.add_argument("--nickname", required=True)
    p.set_defaults(fn=cmd_init)
    p = sub.add_parser("update")
    p.add_argument("--operator-key", default="", help="运营方标识(用于定位 .local/operators/<key>.md; 缺省时回落旧版单运营方档案)")
    p.add_argument("--nickname")
    p.add_argument("--company-name")
    p.add_argument("--website")
    p.add_argument("--contact-email")
    p.add_argument("--target-markets")
    p.add_argument("--default-languages")
    p.set_defaults(fn=cmd_update)
    p = sub.add_parser("validate")
    p.add_argument("--operator-key", default="", help="同 update")
    p.set_defaults(fn=cmd_validate)
    p = sub.add_parser("status")
    p.add_argument("--operator-key", default="", help="同 update")
    p.set_defaults(fn=cmd_status)
    args = parser.parse_args()
    raise SystemExit(args.fn(args) or 0)


if __name__ == "__main__":
    main()
