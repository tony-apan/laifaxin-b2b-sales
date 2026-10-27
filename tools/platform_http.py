#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""进程内平台 HTTP：token/org 只在内存；base 由 api_base_url 唯一决定；拒绝 3xx 外带。

★R2-AC1：LFX_BUNDLE_TEST_BASE_URL 只在 gate 测试票据有效时接受，且必须是合法 loopback；
票据无效/URL 非法/远端 → 在构造 Request/打开 opener 之前抛错（0 opener 调用），绝不静默回生产。
本函数不重复实现 loopback 判定——一律交给 api_base_url.install_test_override 的现有校验，
任何残留 override 在票据失效时先 clear 再拒。
"""
import json, os, urllib.error, urllib.request
import api_base_url


class TestBaseError(RuntimeError):
    pass


def _apply_test_base():
    url = os.environ.get("LFX_BUNDLE_TEST_BASE_URL")
    if not url:
        # R2c fail-closed：无测试 env 时，任何残留 override（先前测试调用安装的）一律清除并回到生产路径
        api_base_url.clear_test_override()
        return
    import auth_guard
    if not auth_guard._test_mode_allowed():
        api_base_url.clear_test_override()  # 残留 override 跨模式不得继续生效
        raise TestBaseError("LFX_BUNDLE_TEST_BASE_URL 存在但测试票据无效——拒绝在非测试模式改写平台地址")
    try:
        api_base_url.install_test_override(url)  # 非 loopback/坏URL 在这里抛 BaseUrlError
    except ValueError as exc:
        raise TestBaseError("测试 base-url 非法（只允许 http loopback+端口）: " + str(exc))


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):
        return None


def post(path, payload, token, org, timeout=60):
    """返回响应文本；任何网络/3xx/4xx5xx 之外的失败按空串返回（调用方 fail-closed）。
    测试 base 非法/票据无效时在 Request/open 之前抛 TestBaseError（0 opener 调用）。"""
    _apply_test_base()
    req = urllib.request.Request(api_base_url.api_url(path), data=json.dumps(payload).encode("utf-8"), method="POST",
                                 headers={"Content-Type": "application/json", "accesstoken": token, "uid": org})
    opener = urllib.request.build_opener(_NoRedirect)
    try:
        with opener.open(req, timeout=timeout) as resp:
            return resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        return exc.read().decode("utf-8", errors="replace") if 400 <= exc.code < 600 else ""
    except (OSError, ValueError):
        return ""


def read_stdin_credentials(stream):
    from credential_input import parse_credentials
    return parse_credentials(stream.buffer.read(8193), max_bytes=8192)


def install_workspace_probe(token, org):
    """让 workspace_guard 的落点探测也走进程内 HTTP（原 curl 子进程会把 token 放进 argv）。"""
    import workspace_guard
    def _probe(t, o, timeout=40):
        try:
            v = json.loads(post(workspace_guard.PROBE_PATH, {}, token, org, timeout=max(1, timeout - 5)))
        except (ValueError, TypeError):
            return None
        return v if isinstance(v, dict) else None
    workspace_guard._probe = _probe
