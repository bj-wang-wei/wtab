"""书签数据接口，契约对齐原项目 app/controller/Link.php。"""
from __future__ import annotations

from fastapi import APIRouter, Request
from sqlalchemy import delete, select

from app.deps import current_user, params, require_admin, require_user
from app.models import History, Link, LinkClick, now
from app.response import fail, ok
from app.services.userdata import default_section, get_doc, reset_user

router = APIRouter(prefix="/link")

HISTORY_KEEP = 50  # 原项目只保留最近 50 条备份


def _db(request: Request):
    return request.state.db


def _fmt(dt) -> str | None:
    return dt.strftime("%Y-%m-%d %H:%M:%S") if dt else None


@router.post("/get")
async def link_get(request: Request):
    db = _db(request)
    user = current_user(request, db)
    if user is None:
        return ok(default_section("link"), "ok")
    return ok(get_doc(db, Link, user.id), "ok")


@router.post("/click")
async def link_click(request: Request):
    """首页点书签时计数，供后台热度榜使用；游客也计，不记用户。"""
    db = _db(request)
    data = await params(request)
    url = str(data.get("url") or "").strip()[:512]
    if not url:
        return fail("缺少 url")
    name = str(data.get("name") or "").strip()[:255]
    row = db.get(LinkClick, url)
    if row is None:
        row = LinkClick(url=url, name=name, count=0)
        db.add(row)
    if name:
        row.name = name
    row.count = (row.count or 0) + 1
    row.last_time = now()
    db.commit()
    return ok(None, "ok")


@router.post("/update")
async def link_update(request: Request):
    db = _db(request)
    user = require_user(request, db)
    data = await params(request)
    link = data.get("link")
    if not isinstance(link, list):
        return fail("保存失败")

    row = db.scalar(select(Link).where(Link.user_id == user.id))
    if row is None:
        db.add(Link(user_id=user.id, link=__import__("json").dumps(link, ensure_ascii=False), update_time=now()))
    else:
        # 覆盖前先备份，用户误操作可回滚
        db.add(History(user_id=user.id, link=row.link, create_time=now()))
        row.link = __import__("json").dumps(link, ensure_ascii=False)
        row.update_time = now()
    db.commit()

    keep = [h.id for h in db.scalars(select(History).where(History.user_id == user.id).order_by(History.id.desc()).limit(HISTORY_KEEP))]
    if keep:
        db.execute(delete(History).where(History.user_id == user.id, History.id.not_in(keep)))
        db.commit()
    return ok(None, "ok")


@router.post("/history")
async def link_history(request: Request):
    db = _db(request)
    user = require_user(request, db)
    rows = db.scalars(
        select(History).where(History.user_id == user.id, History.create_time.is_not(None)).order_by(History.id.desc()).limit(100)
    )
    return ok([{"id": h.id, "user_id": h.user_id, "create_time": _fmt(h.create_time)} for h in rows], "ok")


@router.post("/delBack")
async def link_del_back(request: Request):
    db = _db(request)
    user = require_user(request, db)
    hid = (await params(request)).get("id")
    if hid:
        result = db.execute(delete(History).where(History.id == int(hid), History.user_id == user.id))
        db.commit()
        if result.rowcount:
            return ok(None, "ok")
    return fail("备份节点不存在")


@router.post("/rollBack")
async def link_roll_back(request: Request):
    db = _db(request)
    user = require_user(request, db)
    hid = (await params(request)).get("id")
    if hid:
        backup = db.scalar(select(History).where(History.id == int(hid), History.user_id == user.id))
        if backup:
            row = db.scalar(select(Link).where(Link.user_id == user.id))
            if row is None:
                db.add(Link(user_id=user.id, link=backup.link, update_time=now()))
            else:
                row.link = backup.link
                row.update_time = now()
            db.commit()
            return ok(None, "ok")
    return fail("备份节点不存在")


@router.post("/reset")
async def link_reset(request: Request):
    db = _db(request)
    user = current_user(request, db)
    if user:
        reset_user(db, user.id)
    return ok(None, "ok")


@router.post("/refreshWebAppCache")
async def refresh_webapp_cache(request: Request):
    require_admin(request, _db(request))
    return ok(None, "刷新完毕")
