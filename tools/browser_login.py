#!/usr/bin/env python3
"""Isolated Chromium login connector. Standard library only, Python 3.9+."""
import argparse
import base64
import hashlib
import hmac
import math
import json
import os
from pathlib import Path
import plistlib
import secrets
import shutil
import socket
import struct
import subprocess
import sys
import tempfile
import time
from urllib import parse, request

ROOT = Path(__file__).resolve().parents[1]
MARKER = '.browser-login-owner'
MAGIC = 'laifaxin-browser-login-v1'
MAX_MESSAGE = 1024 * 1024
PLAYWRIGHT_INSTALL = 'python -m venv .venv && .venv/bin/pip install playwright && .venv/bin/python -m playwright install chromium'
MANUAL_STEPS = (
    '① 二层降级优先：在 app.laifaxin.com 页面按 F12 打开控制台，粘贴一键命令取参',
    '② 仍不行→三步手动兜底：打开 https://app.laifaxin.com → 登录 → 按 F12 粘贴同一一键命令',
    'AI 用 web 入口取参、你手动用 app 入口查看，两者是同一账号的不同入口',
    '如遇登录态互踢以实际为准并报错（跨域有效性 UNVERIFIED，首次真实登录时冒烟验证）',
    '只允许剪贴板粘贴 + session_store（0600/0700），禁止手写文件；不得回显完整 token',
)

DETAIL = {
    0: '连接与工作空间校验通过。',
    10: '还没有读到完整登录信息，窗口仍开着，登录完成后可用 --resume 继续取参，或关掉窗口后重跑；也可用 --clean --force 清理。',
    11: '浏览器环境不可用（无可用 Chrome/Edge、Playwright 缺失、启动失败或 CDP 连接失败）。请' + '；'.join(MANUAL_STEPS[:2]) + '；跨域有效性 UNVERIFIED（首次真实登录时冒烟验证）',
    12: '平台不认这把钥匙，或平台或网络临时问题：请确认页面登录态（F5 刷新）后重新取参；同一份反复重试无意义。',
    13: '缺少工作空间编号（orgId）：请在来发信页面右上角确认目标空间后一键双取，不要手敲。',
    14: '上次窗口还开着，请先完成那次操作；可用 --resume 继续，或 --clean --force 清理本工具窗口。若窗口已不可用：' + '；'.join(MANUAL_STEPS[:2]) + '；跨域有效性 UNVERIFIED（首次真实登录时冒烟验证）',
    15: '疑似多账号或工作空间不符：请退出多余账号、确认右上角目标空间后重新一键双取；仍不符请报错人工处理。',
    20: '参数不合法，仅支持来发信 HTTPS 子域名与有效选项；仍不行：' + '；'.join(MANUAL_STEPS[:2]) + '；跨域有效性 UNVERIFIED（首次真实登录时冒烟验证）',
    21: '专用目录不安全，请使用仓库 .local 下的本工具目录；仍不行：' + '；'.join(MANUAL_STEPS[:2]) + '；跨域有效性 UNVERIFIED（首次真实登录时冒烟验证）',
    22: '窗口关了，需要时我再开。',
    23: '本次操作中断或校验程序异常，请稍后重试。',
    24: '登录信息格式不完整：请重新一键双取（accesstoken 与 orgId 两行一起），不要手敷。',
    25: '平台没给判定依据：请重新一键双取；仍不行请报错人工处理。',
    26: 'Playwright 环境未就绪。安装命令：' + PLAYWRIGHT_INSTALL + '；' + '；'.join(MANUAL_STEPS[:2]) + '；跨域有效性 UNVERIFIED（首次真实登录时冒烟验证）',
    27: '检测到你在另一个入口也登录着，要用这个账号的空间吗？（是/否）确认后请加 --accept-fallback-host 重跑；未确认不会保存任何凭据，也不会继续。' + '；跨域有效性 UNVERIFIED（首次真实登录时冒烟验证）',
}

class Failure(Exception):
    def __init__(self, code, stage, diagnostic=None, **fields):
        self.code, self.stage = code, stage
        self.fields = fields
        self.diagnostic = diagnostic or 'E_' + {10: 'TIMEOUT', 11: 'ENVIRONMENT', 12: 'INVALID', 13: 'ORG_MISSING', 14: 'LOCKED', 15: 'CONFLICT', 20: 'ARGUMENT', 21: 'PROFILE', 22: 'CLOSED', 23: 'SUBPROCESS', 24: 'INPUT_FORMAT', 25: 'UNDETERMINED', 27: 'FALLBACK_NEEDS_CONFIRM'}.get(code, 'UNKNOWN')
        super().__init__(self.diagnostic)


def allowed_host(host):
    """host 白名单精确两值；不得用后缀匹配放行任意子域。"""
    return isinstance(host, str) and host.lower() in ALLOWED_HOSTS


ALLOWED_HOSTS = frozenset(('app.laifaxin.com', 'web.laifaxin.com'))


def validate_url(url):
    try:
        u = parse.urlsplit(url)
        if u.scheme != 'https' or not allowed_host(u.hostname) or u.username or u.password or u.port not in (None, 443):
            raise ValueError()
        return u.hostname.lower()
    except ValueError:
        raise Failure(20, 'probe')


def alive(pid):
    if not isinstance(pid, int) or pid <= 0:
        return False
    if os.name == "nt":
        import ctypes
        k32 = ctypes.windll.kernel32
        handle = k32.OpenProcess(0x1000, False, int(pid))
        if not handle:
            return False
        try:
            code = ctypes.c_ulong()
            return bool(k32.GetExitCodeProcess(handle, ctypes.byref(code))) and code.value == 259
        finally:
            k32.CloseHandle(handle)
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False


def owner_key(profile, create=False):
    keyfile = profile.parent / '.browser-login-key'
    if keyfile.is_symlink():
        raise Failure(21, 'launch')
    if create and not keyfile.exists():
        fd = os.open(str(keyfile), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, 'w') as f:
            f.write(secrets.token_hex(32))
    return keyfile.read_bytes()


def read_owner(profile):
    marker = profile / MARKER
    if marker.is_symlink():
        raise Failure(21, 'launch')
    try:
        data = json.loads(marker.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return None
        signature = data.pop('signature')
        expected = hmac.new(owner_key(profile), json.dumps(data, sort_keys=True).encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(signature, expected):
            return None
        if (data.get('owner') != MAGIC or data.get('profile') != str(profile.resolve())
                or not isinstance(data.get('nonce'), str) or len(data['nonce']) != 64
                or any(c not in '0123456789abcdef' for c in data['nonce'])
                or not isinstance(data.get('exe'), str) or (data['exe'] and not Path(data['exe']).is_absolute())
                or not isinstance(data.get('time'), (int, float)) or not math.isfinite(data['time']) or data['time'] <= 0):
            return None
        if data.get('pid') is not None:
            if (not data['exe'] or not isinstance(data.get('pid'), int) or data['pid'] <= 0
                    or not isinstance(data.get('port'), int) or not 1 <= data['port'] <= 65535
                    or not isinstance(data.get('process_identity'), str) or not data['process_identity']):
                return None
        return data
    except (OSError, ValueError, KeyError, TypeError):
        return None


def safe_profile(root, value, create=True):
    root = root.resolve()
    path = Path(value)
    if not path.is_absolute():
        path = root / path
    if any(p.is_symlink() for p in (path,) + tuple(path.parents) if p == root or root in p.parents):
        raise Failure(21, 'launch')
    local = root / '.local'
    resolved = path.resolve()
    if not resolved.is_relative_to(local.resolve()) or resolved == local.resolve() or not resolved.is_relative_to(root):
        raise Failure(21, 'launch')
    if resolved.exists():
        # Signed ownership permits our Chromium files, without opening their contents.
        if not resolved.is_dir() or (any(resolved.iterdir()) and not read_owner(resolved)):
            raise Failure(21, 'launch')
    if create:
        local.mkdir(parents=True, exist_ok=True, mode=0o700)
        local.chmod(0o700)
        resolved.mkdir(parents=True, exist_ok=True, mode=0o700)
        resolved.chmod(0o700)
        if not read_owner(resolved):
            save_owner(resolved, {})
    return resolved


def save_owner(profile, fields):
    marker = profile / MARKER
    if marker.is_symlink():
        raise Failure(21, 'launch')
    data = dict(fields, owner=MAGIC, profile=str(profile.resolve()),
                nonce=secrets.token_hex(32), exe=str(Path(fields['exe']).resolve()) if fields.get('exe') else '',
                time=fields.get('time', time.time()))
    data['signature'] = hmac.new(owner_key(profile, True), json.dumps(data, sort_keys=True).encode(), hashlib.sha256).hexdigest()
    fd = os.open(str(marker), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, 'w') as stream:
        json.dump(data, stream)


class ProfileLock:
    def __init__(self, profile, resume_owner=None):
        self.resume_owner = resume_owner
        self.path = profile / '.lock'
        self.identity = secrets.token_hex(16)

    def __enter__(self):
        # Stable external inode serializes stale reclamation and profile deletion.
        guard = self.path.parent.parent / ('.browser-lock-' + hashlib.sha256(str(self.path.parent).encode()).hexdigest()[:24])
        if guard.is_symlink():
            raise Failure(21, 'launch')
        self.guard_fd = os.open(str(guard), os.O_CREAT | os.O_RDWR, 0o600)
        try:
            if os.name == 'nt':
                import msvcrt
                if os.fstat(self.guard_fd).st_size == 0:
                    os.write(self.guard_fd, b'0')
                os.lseek(self.guard_fd, 0, os.SEEK_SET)
                try:
                    msvcrt.locking(self.guard_fd, msvcrt.LK_NBLCK, 1)
                except OSError:
                    raise Failure(14, 'launch')
            else:
                import fcntl
                fcntl.flock(self.guard_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return self.acquire()
        except BaseException as exc:
            os.close(self.guard_fd)
            self.guard_fd = None
            if isinstance(exc, BlockingIOError):
                raise Failure(14, 'launch')
            raise

    def acquire(self):
        for attempt in range(2):
            if self.path.is_symlink():
                raise Failure(21, 'launch')
            try:
                fd = os.open(str(self.path), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            except FileExistsError:
                before = self.path.stat()
                raw = self.path.read_text(encoding="utf-8")
                try:
                    old = json.loads(raw)
                    if not isinstance(old, dict):
                        raise ValueError()
                    resume = self.resume_owner and old.get('pid') == self.resume_owner.get('pid') and old.get('identity') == self.resume_owner.get('nonce')
                    stale = not alive(old.get('pid')) or resume
                    if not stale and time.time() - float(old.get('time', 0)) > 7200:
                        print('E_OLD_LIVE_LOCK', file=sys.stderr)
                except (OSError, ValueError, TypeError, KeyError):
                    stale = time.time() - self.path.stat().st_mtime > 7200
                if not stale or attempt:
                    raise Failure(14, 'launch')
                current = self.path.stat()
                if (current.st_ino, current.st_mtime_ns) != (before.st_ino, before.st_mtime_ns) or self.path.read_text(encoding="utf-8") != raw:
                    raise Failure(14, 'launch')
                self.path.unlink()
                print('E_STALE_LOCK', file=sys.stderr)
                continue
            with os.fdopen(fd, 'w') as stream:
                json.dump({'pid': os.getpid(), 'time': time.time(), 'identity': self.identity}, stream)
            return self
        raise Failure(14, 'launch')

    def __exit__(self, *args):
        try:
            if not getattr(self, 'preserve', False):
                try:
                    if json.loads(self.path.read_text(encoding="utf-8")).get('identity') == self.identity:
                        self.path.unlink()
                except (OSError, ValueError):
                    pass
        finally:
            if self.guard_fd is not None:
                os.close(self.guard_fd)
                self.guard_fd = None


def playwright_browser(root=None):
    root = Path(root or ROOT)
    python = root / '.venv' / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')
    if not python.is_file():
        raise Failure(26, 'launch', 'E_PLAYWRIGHT_MISSING')
    probe = ('from playwright.sync_api import sync_playwright; '
             'p=sync_playwright().start(); print(p.chromium.executable_path); p.stop()')
    try:
        result = subprocess.run([str(python), '-c', probe], stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, text=True, timeout=20, check=False, encoding="utf-8", errors="replace")
    except (OSError, subprocess.SubprocessError):
        raise Failure(26, 'launch', 'E_PLAYWRIGHT_MISSING')
    executable = result.stdout.strip() if result.returncode == 0 else ''
    if not executable or not Path(executable).is_file() or not os.access(executable, os.X_OK):
        raise Failure(26, 'launch', 'E_PLAYWRIGHT_MISSING')
    return {'name': 'playwright', 'path': executable, 'version': 'bundled'}


def detect_browsers(browser='auto'):
    if browser == 'playwright':
        return [playwright_browser()]
    candidates = []
    apps = [('chrome', 'Google Chrome', 'Google Chrome'), ('edge', 'Microsoft Edge', 'Microsoft Edge'), ('brave', 'Brave Browser', 'Brave Browser'), ('vivaldi', 'Vivaldi', 'Vivaldi'), ('chromium', 'Chromium', 'Chromium')]
    windows = [('chrome', 'Google/Chrome/Application/chrome.exe'), ('edge', 'Microsoft/Edge/Application/msedge.exe'), ('brave', 'BraveSoftware/Brave-Browser/Application/brave.exe'), ('vivaldi', 'Vivaldi/Application/vivaldi.exe'), ('chromium', 'Chromium/Application/chrome.exe')]
    for name, app, executable in apps:
        for base in [Path('/Applications'), Path.home() / 'Applications']:
            candidates.append((name, str(base / (app + '.app') / 'Contents/MacOS' / executable)))
    for variable in ['PROGRAMFILES', 'PROGRAMFILES(X86)', 'LOCALAPPDATA']:
        base = os.environ.get(variable)
        if base:
            candidates.extend((name, str(Path(base) / relative)) for name, relative in windows)
    for name, names in [('chrome', ['google-chrome', 'google-chrome-stable', 'chrome', 'chrome.exe']), ('edge', ['microsoft-edge', 'microsoft-edge-stable', 'msedge', 'msedge.exe']), ('brave', ['brave-browser', 'brave', 'brave.exe']), ('vivaldi', ['vivaldi', 'vivaldi-stable', 'vivaldi.exe']), ('chromium', ['chromium', 'chromium-browser'])]:
        for executable in names:
            found = shutil.which(executable)
            if found:
                candidates.append((name, found))
    result, seen = [], set()
    for name, path in candidates:
        if browser not in ('auto', name) or path in seen:
            continue
        if Path(path).is_file() and os.access(path, os.X_OK):
            seen.add(path)
            # Read macOS bundle metadata; never execute an app for its version.
            version = 'unknown'
            metadata = Path(path).parent.parent / 'Info.plist'
            try:
                with metadata.open('rb') as stream:
                    value = plistlib.load(stream).get('CFBundleShortVersionString')
                if isinstance(value, str) and len(value) <= 64 and all(c.isdigit() or c == '.' for c in value):
                    version = value
            except (OSError, ValueError, TypeError, AttributeError):
                pass
            result.append({'name': name, 'path': path, 'version': version})
    return result


def launch(path, profile, port, url):
    return subprocess.Popen([path, '--remote-debugging-address=127.0.0.1', '--remote-debugging-port=0', '--user-data-dir=' + str(profile), '--no-first-run', '--no-default-browser-check', url], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def remaining(deadline):
    value = deadline - time.monotonic()
    if value <= 0:
        raise TimeoutError()
    return value


def active_port(profile):
    path = profile / 'DevToolsActivePort'
    if path.is_symlink():
        raise ValueError()
    lines = path.read_text(encoding="utf-8").splitlines()
    if len(lines) != 2:
        raise ValueError()
    port = int(lines[0])
    if not 1 <= port <= 65535 or len(lines) < 2 or not lines[1].startswith('/devtools/browser/'):
        raise ValueError()
    return port


def cdp_json(port, path, deadline):
    # Raw loopback HTTP keeps every recv under the same absolute deadline.
    with socket.create_connection(('127.0.0.1', port), timeout=remaining(deadline)) as sock:
        sock.settimeout(remaining(deadline))
        sock.sendall(('GET %s HTTP/1.1\r\nHost: 127.0.0.1:%d\r\nConnection: close\r\n\r\n' % (path, port)).encode('ascii'))
        raw = b''
        split = None
        length = None
        while True:
            sock.settimeout(remaining(deadline))
            chunk = sock.recv(65536)
            if not chunk:
                break
            raw += chunk
            if len(raw) > MAX_MESSAGE + 16384:
                raise ValueError()
            if split is None and b'\r\n\r\n' in raw:
                head, _ = raw.split(b'\r\n\r\n', 1)
                split = len(head) + 4
                lines = head.decode('ascii').split('\r\n')
                if lines[0].split()[1] != '200':
                    raise ValueError()
                headers = dict(line.lower().split(':', 1) for line in lines[1:])
                if 'transfer-encoding' in headers:
                    raise ValueError()
                length = int(headers['content-length']) if 'content-length' in headers else None
                if length is not None and not 0 <= length <= MAX_MESSAGE:
                    raise ValueError()
            if split is not None and length is not None and len(raw) - split >= length:
                break
        if split is None or (length is not None and len(raw) - split != length) or len(raw) - split > MAX_MESSAGE:
            raise ValueError()
        return json.loads(raw[split:])


def version(port, deadline):
    data = cdp_json(port, '/json/version', deadline)
    u = parse.urlsplit(data['webSocketDebuggerUrl'])
    if u.scheme != 'ws' or u.hostname != '127.0.0.1' or u.port != port or not u.path.startswith('/devtools/browser/'):
        raise ValueError()


def wait_port(profile, proc, deadline):
    end = min(deadline, time.monotonic() + 10)
    while time.monotonic() < end:
        if proc.poll() is not None:
            raise Failure(22, 'launch')
        try:
            port = active_port(profile)
            version(port, end)
            return port
        except (OSError, ValueError, KeyError):
            time.sleep(min(.05, max(0, end - time.monotonic())))
    raise Failure(11, 'launch', 'E_CDP_UNAVAILABLE')


def process_identity(pid):
    if os.name == 'nt':
        command = '$p=Get-CimInstance Win32_Process -Filter \"ProcessId=' + str(int(pid)) + '\"; $p.CreationDate.ToString(\"o\"); $p.CommandLine'
        result = subprocess.run(['powershell', '-NoProfile', '-NonInteractive', '-Command', command], capture_output=True, text=True, timeout=1, encoding="utf-8", errors="replace")
        return result.stdout.strip() if result.returncode == 0 else ''
    result = subprocess.run(['ps', '-p', str(pid), '-o', 'lstart=', '-o', 'command='], capture_output=True, text=True, timeout=1, encoding="utf-8", errors="replace")
    return result.stdout.strip() if result.returncode == 0 else ''


def self_instance(profile, owner, deadline):
    try:
        port = active_port(profile)
        identity = process_identity(owner['pid'])
        if (not alive(owner['pid']) or port != owner['port'] or identity != owner['process_identity']
                or owner['exe'] not in identity or '--user-data-dir=' + str(profile) not in identity
                or not any(x in identity for x in ('--remote-debugging-port=0', '--remote-debugging-port=' + str(port)))):
            raise ValueError()
        version(port, deadline)
        return port
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError):
        raise Failure(11, 'launch', 'E_NO_SELF_INSTANCE')


def terminate_owner(owner, *, force=False):
    pid = owner['pid']
    if not alive(pid):
        return
    identity = process_identity(pid)
    if not identity and force:
        # No readable process identity: remove our signed profile, never signal
        # an unverified PID. A readable mismatch must still refuse below.
        return
    if identity != owner['process_identity']:
        raise Failure(11, 'launch', 'E_NO_SELF_INSTANCE@terminate_owner')
    import signal
    os.kill(pid, signal.SIGTERM)
    end = time.monotonic() + 2
    while alive(pid) and time.monotonic() < end:
        try:
            waited, _ = os.waitpid(pid, os.WNOHANG)
            if waited:
                return
        except ChildProcessError:
            pass
        time.sleep(.05)
    if alive(pid):
        raise Failure(14, 'launch')


def stop(proc):
    if proc.poll() is None:
        proc.terminate()
    try:
        proc.wait(timeout=1)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=1)


def list_pages(port, timeout=1):
    data = cdp_json(port, '/json/list', time.monotonic() + timeout)
    if not isinstance(data, list):
        raise ValueError()
    return data


class NoRedirect(request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        raise ValueError()


def profile_status(profile):
    if not profile.exists():
        return 'missing'
    if profile.is_symlink() or (profile / MARKER).is_symlink() or not profile.is_dir():
        return 'foreign'
    try:
        if read_owner(profile):
            return 'ours'
    except (Failure, OSError, ValueError, TypeError):
        return 'foreign'
    # Only connector metadata is opened; Chrome business files are never read.
    try:
        old = json.loads((profile / MARKER).read_text(encoding="utf-8"))
        if isinstance(old, dict) and old.get('owner') == MAGIC and 'signature' not in old:
            return 'legacy'
    except (OSError, ValueError, TypeError):
        pass
    return 'foreign'


def probe(browsers, allow, profile=None):
    can_launch = False
    if allow and browsers:
        try:
            with tempfile.TemporaryDirectory(prefix='laifaxin-browser-probe-') as temp:
                proc = launch(browsers[0]['path'], Path(temp), 0, 'about:blank')
                try:
                    wait_port(Path(temp), proc, time.monotonic() + 2.3)
                    can_launch = True
                finally:
                    stop(proc)
        except (OSError, ValueError, subprocess.SubprocessError, Failure):
            pass
    state = profile_status(profile) if profile else 'missing'
    owner = read_owner(profile) if profile and state == 'ours' else None
    can_connect = False
    if owner and alive(owner.get('pid')):
        try:
            can_connect = active_port(profile) == owner.get('port')
        except (OSError, ValueError):
            pass
    return dict(ok=True, code=0, stage='probe', host='', workspace='', can_auto=can_launch,
                profile_state=state, profile_path=str(profile) if profile else '',
                browsers=browsers, can_launch=can_launch, can_connect_self=can_connect,
                host_tool='unknown', recommend='auto' if can_launch else 'auto_unverified' if browsers else 'manual',
                detail='专用窗口试启动通过。' if can_launch else '检测到浏览器（未验证能否启动）。' if browsers else DETAIL[11])


class WebSocket:
    """Small RFC6455 client; accepts only this instance's loopback CDP URL."""
    def __init__(self, url, port, timeout=2, deadline=None):
        self.deadline = deadline if deadline is not None else time.monotonic() + timeout
        timeout = min(timeout, remaining(self.deadline))
        u = parse.urlsplit(url)
        if u.scheme != 'ws' or u.hostname != '127.0.0.1' or u.port != port or u.username or u.password or u.fragment:
            raise Failure(11, 'read', 'E_CDP_URL')
        self.sock = socket.create_connection(('127.0.0.1', port), timeout=timeout)
        self.buffer = b''
        try:
            key = base64.b64encode(secrets.token_bytes(16)).decode('ascii')
            target = u.path or '/'
            if u.query:
                target += '?' + u.query
            if any(c in target for c in '\r\n'):
                raise ValueError()
            self.sock.sendall(('GET %s HTTP/1.1\r\nHost: 127.0.0.1:%d\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Key: %s\r\nSec-WebSocket-Version: 13\r\n\r\n' % (target, port, key)).encode('ascii'))
            while b'\r\n\r\n' not in self.buffer:
                self.sock.settimeout(remaining(self.deadline))
                chunk = self.sock.recv(4096)
                if not chunk or len(self.buffer) > 16384:
                    raise ValueError()
                self.buffer += chunk
            header, self.buffer = self.buffer.split(b'\r\n\r\n', 1)
            lines = header.decode('ascii').split('\r\n')
            headers = {key.lower(): value for key, value in (line.split(':', 1) for line in lines[1:] if ':' in line)}
            expected = base64.b64encode(hashlib.sha1((key + '258EAFA5-E914-47DA-95CA-C5AB0DC85B11').encode()).digest()).decode()
            if lines[0].split()[1] != '101' or headers.get('sec-websocket-accept', '').strip() != expected or headers.get('upgrade', '').strip().lower() != 'websocket' or 'upgrade' not in headers.get('connection', '').lower():
                raise ValueError()
        except BaseException:
            self.sock.close()
            raise

    def close(self):
        self.sock.close()

    def exact(self, count):
        while len(self.buffer) < count:
            self.sock.settimeout(remaining(self.deadline))
            part = self.sock.recv(min(65536, count - len(self.buffer)))
            if not part:
                raise OSError()
            self.buffer += part
        value, self.buffer = self.buffer[:count], self.buffer[count:]
        return value

    def send(self, text, opcode=1):
        payload = text.encode('utf-8') if isinstance(text, str) else text
        if len(payload) > MAX_MESSAGE:
            raise ValueError()
        size = len(payload)
        header = bytes([0x80 | opcode, 0x80 | (size if size < 126 else (126 if size < 65536 else 127))])
        if size >= 126:
            header += struct.pack('!H' if size < 65536 else '!Q', size)
        mask = secrets.token_bytes(4)
        self.sock.settimeout(remaining(self.deadline))
        self.sock.sendall(header + mask + bytes(x ^ mask[i % 4] for i, x in enumerate(payload)))

    def recv(self):
        parts, started, size = [], False, 0
        deadline = self.deadline
        while time.monotonic() < deadline:
            self.sock.settimeout(max(0.01, deadline - time.monotonic()))
            first, second = self.exact(2)
            fin, opcode = bool(first & 128), first & 15
            if first & 0x70 or second & 128:
                raise ValueError()
            length = second & 127
            if length == 126:
                length = struct.unpack('!H', self.exact(2))[0]
            elif length == 127:
                length = struct.unpack('!Q', self.exact(8))[0]
            if length > MAX_MESSAGE or (opcode >= 8 and (not fin or length > 125)):
                raise ValueError()
            data = self.exact(length)
            if opcode == 8:
                if length == 1:
                    raise ValueError()
                raise Failure(22, 'read')
            if opcode == 9:
                self.send(data, 10)
                continue
            if opcode == 10:
                continue
            if opcode == 1 and not started:
                started = True
            elif opcode != 0 or not started:
                raise ValueError()
            size += length
            if size > MAX_MESSAGE:
                raise ValueError()
            parts.append(data)
            if fin:
                return b''.join(parts).decode('utf-8')
        raise OSError()


EXPRESSION = """(() => { const out=[]; const scan=(w)=>{try { if (!w.location.hostname.endsWith('.laifaxin.com')) return; out.push({host:w.location.hostname,accesstoken:w.localStorage.getItem('accesstoken')||w.sessionStorage.getItem('accesstoken'),orgId:w.localStorage.getItem('orgId')||w.sessionStorage.getItem('orgId')}); for(let i=0;i<w.frames.length;i++) scan(w.frames[i]); }catch(e){} }; scan(window); return out; })()"""


def read_page(page, port, deadline=None):
    host = parse.urlsplit(page.get('url', '')).hostname
    if page.get('type') not in ('page', 'iframe') or not allowed_host(host):
        return []
    ws = WebSocket(page.get('webSocketDebuggerUrl', ''), port, deadline=deadline)
    try:
        ws.send(json.dumps({'id': 1, 'method': 'Runtime.evaluate', 'params': {'expression': EXPRESSION, 'returnByValue': True}}))
        for _ in range(100):
            message = json.loads(ws.recv())
            if message.get('id') == 1:
                values = message.get('result', {}).get('result', {}).get('value', [])
                if not isinstance(values, list):
                    return []
                return [(v.get('host'), v.get('accesstoken'), v.get('orgId')) for v in values if isinstance(v, dict) and allowed_host(v.get('host'))]
        raise ValueError()
    finally:
        ws.close()


class Choice(tuple):
    """3 元组兼容 (host, token, org)，附加跨域回退留痕字段。"""

    def __new__(cls, host, token, org, host_source="entry", entry_host=""):
        self = super().__new__(cls, (host, token, org))
        self.host_source = host_source
        self.entry_host = entry_host
        self.token_host = host
        return self


def choose(values, entry_host=None):
    """入口域过滤优先；回退取另一域必须留痕，不得静默。

    - entry_host 有 token → host_source="entry"；
    - entry_host 无 token、回退另一域 → host_source="fallback"（附 entry_host/token_host）；
    - 未指定 entry_host 且两域 token 不同 → Failure(15)（fail-closed，不得静默选）。
    """
    found = []
    for host, token, org in values:
        if (allowed_host(host) and isinstance(token, str) and len(token) < 4096
                and len(token.split("&")) == 3 and all(token.split("&"))
                and not any(c in token for c in "\r\n")):
            found.append((host, token, org))
    if not found:
        return None
    if entry_host in ALLOWED_HOSTS:
        same = [v for v in found if v[0] == entry_host]
        if same:
            pool, source = same, "entry"
        else:
            pool = sorted(found, key=lambda v: (0 if v[0] == "web.laifaxin.com" else 1))
            source = "fallback"
    else:
        if len({v[1] for v in found}) > 1:
            raise Failure(15, "read")
        pool = sorted(found, key=lambda v: (0 if v[0] == "web.laifaxin.com" else 1))
        source = "default"
    if len({v[1] for v in pool}) > 1 or len({str(v[2]) for v in pool if v[2]}) > 1:
        raise Failure(15, "read")
    host, token, org = pool[0]
    if not isinstance(org, (str, int)) or not str(org).strip():
        raise Failure(13, "read")
    org = str(org)
    if len(org) > 1024 or any(c in org for c in "\r\n"):
        raise Failure(13, "read")
    return Choice(host, token, org, host_source=source,
                  entry_host=entry_host if entry_host in ALLOWED_HOSTS else "")


def fallback_org_check(root, token, org):
    """回退域凭据必须再过一次落点校验（workspace_guard），不过即失败。"""
    verify(root, token, org)

def wait_credentials(port, timeout, proc, deadline=None, owner=None, entry_host=None):
    end = deadline if deadline is not None else time.monotonic() + min(timeout, 90)
    connected, saw_page = False, False
    while time.monotonic() < end:
        if (proc is not None and proc.poll() is not None) or (owner and not alive(owner.get('pid'))):
            raise Failure(22, 'wait')
        values = []
        try:
            pages = list_pages(port, timeout=remaining(end))
            connected = True
        except (OSError, ValueError, KeyError, TypeError):
            pages = []
        for page in pages:
            if not isinstance(page, dict):
                continue
            try:
                if page.get('type') in ('page', 'iframe') and allowed_host(parse.urlsplit(page.get('url', '')).hostname):
                    saw_page = True
                values.extend(read_page(page, port, deadline=min(end, time.monotonic() + 2)))
            except Failure as exc:
                if exc.code == 22 and proc is not None and proc.poll() is not None:
                    raise
            except (OSError, ValueError, KeyError, TypeError):
                continue
        value = choose(values, entry_host=entry_host)
        if value:
            return value
        # 已看到来发信页面但还没登录：在预算内每 5 秒复查一次，直到 deadline。
        # 不因"复查过一次"就提前放弃——真人登录可能要几分钟（2026-10-21 真机首跑踩到）。
        interval = 5 if saw_page else 0.2
        if end - time.monotonic() < interval:
            break
        time.sleep(interval)
    if not connected and timeout > 0:
        raise Failure(11, 'wait', 'E_CDP_UNAVAILABLE')
    if saw_page:
        raise Failure(10, 'read', 'E_NO_TOKEN')
    raise Failure(10, 'wait')


def verify(root, token, org, *, classify_transient=False):
    credentials = 'accesstoken=' + token + '\norgId=' + org + '\n'
    for tool, flags in [('check_login.py', []), ('workspace_guard.py', ['--require-verified'])]:
        try:
            env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUTF8="1")
            result = subprocess.run([sys.executable, str(root / 'tools' / tool), '--credentials-stdin', '--gate-mode'] + flags, input=credentials, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, cwd=str(root), timeout=180, encoding="utf-8", errors="replace", env=env)
        except (OSError, subprocess.SubprocessError):
            raise Failure(23, 'verify')
        if isinstance(result.stderr, str) and 'Traceback' in result.stderr:
            raise Failure(23, 'verify', 'E_TOOL_CRASH', tool=tool, child_code=result.returncode)
        code = result.returncode
        if not code:
            continue
        if tool == 'check_login.py':
            if classify_transient and code == 3:
                raise Failure(23, 'verify', 'E_VERIFY_TRANSIENT')
            raise Failure(24 if code == 2 else 12 if code in (1, 3) else 23, 'verify')
        if classify_transient and code == 3:
            raise Failure(23, 'verify', 'E_VERIFY_TRANSIENT')
        raise Failure({1: 15, 2: 24, 3: 12, 4: 25, 5: 25}.get(code, 23), 'verify', tool=tool, child_code=code)


# Compatibility exports; persistence and strict reads live in session_store.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from session_store import SessionError, forget_session, load_ready, save_session, session_path


class Parser(argparse.ArgumentParser):
    def error(self, message):
        raise Failure(20, 'probe')

    def format_help(self):
        # --help 是唯一允许的非 JSON stdout：只列参数名与用法，不含任何凭据。
        return super().format_help()


def admit_credentials(root, choice, *, accept_fallback=False):
    """取参后准入：回退来源必须先由用户确认，再做 workspace_guard 兜底。"""
    host, token, org = choice
    source = getattr(choice, "host_source", "entry")
    if source == "fallback":
        if not accept_fallback:
            # 回退可能取到同一浏览器里其它账号的凭据：停住，等用户显式确认。
            parts = token.split("&")
            uid = parts[1] if len(parts) == 3 else ""
            raise Failure(27, "read",
                          host_source="fallback",
                          entry_host=getattr(choice, "entry_host", ""),
                          token_host=getattr(choice, "token_host", host),
                          uid=uid, org=str(org))
        fallback_org_check(root, token, org)
    else:
        verify(root, token, org)
    return {"host": host, "token": token, "org": org,
            "token_host": getattr(choice, "token_host", host),
            "host_source": source,
            "entry_host": getattr(choice, "entry_host", "")}

def execute(argv):
    parser = Parser(add_help=True)
    parser.add_argument('--login-url', default='https://web.laifaxin.com')
    parser.add_argument('--timeout', default=180, type=float)
    parser.add_argument('--profile-dir', default='.local/browser-profile')
    parser.add_argument('--browser', choices=['auto', 'chrome', 'edge', 'none', 'playwright'], default='auto')
    parser.add_argument('--confirm-profile')
    for flag in ['probe-only', 'no-launch', 'allow-launch-probe', 'clean', 'force-legacy', 'force', 'resume', 'keep-open', 'save-session', 'from-session', 'forget', 'accept-fallback-host']:
        parser.add_argument('--' + flag, action='store_true')
    args = parser.parse_args(argv)
    args.no_launch = args.no_launch or args.resume
    if args.forget:
        forget_session(ROOT)
        return 0, {'stage': 'verify', 'forgotten': True}
    if args.from_session:
        host, _, _ = load_ready(ROOT)
        return 0, {'stage': 'verify', 'source': 'session', 'host': host,
                   'workspace': 'verified', 'can_auto': True}
    host = validate_url(args.login_url)
    if not 0 < args.timeout <= 180 or (args.allow_launch_probe and not args.probe_only) or (args.clean and args.probe_only):
        raise Failure(20, 'probe')
    # Probe reports directory state without opening legacy data or creating files.
    candidate = Path(args.profile_dir)
    profile = candidate.absolute() if candidate.is_absolute() else (ROOT / candidate).absolute()
    state = profile_status(profile)
    if not args.probe_only and state == 'legacy':
        entries = list(profile.iterdir())
        if all(p.name == MARKER and p.is_file() and not p.is_symlink() for p in entries):
            # An empty legacy probe marker carries no browser data.
            local = ROOT.resolve() / '.local'
            if (not profile.resolve().is_relative_to(local) or profile.resolve() == local
                    or any(p.is_symlink() for p in (profile,) + tuple(profile.parents) if p == ROOT or ROOT in p.parents)):
                raise Failure(21, 'launch')
            (profile / MARKER).unlink()
            profile.rmdir()
            state = 'missing'
        elif not (args.clean and args.force_legacy):
            return 21, {'stage': 'launch', 'detail': '旧目录含浏览器文件；确认清理请用 --clean --force-legacy --confirm-profile ' + str(profile.resolve())}
    legacy_clean = args.clean and args.force_legacy and state == 'legacy'
    if not args.probe_only and not legacy_clean:
        profile = safe_profile(ROOT, args.profile_dir, create=False)
    browsers = detect_browsers(args.browser)
    if args.probe_only:
        value = probe(browsers, args.allow_launch_probe and not args.no_launch, profile)
        return 0, value
    if args.clean:
        if legacy_clean:
            # Validate the lexical boundary without reading any legacy marker or data.
            local = ROOT.resolve() / '.local'
            if (not profile.resolve().is_relative_to(local) or profile.resolve() == local
                    or any(p.is_symlink() for p in (profile,) + tuple(profile.parents) if p == ROOT or ROOT in p.parents)):
                raise Failure(21, 'launch')
            if args.confirm_profile != str(profile.resolve()):
                return 21, {'stage': 'launch', 'detail': '将清理旧专用目录：' + str(profile.resolve()) + '；确认后加 --confirm-profile 与此绝对路径。'}
            with ProfileLock(profile):
                shutil.rmtree(profile)
            return 0, {'stage': 'launch', 'detail': '旧专用目录已按显式确认清理。'}
        if not profile.exists():
            return 0, {'stage': 'launch', 'detail': '专用目录与锁已清理。'}
        if not read_owner(profile):
            raise Failure(21, 'launch')
        owner = read_owner(profile)
        if alive(owner.get('pid')) and not args.force:
            raise Failure(14, 'launch')
        if alive(owner.get('pid')) and not args.force:
            self_instance(profile, owner, time.monotonic() + 3)
        with ProfileLock(profile, owner if args.force else None):
            if alive(owner.get('pid')):
                terminate_owner(owner, force=args.force)
            shutil.rmtree(profile)
        return 0, {'stage': 'launch', 'detail': '专用目录与锁已清理。'}
    if not args.no_launch and not browsers:
        raise Failure(11, 'probe', 'E_NO_BROWSER')
    profile = safe_profile(ROOT, profile)
    proc = None
    deadline = time.monotonic() + min(args.timeout, 90)
    owner = read_owner(profile)
    if args.no_launch:
        self_instance(profile, owner, deadline)
    keep = False
    with ProfileLock(profile, owner if args.no_launch else None) as lock:
        try:
            if args.no_launch:
                port = self_instance(profile, owner, deadline)
            else:
                if alive(owner.get('pid')):
                    raise Failure(14, 'launch')
                (profile / 'DevToolsActivePort').unlink(missing_ok=True)
                try:
                    proc = launch(browsers[0]['path'], profile, 0, args.login_url)
                except OSError:
                    raise Failure(11, 'launch', 'E_LAUNCH')
                # Every operation after Popen is covered by this finally.
                port = wait_port(profile, proc, deadline)
                save_owner(profile, {'pid': proc.pid, 'port': port, 'exe': browsers[0]['path'],
                                     'process_identity': process_identity(proc.pid)})
            entry_host = parse.urlsplit(args.login_url).hostname
            choice = wait_credentials(port, args.timeout, proc,
                                      deadline=deadline,
                                      owner=owner if args.no_launch else None,
                                      entry_host=entry_host)
            pre_saved = False
            if args.save_session and getattr(choice, 'host_source', 'entry') != 'fallback':
                try:
                    save_session(ROOT, choice[0], choice[1], str(choice[2]))
                    pre_saved = True
                except (OSError, Failure, SessionError):
                    pass
            admitted = admit_credentials(ROOT, choice,
                                          accept_fallback=args.accept_fallback_host)
            host, token, org = admitted['host'], admitted['token'], admitted['org']
            result = {'stage': 'verify', 'host': host, 'workspace': 'verified', 'can_auto': True,
                      'token_host': admitted['token_host'],
                      'host_source': admitted['host_source'],
                      'entry_host': admitted['entry_host']}
            if args.save_session:
                try:
                    if not pre_saved:
                        save_session(ROOT, host, token, org)
                    result['session_saved'] = True
                except (OSError, Failure, SessionError):
                    # 绝不回显凭证：只报保存成败。
                    result['session_saved'] = False
                    result['detail'] = '凭证保存失败。'
            if args.keep_open:
                # 锁必须由仍然存活的浏览器持有，不能绑定即将退出的 Python。
                current = read_owner(profile)
                (profile / '.lock').write_text(json.dumps({
                    'pid': current['pid'], 'time': time.time(), 'identity': current['nonce']}), encoding="utf-8")
                keep = True
                lock.preserve = True
                result['kept_open'] = True
                result['detail'] = '窗口保持打开，未清理专用目录；收尾请用 --clean --force。'
            return 0, result
        except Failure as exc:
            if exc.code == 10:
                keep = True
                current = read_owner(profile)
                (profile / '.lock').write_text(json.dumps({'pid': current['pid'], 'time': time.time(), 'identity': current['nonce']}), encoding="utf-8")
                lock.preserve = True
            raise
        finally:
            if args.no_launch and not keep:
                terminate_owner(owner)
                shutil.rmtree(profile)
            if proc is not None and not keep:
                stop(proc)
                # Only the directory validated and locked before this Popen is owned.
                # Chromium writes real-profile files; remove our ephemeral profile now.
                shutil.rmtree(profile)



def main(argv=None):
    try:
        code, fields = execute(argv)
    except SessionError as exc:
        code, fields = 12, {'stage': 'verify', 'detail': exc.detail}
        print(exc.diagnostic, file=sys.stderr)
    except Failure as exc:
        code, fields = exc.code, {'stage': exc.stage}
        fields.update(getattr(exc, 'fields', {}) or {})
        diagnostic = exc.diagnostic
        if exc.code in (11, 14, 20, 21, 26):
            diagnostic = 'E_BROWSER_UNSUPPORTED ' + diagnostic
        print(diagnostic, file=sys.stderr)
    except (Exception, KeyboardInterrupt):
        code, fields = 23, {'stage': 'verify'}
        print('E_SUBPROCESS', file=sys.stderr)
    if 'browsers' in fields:
        output = fields
    else:
        output = {'ok': code == 0, 'code': code, 'stage': 'verify', 'host': '', 'workspace': '', 'can_auto': False, 'detail': DETAIL[code]}
        output.update(fields)
    print(json.dumps(output, ensure_ascii=False))
    return code


if __name__ == '__main__':
    sys.exit(main())
