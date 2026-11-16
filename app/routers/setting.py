"""系统设置 API，对应原项目 app/controller/Setting.php。"""
from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from app.config import BASE_DIR
from app.deps import demo_guard, params, require_admin
from app.models import now
from app.response import fail, ok
from app.services import mailer, settings_store
from app.services.site import DEFAULTS as SITE_DEFAULTS

router = APIRouter(prefix="/setting", tags=["setting"])

BROWSER_EXT_ZIP = BASE_DIR / "browserExt.zip"


def _refresh_all() -> None:
    """原项目删 webConfig / searchEngine / cardList / hotTab 等几个缓存。"""
    from app.routers import admin, searchengine

    settings_store.refresh()
    searchengine.clear_cache()
    admin.clear_cache()


@router.post("/saveSetting")
async def save_setting(request: Request):
    db = request.state.db
    require_admin(request, db)
    demo_guard()
    body = await params(request)
    form = body.get("form") or {}
    if not isinstance(form, dict):
        return fail("缺少数据")
    settings_store.save(db, form)
    _refresh_all()
    return ok(msg="保存成功")


@router.post("/refreshCache")
async def refresh_cache(request: Request):
    db = request.state.db
    require_admin(request, db)
    _refresh_all()
    return ok(msg="刷新成功")


@router.post("/getSetting")
async def get_setting(request: Request):
    db = request.state.db
    require_admin(request, db)
    body = await params(request)
    role = body.get("role") or []
    info = settings_store.all_settings(db)
    data = {k: (info.get(k) or SITE_DEFAULTS.get(k, "")) for k in role} if role else {}
    url = "/browserExt.zip" if "ext_name" in role and BROWSER_EXT_ZIP.exists() else ""
    if data:
        return JSONResponse({"msg": "ok", "data": data, "code": 1, "url": url})
    return JSONResponse({"msg": "ok", "data": False, "code": 0, "url": url})


@router.post("/mailTest")
async def mail_test(request: Request):
    db = request.state.db
    require_admin(request, db)
    body = await params(request)
    email = body.get("email") or ""
    if not email:
        return fail("请填写收件邮箱")
    html = mailer.code_html(db, "123456", now().strftime("%Y-%m-%d %H:%M:%S"))
    try:
        mailer.send(db, email, html, smtp=body.get("smtp") or None)
    except Exception as exc:  # noqa: BLE001 - 原项目把异常消息直接回给前端
        return fail(str(exc))
    return ok(msg="发送成功")


@router.post("/delExt")
async def del_ext(request: Request):
    db = request.state.db
    require_admin(request, db)
    if BROWSER_EXT_ZIP.exists():
        BROWSER_EXT_ZIP.unlink()
    return ok(msg="ok")
