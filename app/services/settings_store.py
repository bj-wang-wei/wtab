"""系统设置 KV（setting 表）。对应原项目 SettingModel::Config，缓存 300s。"""
from __future__ import annotations

import time
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Setting

_TTL = 300
_cache: dict[str, str] | None = None
_cache_at = 0.0


def _load(db: Session) -> dict[str, str]:
    global _cache, _cache_at
    if _cache is None or time.monotonic() - _cache_at > _TTL:
        rows = db.execute(select(Setting.keys, Setting.value)).all()
        _cache = {k: v for k, v in rows if v is not None}
        _cache_at = time.monotonic()
    return _cache


def get(db: Session, key: str, default: Any = None) -> Any:
    """取单个设置；空字符串视为未设置（与原项目 systemSetting 的 emptyReplace 行为一致）。"""
    value = _load(db).get(key)
    return value if value else default


def all_settings(db: Session) -> dict[str, str]:
    return dict(_load(db))


def save(db: Session, form: dict[str, Any]) -> None:
    for key, value in form.items():
        if isinstance(value, bool):
            value = "1" if value else "0"
        db.merge(Setting(keys=key, value="" if value is None else str(value)))
    db.commit()
    refresh()


def refresh() -> None:
    global _cache, _cache_at
    _cache = None
    _cache_at = 0.0
