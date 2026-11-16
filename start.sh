#!/bin/sh
# Linux / macOS 启动入口
cd "$(dirname "$0")" || exit 1
exec python -m scripts.start "$@"
