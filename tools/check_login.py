#!/usr/bin/env python3
"""Read-only LAIFAXIN login check with credentials supplied explicitly."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import tempfile
import time
from urllib import error, request

from credential_input import Invalid, parse_credentials


GUIDE_URL = "https://www.laifa.xin/share/ai/laifaxin-ai-account-connection"
TOKEN_SHAPE = re.compile(r"[^\s&]+&[^\s&]+&[^\s&]+")
DEFAULT_FAIL_FILE = Path(__file__).resolve().parent.parent / ".local" / "token-fail.json"


class PlatformResponseError(Exception):
    """The platform returned an HTTP body that is not a JSON object."""


def redact(value, token=""):
    text = str(value or "")
    if token:
        text = text.replace(token, "[REDACTED]")
    return TOKEN_SHAPE.sub("[REDACTED]", text)


def mask_identifier(value):
    text = str(value)
    if len(text) <= 4:
        return "*" * len(text)
    return "*" * (len(text) - 4) + text[-4:]


def plain_platform_message(message):
    """把平台返回的原始错误翻成人话（用户可能看到；禁止把平台术语原样透出）。

    实测平台会返回「token已失效」「未登录」这类词——"token"对小白是黑话，
    照抄会让用户以为要自己处理什么技术问题。
    """
    text = str(message or "").strip()
    low = text.lower()
    if "token" in low and ("失效" in text or "invalid" in low or "expire" in low):
        return "登录信息已过期"
    if "未登录" in text or "not login" in low or "unauthorized" in low:
        return "登录状态已失效"
    if "过期" in text or "expire" in low:
        return "登录信息已过期"
    # ★对抗审查 F-08：无匹配时不得把平台原文/英文透给用户（RULES：英文须先给中文解释）
    if re.search(r"[A-Za-z]{4,}", text):
        return "平台未说明具体原因（我来帮您查）"
    return text or "平台未说明原因"


def guide(reason, gate_mode=False):
    if gate_mode:
        print("登录校验失败：账号信息已失效或未登录。")
        return
    print(f"登录校验失败：{reason}")
    print(f"获取登录信息教程：{GUIDE_URL}")
    print("请把浏览器里一键复制到的两行，整段直接粘贴到当前聊天框发给 AI（不用拆分、不用改格式）。")


def _decode_response(body):
    if not body.strip():
        return None
    try:
        value = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def request_once(token, org):
    req = request.Request(
        "https://web.laifaxin.com/api/benefits/refine-data",
        data=b"{}",
        # ★工作空间必须放 header `uid`——实测 query 参数不起作用（2026-09-09 真实双空间对照）：
        #   header uid=企业ID → isOrg=true/企业数据；query uid=企业ID → isOrg=false/个人数据
        headers={"Content-Type": "application/json", "accesstoken": token, "uid": org},
        method="POST",
    )
    try:
        with request.urlopen(req, timeout=40) as response:
            body = response.read()
    except error.HTTPError as exc:
        body = exc.read()
        value = _decode_response(body)
        if value is not None:
            return value
        raise PlatformResponseError("HTTP response was not a JSON object") from exc
    return _decode_response(body)


def _parser():
    parser = argparse.ArgumentParser()
    parser.add_argument("--credentials-stdin", action="store_true", help="从 stdin 读取两行凭据")
    parser.add_argument("--gate-mode", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--token", default="", help="DEPRECATED/不安全：AI内部兼容；值会进入 argv，禁止面向用户")
    parser.add_argument("--org", default="", help="DEPRECATED/不安全：AI内部兼容；值会进入 argv，禁止面向用户")
    return parser


def _load_credentials(args, stdin):
    using_legacy = bool(args.token or args.org)
    if args.credentials_stdin and using_legacy:
        raise Invalid("stdin credentials cannot be mixed with legacy arguments")
    if args.credentials_stdin:
        if stdin.isatty():
            raise Invalid("--credentials-stdin requires non-interactive stdin")
        return parse_credentials(stdin.buffer.read(8193), max_bytes=8192)
    if using_legacy:
        if not args.token or not args.org:
            raise Invalid("legacy --token and --org must both be provided")
        blob = f"accesstoken={args.token}\norgId={args.org}".encode("utf-8")
        return parse_credentials(blob, max_bytes=8192)
    raise Invalid("no credentials supplied")


def _record_failure(token, fail_file, now):
    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()[:12]
    count = 1
    try:
        current = json.loads(fail_file.read_text(encoding="utf-8")) if fail_file.is_file() else {}
        if current.get("token_hash") == token_hash:
            count = int(current.get("count", 0)) + 1
    except (OSError, ValueError, TypeError):
        count = 1

    record = json.dumps({"token_hash": token_hash, "count": count, "last": now()})
    fail_file.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{fail_file.name}.", suffix=".tmp", dir=str(fail_file.parent)
    )
    try:
        try:
            os.fchmod(descriptor, 0o600)
        except OSError:
            pass
        with os.fdopen(descriptor, "w", encoding="utf-8") as temporary:
            temporary.write(record)
            temporary.flush()
            os.fsync(temporary.fileno())
        try:
            os.chmod(temporary_name, 0o600)
        except OSError:
            pass
        os.replace(temporary_name, fail_file)
        try:
            os.chmod(fail_file, 0o600)
        except OSError:
            pass
    finally:
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass
    return count


def main(argv=None, *, stdin=None, request=request_once, sleep=time.sleep,
         fail_file=DEFAULT_FAIL_FILE, now=None):
    args = _parser().parse_args(argv)
    stdin = stdin or sys.stdin
    now = now or (lambda: time.strftime("%Y-%m-%dT%H:%M:%S"))
    try:
        token, org = _load_credentials(args, stdin)
    except (Invalid, UnicodeError) as exc:
        reason = "未提供凭据" if not args.credentials_stdin and not (args.token or args.org) else redact(exc)
        if not args.credentials_stdin and not (args.token or args.org):
            guide(reason, args.gate_mode)
        else:
            print("发来的内容不完整或格式不对——通常是复制时少了一段。请把浏览器里一键复制到的两行整段发我（不用拆分、不用改格式）。", file=sys.stderr)
        return 2

    data = None
    last_error = None
    for attempt in range(3):
        try:
            data = request(token, org)
            last_error = None
        except Exception as exc:
            last_error = exc
            data = None
        if data is not None:
            break
        if attempt < 2:
            if not args.gate_mode:
                print(f"接口返回为空，5 秒后自动重试（{attempt + 1}/3）...")
            sleep(5)

    if data is None:
        if isinstance(last_error, PlatformResponseError):
            print("平台返回错误页/非JSON，请稍后重试。", file=sys.stderr)
        elif last_error is not None:
            print("网络不通或请求超时——不是您粘贴内容的问题，稍后重试即可。", file=sys.stderr)
        else:
            print("平台连续三次返回空或非 JSON 内容，请稍后重试。", file=sys.stderr)
        return 3

    if data.get("success") is not True:
        message = redact(data.get("message") or "接口拒绝登录", token)
        try:
            count = _record_failure(token, Path(fail_file), now)
        except OSError:
            count = 1
        if args.gate_mode:
            print("登录校验失败：账号信息已失效或未登录。", file=sys.stderr)
        else:
            guide(f"账号信息已失效或未登录（平台提示：{plain_platform_message(message)}）")
            if count >= 2:
                print(f"这份登录信息已连续 {count} 次失效，反复重贴没用——请回浏览器重新复制一次。")
        return 1

    if args.gate_mode:
        print("登录校验通过。")
        return 0

    details = data.get("data") if isinstance(data.get("data"), dict) else {}

    def response_int(name, default=0):
        value = details.get(name)
        return value if isinstance(value, int) and not isinstance(value, bool) else default

    vip = response_int("vip", None)
    vip_label = "SVIP" if vip == 2 else (f"VIP {vip}" if vip is not None else "未知")
    daily_limit = response_int("dailyLimit")
    daily_used = response_int("dailyUsed")
    monthly_limit = response_int("monthlyLimit")
    monthly_used = response_int("monthlyUsed")
    monthly_charge_count = details.get("monthlyChargeCount")
    monthly_auto_charge = details.get("monthlyAutoCharge")
    show_monthly_charge = (
        isinstance(monthly_charge_count, int)
        and not isinstance(monthly_charge_count, bool)
        and isinstance(monthly_auto_charge, bool)
    )
    print("连接成功，来发信账号状态：")
    print(
        f"   操作用户：{mask_identifier(token.split('&')[1])} | "
        f"当前操作空间：{mask_identifier(org)}"
    )
    print(f"   账号等级：{vip_label}")
    print(f"   今日查看配额：{daily_limit} 条，已用 {daily_used} 条")
    print(f"   本月查看配额：{monthly_limit} 条，已用 {monthly_used} 条")
    if show_monthly_charge:
        auto_label = "已开启" if monthly_auto_charge else "未开启"
        print(f"   本月充值：{monthly_charge_count} 次（自动充值：{auto_label}）")
    print("   本次只做连接检查，没有搜索、保存、扣点或发信。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
