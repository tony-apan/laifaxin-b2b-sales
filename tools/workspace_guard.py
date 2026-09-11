#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""★工作空间落点校验（fail-closed）——防"给了企业 orgId 却写进个人空间"。

为什么必须单独校验：
  ★2026-09-09 真实双空间对照实测（推翻旧诊断）：平台的工作空间由 **HTTP header `uid`** 决定，
  **query 参数 `?uid=` 无效**——同一 token 同一 orgId，header 传 → isOrg=true/企业数据，
  query 传 → isOrg=false/个人数据（query 传任意值含不存在的 ID 都落个人空间）。
  历史事故"给了企业 orgId 却写进个人账号"的根因就是工具把 uid 放 query。
  即便如此，落点仍须显式校验：token 可能属于别的账号、orgId 可能抄错、切换空间后没重取。
  "接口返回成功 + 参数回显一致"**不能**证明数据落进了目标空间；必须比对
  "声明的空间"与"平台实判的空间"。

判据（只读 `benefits/refine-data`，不写任何数据）：
  token 形状 `web.laifaxin.com&<用户UID>&<hash>`，中段=用户ID；`--org`=工作空间ID。
  - `isOrg=false`（平台判为个人空间）但 `org != uid` → **明确误路由**：请求的 org 未被采纳，
    数据会写进 token 所属个人空间。→ 阻断。
  - `isOrg=true`（平台判为企业空间）但 `org == uid` → 自相矛盾：企业工作空间 ID 不该等于
    用户 ID。→ 阻断，让用户回平台重新一键双取。
  - `isOrg=false` 且 `org == uid` → 个人空间自洽。→ 通过。
  - `isOrg=true` 且 `org != uid` → 企业空间自洽。→ 通过。
  - `isOrg` 缺失/类型异常 → **无法判定**：默认只告警不阻断（`--require-verified` 可改为阻断）。
    绝不把"未校验"说成"已校验"。

用法：
  python3 tools/workspace_guard.py --credentials-stdin
  python3 tools/workspace_guard.py --credentials-stdin --require-verified
  python3 tools/workspace_guard.py --token <T> --org <orgId>          # AI 内部兼容，禁止面向用户
输出：exit 0=通过 / 1=落点不匹配或未校验(按 require-verified) / 2=输入格式错 / 3=网络问题
"""
import argparse
import hashlib
import json
import subprocess
import sys

from credential_input import Invalid, parse_credentials

PROBE_PATH = "benefits/refine-data"


def token_uid(token):
    """取 token 中段=用户UID。形状不合法返回空串（不抛，交给调用方判定）。"""
    segments = str(token or "").split("&")
    return segments[1] if len(segments) == 3 and all(segments) else ""


def _probe(token, org, timeout=40):
    """只读探测：POST benefits/refine-data（工作空间靠 header uid 指定，非 query），返回解析后的 dict；非 JSON/失败返回 None。
    走 curl 子进程（与其余工具同一条网络路径），因此离线集成测试的 PATH 假 curl 可拦截。"""
    cmd = ["curl", "-sSL", "-m", str(max(1, timeout - 5)), "-X", "POST",
           f"https://web.laifaxin.com/api/{PROBE_PATH}",
           "-H", "Content-Type: application/json",
           "-H", f"accesstoken: {token}",
           "-H", f"uid: {org}",
           "-d", "{}"]
    try:
        completed = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.SubprocessError):
        return None
    try:
        value = json.loads(completed.stdout)
    except (ValueError, TypeError):
        return None
    return value if isinstance(value, dict) else None


def _as_bool(value):
    """isOrg 归一化：True/False 原样；1/0 视为真/假；其他（含缺失）返回 None。"""
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return bool(value)
    return None


def verify_workspace(token, org, probe=None):
    """校验"声明的工作空间"是否被平台采纳。

    返回 dict：
      ok        —— 是否允许继续
      verified  —— 是否真的拿到了平台判定（False=平台没返回 isOrg）
      blocked   —— 是否命中明确误路由（必须停止）
      reason    —— 人类可读结论
      observed  —— {is_org, vip, monthly_limit, daily_limit}（用于指纹）

    阻断只发生在"确凿矛盾"上；探测不到（网络/未登录/无 isOrg）只记未校验，
    由调用方按 --require-verified 决定是否阻断——绝不把"没校验"说成"已通过"。
    """
    uid = token_uid(token)
    if not str(org or "").strip():
        return {"ok": False, "verified": False, "blocked": True,
                "reason": "缺少 orgId——禁止回退 token 中段或默认个人空间",
                "observed": {}}

    data = (probe or _probe)(token, str(org))
    if data is None:
        return {"ok": False, "verified": False, "blocked": False,
                "reason": "网络/接口未取到探测结果——无法校验工作空间落点（不是凭据格式问题）",
                "observed": {}}
    if data.get("success") is not True:
        return {"ok": False, "verified": False, "blocked": False,
                "reason": f"探测接口未返回成功（{data.get('message') or '未登录或凭据无效'}）——无法校验落点",
                "observed": {}}

    details = data.get("data") if isinstance(data.get("data"), dict) else {}
    is_org = _as_bool(details.get("isOrg"))
    observed = {
        "is_org": is_org,
        "vip": details.get("vip") if isinstance(details.get("vip"), int) else None,
        "monthly_limit": details.get("monthlyLimit") if isinstance(details.get("monthlyLimit"), int) else None,
        "daily_limit": details.get("dailyLimit") if isinstance(details.get("dailyLimit"), int) else None,
    }
    same = bool(uid) and str(org) == uid

    if is_org is None:
        return {"ok": False, "verified": False, "blocked": False,
                "reason": "平台未返回 isOrg——无法判定落点是个人空间还是企业空间（未校验，不等于已通过）",
                "observed": observed}
    if not uid:
        return {"ok": False, "verified": False, "blocked": False,
                "reason": "token 形状无法解析出用户UID（应为 web.laifaxin.com&<用户UID>&<hash>）——无法比对落点",
                "observed": observed}
    if is_org is False and not same:
        return {"ok": False, "verified": True, "blocked": True,
                "reason": (f"请求的 orgId={org} 未被采纳：平台把本次会话判为【个人空间】，"
                           f"而 token 用户ID={uid} ≠ orgId——数据会写进 token 所属个人账号。"
                           "请回平台切到目标工作空间后重新一键双取，再重跑。"),
                "observed": observed}
    if is_org is True and same:
        return {"ok": False, "verified": True, "blocked": True,
                "reason": (f"自相矛盾：平台判为【企业空间】，但 orgId 与 token 用户ID 相同（{uid}）。"
                           "企业工作空间 ID 应是独立值——请回平台确认当前空间后重新一键双取。"),
                "observed": observed}
    label = "企业空间" if is_org else "个人空间"
    return {"ok": True, "verified": True, "blocked": False,
            "reason": f"工作空间落点一致：{label}（orgId 与 token 用户ID {'不同' if is_org else '相同'}）",
            "observed": observed}


def fingerprint(observed):
    """工作空间指纹（仅哈希，不含明文 ID）：用于把"审批时的工作空间"绑定进写操作参数。
    任何一项缺失都参与哈希（None 序列化为空），因此指纹缺失/变化都会导致不一致。"""
    basis = "|".join(str((observed or {}).get(k)) for k in ("is_org", "vip", "monthly_limit", "daily_limit"))
    return hashlib.sha256(basis.encode("utf-8")).hexdigest()


def preflight(token, org, dry_run=False, what=""):
    """写操作工具的统一入口：写之前先确认"声明的空间"被平台采纳。
    命中明确误路由 → 打印原因并 SystemExit(1)（不写任何数据）。
    dry_run=True 不联网（只读演练不落数据，无需校验）。
    返回指纹字符串（未校验时为空串），便于调用方记入审批参数。"""
    if dry_run:
        print("●工作空间校验: (dry-run 跳过线上校验)")
        return ""
    result = verify_workspace(token, org)
    if result["blocked"]:
        print(f"❌ 工作空间校验未通过：{result['reason']}")
        print(f"   拒绝写操作{f'（{what}）' if what else ''}——本次不会向平台写入任何数据。")
        raise SystemExit(1)
    if not result["verified"]:
        print(f"⚠️  工作空间未校验（不等于通过）：{result['reason']}")
        print("   已继续，但平台未提供判定字段，本次落点未核对；请勿据此声称空间已核对。")
        return ""
    print(f"  ✅ 工作空间校验: {result['reason']}")
    return fingerprint(result["observed"])


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
        return parse_credentials(f"accesstoken={args.token}\norgId={args.org}".encode("utf-8"), max_bytes=8192)
    raise Invalid("no credentials supplied")


def main(argv=None, *, stdin=None, probe=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--credentials-stdin", action="store_true", help="从 stdin 读取两行凭据")
    ap.add_argument("--require-verified", action="store_true",
                    help="平台未返回 isOrg（无法校验）时也阻断，而非仅告警")
    ap.add_argument("--gate-mode", action="store_true", help="脚本化调用：只输出一行结论")
    ap.add_argument("--fingerprint", action="store_true", help="额外输出工作空间指纹(sha256)")
    ap.add_argument("--token", default="", help="DEPRECATED/不安全：AI 内部兼容；禁止面向用户")
    ap.add_argument("--org", default="", help="DEPRECATED/不安全：AI 内部兼容；禁止面向用户")
    args = ap.parse_args(argv)
    stdin = stdin or sys.stdin

    try:
        token, org = _load_credentials(args, stdin)
    except (Invalid, UnicodeError) as exc:
        print(f"凭据格式错误：{exc}", file=sys.stderr)
        return 2

    result = verify_workspace(token, org, probe=probe)
    if result["blocked"]:
        print(f"❌ 工作空间校验未通过：{result['reason']}", file=sys.stderr)
        return 1
    if not result["verified"]:
        if args.require_verified:
            print(f"❌ 工作空间校验未通过：{result['reason']}", file=sys.stderr)
            return 1
        print(f"⚠️  未校验（不等于通过）：{result['reason']}", file=sys.stderr if args.gate_mode else sys.stdout)
        return 4
    print(f"✅ {result['reason']}")
    if args.fingerprint:
        print(f"   工作空间指纹: {fingerprint(result['observed'])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
