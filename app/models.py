"""SQLAlchemy 2.0 模型。对应原项目 install.sql 的表，去掉 card / plugins_todo / plugins_todo_folder。

字段名、类型尽量与原库一致，便于直接接管既有 wtab 数据库。
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import (
    BigInteger,
    DateTime,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects import mysql
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

# 原项目主键为 bigint auto_increment；SQLite 只有 INTEGER PRIMARY KEY 才能自增
BigIntPK = BigInteger().with_variant(Integer, "sqlite")
# link / config / tabs 等存整份 JSON，MySQL 的 TEXT 只有 64KB，用 MEDIUMTEXT
LongText = Text().with_variant(mysql.MEDIUMTEXT(), "mysql")

# 原项目用 date('Y-m-d H:i:s') 写本地时间（Asia/Shanghai）。
# Windows 自带不带 IANA 时区库，缺 tzdata 时 ZoneInfo 会抛错，这里回退到固定 +08:00。
try:
    TZ = ZoneInfo("Asia/Shanghai")
except Exception:  # noqa: BLE001 - 任何 tzdata 缺失都退回固定偏移
    TZ = timezone(timedelta(hours=8))


def now() -> datetime:
    """原项目用 date('Y-m-d H:i:s') 写本地时间，这里保持一致（naive 本地时间）。"""
    return datetime.now(TZ).replace(tzinfo=None, microsecond=0)


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "user"

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    avatar: Mapped[str | None] = mapped_column(String(255))
    mail: Mapped[str | None] = mapped_column(String(255))
    password: Mapped[str | None] = mapped_column(String(64))
    create_time: Mapped[datetime | None] = mapped_column(DateTime)
    login_ip: Mapped[str | None] = mapped_column(String(255))
    register_ip: Mapped[str | None] = mapped_column(String(255))
    manager: Mapped[int] = mapped_column(Integer, default=0)
    login_fail_count: Mapped[int] = mapped_column(Integer, default=0)
    login_time: Mapped[datetime | None] = mapped_column(DateTime)
    qq_open_id: Mapped[str | None] = mapped_column(String(255))
    nickname: Mapped[str | None] = mapped_column(String(255))
    status: Mapped[int] = mapped_column(Integer, default=0)  # 0 正常 1 冻结
    active: Mapped[str | None] = mapped_column(String(64))
    group_id: Mapped[int] = mapped_column(Integer, default=0)

    __table_args__ = (
        UniqueConstraint("mail", name="user_mail"),
        UniqueConstraint("qq_open_id", name="user_qq_open_id"),
    )


class Token(Base):
    __tablename__ = "token"

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    user_id: Mapped[int | None] = mapped_column(BigInteger)
    token: Mapped[str | None] = mapped_column(String(64))
    create_time: Mapped[int | None] = mapped_column(BigInteger)  # 秒级时间戳
    ip: Mapped[str | None] = mapped_column(String(255))
    user_agent: Mapped[str | None] = mapped_column(String(255))
    access_token: Mapped[str | None] = mapped_column(String(255))

    __table_args__ = (Index("token_user_id", "user_id"),)


class UserGroup(Base):
    __tablename__ = "user_group"

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    name: Mapped[str | None] = mapped_column(String(255))
    create_time: Mapped[datetime | None] = mapped_column(DateTime)
    sort: Mapped[int] = mapped_column(Integer, default=0)


class Link(Base):
    """每个用户一份整书签 JSON。"""

    __tablename__ = "link"

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    user_id: Mapped[int | None] = mapped_column(BigInteger)
    update_time: Mapped[datetime | None] = mapped_column(DateTime)
    link: Mapped[str | None] = mapped_column(LongText)

    __table_args__ = (Index("link_user_id", "user_id"),)


class History(Base):
    """书签备份，只保留最近 50 条。"""
    __tablename__ = "history"

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    user_id: Mapped[int | None] = mapped_column(BigInteger)
    link: Mapped[str | None] = mapped_column(LongText)
    create_time: Mapped[datetime | None] = mapped_column(DateTime)

    __table_args__ = (Index("history_user_id", "user_id"),)


class LinkClick(Base):
    """书签点击计数，用于后台热度榜。"""

    __tablename__ = "link_click"

    url: Mapped[str] = mapped_column(String(512), primary_key=True)
    name: Mapped[str | None] = mapped_column(String(255))
    count: Mapped[int] = mapped_column(BigInteger, default=0)
    last_time: Mapped[datetime | None] = mapped_column(DateTime)


class Config(Base):
    """每用户界面配置 JSON。"""
    __tablename__ = "config"

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    user_id: Mapped[int | None] = mapped_column(BigInteger)
    config: Mapped[str | None] = mapped_column(LongText)

    __table_args__ = (Index("config_user_id", "user_id"),)


class Tabbar(Base):
    __tablename__ = "tabbar"

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    user_id: Mapped[int | None] = mapped_column(BigInteger)
    tabs: Mapped[str | None] = mapped_column(LongText)
    update_time: Mapped[datetime | None] = mapped_column(DateTime)


class UserSearchEngine(Base):
    __tablename__ = "user_search_engine"

    user_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    list: Mapped[str | None] = mapped_column(LongText)


class SearchEngine(Base):
    __tablename__ = "search_engine"

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    name: Mapped[str | None] = mapped_column(String(255))
    icon: Mapped[str | None] = mapped_column(String(255))
    url: Mapped[str | None] = mapped_column(String(255))  # 含 {1} 占位符
    sort: Mapped[int] = mapped_column(Integer, default=0)
    create_time: Mapped[datetime | None] = mapped_column(DateTime)
    status: Mapped[int] = mapped_column(Integer, default=1)
    tips: Mapped[str | None] = mapped_column(String(255))


class Note(Base):
    __tablename__ = "note"

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    user_id: Mapped[int | None] = mapped_column(BigInteger)
    title: Mapped[str | None] = mapped_column(String(255))
    text: Mapped[str | None] = mapped_column(LongText)
    create_time: Mapped[datetime | None] = mapped_column(DateTime)
    update_time: Mapped[datetime | None] = mapped_column(DateTime)
    weight: Mapped[int] = mapped_column(Integer, default=0)
    sort: Mapped[int] = mapped_column(Integer, default=0)

    __table_args__ = (Index("note_user_id", "user_id"),)


class Wallpaper(Base):
    __tablename__ = "wallpaper"

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    type: Mapped[int] = mapped_column(Integer, default=0)  # 1 文件夹 0 资源
    folder: Mapped[str | None] = mapped_column(String(255))
    mime: Mapped[int] = mapped_column(Integer, default=0)  # 0 图片 1 视频
    url: Mapped[str | None] = mapped_column(String(255))
    cover: Mapped[str | None] = mapped_column(String(255))
    create_time: Mapped[datetime | None] = mapped_column(DateTime)
    name: Mapped[str | None] = mapped_column(String(255))
    sort: Mapped[int] = mapped_column(Integer, default=0)


class File(Base):
    __tablename__ = "file"

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    path: Mapped[str | None] = mapped_column(String(255))
    user_id: Mapped[int | None] = mapped_column(BigInteger)
    create_time: Mapped[datetime | None] = mapped_column(DateTime)
    size: Mapped[int | None] = mapped_column(BigInteger)
    mime_type: Mapped[str | None] = mapped_column(String(255))
    hash: Mapped[str | None] = mapped_column(String(255))


class Setting(Base):
    """系统设置 KV（原库主键列名就叫 keys）。"""

    __tablename__ = "setting"

    keys: Mapped[str] = mapped_column(String(255), primary_key=True)
    value: Mapped[str | None] = mapped_column(Text)
