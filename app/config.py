"""应用配置。数据库默认 SQLite，设置 DATABASE_URL 可切 PostgreSQL / MySQL。"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
UPLOAD_DIR = BASE_DIR / "uploads"
STATIC_DIR = BASE_DIR / "static"
TEMPLATE_DIR = BASE_DIR / "app" / "templates"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "wTab书签"
    # 唯一版本号来源：站点设置里的 appVersion 也从这里取
    app_version: str = "1.2.5"
    # 兼容原项目常量 app_version_code
    app_version_code: int = 125

    # 监听地址，可写在 .env 里；命令行 --host/--port 优先
    host: str = "0.0.0.0"
    port: int = 8000

    secret_key: str = "change-me-in-production"
    session_cookie: str = "wtab_session"
    session_max_age: int = 60 * 60 * 24 * 15  # 与原项目 token 15 天一致

    database_url: str = f"sqlite:///{(DATA_DIR / 'wtab.db').as_posix()}"

    # 原项目 public/installed.lock 的等价物
    installed_lock: Path = DATA_DIR / "installed.lock"

    # 无人值守安装：.env 里配上就用它建管理员（也可用 WTAB_ADMIN_MAIL / WTAB_ADMIN_PASSWORD 环境变量）
    admin_mail: str = ""
    admin_password: str = ""

    demo_mode: bool = False
    debug: bool = False

    upload_max_mb: int = 20


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()

for _d in (DATA_DIR, UPLOAD_DIR):
    _d.mkdir(parents=True, exist_ok=True)
