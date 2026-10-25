"""Local session persistence. Digests detect accidental damage, not hostile edits.

Unsalted hashes are recomputable by anyone on this machine; remote login and
workspace verification are the actual authorization boundary.
"""
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import json
import os
from pathlib import Path
import secrets
import stat
import time

ROOT = Path(__file__).resolve().parents[1]
NAME = 'session-credential.json'
_FIELDS = ('host', 'org_id', 'access_token', 'saved_at')
_verified = {}
_VERIFY_TTL = 60.0  # 秒：超过则重新做一次远端校验，避免进程内缓存放行已失效凭证


class SessionError(Exception):
    def __init__(self, diagnostic, detail, *, discard=False):
        self.diagnostic, self.detail, self.discard = diagnostic, detail, discard
        super().__init__(diagnostic)


def _stale():
    return SessionError('E_STALE_SESSION', '本机会话无效，请重新登录保存。', discard=True)


def _corrupt():
    return SessionError('E_SESSION_CORRUPT', '本机会话文件损坏，请重新登录保存。', discard=True)


def _transient():
    return SessionError('E_VERIFY_TRANSIENT', '校验暂时失败，凭证已保留，可稍后重试。')


@contextmanager
def _directory(root, create=False):
    """Anchor every operation to opened root/.local descriptors, never a symlink."""
    root_fd = os.open(str(Path(root)), os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    local_fd = None
    try:
        if create:
            try:
                os.mkdir('.local', mode=0o700, dir_fd=root_fd)
            except FileExistsError:
                pass
        local_fd = os.open('.local', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                           dir_fd=root_fd)
        if create:
            os.fchmod(local_fd, 0o700)
        elif stat.S_IMODE(os.fstat(local_fd).st_mode) != 0o700:
            raise _stale()
        yield local_fd
    finally:
        if local_fd is not None:
            os.close(local_fd)
        os.close(root_fd)


def session_path(root):
    return Path(root) / '.local' / NAME


def _bound_digest(data):
    # Early failure for accidental corruption only; not tamper protection.
    encoded = json.dumps({k: data[k] for k in _FIELDS}, sort_keys=True,
                         separators=(',', ':'), ensure_ascii=False).encode()
    return hashlib.sha256(encoded).hexdigest()


def _validate(data):
    if not isinstance(data, dict) or any(
            not isinstance(data.get(k), str) or not data[k].strip() for k in _FIELDS + ('sha256',)):
        raise _corrupt()
    if 'credential_sha256' not in data:
        raise SessionError('E_SESSION_LEGACY', '旧版会话格式，请重新登录保存一次。', discard=True)
    if data['host'] not in ('app.laifaxin.com', 'web.laifaxin.com'):
        raise _stale()
    if any('\n' in data[k] or '\r' in data[k] for k in ('access_token', 'org_id')):
        raise _stale()
    try:
        saved = datetime.fromisoformat(data['saved_at'].replace('Z', '+00:00'))
        if saved.tzinfo is None:
            raise ValueError()
        age = datetime.now(timezone.utc) - saved
        if age < timedelta(0) or age > timedelta(days=7):
            raise ValueError()
    except (ValueError, TypeError, OverflowError):
        raise _stale() from None
    try:
        valid = (hmac.compare_digest(data['sha256'], hashlib.sha256(data['access_token'].encode()).hexdigest())
                 and isinstance(data['credential_sha256'], str)
                 and hmac.compare_digest(data['credential_sha256'], _bound_digest(data)))
    except (TypeError, ValueError):
        valid = False
    if not valid:
        raise _stale()
    return data['host'], data['access_token'], data['org_id']


def _save_session_windows(root, host, token, org):
    data = dict(host=host, access_token=token, org_id=org,
                saved_at=datetime.now(timezone.utc).isoformat(),
                sha256=hashlib.sha256(token.encode()).hexdigest())
    data['credential_sha256'] = _bound_digest(data)
    _validate(data)
    local = Path(root) / '.local'
    try:
        local.mkdir(mode=0o700, exist_ok=True)
        os.chmod(local, 0o700)
    except OSError:
        pass
    target = local / NAME
    temporary = local / ('.' + NAME + '.' + secrets.token_hex(16) + '.tmp')
    fd = None
    try:
        fd = os.open(str(temporary), os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, 'O_BINARY', 0), 0o600)
        stream = os.fdopen(fd, 'w', encoding='utf-8')
        fd = None
        with stream:
            json.dump(data, stream, ensure_ascii=False)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(str(temporary), str(target))
        try: os.chmod(target, 0o600)
        except OSError: pass
        _verified.clear()
    except (OSError, ValueError, TypeError):
        raise SessionError('E_SESSION_SAVE', '保存失败。') from None
    finally:
        if fd is not None:
            os.close(fd)
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def _read_session_windows(root):
    target = Path(root) / '.local' / NAME
    try:
        info = target.stat()
        if not stat.S_ISREG(info.st_mode) or info.st_size > 16384:
            raise _stale()
        with target.open('r', encoding='utf-8') as stream:
            data = json.load(stream)
        return _validate(data)
    except FileNotFoundError:
        raise SessionError('E_NO_SESSION', '未找到本机会话，请先登录保存。') from None
    except (ValueError, UnicodeError, TypeError):
        raise _corrupt() from None
    except OSError:
        raise _transient() from None


def save_session(root, host, token, org):
    if os.name == 'nt':
        return _save_session_windows(root, host, token, org)
    data = dict(host=host, access_token=token, org_id=org,
                saved_at=datetime.now(timezone.utc).isoformat(),
                sha256=hashlib.sha256(token.encode()).hexdigest())
    data['credential_sha256'] = _bound_digest(data)
    _validate(data)
    try:
        with _directory(root, create=True) as directory:
            temporary = '.' + NAME + '.' + secrets.token_hex(16) + '.tmp'
            fd = None
            try:
                fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                             0o600, dir_fd=directory)
                stream = os.fdopen(fd, 'w', encoding='utf-8')
                fd = None  # stream owns the descriptor from here.
                with stream:
                    json.dump(data, stream, ensure_ascii=False)
                    stream.flush()
                    os.fsync(stream.fileno())
                os.replace(temporary, NAME, src_dir_fd=directory, dst_dir_fd=directory)
                _verified.clear()
            finally:
                if fd is not None:
                    os.close(fd)
                try:
                    os.unlink(temporary, dir_fd=directory)
                except FileNotFoundError:
                    pass
    except (OSError, ValueError, TypeError):
        raise SessionError('E_SESSION_SAVE', '保存失败。') from None


def _read_session(root):
    if os.name == 'nt':
        return _read_session_windows(root)
    try:
        with _directory(root) as directory:
            descriptor = os.open(NAME, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                                 dir_fd=directory)
            with os.fdopen(descriptor, 'r', encoding='utf-8') as stream:
                info = os.fstat(stream.fileno())
                if not stat.S_ISREG(info.st_mode) or stat.S_IMODE(info.st_mode) != 0o600:
                    raise _stale()
                if info.st_size > 16384:
                    raise _stale()
                data = json.load(stream)
        return _validate(data)
    except FileNotFoundError:
        raise SessionError('E_NO_SESSION', '未找到本机会话，请先登录保存。') from None
    except (ValueError, UnicodeError, TypeError):
        raise _corrupt() from None
    except OSError:
        raise _transient() from None


def load_verified(root):
    """Strict local validation; discard corrupt/legacy/stale files at this boundary."""
    try:
        return _read_session(root)
    except SessionError as exc:
        if exc.discard:
            forget_session(root)
        raise


def forget_session(root):
    if os.name == 'nt':
        try:
            (Path(root) / '.local' / NAME).unlink()
        except FileNotFoundError:
            pass
        except OSError:
            raise SessionError('E_SESSION_DELETE', '会话清除失败，请稍后重试。') from None
        _verified.clear()
        return
    try:
        with _directory(root, create=True) as directory:
            try:
                os.unlink(NAME, dir_fd=directory)
            except FileNotFoundError:
                pass
        _verified.clear()
    except OSError:
        raise SessionError('E_SESSION_DELETE', '会话清除失败，请稍后重试。') from None


def verify_remote(root, token, org):
    """Reuse browser_login's two stdin gates, retaining transient failures.

    root is threaded through so an alternate checkout or temp root verifies
    against its own gates instead of the module-level ROOT.
    """
    from browser_login import Failure, verify
    try:
        verify(Path(root), token, org, classify_transient=True)
    except Failure as exc:
        if exc.code in (12, 15, 24):
            raise _stale() from None
        raise _transient() from None


def load_ready(root):
    try:
        host, token, org = load_verified(root)
        # Bind cache to the full credential identity and root; never reuse it after
        # an org change, and always re-read age/structure before consulting cache.
        key = (str(Path(root).resolve()), hashlib.sha256(
            json.dumps([host, token, org], separators=(',', ':')).encode()).digest())
        now = time.monotonic()
        verified_at = _verified.get(key)
        if verified_at is None or now - verified_at > _VERIFY_TTL:
            verify_remote(root, token, org)
            _verified[key] = time.monotonic()
        return host, token, org
    except SessionError as exc:
        if exc.discard:
            forget_session(root)
        raise
