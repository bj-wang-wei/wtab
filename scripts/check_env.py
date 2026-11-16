"""环境自检：依赖版本 + 数据库连接 + 静态目录。"""
from __future__ import annotations


def main() -> None:
    import alembic
    import fastapi
    import jinja2
    import sqlalchemy

    from app.config import STATIC_DIR, settings
    from app.database import engine
    from app.models import Base

    print("fastapi", fastapi.__version__)
    print("sqlalchemy", sqlalchemy.__version__)
    print("alembic", alembic.__version__)
    print("jinja2", jinja2.__version__)
    print("db", settings.database_url)
    print("static exists", STATIC_DIR.exists())
    print("tables", sorted(Base.metadata.tables))
    with engine.connect() as conn:
        print("db ok", conn.exec_driver_sql("select 1").scalar())


if __name__ == "__main__":
    main()
