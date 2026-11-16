"""导航栏接口，契约对齐原项目 app/controller/Tabbar.php。"""
from __future__ import annotations

from fastapi import APIRouter, Request

from app.deps import current_user, params, require_user
from app.models import Tabbar
from app.response import fail, ok
from app.services.userdata import default_section, get_doc, save_doc

router = APIRouter(prefix="/tabbar")


@router.post("/get")
async def tabbar_get(request: Request):
    db = request.state.db
    user = current_user(request, db)
    if user is None:
        return ok(default_section("tabbar"), "ok")
    return ok(get_doc(db, Tabbar, user.id), "ok")


@router.post("/update")
async def tabbar_update(request: Request):
    db = request.state.db
    user = require_user(request, db)
    tabbar = (await params(request)).get("tabbar")
    if not isinstance(tabbar, list):
        return fail("保存失败")
    save_doc(db, Tabbar, user.id, tabbar)
    return ok(None, "ok")
