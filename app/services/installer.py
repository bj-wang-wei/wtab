"""安装流程：测试连接 → 建表（Alembic）→ 初始数据 → 管理员 → 写 .env + installed.lock。"""
from __future__ import annotations

import hashlib
import re
import secrets
from urllib.parse import quote_plus

from alembic import command
from alembic.config import Config as AlembicConfig
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from app.config import BASE_DIR, DATA_DIR, get_settings, settings
from app.models import User, now
from app.services import seed, settings_store

DB_TYPES = ("sqlite", "mysql", "postgresql")


class InstallError(Exception):
    pass


def md5(raw: str) -> str:
    """原项目用 md5(明文) 存密码，为兼容既有数据库继续沿用。"""
    return hashlib.md5(raw.encode("utf-8")).hexdigest()


def build_url(form: dict) -> str:
    db_type = str(form.get("db_type") or "sqlite").lower()
    if db_type not in DB_TYPES:
        raise InstallError(f"不支持的数据库类型：{db_type}")
    if db_type == "sqlite":
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        name = re.sub(r"[^A-Za-z0-9_-]", "_", str(form.get("table_name") or "wtab"))
        return f"sqlite:///{(DATA_DIR / (name + '.db')).as_posix()}"

    host = form.get("db_host") or "127.0.0.1"
    port = str(form.get("db_port") or (5432 if db_type == "postgresql" else 3306))
    name = re.sub(r"[^A-Za-z0-9_-]", "_", str(form.get("table_name") or "wtab"))
    user = quote_plus(str(form.get("db_username") or ""))
    password = quote_plus(str(form.get("db_password") or ""))
    auth = f"{user}:{password}@" if user else ""
    if db_type == "postgresql":
        return f"postgresql+psycopg://{auth}{host}:{port}/{name}"
    return f"mysql+pymysql://{auth}{host}:{port}/{name}?charset=utf8mb4"


def _engine(url: str):
    """非 sqlite 的连接加 5 秒超时，避免向导页卡住不返回。"""
    kw: dict = {"pool_pre_ping": True}
    if not url.startswith("sqlite"):
        kw["connect_args"] = {"connect_timeout": 5}
    return create_engine(url, **kw)


def _friendly(exc: Exception, url: str) -> str:
    """把驱动层异常翻成向导能看懂的话；认不出的保留原文（去掉 SQLAlchemy 的文档链接尾巴）。"""
    raw = str(exc)
    low = raw.lower()
    try:
        u = make_url(url)
        target = f"{u.host}:{u.port}" if u.host else "数据库服务器"
        dbname = u.database or "目标库"
    except Exception:  # shortcut: url 已由 build_url 生成，解析失败就退回泛称
        target, dbname = "数据库服务器", "目标库"
    if "1045" in raw or "access denied" in low or "password authentication failed" in low:
        return "数据库用户名或密码错误。"
    if "1049" in raw or "unknown database" in low or ("database" in low and "does not exist" in low):
        return f"数据库 {dbname} 不存在，点「开始安装」会自动创建。"
    if "10061" in raw or "2003" in raw or "2002" in raw or "2005" in raw or "connection refused" in low or "can't connect" in low or "could not connect" in low:
        return f"无法连接到 {target}：目标拒绝连接。请确认数据库服务已启动、端口正确、防火墙已放行。"
    if "timed out" in low or "timeout" in low:
        return f"连接 {target} 超时，请检查主机地址和网络。"
    return re.sub(r"\s*\(Background on this error at: \S+\)", "", raw).strip() or "连接失败"


def ensure_database(url: str) -> None:
    """目标库不存在就自动创建；sqlite 由驱动建文件，跳过。"""
    u = make_url(url)
    backend = u.get_backend_name()
    if backend == "sqlite":
        return
    name = u.database
    # 建库要连服务器自身的系统库：MySQL 不指定库，PostgreSQL 连 postgres。
    # 注意 URL.set(database=None) 是 no-op，清空库名必须用 _replace。
    server = u._replace(database=None) if backend == "mysql" else u.set(database="postgres")
    engine = _engine(server.render_as_string(hide_password=False))
    try:
        if backend == "mysql":
            with engine.connect() as conn:
                conn.execute(text(f"CREATE DATABASE IF NOT EXISTS `{name}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"))
                conn.commit()
        else:
            with engine.connect() as conn:
                exists = conn.execute(text("select 1 from pg_database where datname = :n"), {"n": name}).first()
            if not exists:
                # CREATE DATABASE 不能跑在事务里
                with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
                    conn.execute(text(f'CREATE DATABASE "{name}"'))
    except Exception as exc:
        raise InstallError(f"自动创建数据库 {name} 失败：{_friendly(exc, url)}") from exc
    finally:
        engine.dispose()


def test_connection(url: str) -> None:
    try:
        engine = _engine(url)
        with engine.connect() as conn:
            conn.execute(text("select 1"))
        engine.dispose()
    except Exception as exc:
        raise InstallError(_friendly(exc, url)) from exc


def run_migrations(url: str) -> None:
    cfg = AlembicConfig(str(BASE_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BASE_DIR / "alembic"))
    cfg.attributes["sqlalchemy_url"] = url
    command.upgrade(cfg, "head")


def reset_system() -> None:
    """清空全部数据并移除安装标记：之后的请求会回到安装向导。"""
    cfg = AlembicConfig(str(BASE_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BASE_DIR / "alembic"))
    cfg.attributes["sqlalchemy_url"] = settings.database_url
    command.downgrade(cfg, "base")
    settings.installed_lock.unlink(missing_ok=True)


def create_admin(db: Session, mail: str, password: str) -> None:
    if not mail or not password:
        raise InstallError("管理员邮箱和密码不能为空")
    if db.query(User).filter(User.mail == mail).first():
        raise InstallError("该邮箱已存在")
    db.add(User(mail=mail, password=md5(password), create_time=now(), manager=1, login_fail_count=0, status=0,
                avatar="/static/avatar/presets/01.png"))
    db.commit()


def write_env(url: str) -> str:
    """把 DATABASE_URL / SECRET_KEY 固化到 .env，并让当前进程立即生效（无需重启）。"""
    secret_key = settings.secret_key
    if secret_key == "change-me-in-production":
        secret_key = secrets.token_urlsafe(32)
    env_file = BASE_DIR / ".env"
    kept = []
    if env_file.exists():
        kept = [
            line
            for line in env_file.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.startswith(("DATABASE_URL=", "SECRET_KEY="))
        ]
    env_file.write_text("\n".join([*kept, f"DATABASE_URL={url}", f"SECRET_KEY={secret_key}"]) + "\n", encoding="utf-8")

    settings.database_url = url
    settings.secret_key = secret_key
    get_settings.cache_clear()

    from app import database

    database.reconfigure(url)
    return secret_key


def install(form: dict) -> str:
    url = build_url(form)
    ensure_database(url)
    test_connection(url)
    run_migrations(url)
    engine = _engine(url)
    try:
        with Session(engine) as db:
            seed.seed_defaults(db)
            create_admin(db, str(form.get("admin_email") or ""), str(form.get("admin_password") or ""))
            # 向导里填的站点配置写入 setting，其余键继续走 site.DEFAULTS 回退
            site_cfg = {
                "title": str(form.get("site_title") or "").strip(),
                "description": str(form.get("site_desc") or "").strip(),
                "user_register": "1" if form.get("user_register") in (True, "1", "on") else "0",
            }
            settings_store.save(db, {k: v for k, v in site_cfg.items() if v})
    finally:
        engine.dispose()
    write_env(url)
    settings.installed_lock.parent.mkdir(parents=True, exist_ok=True)
    settings.installed_lock.write_text("installed", encoding="utf-8")
    return url
