# wTab 书签

个人书签主页 — mTab 的 Python 复刻版本，用浏览器即可管理你的书签。

## 截图

| 主页 | 登录 |
| --- | --- |
| ![主页](docs/screenshots/home.jpg) | ![登录](docs/screenshots/login.jpg) |

![安装向导](docs/screenshots/install.jpg)

## 功能概览

- **书签管理**：添加 / 编辑 / 删除书签；右键卡片（文件夹）可修改名称、移动至分类、解散或删除。
- **分类页**：左侧栏列分类，右键可编辑 / 删除分类；书签可按分类分组页显示。
- **图标布局**：卡片内图标均匀分布（`space-evenly`，固定 64×64）；卡片长大顺序：先横向再纵向（2x2 → 2x3 → 3x3 → 3x4 → 4x4 …）。
- **跨文件夹拖动**：拖入目标文件夹后，源文件夹自动缩回。
- **Dock 栏**：支持图标拖入 dock、拖入垃圾桶删除。
- **壁纸**：图片 / 视频壁纸，支持模糊调节；左侧面板「壁纸设置」可管理，点缩略图直接应用。
- **主题外观**：暗色 / 亮色主题切换（设置 → 外观设置）
- **管理后台**：系统设置按分组两列排布；用户列表支持每页条数（10/20/50/100）；壁纸管理为网格 + 点击预览。
- **搜索引擎**：自定义搜索引擎列表，支持默认 / 恢复出厂。
- **用户系统**：注册、登录、邮箱验证、密码找回；管理员可管理用户和分组。
- **设置弹窗**：左侧 5 个 tab（账号 / 外观 / 壁纸 / 管理员 / 关于），弹窗锚定左下角弹出。
- **便签**：内置笔记功能。
- **导入 / 导出**：书签数据迁移。

## 项目结构

```
app/                    # FastAPI 应用
├── main.py             # 应用入口、中间件、路由注册
├── config.py           # Settings（数据库、端口）
├── database.py         # SQLAlchemy 引擎 & Session
├── models.py           # ORM 模型（Link/User/Config/Tabbar …）
├── routers/            # 路由模块
│   ├── install.py      # 安装向导
│   ├── user.py         # 注册/登录/QQ/邮箱验证
│   ├── link.py         # 书签增删改查
│   ├── config.py       # 主题/配置保存
│   ├── tabbar.py       # 底部导航
│   ├── searchengine.py # 搜索引擎管理
│   ├── wallpaper.py    # 壁纸上传/管理
│   ├── admin.py        # 管理员后台 API
│   ├── note.py         # 便签
│   ├── setting.py      # 系统设置（邮件等）
│   ├── captcha.py      # 验证码
│   ├── pages.py        # 页面渲染（后台 /manager）
│   ├── file.py         # 文件上传
│   └── api.py          # 通用 API
├── services/           # 业务层
│   ├── installer.py    # 安装/迁移
│   ├── userdata.py     # 书签数据读写 & reset
│   ├── mailer.py       # 邮件发送
│   └── seed.py         # 种子数据
├── templates/          # Jinja2 模板
│   ├── home.html       # 主页
│   ├── admin.html      # 管理后台
│   └── install.html    # 安装向导
└── static/app/         # 前端资源（JS/CSS）
    ├── home.js
    ├── home.css
    └── admin.js
```

## 安装与运行

### 环境要求

- Python 3.15+（开发环境为 3.15.0，容器镜像同为 3.15）
- 依赖见 `requirements.txt`

### 本地启动

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 启动服务（默认 0.0.0.0:8000）
python -m scripts.start

# 指定地址和端口
python -m scripts.start --host 127.0.0.1 --port 8012

# 开发模式（热重载）
python -m scripts.start --reload
```

### Podman

三种数据库各一份 compose 文件，按需选一个：

```bash
podman compose -f podman-compose_sqlite.yml up -d      # 容器内 SQLite（默认）
podman compose -f podman-compose_mysql.yml up -d       # 带 MySQL 8.4
podman compose -f podman-compose_postgresql.yml up -d  # 带 PostgreSQL 16
```

镜像名是 `docker.io/bjwangweigmail/wtab:latest`，本机没有会自动从 Docker Hub 拉取（也可以先 `podman pull`）。Windows/macOS 上先 `podman machine init && podman machine start`。

想从当前源码自己构建镜像（`Containerfile`，`.containerignore` 控制构建上下文）：

```bash
podman build -t docker.io/bjwangweigmail/wtab:latest -f Containerfile .
```

目标机器连不上 Docker Hub 时，在一台能联网的机器上导出镜像，把 tar 拷过去加载即可（镜像名带完整仓库地址，`load` 之后 compose 用本地镜像，不会再拉取）：

```bash
podman save -o wtab-1.2.2.tar docker.io/bjwangweigmail/wtab:latest  # 能联网的机器
podman load -i wtab-1.2.2.tar                                       # 目标机器
```

`podman-compose_mysql.yml` / `_postgresql.yml` 还需要 `mysql:8.4` / `postgres:16-alpine`，离线环境同样要 `save`/`load`，或改用内网镜像仓库。

首次启动访问 `/install` 走网页安装向导。每种数据库的容器数据放在各自的目录（`data/`、`data/mysql/`、`data/postgresql/`），互不干扰；想重装就删掉对应目录再 `up`。

### 数据库

默认使用 SQLite（`data/wtab.db`）。通过环境变量切换：

```bash
DATABASE_URL=mysql+pymysql://user:pass@host/dbname
DATABASE_URL=postgresql+psycopg://user:pass@host/dbname
```

首次启动会自动执行 Alembic 迁移。

## 配置说明

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `HOST` | `0.0.0.0` | 监听地址（`.env` 或 `--host`） |
| `PORT` | `8000` | 监听端口（`.env` 或 `--port`） |
| `DEBUG` | `false` | 调试模式（开启 `/docs`、热重载） |
| `SECRET_KEY` | `change-me-in-production` | Session 签名密钥 |
| `DATABASE_URL` | `sqlite:///data/wtab.db` | 数据库连接字符串 |
| `WTAB_ADMIN_MAIL` | 空 | 无人值守安装的管理员邮箱 |
| `WTAB_ADMIN_PASSWORD` | 空 | 无人值守安装的管理员密码 |
| `upload_max_mb` | 20 | 文件上传大小上限（MB） |

## 接口速查

| 路径 | 说明 |
|------|------|
| `GET /` | 主页 |
| `GET /install` | 安装向导 |
| `GET /manager` | 管理后台 |
| `POST /user/login` | 登录 |
| `POST /user/register` | 注册 |
| `POST /link/get` | 获取书签列表 |
| `POST /link/update` | 保存书签列表 |
| `POST /link/reset` | 重置当前用户书签 |
| `POST /config/get` | 获取配置 |
| `POST /config/update` | 保存配置 |
| `GET /health` | 健康检查（`{"code":1,"data":{"app":"wTab书签","version":"1.2.2"}}`） |

## 版本与缓存

前端资源与页面同源部署，静态文件由 ETag / Last-Modified 做协商缓存，无需查询参数；修改 `static/app` 下的 CSS/JS 后，浏览器刷新即生效（强缓存客户端需手动刷新一次）。

## 测试

### 冒烟测试

```bash
python -m scripts.smoke http://127.0.0.1:8000
```

冒烟测试覆盖安装向导、认证、书签管理、壁纸、用户管理等，期望全部通过（125 项）。

## 开源协议

本项目基于 [MIT License](LICENSE) 协议，Copyright (c) 2026 Vin。
