"""安装向导。接口形状沿用原 public/install.php（/install/testDb、/install/install），返回 {code:200|500}。"""
from __future__ import annotations

import json

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, RedirectResponse

from app.main import is_installed
from app.services import installer
from app.services.installer import InstallError
from app.templating import render

router = APIRouter(tags=["install"])


async def _json_body(request: Request) -> dict:
    try:
        body = await request.body()
        return json.loads(body) if body else {}
    except json.JSONDecodeError:
        return {}


@router.get("/install")
async def install_page(request: Request):
    if is_installed():
        return RedirectResponse("/", status_code=302)
    return render(request, "install.html")


@router.post("/install/testDb")
async def test_db(request: Request):
    form = await _json_body(request)
    try:
        installer.test_connection(installer.build_url(form))
    except InstallError as exc:
        return JSONResponse({"code": 500, "msg": str(exc)})
    return JSONResponse({"code": 200, "msg": "连接成功"})


@router.post("/install/install")
async def do_install(request: Request):
    if is_installed():
        return JSONResponse({"code": 500, "msg": "已安装，如需重装请删除 data/installed.lock"})
    form = await _json_body(request)
    try:
        url = installer.install(form)
    except InstallError as exc:
        return JSONResponse({"code": 500, "msg": str(exc)})
    except Exception as exc:  # 建表/写库阶段的意外错误
        return JSONResponse({"code": 500, "msg": f"安装失败：{exc}"})
    return JSONResponse({"code": 200, "msg": "安装成功", "data": {"database": url.split("@")[-1]}})
