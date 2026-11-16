"""文件管理：/file/list|del|scanLocal（契约照抄原 app/controller/File.php）。"""
from __future__ import annotations

import hashlib
import io
import mimetypes
import zipfile

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import func, or_, select

from app.deps import demo_guard, params, require_admin
from app.models import File as FileModel
from app.models import User, now
from app.response import ok
from app.storage import UPLOAD_URL, del_file, local_path

router = APIRouter(prefix="/file", tags=["file"])


def _json(row: FileModel, user: User | None) -> dict:
    return {
        "id": row.id,
        "path": row.path,
        "user_id": row.user_id,
        "create_time": row.create_time.strftime("%Y-%m-%d %H:%M:%S") if row.create_time else None,
        "size": row.size,
        "mime_type": row.mime_type,
        "hash": row.hash,
        "user": {"id": user.id, "nickname": user.nickname, "mail": user.mail} if user else None,
    }


@router.post("/list")
async def list_files(request: Request):
    db = request.state.db
    require_admin(request, db)
    data = await params(request)
    limit = int(data.get("limit") or 15)
    page = int(data.get("page") or 1)
    search = data.get("search") or {}
    name = search.get("path")
    user_id = search.get("user_id")

    where = []
    if name:
        where.append(or_(FileModel.mime_type.like(f"%{name}%"), FileModel.path.like(f"%{name}%")))
    if user_id:
        where.append(FileModel.user_id == user_id)

    total = db.scalar(select(func.count()).select_from(FileModel).where(*where)) or 0
    rows = db.scalars(
        select(FileModel).where(*where).order_by(FileModel.id.desc()).limit(limit).offset((page - 1) * limit)
    ).all()
    owners = {
        u.id: u
        for u in db.scalars(
            select(User).where(User.id.in_([r.user_id for r in rows if r.user_id] or [0]))
        ).all()
    }
    return ok(
        {
            "data": [_json(r, owners.get(r.user_id)) for r in rows],
            "total": total,
            "per_page": limit,
            "current_page": page,
            "last_page": max(1, -(-total // limit)),
        },
        "ok",
    )


@router.post("/del")
async def del_files(request: Request):
    db = request.state.db
    require_admin(request, db)
    demo_guard()
    data = await params(request)
    for file_id in data.get("ids") or []:
        row = db.get(FileModel, int(file_id))
        if row:
            del_file(db, row.path)
            if db.get(FileModel, int(file_id)):
                db.delete(row)
                db.commit()
    return ok(None, "删除成功")


@router.post("/scanLocal")
async def scan_local(request: Request):
    """把 uploads 目录里没登记过的文件补进 file 表（原项目扫描 public/images）。"""
    db = request.state.db
    require_admin(request, db)
    demo_guard()
    from app.config import UPLOAD_DIR

    known = set(db.scalars(select(FileModel.path).limit(5000)).all())
    added = 0
    for path in UPLOAD_DIR.rglob("*"):
        if not path.is_file():
            continue
        url = f"{UPLOAD_URL}/{path.relative_to(UPLOAD_DIR).as_posix()}"
        if url in known:
            continue
        digest = hashlib.md5(path.read_bytes()).hexdigest()
        db.add(
            FileModel(
                path=url,
                user_id=None,
                create_time=now(),
                size=path.stat().st_size,
                hash=digest,
                mime_type=mimetypes.guess_type(path.name)[0] or "application/octet-stream",
            )
        )
        added += 1
    db.commit()
    return ok({"added": added}, "扫描完成")


@router.post("/downloadZip")
async def download_zip(request: Request):
    """把勾选的文件打包成 zip 下载（磁盘上已丢失的文件自动跳过）。"""
    db = request.state.db
    require_admin(request, db)
    data = await params(request)
    ids = [int(i) for i in (data.get("ids") or []) if str(i).isdigit()]
    rows = db.scalars(select(FileModel).where(FileModel.id.in_(ids))).all() if ids else []
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for row in rows:
            path = local_path(row.path)
            if path and path.is_file():
                zf.write(path, path.name)
    buf.seek(0)
    return StreamingResponse(
        buf,
        media_type="application/zip",
        headers={"Content-Disposition": 'attachment; filename="files.zip"'},
    )


__all__ = ["router", "local_path"]
