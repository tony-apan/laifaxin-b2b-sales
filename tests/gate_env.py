"""测试放行握手：一次性票据 + 随机 nonce；生产入口只认票据，不认裸 env。"""
from __future__ import annotations

import atexit
import os
import secrets
import shutil
import tempfile

_DIR = tempfile.mkdtemp(prefix="lfx-gate-test-")
_NONCE = secrets.token_hex(16)
_TICKET = os.path.join(_DIR, "ticket")
with open(_TICKET, "w", encoding="utf-8") as _f:
    _f.write(_NONCE)
atexit.register(shutil.rmtree, _DIR, True)

_ENV = {
    "LFX_GATE_TEST_MODE": "1",
    "LFX_GATE_TEST_TICKET": _TICKET,
    "LFX_GATE_TEST_NONCE": _NONCE,
}


def gate_test_env():
    """返回本次测试进程的一次性放行票据环境（可并入子进程 env）。"""
    return dict(_ENV)
