"""站点级设置（页面 <head> 注入、隐私页共用）。"""
from __future__ import annotations

from typing import Any

from app.services import settings_store

DEFAULTS: dict[str, str] = {
    "title": "wTab书签",
    "keywords": "wTab,书签,新标签页,导航",
    "description": "wTab书签 - 一个好用的新标签页书签导航",
    "logo": "/static/wtab.png",
    "favicon": "",
    "copyright": "本项目基于 MIT License 协议，Copyright (c) 2026 Vin。",
    "recordNumber": "",
    "mobileRecordNumber": "0",
    "beianMps": "",
    "user_register": "0",
    "loginCloseRecordNumber": "0",
    "email": "",
    "qqGroup": "",
    "customAbout": "",
    "appName": "wTab书签",
    "appVersion": "1.0.0",
    "appDesc": "一个安静的浏览器起始页：书签、分类、壁纸和搜索引擎都放在一屏里。",
    "appLinks": 'GitHub:https://github.com/|运行状态:/health',
    "aboutMe": '''<p style="margin:0 0 4px;">Wtab 书签 © 2025 — 开源、轻量、安静。</p>
<p style="margin:0;font-size:12px;opacity:.6;">基于 MIT License 协议，欢迎 Star ⭐</p>''',
    "privacy": "",
    "smtp_host": "smtp.qq.com",
    "smtp_port": "465",
    "smtp_email": "bj0_0@hotmail.com",
    "smtp_password": "",
    "smtp_code_template": '''<div style="max-width:520px;margin:0 auto;font-family:sans-serif;color:#333">
  <h3 style="color:#141414">动态令牌</h3>
  <p>您的验证码是：<b style="color:#1e9fff">{$code}</b>。5分钟内有效，请尽快验证。</p>
  <p style="color:#999;font-size:12px">{$time}</p>
</div>''',
    "mail_use_resend": "0",
}


def page_meta(db) -> dict[str, Any]:
    """模板需要的最小集合。customHead 是管理后台允许插入的原样 HTML。"""
    meta = {k: settings_store.get(db, k, v) for k, v in DEFAULTS.items()}
    meta["favicon_url"] = meta["favicon"] or meta["logo"] or "/favicon.ico"
    meta["copyright"] = meta["copyright"] or DEFAULTS["copyright"]
    return meta
