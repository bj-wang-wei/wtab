"""管理后台 API，对应原项目 app/controller/Admin.php。

原项目里这些 action 都先调 BaseController::getAdmin()，非管理员返回 error('not permission')；
这里用 require_admin（AuthError 由 main.py 的异常处理器统一转成 fail(msg)）。
"""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta

from fastapi import APIRouter, Request
from sqlalchemy import select

from app.config import BASE_DIR, STATIC_DIR, settings
from app.deps import demo_guard, params, require_admin
from app.models import Config as ConfigModel
from app.models import (
    File,
    History,
    Link,
    LinkClick,
    Note,
    Tabbar,
    Token,
    User,
    UserSearchEngine,
    now,
)
from app.paging import paginate
from app.response import fail, ok
from app.security import md5
from app.services import settings_store
from app.services.installer import reset_system, run_migrations

router = APIRouter(prefix="/admin", tags=["admin"])

DEFAULT_TAB_FILE = STATIC_DIR / "defaultTab.json"

# 原项目用 Cache 存 60s；这里是进程内缓存，多 worker 各自一份
# shortcut: 多进程下同一份统计会各算一次，量级上来再换 Redis
_CACHE: dict[str, tuple[float, object]] = {}

SORTABLE = {
    "id": User.id,
    "mail": User.mail,
    "nickname": User.nickname,
    "create_time": User.create_time,
    "login_time": User.login_time,
    "status": User.status,
    "manager": User.manager,
    "group_id": User.group_id,
}


def clear_cache() -> None:
    _CACHE.clear()


def _dt(value: datetime | None) -> str | None:
    return value.strftime("%Y-%m-%d %H:%M:%S") if value else None


def _int(value, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def user_json(user: User) -> dict:
    return {
        "id": user.id,
        "avatar": user.avatar,
        "mail": user.mail,
        "create_time": _dt(user.create_time),
        "login_ip": user.login_ip,
        "register_ip": user.register_ip,
        "manager": user.manager,
        "login_fail_count": user.login_fail_count,
        "login_time": _dt(user.login_time),
        "qq_open_id": user.qq_open_id,
        "nickname": user.nickname,
        "status": user.status,
        "active": user.active,
        "group_id": user.group_id,
    }


@router.post("/UserList")
async def user_list(request: Request):
    db = request.state.db
    require_admin(request, db)
    body = await params(request)
    search = body.get("search") or {}
    sort = body.get("sort") or {}

    rows = list(db.scalars(select(User)))
    if search.get("mail"):
        rows = [u for u in rows if search["mail"] in (u.mail or "")]
    if search.get("nickname"):
        rows = [u for u in rows if search["nickname"] in (u.nickname or "")]
    if search.get("status") is not None and _int(search["status"], -1) >= 0:
        rows = [u for u in rows if u.status == _int(search["status"])]
    group_id = body.get("search.group_id", search.get("group_id", -1))
    if group_id is not None and _int(group_id, -1) >= 0:
        rows = [u for u in rows if u.group_id == _int(group_id)]

    column = SORTABLE.get(str(sort.get("prop") or "id"), User.id)
    descending = str(sort.get("order") or "desc").lower() != "asc"
    rows.sort(key=lambda u: (getattr(u, column.key) is None, getattr(u, column.key)), reverse=descending)

    return ok(paginate([user_json(u) for u in rows], _int(body.get("limit"), 50), _int(body.get("page"), 1)), "ok")


@router.post("/userUpdate")
async def user_update(request: Request):
    db = request.state.db
    require_admin(request, db)
    demo_guard()
    body = await params(request)
    user = db.get(User, _int(body.get("id"))) if body.get("id") else None
    if user is None:
        if not body.get("mail"):
            return fail("缺少邮箱")
        user = User(create_time=now())
        db.add(user)

    for field in ("mail", "nickname", "avatar", "status", "group_id", "manager", "active", "qq_open_id"):
        if field in body:
            setattr(user, field, body[field])
    if body.get("password"):
        user.password = md5(str(body["password"]))
    db.commit()
    return ok(msg="保存成功")


@router.post("/userDelete")
async def user_delete(request: Request):
    db = request.state.db
    require_admin(request, db)
    demo_guard()
    body = await params(request)
    user = db.get(User, _int(body.get("id"))) if body.get("id") else None
    if user is not None:
        for model in (Link, Tabbar, History, ConfigModel, Note, UserSearchEngine, Token):
            for row in db.scalars(select(model).where(model.user_id == user.id)):
                db.delete(row)
        db.delete(user)
        db.commit()
    return ok(msg="删除完毕")


@router.post("/export")
async def export(request: Request):
    db = request.state.db
    require_admin(request, db)
    demo_guard()
    body = await params(request)
    link = body.get("link") or []
    if not link:
        return fail("保存失败")
    # 出厂默认书签（link 段）统一写入 defaultTab.json，与 userdata.default_tab() 共用同一份数据
    data = json.loads(DEFAULT_TAB_FILE.read_text(encoding="utf-8"))
    data["link"] = link
    DEFAULT_TAB_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return ok(msg="保存成功")


def _license_html() -> str:
    path = BASE_DIR / "config" / "LICENSE.html"
    return path.read_text(encoding="utf-8") if path.exists() else ""


@router.post("/xyCheck")
async def xy_check(request: Request):
    require_admin(request, request.state.db)
    license_html = _license_html()
    pem = BASE_DIR / "xy.pem"
    if pem.exists() and pem.read_text(encoding="utf-8") == license_html:
        return ok(msg="ok")
    return fail("未找到证书文件", {"license": license_html})


@router.post("/xy")
async def xy(request: Request):
    require_admin(request, request.state.db)
    (BASE_DIR / "xy.pem").write_text(_license_html(), encoding="utf-8")
    return ok(msg="ok")


@router.post("/getServicesStatus")
async def get_services_status(request: Request):
    db = request.state.db
    require_admin(request, db)

    def week_active() -> int:
        start = (date.today() - timedelta(days=7)).strftime("%Y-%m-%d")
        return sum(1 for u in db.scalars(select(User)) if (u.active or "") > start)

    top = db.scalars(select(LinkClick).order_by(LinkClick.count.desc()).limit(20)).all()
    return ok(
        {
            "userNum": len(list(db.scalars(select(User.id)))),
            "fileNum": len(list(db.scalars(select(File.id)))),
            "userWeekActive": week_active(),
            "topLinks": [{"name": t.name or t.url, "url": t.url, "count": t.count or 0} for t in top],
        },
        "ok",
    )


@router.post("/getUserLine")
async def get_user_line(request: Request):
    db = request.state.db
    require_admin(request, db)
    body = await params(request)
    today = date.today()
    date_select = body.get("dateSelect") or [
        today.replace(day=1).strftime("%Y-%m-%d"),
        today.strftime("%Y-%m-%d"),
    ]
    try:
        start_d = datetime.strptime(str(date_select[0]), "%Y-%m-%d").date()
        end_d = datetime.strptime(str(date_select[1]), "%Y-%m-%d").date()
    except (ValueError, IndexError):
        start_d, end_d = today.replace(day=1), today

    counts: dict[str, int] = {}
    for value in db.scalars(select(User.create_time)):
        if not value:
            continue
        day = value.date()
        if start_d <= day <= end_d:
            counts[day.strftime("%Y-%m-%d")] = counts.get(day.strftime("%Y-%m-%d"), 0) + 1

    times: list[str] = []
    totals: list[int] = []
    cursor = start_d
    while cursor <= end_d:
        key = cursor.strftime("%Y-%m-%d")
        times.append(key)
        totals.append(counts.get(key, 0))
        cursor += timedelta(days=1)

    return ok({"time": times, "total": totals, "sum": sum(totals)}, "ok")


@router.post("/userLoginRecord")
async def user_login_record(request: Request):
    db = request.state.db
    require_admin(request, db)
    body = await params(request)
    user_id = _int(body.get("user_id"))
    if not user_id or settings.demo_mode:
        return ok([], "")
    rows = db.scalars(
        select(Token).where(Token.user_id == user_id).order_by(Token.create_time.desc()).limit(100)
    ).all()
    return ok(
        [
            {
                "user_id": row.user_id,
                "create_time": datetime.fromtimestamp(row.create_time).strftime("%Y-%m-%d %H:%M:%S")
                if row.create_time
                else None,
                "user_agent": row.user_agent,
                "ip": row.ip,
            }
            for row in rows
        ],
        "",
    )


@router.post("/repair")
async def repair(request: Request):
    require_admin(request, request.state.db)
    demo_guard()
    # 跑 alembic upgrade head，补齐缺失的表与字段
    try:
        run_migrations(settings.database_url)
    except Exception as exc:
        return fail(f"修复失败：{exc}")
    return ok(msg="修复完毕")


@router.post("/reset")
async def reset(request: Request):
    """重置系统：删掉全部表与安装标记，回到安装向导。不可恢复。"""
    require_admin(request, request.state.db)
    demo_guard()
    # 先结束本请求的事务，否则删表会被这次查询持有的锁挡住
    request.state.db.rollback()
    try:
        reset_system()
    except Exception as exc:
        return fail(f"重置失败：{exc}")
    return ok(msg="已重置")
