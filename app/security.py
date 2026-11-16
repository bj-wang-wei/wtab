"""认证相关的纯函数与内存态（邮件验证码、登录锁定、token 生成）。

shortcut: 验证码与登录锁定放在进程内存，多 worker 或重启即失效；如需横向扩展改为 Redis/DB
"""
from __future__ import annotations

import hashlib
import re
import secrets
import time

EMAIL_RE = re.compile(r"^[\w.+-]+@[\w-]+\.[\w.-]+$")

_CODE_TTL = 300  # 与原项目一致：验证码 5 分钟有效
_LOCK_TTL = 7200  # 连续 10 次失败锁定 2 小时

_codes: dict[str, tuple[str, float]] = {}
_locked: dict[str, float] = {}


def md5(raw: str) -> str:
    """原项目用 md5(明文) 存密码（env.php / install.php），为兼容既有数据库继续沿用。"""
    return hashlib.md5(raw.encode("utf-8")).hexdigest()


def valid_email(mail: str) -> bool:
    return bool(EMAIL_RE.match(mail or ""))


def new_token(user_id: int) -> str:
    return hashlib.md5(f"{user_id}|{time.time()}|{secrets.token_hex(8)}".encode()).hexdigest()


def gen_code() -> str:
    return str(secrets.randbelow(900000) + 100000)


def save_code(mail: str, code: str) -> None:
    _codes[mail] = (code, time.monotonic() + _CODE_TTL)


def check_code(mail: str, code: str) -> bool:
    item = _codes.get(mail)
    if not item:
        return False
    stored, expire_at = item
    if time.monotonic() > expire_at:
        _codes.pop(mail, None)
        return False
    return stored == code


def consume_code(mail: str) -> None:
    _codes.pop(mail, None)


def lock_account(mail: str) -> None:
    _locked[mail] = time.monotonic() + _LOCK_TTL


def unlock_account(mail: str) -> None:
    _locked.pop(mail, None)


def is_locked(mail: str) -> bool:
    until = _locked.get(mail)
    if until is None:
        return False
    if time.monotonic() > until:
        _locked.pop(mail, None)
        return False
    return True
