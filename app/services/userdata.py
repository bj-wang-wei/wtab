"""每用户 JSON 文档（link / config / tabbar / user_search_engine）的读写。

原项目里这些都是「一个 user_id 对应一整份 JSON」，没有行时回退到 static/defaultTab.json。
"""
from __future__ import annotations

import json
from functools import lru_cache
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import STATIC_DIR
from app.models import Config, Link, Tabbar, User, UserSearchEngine, now
from app.services import settings_store


@lru_cache
def default_tab() -> dict[str, Any]:
    return json.loads((STATIC_DIR / "defaultTab.json").read_text(encoding="utf-8"))


def default_section(name: str) -> Any:
    """link / tabbar / config 的出厂值。"""
    return default_tab().get(name, [] if name != "config" else {})


def global_default_config(db: Session) -> dict[str, Any]:
    """管理员设置的全局默认主页配置；未设置时回退出厂值。"""
    raw = settings_store.get(db, "globalDefaultConfig")
    value = None
    if raw:
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                value = parsed
        except (ValueError, TypeError):
            pass
    if value is None:
        value = default_section("config")
    theme = value.setdefault("theme", {})
    if not isinstance(theme, dict):
        theme = value["theme"] = {}
    if not theme.get("colorScheme"):
        # 未登录页面（含登录弹窗）没单独设主题时，跟随最近登录的管理员本人的外观设置
        for owner in db.scalars(
            select(User)
            .where(User.manager == 1)
            .order_by(User.login_time.desc(), User.id)
        ):
            cs = (get_doc(db, Config, owner.id).get("theme") or {}).get("colorScheme")
            if cs:
                theme["colorScheme"] = cs
                break
        else:
            theme["colorScheme"] = "auto"
    return value


def _global_list(db: Session, key: str, section: str) -> list[Any]:
    raw = settings_store.get(db, key)
    if raw:
        try:
            value = json.loads(raw)
            if isinstance(value, list):
                return value
        except (ValueError, TypeError):
            pass
    return default_section(section)


def global_default_links(db: Session) -> list[Any]:
    """管理员设置的未登录主页标签；未设置时回退出厂值。"""
    return _global_list(db, "globalDefaultLinks", "link")


def global_default_tabbar(db: Session) -> list[Any]:
    """管理员设置的未登录主页底栏；未设置时回退出厂值。"""
    return _global_list(db, "globalDefaultTabbar", "tabbar")


def _row(db: Session, model, user_id: int):
    return db.scalar(select(model).where(model.user_id == user_id))


# 模型 → (JSON 列名, defaultTab.json 中的 section)
DOCS = {
    Link: ("link", "link"),
    Config: ("config", "config"),
    Tabbar: ("tabs", "tabbar"),
    UserSearchEngine: ("list", None),
}


def _read(row, field: str) -> Any:
    raw = getattr(row, field)
    if raw is None:
        return None
    return json.loads(raw) if isinstance(raw, str) else raw


def _write(db: Session, model, user_id: int, value: Any) -> None:
    field = DOCS[model][0]
    row = _row(db, model, user_id)
    payload = json.dumps(value, ensure_ascii=False)
    if row is None:
        row = model(user_id=user_id, **{field: payload})
        db.add(row)
    else:
        setattr(row, field, payload)
    if model is Link or model is Tabbar:
        row.update_time = now()
    db.commit()


def get_doc(db: Session, model, user_id: int) -> Any:
    """有个人数据返回个人数据，否则返回出厂默认值。"""
    field, section = DOCS[model]
    row = _row(db, model, user_id)
    value = _read(row, field) if row is not None else None
    if value is None or (isinstance(value, list) and not value):
        return default_section(section) if section else value
    return value


def save_doc(db: Session, model, user_id: int, value: Any) -> None:
    _write(db, model, user_id, value)


def reset_user(db: Session, user_id: int) -> None:
    """原 Link::reset：删掉个人 link / tabbar / config / search engine，回到出厂默认。"""
    for model in (Link, Tabbar, Config, UserSearchEngine):
        row = _row(db, model, user_id)
        if row is not None:
            db.delete(row)
    db.commit()
