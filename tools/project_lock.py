#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""项目级本机写锁：防同一项目被多个AI会话并发执行高风险写操作。"""
import atexit
import json
import os
import time
from pathlib import Path

_HELD = []


def _pid_alive(pid):
    try:
        os.kill(int(pid), 0); return True
    except (OSError, ValueError):
        return False


def acquire_project_lock(record_path, action):
    project_dir = Path(record_path).resolve().parent
    lock = project_dir / ".operation.lock"
    if lock.exists():
        try: info = json.loads((lock / "owner.json").read_text(encoding="utf-8"))
        except Exception: info = {}
        if info.get("pid") and _pid_alive(info["pid"]):
            if int(info["pid"]) == os.getppid() and os.environ.get("LFX_PARENT_LOCK") == str(lock):
                return lock  # 受控子进程复用父锁；子进程不登记/不释放
            raise RuntimeError(f"项目正被另一进程写入: pid={info['pid']} action={info.get('action')} lock={lock}")
        # PID已不存在才清陈旧锁
        for child in lock.glob("*"): child.unlink(missing_ok=True)
        lock.rmdir()
    try:
        lock.mkdir()
    except FileExistsError:
        raise RuntimeError(f"项目写锁竞争失败: {lock}")
    (lock / "owner.json").write_text(json.dumps({"pid": os.getpid(), "action": action, "time": time.time()}), encoding="utf-8")
    _HELD.append(lock)
    return lock


def release_all():
    for lock in reversed(_HELD):
        try:
            for child in lock.glob("*"): child.unlink(missing_ok=True)
            lock.rmdir()
        except OSError:
            pass
    _HELD.clear()


atexit.register(release_all)
