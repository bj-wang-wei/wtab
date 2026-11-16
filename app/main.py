"""Wtab 书签 — 一体式 Web 应用（页面渲染 + 业务逻辑 + API + 静态资源）。"""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from app.config import STATIC_DIR, UPLOAD_DIR, settings
from app.database import SessionLocal
from app.deps import AuthError
from app.response import fail

# 未安装时允许访问的路径前缀
_OPEN_PREFIXES = ("/install", "/static", "/uploads", "/images", "/health", "/favicon", "/captcha", "/v1")


def is_installed() -> bool:
    """等价于原项目 public/installed.lock 的存在性判断。"""
    return settings.installed_lock.exists()


@asynccontextmanager
async def lifespan(app: FastAPI):
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    yield


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    debug=settings.debug,
    docs_url="/docs" if settings.debug else None,
    redoc_url=None,
    lifespan=lifespan,
)

app.add_middleware(
    SessionMiddleware,
    secret_key=settings.secret_key,
    session_cookie=settings.session_cookie,
    max_age=settings.session_max_age,
    same_site="lax",
)


@app.middleware("http")
async def install_gate(request: Request, call_next):
    """未安装 → 全部重定向到安装向导（对应原项目 AppService 的拦截）。"""
    path = request.url.path
    if not is_installed() and not path.startswith(_OPEN_PREFIXES):
        return RedirectResponse("/install", status_code=302)
    return await call_next(request)


@app.middleware("http")
async def cache_control(request: Request, call_next):
    """静态资源每次都协商缓存（ETag/304），避免改了样式浏览器还拿旧文件。"""
    response = await call_next(request)
    if request.url.path.startswith("/static"):
        response.headers["Cache-Control"] = "no-cache"
    if request.url.path in ("/", "/guest", "/manager", "/install") and "text/html" in response.headers.get("content-type", ""):
        response.headers["Cache-Control"] = "no-cache"
    return response


@app.middleware("http")
async def db_session(request: Request, call_next):
    """每请求一个 Session，挂在 request.state.db 上供路由使用。"""
    db = SessionLocal()
    request.state.db = db
    try:
        return await call_next(request)
    finally:
        db.close()


@app.exception_handler(AuthError)
async def auth_error_handler(request: Request, exc: AuthError):
    return fail(str(exc))


app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
# 上传目录同时挂在 /images（原项目路径形状，既有库里的路径可直接用）与 /uploads
app.mount("/images", StaticFiles(directory=str(UPLOAD_DIR)), name="images")
app.mount("/uploads", StaticFiles(directory=str(UPLOAD_DIR)), name="uploads")

from app.routers import admin as admin_router  # noqa: E402
from app.routers import api as api_router  # noqa: E402
from app.routers import captcha as captcha_router  # noqa: E402
from app.routers import config as config_router  # noqa: E402
from app.routers import file as file_router  # noqa: E402
from app.routers import install as install_router  # noqa: E402
from app.routers import link as link_router  # noqa: E402
from app.routers import note as note_router  # noqa: E402
from app.routers import pages as pages_router  # noqa: E402
from app.routers import searchengine as searchengine_router  # noqa: E402
from app.routers import setting as setting_router  # noqa: E402
from app.routers import tabbar as tabbar_router  # noqa: E402
from app.routers import user as user_router  # noqa: E402
from app.routers import wallpaper as wallpaper_router  # noqa: E402

app.include_router(install_router.router)
app.include_router(pages_router.router)
app.include_router(user_router.router)
app.include_router(captcha_router.router)
app.include_router(link_router.router)
app.include_router(config_router.router)
app.include_router(tabbar_router.router)
app.include_router(searchengine_router.router)
app.include_router(note_router.router)
app.include_router(wallpaper_router.router)
app.include_router(file_router.router)
app.include_router(api_router.router)
app.include_router(admin_router.router)
app.include_router(setting_router.router)


@app.get("/v1/models")
async def openai_models():
    """OpenAI 兼容探测端点：本服务不提供模型，返回空列表而不是 404。"""
    return {"object": "list", "data": []}


@app.get("/health")
async def health(request: Request):
    return {
        "code": 1,
        "msg": "ok",
        "data": {
            "app": settings.app_name,
            "version": settings.app_version,
            "installed": is_installed(),
            "debug": settings.debug,
        },
    }
