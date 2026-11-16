"""壁纸：/wallpaper/*（契约照抄原 app/controller/Wallpaper.php）。"""
from __future__ import annotations

import random

from fastapi import APIRouter, Request
from sqlalchemy import func, select

from app.deps import demo_guard, params, require_admin
from app.models import Wallpaper
from app.response import fail, ok
from app.storage import local_path

router = APIRouter(prefix="/wallpaper", tags=["wallpaper"])


def _folder_json(row: Wallpaper) -> dict:
    return {
        "id": row.id,
        "name": row.name,
        "type": row.type,
        "sort": row.sort,
        "create_time": row.create_time.strftime("%Y-%m-%d %H:%M:%S") if row.create_time else None,
    }


def _wall_json(row: Wallpaper) -> dict:
    return {
        "id": row.id,
        "folder": row.folder,
        "type": row.type,
        "mime": row.mime,
        "url": row.url,
        "name": row.name,
        "create_time": row.create_time.strftime("%Y-%m-%d %H:%M:%S") if row.create_time else None,
    }


def _exists(row: Wallpaper) -> bool:
    p = local_path(row.url)
    return p is not None and p.is_file()


def _visible(rows):
    """文件已被删掉的壁纸记录直接过滤，避免前台/后台出现打不开的图。"""
    return [r for r in rows if _exists(r)]


def folders(db) -> list[dict]:
    rows = db.scalars(select(Wallpaper).where(Wallpaper.type == 1).order_by(Wallpaper.sort)).all()
    return [_folder_json(r) for r in rows]


def _unlink(url: str | None) -> None:
    path = local_path(url)
    if path and path.is_file():
        try:
            path.unlink()
        except OSError:
            pass


def _drop_folder_files(db, folder_id) -> None:
    rows = db.scalars(
        select(Wallpaper).where(Wallpaper.type == 0, Wallpaper.folder == str(folder_id))
    ).all()
    for row in rows:
        _unlink(row.url)
        _unlink(row.cover)
        db.delete(row)


@router.post("/editFolder")
async def edit_folder(request: Request):
    db = request.state.db
    require_admin(request, db)
    demo_guard()
    data = await params(request)
    folder_id = data.get("id")
    row = db.get(Wallpaper, int(folder_id)) if folder_id else None
    if row is None:
        row = Wallpaper(type=1)
        db.add(row)
    row.name = data.get("name") or ""
    row.type = 1
    db.commit()
    return ok(folders(db), "处理完毕")


@router.post("/DelFolder")
async def del_folder(request: Request):
    db = request.state.db
    require_admin(request, db)
    data = await params(request)
    folder_id = data.get("id")
    row = db.get(Wallpaper, int(folder_id)) if folder_id else None
    if folder_id and row is None:
        return fail("分类不存在！")
    if row is None:
        return ok(folders(db), "ok")
    _drop_folder_files(db, row.id)
    db.delete(row)
    db.commit()
    return ok(folders(db), "ok")


@router.post("/getFolder")
async def get_folder(request: Request):
    db = request.state.db
    require_admin(request, db)
    return ok(folders(db), "ok")


@router.post("/getFolderClient")
async def get_folder_client(request: Request):
    return ok(folders(request.state.db), "ok")


@router.post("/getFolderWallpaper")
async def get_folder_wallpaper(request: Request):
    db = request.state.db
    require_admin(request, db)
    data = await params(request)
    folder_id = data.get("id")
    if not folder_id:
        return ok(None, "ok")
    limit = int(data.get("limit") or 19)
    page = int(data.get("page") or 1)
    total = db.scalar(
        select(func.count())
        .select_from(Wallpaper)
        .where(Wallpaper.type == 0, Wallpaper.folder == str(folder_id))
    )
    rows = db.scalars(
        select(Wallpaper)
        .where(Wallpaper.type == 0, Wallpaper.folder == str(folder_id))
        .order_by(Wallpaper.create_time.desc())
        .limit(limit)
        .offset((page - 1) * limit)
    ).all()
    # 原项目返回 ThinkPHP paginator，这里给等价的普通分页对象
    return ok(
        {
            "data": [_wall_json(r) for r in _visible(rows)],
            "total": total,
            "per_page": limit,
            "current_page": page,
            "last_page": max(1, -(-total // limit)),
        },
        "ok",
    )


@router.post("/getFolderWallpaperClient")
async def get_folder_wallpaper_client(request: Request):
    db = request.state.db
    data = await params(request)
    folder_id = data.get("id")
    if not folder_id:
        return ok(None, "ok")
    offset = int(data.get("offset") or 0)
    rows = db.scalars(
        select(Wallpaper)
        .where(Wallpaper.type == 0, Wallpaper.folder == str(folder_id))
        .order_by(Wallpaper.id.desc())
        .limit(20)
        .offset(offset * 20)
    ).all()
    return ok([_wall_json(r) for r in _visible(rows)], "ok")


@router.post("/deleteWallpaper")
async def delete_wallpaper(request: Request):
    db = request.state.db
    require_admin(request, db)
    data = await params(request)
    row = db.get(Wallpaper, int(data.get("id") or 0))
    if row:
        _unlink(row.url)
        _unlink(row.cover)
        db.delete(row)
        db.commit()
    return ok(None, "ok")


@router.post("/listAll")
async def list_all(request: Request):
    db = request.state.db
    require_admin(request, db)
    rows = db.scalars(select(Wallpaper).where(Wallpaper.type == 0).order_by(Wallpaper.create_time.desc())).all()
    return ok([_wall_json(r) for r in _visible(rows)], "ok")


@router.post("/addWallpaper")
async def add_wallpaper(request: Request):
    db = request.state.db
    require_admin(request, db)
    data = await params(request)
    payload = {
        "url": data.get("url"),
        "type": data.get("type"),
        "mime": data.get("mime"),
        "folder": data.get("folder"),
    }
    row = db.get(Wallpaper, int(data.get("id"))) if data.get("id") else None
    if row is None:
        row = Wallpaper(
            cover=None,
            url=payload["url"],
            type=int(payload["type"] or 0),
            mime=int(payload["mime"] or 0),
            folder=payload["folder"],
        )
        db.add(row)
    else:
        row.url = payload["url"]
        row.type = int(payload["type"] or 0)
        row.mime = int(payload["mime"] or 0)
        row.folder = payload["folder"]
    db.commit()
    return ok(_wall_json(row), "ok")


@router.post("/allClient")
async def all_client(request: Request):
    db = request.state.db
    data = await params(request)
    offset = int(data.get("offset") or 0)
    limit = int(data.get("limit") or 20)
    rows = db.scalars(
        select(Wallpaper).where(Wallpaper.type == 0).order_by(Wallpaper.id.desc()).limit(limit).offset(offset * limit)
    ).all()
    return ok([_wall_json(r) for r in _visible(rows)], "ok")


@router.post("/randomWallpaper")
async def random_wallpaper(request: Request):
    db = request.state.db
    rows = _visible(db.scalars(select(Wallpaper).where(Wallpaper.type == 0)).all())
    if not rows:
        return ok(None, "ok")
    row = random.choice(rows)
    return ok({"id": row.id, "mime": row.mime, "url": row.url}, "ok")


@router.post("/sortFolder")
async def sort_folder(request: Request):
    db = request.state.db
    require_admin(request, db)
    data = await params(request)
    for item in (data or {}).values():
        if not isinstance(item, dict) or not item.get("id"):
            continue
        row = db.get(Wallpaper, int(item["id"]))
        if row:
            row.sort = int(item.get("sort") or 0)
    db.commit()
    return ok(None, "ok")
