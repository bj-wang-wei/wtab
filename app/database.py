from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import settings

connect_args = {}
if settings.database_url.startswith("sqlite"):
    connect_args["check_same_thread"] = False

engine = create_engine(settings.database_url, pool_pre_ping=True, connect_args=connect_args)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def reconfigure(url: str) -> None:
    """安装向导切换数据库后热替换引擎，免重启。"""
    global engine, connect_args
    connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
    engine.dispose()
    engine = create_engine(url, pool_pre_ping=True, connect_args=connect_args)
    SessionLocal.configure(bind=engine)


def get_db() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
