#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""只读 base-url 配置（Guard V2）。

生产 base-url 固定为 https://web.laifaxin.com，不读任何环境变量、不读配置文件，
不接受任意远端覆盖。唯一的注入通道是 install_test_override()，且仅接受数值
loopback 地址（127.0.0.1 / ::1）+ 端口——这一通道只应由 tests/guard_v2_support.py
的测试 bootstrap 在单一 guard-test-context 下调用（见 GUARD-FIX-V2 §7.1）。

本模块是受控工具链的调用图守卫组件，不是进程组防火墙：不承诺恶意进程无法
绕过，不修改宿主网络配置。
"""
from __future__ import annotations

import ipaddress
from typing import Optional
from urllib.parse import urlparse

PRODUCTION_BASE_URL = "https://web.laifaxin.com"
_LOOPBACK_HOSTS = ("127.0.0.1", "localhost", "::1")

_override_base_url: Optional[str] = None


class BaseUrlError(ValueError):
    """非法 base-url（远端地址 / 坏格式 / 端口缺失）。"""


def _validate_loopback(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme != "http":
        raise BaseUrlError("测试 base-url 只允许 http loopback")
    host = parsed.hostname or ""
    if host not in _LOOPBACK_HOSTS:
        raise BaseUrlError("测试 base-url 只允许 loopback 主机: " + host)
    try:
        ipaddress.ip_address(host)
    except ValueError:
        if host != "localhost":
            raise BaseUrlError("测试 base-url 主机非法: " + host)
    if parsed.port is None:
        raise BaseUrlError("测试 base-url 必须带显式端口")
    return "{0}://{1}:{2}".format(parsed.scheme, host, parsed.port)


def install_test_override(url: str) -> None:
    """安装进程内测试 base-url（仅 loopback+端口；生产代码不得调用）。"""
    global _override_base_url
    _override_base_url = _validate_loopback(url)


def install_from_context(context_path: str) -> str:
    """从 guard-test context 文件安装测试 base-url；返回实际 base-url。

    仅接受由测试父进程生成的 context.json，且其中的 base_url 必须是
    loopback+端口；任何远端地址直接抛错，不静默回退生产地址。
    """
    import json
    from pathlib import Path

    doc = json.loads(Path(context_path).read_text(encoding="utf-8"))
    if not isinstance(doc, dict):
        raise BaseUrlError("guard-test context 必须是 object")
    base_url = doc.get("base_url")
    if not isinstance(base_url, str) or not base_url:
        raise BaseUrlError("guard-test context 缺 base_url")
    install_test_override(base_url)
    return get_base_url()


def clear_test_override() -> None:
    global _override_base_url
    _override_base_url = None


def get_base_url() -> str:
    return _override_base_url if _override_base_url else PRODUCTION_BASE_URL


def api_url(path: str) -> str:
    """平台 API 完整 URL：path 为不带 /api 前缀的相对路径。"""
    if not isinstance(path, str) or not path.strip():
        raise BaseUrlError("api path 为空")
    cleaned = path.strip().strip("/")
    if cleaned.startswith("api/"):
        cleaned = cleaned[4:]
    return get_base_url() + "/api/" + cleaned
