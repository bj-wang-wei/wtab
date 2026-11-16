# wtab 原项目分析（v2.4.3，PHP 8 + ThinkPHP 8）


## 1. 运行架构

| 项 | 实情 |
|---|---|
| 后端 | ThinkPHP 8，单应用 `index`，pathinfo 路由 `/{controller}/{action}` |
| 前端 | 编译好的 Vue SPA 在 `public/dist`，`index.html` 里用 `{$title}` 等占位符由 PHP 正则替换 |
| 重写规则 | `nginx.rewrite`: `rewrite ^(.*)$ /index.php?s=$1`（`public/router.php` 同义） |
| 静态 | `public/static`（图片、壁纸、图标、defaultTab.json） |
| 响应约定 | 所有 API 返回 `{"code":1|0,"msg":str,"data":any}`（`app/BaseController.php:126-140`） |
| 未安装拦截 | `app/AppService.php` 无 `public/installed.lock` 时 302 → `/install.php` |
| 部署 | `Dockerfile` + `docker/`（nginx+php-fpm+redis），容器内 `/app`，对外 80；`env.php` 读 `MYSQL_*`/`ADMIN_*` 环境变量自动装库 |

## 2. 认证

- 密码：`md5(明文)`（`env.php:50`、`public/install.php:178`）
- 登录后写 `token` 表，客户端持有 `user_id` + `token`（Cookie 或 Header `Userid`/`Token`），15 天滚动过期
  （`app/model/UserModel.php:25-60`）
- 管理员：`user.manager = 1`（`app/BaseController.php:115-124`）
- 验证码/邮件码：`api/getMailCode` + `extend/Mail.php`；注册/找回密码用 `code`
- QQ 登录：`user/qLogin`、`user/qq_login`、`qq_open_id` 字段

## 3. 数据表（install.sql 建 17 张；本项目按用户决定去掉 card / plugins_todo / plugins_todo_folder）

| 表 | 关键列 | 说明 |
|---|---|---|
| `user` | id, avatar, mail(uniq), password, create_time, login_ip, register_ip, manager, login_fail_count, login_time, qq_open_id(uniq), nickname, status(0正常/1冻结), active(date), group_id | 账号 |
| `token` | id, user_id, token, create_time(int), ip, user_agent, access_token | 登录令牌 |
| `user_group` | id, name, create_time, sort | 用户分组 |
| `link` | user_id(idx), update_time, link(longtext JSON) | 每用户整份书签 JSON |
| `history` | id, user_id, link(longtext), create_time | 书签备份，保留最近 50 条 |
| `link_folder` | id, name, sort, group_ids | 公共链接库分类，group_ids 控制可见分组 |
| `linkstore` | id, name, src, url, type, size, create_time, hot, area, tips, domain, app, install_num, bgColor, vip(0/1), custom, user_id, status(1展示/0待审), group_ids | 公共链接库 |
| `config` | user_id(idx), config(longtext JSON) | 每用户界面配置 |
| `tabbar` | user_id, tabs(longtext JSON), update_time | 每用户导航栏 |
| `user_search_engine` | user_id(PK), list(longtext JSON) | 用户搜索引擎同步 |
| `search_engine` | id, name, icon, url(含 `{1}` 占位), sort, create_time, status, tips | 系统搜索引擎 |
| `note` | id, user_id(idx), title, text, create_time, update_time, weight, sort | 笔记 |
| `wallpaper` | id, type(1文件夹/0资源), folder, mime(0图/1视频), url, cover, create_time, name, sort | 壁纸 |
| `file` | id, path, user_id, create_time, size, mime_type, hash | 上传文件记录 |
| `setting` | keys(PK), value(text) | 系统设置 KV |

MySQL 特有写法需注意迁移：`auto_increment`、`int unsigned`（实际未用）、`longtext/text/tinytext`、`datetime`、`ON DUPLICATE KEY UPDATE`（defaultData.sql）、`ENGINE/CHARSET`。

## 4. JSON 载荷形状（`public/static/defaultTab.json` 为唯一权威样例）

- `link.link` / `tabbar.tabs` / `config.config` 三段结构在同文件内，分别给出 `link[]`、`tabbar[]`、`config{openType,theme}`。
- 书签条目字段：`id(uuid)`, `app(0/1)`, `pid(uuid|null 组件子项)`, `src`, `url`, `name`, `size("1x1"/"1x2")`,
  `sort`, `type("icon"/"component")`, `component("iconGroup")`, `bgColor`, `pageGroup`, `form`, `tips`, `custom{...}`,
  `origin_id`, `children[]`。`url` 可用伪协议：`tab://addicon`、`tab://setting`、`tab://background`。
- `config.openType`: searchOpen/linkOpen/autofocus/searchLink/searchRecommend/tabbar
- `config.theme`: backgroundImage/backgroundMime/blur/timeColor/tabbar/tabbarMode/iconWidth/iconBg/LinkTitle/
  iconRadius/CompactMode/nameColor/opacity/colsGap/pageGroup/pageGroupStatus/timeView/timeWeek/timeGanZhi/
  timeSecond/timeMonthDay/timeLunar/time24/maxColumn/latestPageGroup/bottom2top

## 5. 接口清单（原 pathinfo 路径 → 模块）

- **Index**：`/`、`/manager`、`/noteApp`、`/privacy`、`/favicon`、`/manifest.json`、`/index/all`
- **User**：`/user/login` `register` `forgetPass` `newMail` `loginOut` `get` `updateInfo` `unbindQQ` `qLogin` `UserGroup` `createGroup` `sortGroup`；`/qq_login`
- **Link**：`/link/update` `get` `history` `delBack` `rollBack` `reset` `refreshWebAppCache`
- **Config**：`/config/update` `get`
- **Tabbar**：`/tabbar/update` `get`
- **Note**：`/note/get` `add` `update` `del` `sort` `setWeight` `getText`
- **Card**：`/card/index` `install_num`（本项目丢弃）
- **Wallpaper**：`/wallpaper/editFolder` `DelFolder` `getFolder` `getFolderClient` `getFolderWallpaper` `getFolderWallpaperClient` `deleteWallpaper` `addWallpaper` `randomWallpaper` `sortFolder`
- **File**：`/file/list` `del` `scanLocal`
- **SearchEngine**：`/searchEngine/index` `list` `add` `del` `searchEngine` `saveSearchEngine` `sort`
- **Api**：`/api/site` `background` `DefBg` `globalNotify` `getMailCode` `getIcon` `upload` `AdminUpload` `refresh` `cardImages` `moveFile` `delImages`
- **Setting**：`/setting/saveSetting` `refreshCache` `getSetting` `mailTest` `delExt`
- **Admin**：`/admin/UserList` `userUpdate` `userDelete` `export` `xyCheck` `xy` `getServicesStatus` `getUserLine` `userLoginRecord` `repair`
- **Install**：`/install.php?s=/testDb|/install|/ext|(index)`；`/installApp/*`
- **app/controller/apps/***（todo/poetry/topSearch/weather/food）：旧版卡片后端，随卡片系统一并丢弃
- **插件**：`/plugins/:dir/static/:file` + `PluginsBase` + `admin/Index::installCard` 动态加载；仓库内无 `plugins/` 目录，外部下载包，本次不复刻

## 6. 本项目（Python 复刻）已确认的决策

1. **前端**：用 **Jinja2 全量重写界面**，不保留 Vue SPA、不做前后端分离；一个 FastAPI 服务同时提供页面、API、静态资源。
2. **卡片/插件系统**：**完全不要**（丢弃 `card`、`plugins_todo`、`plugins_todo_folder`、`apps/*`、`extend/PluginsInstall.php`）。
3. **数据库**：默认 **SQLite**，通过 `DATABASE_URL` 可迁移 PostgreSQL / MySQL；用 SQLAlchemy 2.0 + Alembic。
4. **认证**：原项目为 md5 + 双 Cookie token。为保证既有 wtab 数据库可直接接管，**继续兼容 md5 校验**（`md5(明文)`），但登录态改为签名 Session Cookie（`itsdangerous`），不再依赖 `token` 表（表保留）。
5. 接口路径尽量沿用原 pathinfo（`/user/login`、`/link/get` …），返回体保持 `{code,msg,data}`。
