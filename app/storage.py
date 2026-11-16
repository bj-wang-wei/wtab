"""上传文件与本地资源的路径映射。

原项目上传文件放在 `public/images`，URL 也是 `/images/...`。为了让既有 wtab 数据库里的
路径（书签图标、壁纸 url、file.path）直接可用，这里把 UPLOAD_DIR 挂到 `/images`。
"""
from __future__ import annotations

import hashlib
import mimetypes
import secrets
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import STATIC_DIR, UPLOAD_DIR
from app.models import File as FileModel
from app.models import Wallpaper
from app.models import now

UPLOAD_URL = "/images"
STATIC_URL = "/static"
IMAGE_EXTS = {"png", "jpg", "jpeg", "webp", "ico", "svg"}

# URL 前缀 → 磁盘根目录
ROOTS = ((UPLOAD_URL, UPLOAD_DIR), (STATIC_URL, STATIC_DIR))


def local_path(url: str | None) -> Path | None:
    """把 `/images/...` 或 `/static/...` 转成本地路径；越界或未知前缀返回 None。

    统一按 URL 语义处理：Windows 客户端或既有数据库里可能写成 `\\` 分隔，先归一成 `/`。
    """
    if not url:
        return None
    clean = url.split("?")[0].split("#")[0].replace("\\", "/")
    for prefix, root in ROOTS:
        if clean.startswith(prefix + "/"):
            rel = clean[len(prefix) + 1 :].lstrip("/")
            path = (root / rel).resolve()
            # 路径穿越防护（URL 可能来自既有库或客户端）
            if path.is_relative_to(root.resolve()):
                return path
    return None


def url_dir(category: str = "linklogo") -> str:
    """上传目录按用途分类：/images/wallpaper|avatar|linklogo/。"""
    return f"{UPLOAD_URL}/{category}/"


def random_name(ext: str) -> str:
    return f"{secrets.token_hex(16)}.{ext.lstrip('.')}"


def _md5(path: Path) -> str:
    h = hashlib.md5()
    with path.open("rb") as fp:
        for chunk in iter(lambda: fp.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def add_file(db: Session, url: str, user_id: int | None = None) -> str | None:
    """登记上传文件，按内容 md5 去重（等价原 FileModel::addFile）。返回入库路径。"""
    path = local_path(url)
    if path is None or not path.is_file():
        return None
    digest = _md5(path)
    exist = db.scalar(select(FileModel).where(FileModel.hash == digest))
    if exist:
        if exist.path != url:
            path.unlink(missing_ok=True)
        return exist.path
    db.add(
        FileModel(
            path=url,
            user_id=user_id,
            create_time=now(),
            size=path.stat().st_size,
            hash=digest,
            mime_type=mimetypes.guess_type(path.name)[0] or "application/octet-stream",
        )
    )
    db.commit()
    return url


def del_file(db: Session, url: str) -> bool:
    """删除磁盘文件，并清掉对应的 file 行和引用该文件的壁纸记录。"""
    path = local_path(url)
    if path is None or not path.is_file():
        return False
    digest = _md5(path)
    path.unlink(missing_ok=True)
    row = db.scalar(select(FileModel).where(FileModel.hash == digest))
    if row:
        db.delete(row)
    walls = db.scalars(
        select(Wallpaper).where((Wallpaper.url == url) | (Wallpaper.cover == url))
    ).all()
    for wall in walls:
        db.delete(wall)
    db.commit()
    return True


def move_file(db: Session, old_url: str, new_url: str) -> bool:
    """移动文件并把 file.path 改到新位置（等价原 FileModel::moveFile）。"""
    src, dst = local_path(old_url), local_path(new_url)
    if src is None or dst is None or not src.is_file():
        return False
    row = db.scalar(select(FileModel).where(FileModel.hash == _md5(src)))
    if not row:
        return False
    dst.parent.mkdir(parents=True, exist_ok=True)
    src.replace(dst)
    row.path = new_url if new_url.startswith("/") else "/" + new_url
    db.commit()
    return True
