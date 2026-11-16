"""初始数据与用户默认数据（对应原项目 defaultData.sql 的 search_engine / wallpaper）。

不显式写主键，避免 PostgreSQL 序列不同步的问题；原库中的 id 仅用于顺序，这里用插入顺序代替。
"""
from __future__ import annotations

import json

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import STATIC_DIR
from app.models import Config, Link, SearchEngine, Tabbar, Wallpaper, now

# (name, icon, url, sort, tips)
SEARCH_ENGINES = [
    ("百度", "/static/searchEngine/baidu.svg", "https://www.baidu.com/s?wd={1}", 0, "中国领先的搜索引擎和互联网公司，提供全球最大的中文搜索引擎服务"),
    ("必应", "/static/searchEngine/bing.svg", "https://www.bing.com/search?q={1}", 99, "微软推出的搜索引擎，以直观的界面和优质搜索结果而闻名"),
    ("Google", "/static/searchEngine/google.svg", "https://www.google.com/search?q={1}", 98, "全球最大的搜索引擎"),
    ("搜狗", "/static/searchEngine/sougou.svg", "https://www.sogou.com/web?query={1}", 0, "中国领先的搜索引擎"),
    ("360", "/static/searchEngine/360.svg", "https://www.so.com/s?q={1}", 0, "中国知名搜索引擎，注重用户隐私安全"),
    ("开发者搜索", "/static/searchEngine/baidudev.png", "https://kaifa.baidu.com/searchPage?module=SEARCH&wd={1}", 0, "专注于技术文档、API 和开发者资源的搜索引擎"),
    ("B站", "/static/searchEngine/bilibiliico.png", "https://search.bilibili.com/all?keyword={1}", 0, "中国弹幕视频平台"),
    ("微博", "/static/searchEngine/weiboico.png", "https://s.weibo.com/weibo?q={1}", 0, "中国社交媒体平台"),
]

DEFAULT_FOLDER = "默认壁纸"
# 缩略图与背景统一用 wallpaper-N（不再使用 m_wallpaper-*）
WALLPAPERS = [
    "/static/wallpaper/wallpaper-1.jpeg",
    "/static/wallpaper/wallpaper-2.jpeg",
    "/static/wallpaper/wallpaper-3.jpeg",
    "/static/wallpaper/wallpaper-4.jpeg",
    "/static/wallpaper/wallpaper-5.jpeg",
]


def seed_defaults(db: Session) -> None:
    """首次安装写入系统搜索引擎、壁纸、公共链接库。"""
    if not db.scalar(select(func.count()).select_from(SearchEngine)):
        db.add_all(
            SearchEngine(name=n, icon=ic, url=u, sort=s, create_time=now(), status=1, tips=t)
            for n, ic, u, s, t in SEARCH_ENGINES
        )
    if not db.scalar(select(func.count()).select_from(Wallpaper)):
        folder = Wallpaper(type=1, folder=None, mime=0, url=None, cover=None, create_time=now(), name=DEFAULT_FOLDER, sort=999)
        db.add(folder)
        db.flush()  # 取到文件夹 id 后再挂壁纸
        db.add_all(
            Wallpaper(type=0, folder=str(folder.id), mime=0, url=u, cover=None, create_time=now(), name=None, sort=999)
            for u in WALLPAPERS
        )
    db.commit()
    seed_global_defaults(db)


def seed_global_defaults(db: Session) -> None:
    """初始化：把 static/defaultTab.json 写入全局默认键（已存在则不覆盖）。"""
    from app.services import settings_store
    from app.services.userdata import default_tab

    default = default_tab()
    for section, key in (
        ("link", "globalDefaultLinks"),
        ("config", "globalDefaultConfig"),
        ("tabbar", "globalDefaultTabbar"),
    ):
        if not settings_store.get(db, key):
            settings_store.save(db, {key: json.dumps(default[section], ensure_ascii=False)})


def ensure_user_data(db: Session, user_id: int) -> None:
    """新用户首次访问时，从 static/defaultTab.json 初始化书签 / 配置 / 导航栏（原项目 Config::index 同逻辑）。"""
    if db.scalar(select(func.count()).where(Link.user_id == user_id).select_from(Link)):
        return
    from app.services.userdata import global_default_config

    default = json.loads((STATIC_DIR / "defaultTab.json").read_text(encoding="utf-8"))
    config = global_default_config(db)
    db.add(Link(user_id=user_id, link=json.dumps(default["link"], ensure_ascii=False), update_time=now()))
    db.add(Config(user_id=user_id, config=json.dumps(config, ensure_ascii=False)))
    db.add(Tabbar(user_id=user_id, tabs=json.dumps(default["tabbar"], ensure_ascii=False), update_time=now()))
    db.commit()
