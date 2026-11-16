"""笔记：/note/get|add|update|del|sort|setWeight|getText（契约照抄原 app/controller/Note.php）。"""
from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import PlainTextResponse
from sqlalchemy import select

from app.deps import current_user, require_user
from app.models import Note, now
from app.response import fail, ok

router = APIRouter(prefix="/note", tags=["note"])
FIELDS = "user_id,id,title,create_time,update_time,weight,sort"


def _stamp(value) -> str | None:
    return value.strftime("%Y-%m-%d %H:%M:%S") if value else None


def _json(row: Note) -> dict:
    return {
        "user_id": row.user_id,
        "id": row.id,
        "title": row.title,
        "create_time": _stamp(row.create_time),
        "update_time": _stamp(row.update_time),
        "weight": row.weight,
        "sort": row.sort,
    }


async def _args(request: Request) -> dict:
    """原项目混用 get()/post()，这里查询串与请求体都读。"""
    from app.deps import params

    data = await params(request)
    merged = dict(request.query_params)
    merged.update(data)
    return merged


@router.post("/get")
async def get_notes(request: Request):
    db = request.state.db
    # 未登录返回空列表（原项目行为），不报错
    user = current_user(request, db)
    if user is None:
        return ok([], "")
    limit = int(request.query_params.get("limit") or 999999)
    rows = (
        db.execute(
            select(Note)
            .where(Note.user_id == user.id)
            .order_by(Note.sort.asc(), Note.create_time.desc())
            .limit(limit)
        )
        .scalars()
        .all()
    )
    return ok([_json(r) for r in rows], "ok")


@router.post("/add")
async def add_note(request: Request):
    db = request.state.db
    user = require_user(request, db)
    args = await _args(request)
    if args.get("id") not in ("", None):
        return await update_note(request)
    row = Note(
        user_id=user.id,
        title=args.get("title") or "",
        text=args.get("text") or "",
        weight=int(args.get("weight") or 0),
        create_time=now(),
        update_time=now(),
    )
    db.add(row)
    db.commit()
    data = _json(row)
    data["text"] = row.text
    return ok(data, "创建成功")


@router.post("/update")
async def update_note(request: Request):
    db = request.state.db
    user = require_user(request, db)
    args = await _args(request)
    note_id = args.get("id")
    if not note_id:
        return fail("no")
    row = db.scalar(select(Note).where(Note.id == int(note_id), Note.user_id == user.id))
    if row is None:
        return fail("失败")
    row.title = args.get("title") or ""
    row.text = args.get("text") or ""
    row.weight = int(args.get("weight") or 0)
    row.update_time = now()
    db.commit()
    data = _json(row)
    data["text"] = row.text
    return ok(data, "修改")


@router.post("/del")
async def del_note(request: Request):
    db = request.state.db
    user = require_user(request, db)
    args = await _args(request)
    row = db.scalar(select(Note).where(Note.id == int(args.get("id") or 0), Note.user_id == user.id))
    if row is None:
        return ok(0, "删除成功")
    db.delete(row)
    db.commit()
    return ok(1, "删除成功")


@router.post("/sort")
async def sort_notes(request: Request):
    db = request.state.db
    user = require_user(request, db)
    args = await _args(request)
    ids = args.get("ids") or []
    owned = set(
        db.scalars(select(Note.id).where(Note.user_id == user.id, Note.id.in_([int(i) for i in ids]))).all()
    )
    for index, note_id in enumerate(ids):
        if int(note_id) in owned:
            row = db.get(Note, int(note_id))
            row.sort = index
    db.commit()
    return ok(None, "ok")


@router.post("/setWeight")
async def set_weight(request: Request):
    db = request.state.db
    user = require_user(request, db)
    args = await _args(request)
    if args.get("id"):
        row = db.scalar(select(Note).where(Note.id == int(args["id"]), Note.user_id == user.id))
        if row:
            row.weight = int(args.get("weight") or 0)
            row.update_time = now()
            db.commit()
    return ok(None, "ok")


@router.get("/getText")
async def get_text(request: Request):
    """原项目返回裸文本（非 JSON）。"""
    db = request.state.db
    user = require_user(request, db)
    row = db.scalar(
        select(Note).where(Note.id == int(request.query_params.get("id") or 0), Note.user_id == user.id)
    )
    return PlainTextResponse(row.text if row and row.text else "")
