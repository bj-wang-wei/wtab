"""界面配置接口，契约对齐原项目 app/controller/Config.php。"""
from __future__ import annotations

import json

from fastapi import APIRouter, Request

from app.deps import current_user, params, require_admin, require_user
from app.models import Config
from app.response import fail, ok
from app.services import settings_store
from app.services.userdata import default_section, get_doc, global_default_config, save_doc

router = APIRouter(prefix="/config")


@router.post("/get")
async def config_get(request: Request):
    db = request.state.db
    user = current_user(request, db)
    if user is None:
        return ok(global_default_config(db), "noLogin")
    return ok(get_doc(db, Config, user.id), "ok")


@router.post("/setGuest")
async def config_set_guest(request: Request):
    """管理员保存未登录主页：{link?, config?, tabbar?} 各段整份覆盖。"""
    db = request.state.db
    require_admin(request, db)
    body = await params(request)
    keys = {"link": "globalDefaultLinks", "config": "globalDefaultConfig", "tabbar": "globalDefaultTabbar"}
    data = {
        key: json.dumps(body[section], ensure_ascii=False)
        for section, key in keys.items()
        if isinstance(body.get(section), (list, dict))
    }
    if not data:
        return fail("保存失败")
    settings_store.save(db, data)
    return ok(None, "ok")


@router.post("/update")
async def config_update(request: Request):
    db = request.state.db
    user = require_user(request, db)
    config = (await params(request)).get("config")
    if not config:
        return fail("保存失败")
    save_doc(db, Config, user.id, config)
    return ok(None, "ok")
