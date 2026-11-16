"""跨平台启动器：Linux / macOS / Windows 通用。

等价于 container/entrypoint.sh 的三步：补迁移 → （可选）无人值守安装 → 启动 uvicorn。
从任意工作目录启动都可以，内部按项目根目录寻址。

    python -m scripts.start                      # 0.0.0.0:8000
    python -m scripts.start --host 127.0.0.1 --port 8012 --reload
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))


def main() -> None:
    parser = argparse.ArgumentParser(description="Wtab 书签启动器")
    # 默认值留给 .env 的 HOST / PORT（命令行参数优先）
    parser.add_argument("--host", default=None, help="监听地址，默认取 .env 的 HOST，否则 0.0.0.0")
    parser.add_argument("--port", type=int, default=None, help="监听端口，默认取 .env 的 PORT，否则 8000")
    parser.add_argument("--reload", action="store_true", help="开发模式热重载（单进程）")
    parser.add_argument(
        "--debug",
        action="store_true",
        default=os.environ.get("DEBUG", "").lower() in ("1", "true", "yes", "on"),
        help="调试模式：自动热重载 + debug 日志 + 返回异常栈 + 开启 /docs",
    )
    parser.add_argument("--workers", type=int, default=int(os.environ.get("WEB_CONCURRENCY", "1")))
    args = parser.parse_args()

    if args.debug:
        # app.config 在下面才导入，这里设置可让它读到 DEBUG
        os.environ["DEBUG"] = "1"

    import uvicorn

    from app.config import settings

    host = args.host or settings.host
    port = args.port or settings.port

    # 已安装的库先补齐迁移（等价 entrypoint.sh 里的 alembic upgrade head）
    if settings.installed_lock.exists():
        from app.services.installer import run_migrations

        run_migrations(settings.database_url)

    from scripts import autoinstall

    autoinstall.main()

    uvicorn.run(
        "app.main:app",
        host=host,
        port=port,
        reload=args.reload or args.debug,
        workers=None if (args.reload or args.debug) else args.workers,
        log_level="debug" if settings.debug else "info",
        proxy_headers=True,
        forwarded_allow_ips="*",
    )


if __name__ == "__main__":
    main()
