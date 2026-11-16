"""用户与认证接口，路径与参数沿用原项目 app/controller/User.php。"""
from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.deps import AuthError, client_ip, current_user, params, require_admin, require_user
from app.models import Token, User, UserGroup, now
from app.response import fail, ok
from app.routers import captcha
from app.security import (
    check_code,
    consume_code,
    gen_code,
    is_locked,
    lock_account,
    md5,
    new_token,
    save_code,
    unlock_account,
    valid_email,
)
from app.services import mailer, settings_store
from app.templating import templates

router = APIRouter()


def _db(request: Request) -> Session:
    return request.state.db


def _issue_token(request: Request, db: Session, user: User) -> dict:
    """写 token 表供浏览器扩展等旧客户端使用，同时写会话 Cookie（本应用页面用）。"""
    token = new_token(user.id)
    db.add(
        Token(
            user_id=user.id,
            token=token,
            create_time=int(now().timestamp()),
            ip=client_ip(request),
            user_agent=(request.headers.get("user-agent") or "")[:250],
        )
    )
    db.commit()
    request.session["user_id"] = user.id
    return {"user_id": user.id, "token": token, "create_time": int(now().timestamp())}


def _user_json(user: User, with_secret: bool = False) -> dict:
    data = {
        "id": user.id,
        "mail": user.mail,
        "manager": user.manager,
        "nickname": user.nickname,
        "avatar": user.avatar,
        "qqBind": bool(user.qq_open_id),
        "active": user.active,
    }
    if with_secret:
        data.update({"status": user.status, "group_id": user.group_id, "create_time": user.create_time})
    return data


@router.post("/user/login")
async def login(request: Request):
    form = await params(request)
    db = _db(request)
    mail = str(form.get("username") or form.get("mail") or "").strip()
    password = str(form.get("password") or "").strip()
    code = str(form.get("code") or "").strip()

    if is_locked(mail):
        return fail("账号已被安全锁定,您可以修改密码然后登录")
    if not captcha.verify(request, code):
        return fail("验证码错误或已过期")
    user = db.query(User).filter(User.mail == mail).first()
    if not user:
        return fail("账号不存在")
    if user.login_fail_count == 10:
        lock_account(mail)
        user.login_fail_count = 0
        db.commit()
        return fail("账号已被锁定2小时")
    if user.password != md5(password):
        user.login_fail_count += 1
        db.commit()
        return fail("账号不存在或密码错误")
    if user.status == 1:
        return fail("账号已被冻结")

    auth = _issue_token(request, db, user)
    user.login_ip = client_ip(request)
    user.login_time = now()
    user.active = now().strftime("%Y-%m-%d")
    user.login_fail_count = 0
    db.commit()
    return ok(auth, "登录成功")


@router.post("/user/register")
async def register(request: Request):
    form = await params(request)
    db = _db(request)
    if settings_store.get(db, "user_register", "0") == "1":
        return fail("管理员已关闭用户注册功能")

    mail = str(form.get("username") or form.get("mail") or "").strip()
    password = str(form.get("password") or "").strip()
    code = str(form.get("code") or "")
    if not mail or not password:
        return fail("注册失败")
    if not valid_email(mail):
        return fail("邮箱格式错误")
    if len(password) < 6:
        return fail("密码过短")
    if not check_code(mail, code):
        return fail("验证码错误")
    if db.query(User).filter(User.mail == mail).first():
        return fail("账号已存在")

    db.add(User(mail=mail, password=md5(password), create_time=now(), register_ip=client_ip(request), status=0))
    db.commit()
    consume_code(mail)
    return ok(msg="ok")


@router.post("/user/forgetPass")
async def forget_pass(request: Request):
    form = await params(request)
    db = _db(request)
    mail = str(form.get("username") or form.get("mail") or "").strip()
    password = str(form.get("password") or "").strip()
    code = str(form.get("code") or "")
    if not mail or not password:
        return fail("修改失败")
    if not valid_email(mail):
        return fail("邮箱格式错误")
    if len(password) < 6:
        return fail("密码过短")
    user = db.query(User).filter(User.mail == mail).first()
    if not user:
        return fail("账号不存在")
    if not check_code(mail, code):
        return fail("验证码错误")

    user.password = md5(password)
    db.query(Token).filter(Token.user_id == user.id).delete()
    db.commit()
    consume_code(mail)
    unlock_account(mail)
    return ok(msg="ok")


@router.post("/user/newMail")
async def new_mail(request: Request):
    form = await params(request)
    db = _db(request)
    user = require_user(request, db)
    mail = str(form.get("mail") or "").strip()
    code = str(form.get("code") or "")
    if not mail or not code:
        return fail("请认真填写表单")
    if not valid_email(mail):
        return fail("邮箱格式错误")
    if db.query(User).filter(User.mail == mail).first():
        return fail("该邮箱已被使用！")
    if not check_code(mail, code):
        return fail("验证码错误")
    user.mail = mail
    db.commit()
    consume_code(mail)
    return ok(msg="修改成功")


@router.post("/user/loginOut")
async def login_out(request: Request):
    db = _db(request)
    uid = request.session.get("user_id")
    token = request.headers.get("token") or request.cookies.get("token")
    if uid:
        db.query(Token).filter(Token.user_id == uid, Token.token == token).delete()
        db.commit()
    request.session.pop("user_id", None)
    return ok(msg="ok")


@router.post("/user/get")
async def get_user(request: Request):
    db = _db(request)
    user = require_user(request, db)
    today = now().strftime("%Y-%m-%d")
    if user.active != today:
        user.active = today
        db.commit()
    return ok(_user_json(user, with_secret=True), "ok")


@router.post("/user/updateInfo")
async def update_info(request: Request):
    form = await params(request)
    db = _db(request)
    user = require_user(request, db)
    field = str(form.get("field") or "")
    value = form.get("value")
    if field in ("nickname", "avatar") and value not in (None, ""):
        setattr(user, field, str(value))
        db.commit()
    return ok(msg="修改成功")


@router.post("/user/changePassword")
async def change_password(request: Request):
    form = await params(request)
    db = _db(request)
    user = require_user(request, db)
    old = str(form.get("old") or "").strip()
    new_pw = str(form.get("new") or "").strip()
    if not old or not new_pw:
        return fail("请填写完整")
    if len(new_pw) < 6:
        return fail("密码至少 6 位")
    if md5(old) != user.password:
        return fail("原密码错误")
    user.password = md5(new_pw)
    db.commit()
    return ok(msg="密码已修改")


@router.post("/user/unbindQQ")
async def unbind_qq(request: Request):
    db = _db(request)
    user = require_user(request, db)
    if not user.mail:
        return fail("请先绑定邮箱后再解绑")
    user.qq_open_id = None
    db.commit()
    return ok(_user_json(user), "解绑成功")


@router.post("/api/getMailCode")
async def get_mail_code(request: Request):
    """原项目在 Api 控制器，路径保持 /api/getMailCode。"""
    form = await params(request)
    db = _db(request)
    mail = str(form.get("mail") or "").strip()
    if not valid_email(mail):
        return fail("邮箱格式错误")
    code = gen_code()
    try:
        mailer.send(db, mail, mailer.code_html(db, code, now().strftime("%Y-%m-%d %H:%M:%S")))
    except Exception as exc:
        return fail(f"发送失败：{exc}")
    save_code(mail, code)
    return ok(msg="发送成功")


# ---------- 用户分组（管理员） ----------


@router.post("/user/UserGroup")
async def user_group(request: Request):
    db = _db(request)
    require_admin(request, db)
    rows = db.query(UserGroup).order_by(UserGroup.sort.desc()).all()
    return ok(
        [
            {"id": r.id, "name": r.name, "sort": r.sort, "create_time": r.create_time}
            for r in rows
        ],
        "ok",
    )


@router.post("/user/createGroup")
async def create_group(request: Request):
    form = await params(request)
    db = _db(request)
    require_admin(request, db)
    op = str(form.get("type") or "")
    info = form.get("info") or {}
    if not isinstance(info, dict):
        raise AuthError("参数错误")

    if op == "edit":
        group_id = int(info.get("id") or 0)
        if group_id > 0:
            group = db.get(UserGroup, group_id)
            if group:
                group.name = str(info.get("name") or group.name)
        else:
            db.add(UserGroup(name=str(info.get("name") or ""), create_time=now(), sort=int(info.get("sort") or 0)))
    elif op == "del":
        group_id = int(form.get("id") or 0)
        group = db.get(UserGroup, group_id)
        if group:
            db.delete(group)
            db.query(User).filter(User.group_id == group_id).update({User.group_id: 0})
    db.commit()
    return ok(msg="处理完毕！")


@router.post("/user/sortGroup")
async def sort_group(request: Request):
    form = await params(request)
    db = _db(request)
    require_admin(request, db)
    for key, value in form.items():
        if isinstance(value, dict) and value.get("id"):
            db.query(UserGroup).filter(UserGroup.id == int(value["id"])).update(
                {UserGroup.sort: int(value.get("sort") or 0)}
            )
    db.commit()
    return ok(msg="ok")


