"""容器无人值守安装：设置了 WTAB_ADMIN_MAIL / WTAB_ADMIN_PASSWORD 时自动完成安装。

未设置（或已安装）时什么都不做，仍可走网页安装向导 /install。
"""
from __future__ import annotations

import os

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.config import settings
from app.models import User
from app.services import installer, seed


def ensure_admin(mail: str, password: str) -> None:
    """已安装的实例：.env 配的管理员不存在时补建（不改动已有账号的密码）。"""
    if not mail or not password:
        return
    engine = create_engine(settings.database_url)
    try:
        with Session(engine) as db:
            if db.query(User).filter(User.mail == mail).first():
                print(f"[autoinstall] admin exists: {mail}")
                return
            installer.create_admin(db, mail, password)
            print(f"[autoinstall] admin created: {mail}")
    finally:
        engine.dispose()


def main() -> None:
    # .env 的 ADMIN_MAIL/ADMIN_PASSWORD 优先，兼容容器里的 WTAB_ADMIN_* 环境变量
    mail = settings.admin_mail or os.environ.get("WTAB_ADMIN_MAIL", "")
    password = settings.admin_password or os.environ.get("WTAB_ADMIN_PASSWORD", "")

    if settings.installed_lock.exists():
        ensure_admin(mail, password)
        return
    if not mail or not password:
        print("[autoinstall] skip (ADMIN_MAIL/ADMIN_PASSWORD not set)")
        return

    url = os.environ.get("DATABASE_URL") or settings.database_url
    installer.run_migrations(url)
    engine = create_engine(url)
    try:
        with Session(engine) as db:
            seed.seed_defaults(db)
            installer.create_admin(db, mail, password)
    finally:
        engine.dispose()

    # DATABASE_URL 由外部注入时不覆盖 .env（避免把容器内地址固化）
    if not os.environ.get("DATABASE_URL"):
        installer.write_env(url)
    settings.installed_lock.parent.mkdir(parents=True, exist_ok=True)
    settings.installed_lock.write_text("installed", encoding="utf-8")
    print(f"[autoinstall] installed to {url}")


if __name__ == "__main__":
    main()
