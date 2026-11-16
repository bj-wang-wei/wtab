"""搜索引擎：系统表维护（管理员）+ 每用户自定义列表。"""
from __future__ import annotations

import time

from fastapi import APIRouter, Request
from sqlalchemy.orm import Session

from app.deps import demo_guard, params, require_admin, require_user
from app.models import SearchEngine, UserSearchEngine
from app.response import fail, ok
from app.services import userdata

router = APIRouter(prefix="/searchEngine")

_CACHE_TTL = 60 * 60 * 24  # 与原项目 Cache::set("searchEngine", ..., 86400) 一致
_cache: dict = {"at": 0.0, "list": []}


def clear_cache() -> None:
    _cache["at"] = 0.0
    _cache["list"] = []


def _row_json(row: SearchEngine) -> dict:
    return {
        "id": row.id,
        "name": row.name,
        "icon": row.icon,
        "url": row.url,
        "sort": row.sort,
        "status": row.status,
        "tips": row.tips,
    }


def system_engines(db: Session, limit: int | None = None, use_cache: bool = True) -> list[dict]:
    if limit is None and use_cache and _cache["list"] and time.time() - _cache["at"] < _CACHE_TTL:
        return _cache["list"]
    q = db.query(SearchEngine).filter(SearchEngine.status == 1).order_by(SearchEngine.sort.desc(), SearchEngine.id)
    if limit:
        q = q.limit(limit)
    rows = [_row_json(r) for r in q.all()]
    if limit is None and use_cache:
        _cache["at"] = time.time()
        _cache["list"] = rows
    return rows


def engines_for(db: Session, user) -> list[dict]:
    """首页搜索栏用：登录用户优先用个人列表，否则系统前 10 条。"""
    if user is not None:
        personal = userdata.get_doc(db, UserSearchEngine, user.id)
        if personal:
            # 实时查 status=1 的引擎 ID，过滤掉已被禁用/删除的条目
            active_ids = {e["id"] for e in system_engines(db, limit=100)}
            filtered = [e for e in personal if e.get("id", -1) >= 0 and e["id"] in active_ids]
            if filtered:
                return filtered
    return system_engines(db, limit=10)


@router.post("/index")
async def index(request: Request):
    """搜索引擎编辑视图：始终实时查库，不用缓存。"""
    db: Session = request.state.db
    return ok(system_engines(db, use_cache=False))





@router.post("/list")
async def list_engines(request: Request):
    db: Session = request.state.db
    require_admin(request, db)
    data = await params(request)
    name = (data.get("search") or {}).get("name") if isinstance(data.get("search"), dict) else data.get("name")
    q = db.query(SearchEngine)
    if name:
        like = f"%{name}%"
        q = q.filter((SearchEngine.name.like(like)) | (SearchEngine.tips.like(like)))
    rows = q.order_by(SearchEngine.sort.desc(), SearchEngine.id).all()
    return ok([_row_json(r) for r in rows])


@router.post("/add")
async def add(request: Request):
    db: Session = request.state.db
    demo_guard()
    require_admin(request, db)
    data = await params(request)
    form = data.get("form") or {}
    if not isinstance(form, dict) or not form:
        return fail("缺少数据")
    fields = {k: form[k] for k in ("name", "icon", "url", "sort", "status", "tips") if k in form}
    if "sort" in fields:
        fields["sort"] = int(fields["sort"] or 0)
    if "status" in fields:
        fields["status"] = int(fields["status"] or 0)
    row = db.get(SearchEngine, int(form["id"])) if form.get("id") else SearchEngine()
    if row is None:
        return fail("缺少数据")
    for k, v in fields.items():
        setattr(row, k, v)
    if not form.get("id"):
        row.create_time = userdata.now()
        if row.sort is None:
            row.sort = 0
        db.add(row)
    db.commit()
    clear_cache()
    return ok(None, "保存成功！")


@router.post("/del")
async def delete(request: Request):
    db: Session = request.state.db
    demo_guard()
    require_admin(request, db)
    data = await params(request)
    ids = data.get("ids") or []
    if not isinstance(ids, list):
        ids = [ids]
    if ids:
        db.query(SearchEngine).filter(SearchEngine.id.in_([int(i) for i in ids])).delete(synchronize_session=False)
        db.commit()
    clear_cache()
    return ok(None, "删除成功")


@router.post("/searchEngine")
async def search_engine(request: Request):
    from app.deps import current_user

    db: Session = request.state.db
    return ok(engines_for(db, current_user(request, db)))


@router.post("/saveSearchEngine")
async def save_search_engine(request: Request):
    db: Session = request.state.db
    user = require_user(request, db)
    data = await params(request)
    engine_list = data.get("searchEngine") or []
    if not engine_list:
        return fail("保存失败")
    # 过滤掉已被禁用/删除的系统引擎，保留用户自定义条目（id < 0）
    active_ids = {e["id"] for e in system_engines(db, limit=100)}
    clean = [e for e in engine_list if e.get("id", -1) < 0 or e.get("id") in active_ids]
    userdata.save_doc(db, UserSearchEngine, user.id, clean)
    return ok()


@router.post("/sort")
async def sort(request: Request):
    db: Session = request.state.db
    # 原项目此处未做权限校验（任何人可改排序），这里补上管理员校验
    require_admin(request, db)
    data = await params(request)
    items = data.values() if isinstance(data, dict) else data
    for item in items:
        if isinstance(item, dict) and item.get("id") is not None:
            db.query(SearchEngine).filter(SearchEngine.id == int(item["id"])).update(
                {"sort": int(item.get("sort") or 0)}, synchronize_session=False
            )
    db.commit()
    clear_cache()
    return ok()
