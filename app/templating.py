"""Jinja2 环境与通用渲染上下文。"""
from __future__ import annotations

from typing import Any

from fastapi import Request
from fastapi.templating import Jinja2Templates

from app.config import STATIC_DIR, TEMPLATE_DIR, settings
from app.services import site

templates = Jinja2Templates(directory=str(TEMPLATE_DIR))


def _page_meta(request: Request) -> dict[str, Any]:
    """站点设置注入页面 head。安装前或库不可用时退回默认值。"""
    db = getattr(request.state, "db", None)
    if db is None:
        return dict(site.DEFAULTS) | {"favicon_url": "/favicon.ico"}
    try:
        return site.page_meta(db)
    except Exception:  # shortcut: 安装前 setting 表还不存在，退回默认值即可
        return dict(site.DEFAULTS) | {"favicon_url": "/favicon.ico"}


def render(request: Request, name: str, **ctx: Any):
    meta = _page_meta(request)
    base = {
        "request": request,
        "app_name": settings.app_name,
        "app_version": settings.app_version,
        "app_version_code": settings.app_version_code,
        "appVersion": meta.get("appVersion") or settings.app_version,
        "appDesc": meta.get("appDesc") or site.DEFAULTS.get("appDesc", ""),
        "static_prefix": "/static",
        "demo_mode": settings.demo_mode,
        "meta": meta,
    }
    base.update(ctx)
    return templates.TemplateResponse(request, name, base)


__all__ = ["templates", "render", "STATIC_DIR"]
