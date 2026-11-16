#!/bin/sh
# 容器/系统服务入口：迁移 → （可选）无人值守安装 → 启动服务。
# 直接用跨平台启动器，避免 shell 脚本与 Windows 版本走两套逻辑。
set -e

exec python -m scripts.start --host 0.0.0.0 --port "${PORT:-8000}"
