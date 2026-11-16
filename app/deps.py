"""请求依赖：客户端 IP、当前用户、权限校验。

登录态优先取签名 Session Cookie；同时兼容原项目的 user_id + token 双值（浏览器扩展在用）。
"""
from __future__ import annotations

import time

from fastapi import Request
from sqlalchemy.orm import Session

from app.config import settings
from app.models import Token, User


class AuthError(Exception):
    """需要登录 / 权限不足，由 main.py 的统一异常处理器转成 {code:0,msg}。"""


async def params(request: Request) -> dict:
    """兼容 JSON 与表单两种提交方式（原项目前端全部走 JSON）。"""
    ctype = request.headers.get("content-type", "")
    if "application/json" in ctype:
        try:
            data = await request.json()
            return data if isinstance(data, dict) else {}
        except ValueError:
            return {}
    form = await request.form()
    return dict(form)


def client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else ""


def _by_token(request: Request, db: Session) -> User | None:
    user_id = request.headers.get("userid") or request.cookies.get("user_id")
    token = request.headers.get("token") or request.cookies.get("token")
    if not user_id or not token:
        return None
    row = db.query(Token).filter(Token.user_id == user_id, Token.token == token).first()
    if not row:
        return None
    if row.create_time and time.time() - int(row.create_time) > settings.session_max_age:
        return None
    return db.get(User, int(user_id))


def current_user(request: Request, db: Session) -> User | None:
    user = None
    user_id = request.session.get("user_id")
    if user_id:
        user = db.get(User, int(user_id))
    if user is None:
        user = _by_token(request, db)
    if user is None or user.status == 1:
        return None
    return user


def require_user(request: Request, db: Session) -> User:
    user = current_user(request, db)
    if user is None:
        raise AuthError("请先登录")
    return user


def require_admin(request: Request, db: Session) -> User:
    user = require_user(request, db)
    if user.manager != 1:
        raise AuthError("无权限")
    return user


def demo_guard() -> None:
    """等价原项目 is_demo_mode(true)：演示站点禁止写操作。"""
    if settings.demo_mode:
        raise AuthError("演示模式，禁止操作")
