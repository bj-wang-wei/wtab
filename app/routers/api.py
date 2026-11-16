"""站点信息与资源接口：/api/site|background|DefBg|globalNotify|refresh|getIcon|renderIco|upload|AdminUpload|moveFile|delImages。

契约照抄原 app/controller/Api.php。`/api/getMailCode` 在 user.py。
卡片相关的 `/api/cardImages` 随卡片系统一并移除。
"""
from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from html.parser import HTMLParser

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse, Response
from sqlalchemy import select

from app.config import STATIC_DIR, UPLOAD_DIR, settings
from app.deps import demo_guard, params, require_admin, current_user
from app.models import Link, now
from app.response import fail, ok
from app.services import settings_store
from app.services.site import DEFAULTS as SITE_DEFAULTS
from app.storage import IMAGE_EXTS, add_file, del_file, move_file, random_name, url_dir
from app.services.userdata import default_tab

router = APIRouter(prefix="/api", tags=["api"])
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
MAX_REMOTE_BYTES = 8 * 1024 * 1024


def _get(db, key: str, default: str = "") -> str:
    val = settings_store.get(db, key, default)
    return val or default


@router.post("/site")
async def site(request: Request):
    db = request.state.db
    logged = current_user(request, db) is not None
    data = {
        "email": _get(db, "email"),
        "qqGroup": _get(db, "qqGroup"),
        "beianMps": _get(db, "beianMps"),
        "copyright": _get(db, "copyright"),
        "recordNumber": _get(db, "recordNumber"),
        "mobileRecordNumber": _get(db, "mobileRecordNumber", "0"),
        "auth": logged,
        "logo": _get(db, "logo"),
        "loginCloseRecordNumber": _get(db, "loginCloseRecordNumber", "0"),
        "customAbout": _get(db, "customAbout"),
        "aboutMe": _get(db, "aboutMe", SITE_DEFAULTS["aboutMe"]),
        "appName": _get(db, "appName", SITE_DEFAULTS["appName"]),
        "appVersion": _get(db, "appVersion", SITE_DEFAULTS["appVersion"]),
        "appDesc": _get(db, "appDesc", SITE_DEFAULTS["appDesc"]),
        "appLinks": _get(db, "appLinks", SITE_DEFAULTS["appLinks"]),
        "user_register": _get(db, "user_register", "0"),
        "tip": {
            "ds_status": _get(db, "ds_status", "0"),
            "ds_template": _get(db, "ds_template", "org"),
            "ds_alipay_img": _get(db, "ds_alipay_img"),
            "ds_wx_img": _get(db, "ds_wx_img"),
            "ds_custom_url": _get(db, "ds_custom_url"),
            "ds_title": _get(db, "ds_title"),
            "ds_tips": _get(db, "ds_tips"),
        },
    }
    return ok(data, "ok")


@router.get("/background")
async def background():
    path = STATIC_DIR / "background.jpeg"
    if not path.is_file():
        return fail("默认背景不存在")
    # 原项目用 download()->expire() 提供带缓存的静态文件
    return FileResponse(path, media_type="image/jpeg", headers={"Cache-Control": "public, max-age=259200"})


@router.post("/DefBg")
async def def_bg(request: Request):
    db = request.state.db
    tab = default_tab()
    theme = (tab.get("config") or {}).get("theme") or {}
    if theme.get("backgroundImage"):
        return ok({"background": theme["backgroundImage"], "mime": theme.get("backgroundMime", 0)}, "ok")
    return ok({"background": "static/background.jpeg", "mime": 0}, "ok")


@router.post("/globalNotify")
async def global_notify(request: Request):
    raw = _get(request.state.db, "globalNotify")
    info = None
    if raw:
        try:
            info = json.loads(raw)
        except ValueError:
            # 非 JSON 时按纯文本公告处理，省得用户必须写 JSON
            info = {"status": "1", "content": raw}
    # 原项目把 data 作为 JSON 字符串返回；这里直接给对象，方便模板/前端消费
    if info and str(info.get("status")) == "1":
        return ok(info, "ok")
    return fail("empty")


@router.post("/refresh")
async def refresh(request: Request):
    db = request.state.db
    user = current_user(request, db)
    if user is None:
        return fail("not login")
    row = db.scalar(select(Link).where(Link.user_id == user.id))
    update_time = row.update_time.strftime("%Y-%m-%d %H:%M:%S") if row and row.update_time else None
    return ok({"link_update_time": update_time}, "ok")


# ---------------------------------------------------------------- 远程图标抓取


class _IconParser(HTMLParser):
    """收集 <title> 与各类 <link rel="...icon...">。"""

    def __init__(self) -> None:
        super().__init__()
        self.title = ""
        self.icons: list[str] = []
        self._in_title = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "title":
            self._in_title = True
        elif tag == "link":
            attr = {k.lower(): (v or "") for k, v in attrs}
            if "icon" in attr.get("rel", "").lower() and attr.get("href"):
                self.icons.append(attr["href"])

    def handle_endtag(self, tag: str) -> None:
        if tag == "title":
            self._in_title = False

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self.title += data


def _fetch(url: str) -> tuple[bytes, str]:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=10) as resp:
        return resp.read(MAX_REMOTE_BYTES), resp.headers.get("Content-Type", "")


def _site_root(url: str) -> str:
    """去掉路径只留 scheme://host（原 addHttpProtocolRemovePath）。"""
    if not url.lower().startswith(("http://", "https://")):
        url = "http://" + url
    parts = urllib.parse.urlsplit(url)
    return f"{parts.scheme}://{parts.netloc}"


def _save_remote(db, raw: bytes, name: str, user_id: int | None, category: str = "linklogo") -> str | None:
    directory = UPLOAD_DIR / category
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / name
    path.write_bytes(raw)
    return add_file(db, f"{url_dir(category)}{name}", user_id)


@router.post("/getIcon")
async def get_icon(request: Request):
    db = request.state.db
    user = current_user(request, db)
    data = await params(request)

    url = data.get("url")
    if not url:
        return fail("没有抓取到图标")

    root = _site_root(str(url))
    cdn = _get(db, "assets_host")
    try:
        body, content_type = _fetch(root)
        icon = ""
        title = ""
        if "text/html" in content_type.lower():
            parser = _IconParser()
            parser.feed(body.decode("utf-8", "ignore"))
            title = parser.title.strip()
            for href in parser.icons:
                href = href if href.lower().startswith(("http", "//", "data:")) else root + "/" + href.lstrip("/")
                if href.startswith("//"):
                    href = "https:" + href
                if href.startswith("data:"):
                    continue
                icon = _download_icon(db, href, root, cdn, user.id if user else None)
                if icon:
                    break
        if not icon:
            icon = _download_favicon(db, root, cdn, user.id if user else None)
        if icon:
            return ok({"src": icon, "name": title})
    except (urllib.error.URLError, OSError, ValueError):
        return fail("没有抓取到图标")
    return fail("没有抓取到图标")


def _md5(text: str) -> str:
    import hashlib

    return hashlib.md5(str(text).encode()).hexdigest()


def _download_icon(db, href: str, root: str, cdn: str, user_id: int | None) -> str:
    try:
        raw, content_type = _fetch(href)
    except (urllib.error.URLError, OSError):
        return ""
    ext = {"png": "png", "jpg": "jpg", "jpeg": "jpeg", "x-icon": "ico", "svg+xml": "svg"}
    subtype = content_type.split("/")[-1].split(";")[0].strip().lower()
    if subtype not in ext:
        return ""
    path = _save_remote(db, raw, f"{_md5(root)}.{ext[subtype]}", user_id)
    return cdn + path if path else ""


def _download_favicon(db, root: str, cdn: str, user_id: int | None) -> str:
    try:
        raw, _ = _fetch(root + "/favicon.ico")
    except (urllib.error.URLError, OSError):
        return ""
    path = _save_remote(db, raw, f"{_md5(root)}.ico", user_id)
    return cdn + path if path else ""


# ---------------------------------------------------------------------- 上传


def _upload_size(db) -> float:
    try:
        return float(_get(db, "upload_size", "2") or 2)
    except ValueError:
        return 2.0


UPLOAD_CATEGORIES = {"wallpaper", "avatar", "linklogo"}


def _category(value, default: str = "linklogo") -> str:
    return value if value in UPLOAD_CATEGORIES else default


async def _store(file, db, user_id: int | None, force_ext: bool, category: str = "linklogo") -> tuple[str | None, str]:
    """保存上传文件并登记，返回 (url, 原始文件名)。"""
    raw = await file.read()
    name = file.filename or ""
    ext = (name.rsplit(".", 1)[-1] if "." in name else "").lower()
    if force_ext and ext not in IMAGE_EXTS:
        return None, name
    directory = UPLOAD_DIR / category
    directory.mkdir(parents=True, exist_ok=True)
    file_name = random_name(ext or "bin")
    (directory / file_name).write_bytes(raw)
    return add_file(db, f"{url_dir(category)}{file_name}", user_id), name


@router.post("/upload")
async def upload(request: Request):
    db = request.state.db
    user = current_user(request, db)
    if user is None:
        return fail("请登录后使用")

    form = await request.form()
    file = form.get("file")
    if file is None or not getattr(file, "filename", ""):
        return fail("not File")

    max_size = _upload_size(db)
    raw = await file.read()
    if len(raw) > 1024 * 1024 * max_size:
        limit = f"{max_size * 1000}KB" if max_size < 1 else f"{max_size}MB"
        return fail(f"文件最大{limit},请压缩后再试")
    await file.seek(0)

    # shortcut: 原项目用 ImageBack 把 icon/avatar 缩到 144 宽、AdminBackground 生成 min 缩略图，
    # 这里不引入 Pillow，直接存原图；需要省空间时再加图片处理。
    url, _ = await _store(file, db, user.id if user else None, force_ext=True,
                          category=_category(form.get("category")))
    if not url:
        return fail("上传失败")
    return ok({"url": url, "minUrl": "", "filename": url.rsplit("/", 1)[-1]})


@router.post("/AdminUpload")
async def admin_upload(request: Request):
    db = request.state.db
    user = require_admin(request, db)
    demo_guard()
    form = await request.form()
    file = form.get("file")
    if file is None or not getattr(file, "filename", ""):
        return fail("not File")
    raw = await file.read()
    if len(raw) > 1024 * 1024 * 8:
        return fail("文件最大8MB,请压缩后再试")
    await file.seek(0)
    url, _ = await _store(file, db, user.id, force_ext=False,
                          category=_category(form.get("category"), "wallpaper"))
    if not url:
        return fail("上传失败")
    cdn = _get(db, "assets_host")
    # cdn 为空或 "/" 时直接用本地路径；避免拼出 "//images/..." 被当成协议相对地址
    return ok({"url": cdn.rstrip("/") + url if cdn and cdn != "/" else url})


@router.post("/moveFile")
async def move_file_api(request: Request):
    db = request.state.db
    require_admin(request, db)
    data = await params(request)
    move_file(db, str(data.get("old") or ""), str(data.get("new") or ""))
    return ok(None, "文件移动成功")


@router.post("/delImages")
async def del_images(request: Request):
    db = request.state.db
    require_admin(request, db)
    data = await params(request)
    del_file(db, str(data.get("url") or ""))
    return ok(None, "删除完毕")
