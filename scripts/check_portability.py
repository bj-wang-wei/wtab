"""跨平台自检：路径映射、时区、SQLite 连接串在 Linux / Windows 下都要一致。

    python -m scripts.check_portability
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

FAILED: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    print(("PASS " if cond else "FAIL ") + name + (f"  {detail}" if detail and not cond else ""))
    if not cond:
        FAILED.append(name)


def main() -> None:
    from app.config import STATIC_DIR, TEMPLATE_DIR, UPLOAD_DIR
    from app.models import now
    from app.services import installer
    from app import storage

    # 1. 磁盘目录按 Path 拼接，分隔符由系统决定
    check("静态目录存在", STATIC_DIR.is_dir(), str(STATIC_DIR))
    check("模板目录存在", (TEMPLATE_DIR / "base.html").is_file(), str(TEMPLATE_DIR))

    # 2. URL → 本地路径：正斜杠与反斜杠必须映射到同一个文件
    fwd = storage.local_path("/images/2026/10/24/abc.png")
    back = storage.local_path("\\images\\2026\\10\\24\\abc.png")
    check("正斜杠 URL 映射到 uploads", fwd is not None and fwd.is_relative_to(UPLOAD_DIR.resolve()), str(fwd))
    check("反斜杠 URL 映射一致", fwd is not None and back == fwd, f"{fwd} vs {back}")
    check("查询串被忽略", storage.local_path("/images/a.png?x=1") == storage.local_path("/images/a.png"))
    static_hit = storage.local_path("/static/defaultTab.json")
    check(
        "/static 前缀走静态目录",
        static_hit is not None and static_hit.is_relative_to(STATIC_DIR.resolve()) and static_hit.is_file(),
        str(static_hit),
    )

    # 3. 路径穿越与未知前缀必须被拒
    check("路径穿越被拒", storage.local_path("/images/../../app/config.py") is None)
    check("反斜杠穿越被拒", storage.local_path("\\images\\..\\..\\app\\config.py") is None)
    check("未知前缀被拒", storage.local_path("/etc/passwd") is None)
    check("空值被拒", storage.local_path(None) is None and storage.local_path("") is None)

    # 4. SQLite 连接串用 as_posix()，三平台都能被 SQLAlchemy 解析
    url = installer.build_url({"db_type": "sqlite", "table_name": "portability"})
    check("SQLite 串无反斜杠", "\\" not in url, url)
    check("SQLite 串绝对路径", url.startswith("sqlite:///") and "portability.db" in url, url)
    from sqlalchemy.engine import make_url

    check("SQLAlchemy 可解析该串", make_url(url).database is not None, url)

    # 5. 时间：naive 本地时间，偏移固定 +08:00（tzdata 缺失时回退也能用）
    local = now()
    utc = datetime.now(timezone.utc).replace(tzinfo=None)
    delta = local - utc
    check("now() 为 naive 本地时间", local.tzinfo is None)
    check("now() 偏移 +8 小时", abs(delta - timedelta(hours=8)) < timedelta(minutes=5), str(delta))

    # 6. 上传目录可写（Windows 下常见权限坑）
    probe = UPLOAD_DIR / ".portability"
    try:
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
        check("上传目录可写", True)
    except OSError as exc:
        check("上传目录可写", False, str(exc))

    print("全部通过" if not FAILED else f"失败 {len(FAILED)} 项：{FAILED}")


if __name__ == "__main__":
    main()
