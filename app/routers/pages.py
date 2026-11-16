"""页面路由（服务端渲染，非前后端分离）。"""
from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse

from app import storage
from app.config import settings
from app.deps import current_user, params
from app.models import Config, Link, Tabbar
from app.response import ok
from app.routers.searchengine import engines_for
from app.services import site
from app.services.seed import ensure_user_data
from app.services.userdata import (
    get_doc,
    global_default_config,
    global_default_links,
    global_default_tabbar,
)
from app.templating import render

router = APIRouter()


def home_context(request: Request) -> dict:
    db = request.state.db
    user = current_user(request, db)
    if user is not None:
        ensure_user_data(db, user.id)  # 新用户首访落一份个人副本，之后可自由改

    links = get_doc(db, Link, user.id) if user else global_default_links(db)
    config = get_doc(db, Config, user.id) if user else global_default_config(db)
    tabbar = get_doc(db, Tabbar, user.id) if user else global_default_tabbar(db)

    engines = engines_for(db, user)

    return {
        "user": user,
        "links": links,
        "config": config,
        "tabbar": tabbar,
        "engines": engines,
        "lunar": lunar_today(),
    }


def lunar_today() -> str:
    """当日农历（月日在前 + 干支年生肖在后），由 lunar_python 计算；跨天自动更新。"""
    from datetime import date

    from lunar_python import Solar

    now = date.today()
    lunar = Solar.fromYmdHms(now.year, now.month, now.day, 0, 0, 0).getLunar()
    return f"{lunar.getMonthInChinese()}月{lunar.getDayInChinese()} {lunar.getYearInGanZhi()}{lunar.getYearShengXiao()}年"


def _page_groups(links: list[dict], config: dict | None = None) -> list[str]:
    seen: list[str] = []
    # 显式创建的分类（config.pageGroups）即使还没有标签也要保留
    for group in (config or {}).get("pageGroups") or []:
        if isinstance(group, str) and group and group not in seen:
            seen.append(group)
    for item in sorted(links, key=lambda i: i.get("sort", 0)):
        group = item.get("pageGroup") or ""
        if group and group not in seen:
            seen.append(group)
    return seen


@router.get("/")
async def home(request: Request):
    ctx = home_context(request)
    links = ctx["links"] if isinstance(ctx["links"], list) else []
    ctx["links"] = [i for i in links if isinstance(i, dict)]
    ctx["page_groups"] = _page_groups(ctx["links"], ctx["config"])
    return render(request, "home.html", **ctx)


@router.get("/guest")
async def guest_home(request: Request):
    """管理员编辑未登录主页（标签 / 分类 / 底栏 / 外观）：改动只在页面内，点「保存」才写库。"""
    db = request.state.db
    user = current_user(request, db)
    if user is None:
        return RedirectResponse("/", status_code=302)
    if user.manager != 1:
        return RedirectResponse("/", status_code=302)
    links = [i for i in global_default_links(db) if isinstance(i, dict)]
    config = global_default_config(db)
    return render(
        request,
        "home.html",
        user=user,
        links=links,
        config=config,
        tabbar=global_default_tabbar(db),
        engines=engines_for(db, user),
        page_groups=_page_groups(links, config),
        guest_edit=True,
        lunar=lunar_today(),
    )


@router.get("/noteApp")
async def note_page(request: Request):
    """原项目 Index::noteApp 的页面（笔记应用）。"""
    user = current_user(request, request.state.db)
    return render(request, "notes.html", user=user)


@router.get("/manager")
async def manager_page(request: Request):
    """原项目 /manager 的管理后台页面（原来是 Vue SPA，这里用 Jinja2 重写）。"""
    db = request.state.db
    user = current_user(request, db)
    if user is None:
        return RedirectResponse("/", status_code=302)
    if user.manager != 1:
        return RedirectResponse("/", status_code=302)
    cfg = get_doc(db, Config, user.id) or {}
    theme = (cfg.get("theme") if isinstance(cfg, dict) else None) or {}
    return render(
        request,
        "admin.html",
        user=user,
        color_scheme=theme.get("colorScheme") if theme.get("colorScheme") in ("light", "dark") else None,
        user_json={
            "id": user.id,
            "mail": user.mail,
            "nickname": user.nickname,
            "avatar": user.avatar,
            "manager": user.manager,
        },
    )


@router.get("/privacy")
async def privacy_page(request: Request):
    """原项目 Index::privacy 的页面。"""
    db = request.state.db
    meta = site.page_meta(db)
    return render(request, "privacy.html", content=meta.get("privacy") or "", user=current_user(request, db))


@router.get("/favicon")
async def favicon(request: Request):
    """原项目 Index::favicon：自定义图标存在则返回，否则跳默认图标。"""
    db = request.state.db
    try:
        meta = site.page_meta(db)
    except Exception:  # shortcut: 安装前无 setting 表，直接给默认图标
        meta = dict(site.DEFAULTS)
    for key in ("favicon", "logo"):
        local = storage.local_path(meta.get(key) or "")
        if local and local.is_file():
            return FileResponse(local, headers={"Cache-Control": "public, max-age=86400"})
    return RedirectResponse("/static/wtab.png", status_code=302)


@router.post("/index/all")
async def index_all(request: Request):
    """原项目 Index::all：只返回 ids 里没请求过的模块（原项目还有 card，本项目已丢弃）。"""
    ctx = home_context(request)
    payload = {
        "link": ctx["links"],
        "tabbar": ctx["tabbar"],
        "config": ctx["config"],
        "site": site.page_meta(request.state.db),
    }
    body = await params(request)
    ids = body.get("ids") or []
    if isinstance(ids, str):
        ids = [ids]
    return ok({k: v for k, v in payload.items() if k not in ids}, "ok")
