"""冒烟测试：直接打 HTTP，覆盖安装向导、认证与基础路由。用法：python -m scripts.smoke [base_url]"""
from __future__ import annotations

import http.cookiejar
import json
import re
import sys
import urllib.error
import urllib.request
import uuid
from pathlib import Path

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8012"
_jar = http.cookiejar.CookieJar()
OPENER = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(_jar))


def call(path: str, payload: dict | None = None, headers: dict | None = None) -> tuple[int, str]:
    data = json.dumps(payload).encode() if payload is not None else None
    hdrs = {"Content-Type": "application/json"} if data else {}
    hdrs.update(headers or {})
    req = urllib.request.Request(BASE + path, data=data, headers=hdrs, method="POST" if data else "GET")
    try:
        with OPENER.open(req, timeout=30) as resp:
            return resp.status, resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8", "replace")


def upload_file(path: str, filename: str, content: bytes) -> tuple[int, str]:
    """手工拼 multipart/form-data，复用同一个 cookie jar。"""
    boundary = "----wtabsmoke7d1a"
    body = (
        ("--" + boundary + "\r\n").encode()
        + f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'.encode()
        + b"Content-Type: application/octet-stream\r\n\r\n"
        + content
        + b"\r\n"
        + ("--" + boundary + "--\r\n").encode()
    )
    req = urllib.request.Request(
        BASE + path,
        data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        method="POST",
    )
    try:
        with OPENER.open(req, timeout=30) as resp:
            return resp.status, resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8", "replace")


def captcha_code() -> str:
    """拉一张图形验证码，从 SVG 里取出答案（同一个 cookie jar，Session 对得上）。"""
    status, body = call("/captcha")
    return "".join(re.findall(r">([0-9A-Z])</text>", body))


# 最小合法 PNG（1x1 透明）
PNG_BYTES = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4"
    "890000000a49444154789c6300010000050001"
    "0d0a2db40000000049454e44ae426082"
)


def main() -> int:
    failures = []

    def check(name: str, cond: bool, detail: str = "") -> None:
        print(("PASS " if cond else "FAIL ") + name + ((" -> " + detail) if detail and not cond else ""))
        if not cond:
            failures.append(name)

    def code_of(body: str) -> int:
        try:
            return json.loads(body).get("code")
        except ValueError:
            return -1

    status, body = call("/health")
    check("GET /health", status == 200 and code_of(body) == 1, f"{status} {body[:200]}")
    installed = "installed\":true" in body.replace(" ", "")

    if not installed:
        status, body = call("/")
        check("未安装时 / 跳转到安装向导", status == 200 and 'id="install-form"' in body, f"{status}")

        status, body = call("/install/testDb", {"db_type": "sqlite", "table_name": "wtab"})
        check("POST /install/testDb", code_of(body) == 200, f"{status} {body[:200]}")

        status, body = call(
            "/install/install",
            {"db_type": "sqlite", "table_name": "wtab", "admin_email": "admin@example.com", "admin_password": "admin123"},
        )
        check("POST /install/install", code_of(body) == 200, f"{status} {body[:200]}")
    else:
        print("SKIP 未安装流程（已安装，直接测已安装路径）")

    status, body = call("/health")
    check("安装后 installed=true", '"installed":true' in body.replace(" ", ""), body[:200])

    status, body = call("/")
    check("安装后 / 渲染首页", status == 200 and "wTab" in body, f"{status} {body[:200]}")

    status, body = call("/install")
    check("已安装时 /install 跳回首页", status == 200 and "install-form" not in body, f"{status}")

    # ---- M2 认证 ----
    status, body = call("/login")
    check("GET /login 已移除", status == 404, f"{status}")

    status, body = call("/captcha")
    check("GET /captcha 返回图形验证码", status == 200 and "<svg" in body, f"{status}")

    status, body = call("/user/login", {"username": "admin@example.com", "password": "admin123"})
    check("缺少验证码的登录被拒绝", code_of(body) == 0, f"{status} {body[:160]}")

    status, body = call("/user/login", {"username": "admin@example.com", "password": "admin123", "code": "0000"})
    check("错误验证码被拒绝", code_of(body) == 0, f"{status} {body[:160]}")

    status, body = call("/user/login", {"username": "admin@example.com", "password": "wrong", "code": captcha_code()})
    check("错误密码被拒绝", code_of(body) == 0, f"{status} {body[:200]}")

    status, body = call("/user/login", {"username": "admin@example.com", "password": "admin123", "code": captcha_code()})
    check("管理员登录成功（写会话 Cookie）", code_of(body) == 1, f"{status} {body[:200]}")

    status, body = call("/user/get", {})
    check("会话 Cookie 可读 /user/get", status == 200 and '"manager":1' in body.replace(" ", ""), f"{status} {body[:200]}")

    status, body = call("/user/updateInfo", {"field": "nickname", "value": "管理员"})
    check("updateInfo 生效", code_of(body) == 1, f"{status} {body[:200]}")

    # ---- M3 书签 / 配置 / 导航栏 ----
    status, body = call("/")
    check("登录后 GET / 注入 window.WTAB", status == 200 and "window.WTAB" in body and "home.js" in body, f"{status}")

    # 弹层靠 hidden 属性显隐；CSS 里 .modal 自带 display:grid，必须有 [hidden] 兜底规则，
    # 否则所有弹窗永久显示且关不掉（曾出现过）。
    status, body = call("/static/app/app.css")
    check("app.css 含 [hidden] 兜底规则", status == 200 and "[hidden]" in body, f"{status} {len(body)}")

    status, body = call("/link/get", {})
    data = json.loads(body).get("data") if code_of(body) == 1 else None
    check("POST /link/get 返回书签数组", isinstance(data, list) and len(data) > 0, f"{status} {body[:160]}")
    original = data or []

    status, body = call("/link/update", {"link": original + [{"id": "TEST-1", "name": "冒烟", "url": "https://example.com", "size": "1x1", "type": "icon", "sort": 9999, "pageGroup": ""}]})
    check("POST /link/update 保存", code_of(body) == 1, f"{status} {body[:200]}")

    status, body = call("/link/get", {})
    data = json.loads(body).get("data") if code_of(body) == 1 else []
    check("保存后数据一致", any(i.get("id") == "TEST-1" for i in data), f"{status}")

    status, body = call("/link/history", {})
    history = json.loads(body).get("data") if code_of(body) == 1 else []
    check("POST /link/history 有备份", isinstance(history, list) and len(history) >= 1, f"{status} {body[:160]}")
    hid = history[0]["id"] if history else None

    status, body = call("/link/rollBack", {"id": hid})
    check("POST /link/rollBack 回滚", code_of(body) == 1, f"{status} {body[:160]}")
    status, body = call("/link/get", {})
    check("回滚后 TEST-1 消失", not any(i.get("id") == "TEST-1" for i in json.loads(body).get("data") or []), f"{status}")

    status, body = call("/link/delBack", {"id": hid})
    check("POST /link/delBack 删备份", code_of(body) == 1, f"{status} {body[:160]}")

    status, body = call("/config/get", {})
    cfg = json.loads(body).get("data") if code_of(body) == 1 else None
    check("POST /config/get 返回配置", isinstance(cfg, dict) and "theme" in cfg, f"{status} {body[:160]}")

    cfg["theme"]["LinkTitle"] = True
    status, body = call("/config/update", {"config": cfg})
    check("POST /config/update 保存", code_of(body) == 1, f"{status} {body[:160]}")
    status, body = call("/config/get", {})
    check("配置已持久化", json.loads(body)["data"]["theme"]["LinkTitle"] is True, f"{status}")

    status, body = call("/tabbar/get", {})
    tabs = json.loads(body).get("data") if code_of(body) == 1 else None
    check("POST /tabbar/get 返回数组", isinstance(tabs, list) and len(tabs) > 0, f"{status} {body[:160]}")
    status, body = call("/tabbar/update", {"tabbar": tabs or []})
    check("POST /tabbar/update 保存", code_of(body) == 1, f"{status} {body[:160]}")

    status, body = call("/searchEngine/index", {})
    engines = json.loads(body).get("data") if code_of(body) == 1 else None
    check("POST /searchEngine/index 返回启用引擎", isinstance(engines, list) and len(engines) > 0, f"{status} {body[:160]}")

    status, body = call("/searchEngine/searchEngine", {})
    check("POST /searchEngine/searchEngine 取当前列表", code_of(body) == 1, f"{status} {body[:160]}")

    status, body = call("/searchEngine/saveSearchEngine", {"searchEngine": engines})
    check("POST /searchEngine/saveSearchEngine 保存个人引擎", code_of(body) == 1, f"{status} {body[:160]}")

    status, body = call("/searchEngine/list", {})
    check("POST /searchEngine/list 管理员可读全部", code_of(body) == 1, f"{status} {body[:160]}")

    status, body = call("/searchEngine/add", {"form": {"name": "冒烟引擎", "url": "https://example.com/s?q={1}", "sort": 1, "status": 1}})
    check("POST /searchEngine/add 新增", code_of(body) == 1, f"{status} {body[:160]}")
    status, body = call("/searchEngine/list", {"name": "冒烟引擎"})
    added = (json.loads(body).get("data") or [{}])[0] if code_of(body) == 1 else {}
    check("新增引擎可搜到", added.get("name") == "冒烟引擎", f"{status} {body[:200]}")

    status, body = call("/searchEngine/sort", {"0": {"id": added.get("id"), "sort": 9}})
    check("POST /searchEngine/sort 排序", code_of(body) == 1, f"{status} {body[:160]}")

    status, body = call("/searchEngine/del", {"ids": [added.get("id")]})
    check("POST /searchEngine/del 删除", code_of(body) == 1, f"{status} {body[:160]}")

    status, body = call("/link/reset", {})
    check("POST /link/reset 重置", code_of(body) == 1, f"{status} {body[:160]}")

    status, body = call("/searchEngine/searchEngine", {})
    check("reset 后引擎回到系统默认", code_of(body) == 1 and len(json.loads(body)["data"]) == len(engines), f"{status} {body[:160]}")

    # ---- M5 笔记 ----
    status, body = call("/noteApp")
    check("GET /noteApp 渲染笔记页", status == 200 and "note-list" in body, f"{status}")

    status, body = call("/note/add", {"title": "冒烟笔记", "text": "hello note"})
    note = json.loads(body).get("data") if code_of(body) == 1 else {}
    check("POST /note/add 新建笔记", code_of(body) == 1 and note.get("id"), f"{status} {body[:160]}")

    status, body = call("/note/get", {})
    listed = json.loads(body).get("data") if code_of(body) == 1 else []
    check("POST /note/get 列出笔记", any(n.get("id") == note.get("id") for n in (listed or [])), f"{status} {body[:160]}")

    note_id = note.get("id")
    status, body = call("/note/update", {"id": note_id, "title": "冒烟笔记2", "text": "changed"})
    check("POST /note/update 修改笔记", code_of(body) == 1, f"{status} {body[:160]}")

    status, body = call(f"/note/getText?id={note_id}")
    check("GET /note/getText 返回纯文本", status == 200 and body.strip() == "changed", f"{status} {body[:80]}")

    status, body = call("/note/setWeight", {"id": note_id, "weight": 1})
    check("POST /note/setWeight 置顶", code_of(body) == 1, f"{status} {body[:160]}")

    status, body = call("/note/sort", {"ids": [note_id]})
    check("POST /note/sort 排序", code_of(body) == 1, f"{status} {body[:160]}")

    # ---- M5 壁纸 ----
    status, body = call("/wallpaper/getFolderClient", {})
    folders = json.loads(body).get("data") if code_of(body) == 1 else []
    check("POST /wallpaper/getFolderClient 返回壁纸分类", isinstance(folders, list) and len(folders) > 0, f"{status} {body[:160]}")

    status, body = call("/wallpaper/getFolderWallpaperClient", {"id": folders[0]["id"], "offset": 0})
    walls = json.loads(body).get("data") if code_of(body) == 1 else []
    check("POST /wallpaper/getFolderWallpaperClient 返回壁纸", isinstance(walls, list) and len(walls) > 0, f"{status} {body[:160]}")

    status, body = call("/wallpaper/randomWallpaper", {})
    check("POST /wallpaper/randomWallpaper 随机壁纸", code_of(body) == 1 and json.loads(body)["data"].get("url"), f"{status} {body[:160]}")

    status, body = call("/wallpaper/editFolder", {"name": "冒烟分类"})
    edited = json.loads(body).get("data") if code_of(body) == 1 else []
    smoke_folder = [f for f in (edited or []) if f.get("name") == "冒烟分类"]
    check("POST /wallpaper/editFolder 新建分类", code_of(body) == 1 and smoke_folder, f"{status} {body[:160]}")

    if smoke_folder:
        fid = smoke_folder[0]["id"]
        status, body = call("/wallpaper/addWallpaper", {"name": "冒烟壁纸", "url": "/static/wallpaper/wallpaper-1.jpeg", "type": 0, "mime": 0, "folder": fid})
        wall_id = json.loads(body).get("data", {}).get("id") if code_of(body) == 1 else None
        check("POST /wallpaper/addWallpaper 新增壁纸", code_of(body) == 1 and wall_id, f"{status} {body[:160]}")

        status, body = call("/wallpaper/getFolderWallpaper", {"id": fid, "limit": 10})
        check("POST /wallpaper/getFolderWallpaper 分页", code_of(body) == 1 and json.loads(body)["data"].get("total") == 1, f"{status} {body[:160]}")

        status, body = call("/wallpaper/deleteWallpaper", {"id": wall_id})
        check("POST /wallpaper/deleteWallpaper 删除壁纸", code_of(body) == 1, f"{status} {body[:160]}")

        status, body = call("/wallpaper/DelFolder", {"id": fid})
        check("POST /wallpaper/DelFolder 删除分类", code_of(body) == 1, f"{status} {body[:160]}")

    status, body = call("/wallpaper/sortFolder", {"0": {"id": folders[0]["id"], "sort": 1}})
    check("POST /wallpaper/sortFolder 排序", code_of(body) == 1, f"{status} {body[:160]}")

    # ---- M5 站点接口与上传 ----
    status, body = call("/api/site", {})
    site = json.loads(body).get("data") if code_of(body) == 1 else {}
    check("POST /api/site 返回站点信息", code_of(body) == 1 and "user_register" in (site or {}), f"{status} {body[:160]}")

    status, body = call("/api/DefBg", {})
    check("POST /api/DefBg 返回默认背景", code_of(body) == 1 and json.loads(body)["data"].get("background"), f"{status} {body[:160]}")

    status, body = call("/api/background")
    check("GET /api/background 返回默认背景图", status == 200 and len(body) > 1000, f"{status} {len(body)}")

    status, body = call("/api/refresh", {})
    check("POST /api/refresh 返回书签更新时间", code_of(body) == 1, f"{status} {body[:160]}")

    status, body = call("/api/getIcon", {})
    check("POST /api/getIcon 无参数报错", code_of(body) == 0, f"{status} {body[:160]}")

    status, body = call("/api/upload", {})
    check("POST /api/upload 无文件报错", code_of(body) == 0 and "not File" in body, f"{status} {body[:160]}")

    status, body = upload_file("/api/upload", "smoke.png", PNG_BYTES)
    up = json.loads(body).get("data") if code_of(body) == 1 else {}
    check("POST /api/upload 上传图片", code_of(body) == 1 and (up or {}).get("url", "").startswith("/images/"), f"{status} {body[:160]}")

    if (up or {}).get("url"):
        status, body = call(up["url"])
        check("上传的文件可通过 /images 访问", status == 200 and len(body) > 50, f"{status}")

    status, body = upload_file("/api/upload", "smoke.txt", b"not an image")
    check("POST /api/upload 拦截非图片", code_of(body) == 0, f"{status} {body[:160]}")

    status, body = call("/file/list", {"limit": 5})
    check("POST /file/list 管理员可读", code_of(body) == 1 and "data" in json.loads(body)["data"], f"{status} {body[:160]}")

    status, body = call("/file/scanLocal", {})
    check("POST /file/scanLocal 扫描完成", code_of(body) == 1, f"{status} {body[:160]}")

    if (up or {}).get("url"):
        status, body = call("/api/delImages", {"url": up["url"]})
        check("POST /api/delImages 删除图片", code_of(body) == 1, f"{status} {body[:160]}")

    status, body = call("/note/del", {"id": note_id})
    check("POST /note/del 删除笔记", code_of(body) == 1, f"{status} {body[:160]}")

    # ---- M7 管理后台 ----
    status, body = call("/manager")
    check("GET /manager 管理员渲染后台页", status == 200 and "admin-shell" in body, f"{status}")

    status, body = call("/admin/getServicesStatus", {})
    dash = json.loads(body).get("data") if code_of(body) == 1 else {}
    check("POST /admin/getServicesStatus 仪表盘统计", code_of(body) == 1 and "userNum" in (dash or {}), f"{status} {body[:160]}")

    status, body = call("/admin/getUserLine", {})
    line = json.loads(body).get("data") if code_of(body) == 1 else {}
    check("POST /admin/getUserLine 注册曲线", code_of(body) == 1 and "time" in (line or {}), f"{status} {body[:160]}")

    status, body = call("/admin/UserList", {"limit": 5})
    users = json.loads(body).get("data") if code_of(body) == 1 else {}
    check("POST /admin/UserList 分页用户列表", code_of(body) == 1 and "data" in (users or {}), f"{status} {body[:160]}")
    check("用户列表不含密码", "password" not in json.dumps(users or {}), "")

    status, body = call("/admin/UserList", {"limit": 5, "search": {"group_id": -1, "status": -1}})
    check("POST /admin/UserList 筛选条件", code_of(body) == 1, f"{status} {body[:160]}")

    status, body = call("/admin/userUpdate", {"mail": "smoke_user@example.com", "nickname": "冒烟用户", "password": "smoke123", "status": 0, "manager": 0, "group_id": 0})
    check("POST /admin/userUpdate 新建用户", code_of(body) == 1, f"{status} {body[:160]}")

    status, body = call("/admin/UserList", {"limit": 50, "search": {"mail": "smoke_user@example.com"}})
    found = (json.loads(body).get("data") or {}).get("data") if code_of(body) == 1 else []
    smoke_uid = found[0]["id"] if found else None
    check("新建用户可查到", smoke_uid is not None, f"{status} {body[:160]}")

    if smoke_uid:
        status, body = call("/admin/userUpdate", {"id": smoke_uid, "nickname": "冒烟用户2", "password": ""})
        check("POST /admin/userUpdate 改资料（空密码不改密）", code_of(body) == 1, f"{status} {body[:160]}")

        status, body = call("/admin/userLoginRecord", {"user_id": smoke_uid})
        check("POST /admin/userLoginRecord 登录记录", code_of(body) == 1 and isinstance(json.loads(body).get("data"), list), f"{status} {body[:160]}")

    pem = Path(__file__).resolve().parent.parent / "xy.pem"
    pem.unlink(missing_ok=True)
    status, body = call("/admin/xyCheck", {})
    check("POST /admin/xyCheck 无证书返回 license", code_of(body) == 0 and "license" in body, f"{status} {body[:80]}")

    status, body = call("/admin/xy", {})
    check("POST /admin/xy 写证书", code_of(body) == 1, f"{status} {body[:160]}")

    status, body = call("/admin/xyCheck", {})
    check("POST /admin/xyCheck 已有证书", code_of(body) == 1, f"{status} {body[:80]}")
    pem.unlink(missing_ok=True)

    status, body = call("/admin/repair", {})
    check("POST /admin/repair 修复数据表", code_of(body) == 1, f"{status} {body[:160]}")

    status, body = call("/link/get", {})
    cur_links = json.loads(body).get("data") if code_of(body) == 1 else None
    status, body = call("/admin/export", {"link": cur_links})
    check("POST /admin/export 导出默认书签", code_of(body) == 1, f"{status} {body[:160]}")

    status, body = call("/setting/getSetting", {"role": ["title", "logo", "user_register"]})
    got = json.loads(body) if body.strip().startswith("{") else {}
    check("POST /setting/getSetting 返回设置", got.get("msg") == "ok" and "data" in got, f"{status} {body[:160]}")

    status, body = call("/setting/saveSetting", {"form": {"title": "Wtab书签冒烟", "user_register": "1"}})
    check("POST /setting/saveSetting 保存设置", code_of(body) == 1, f"{status} {body[:160]}")

    status, body = call("/setting/getSetting", {"role": ["title"]})
    saved = json.loads(body) if body.strip().startswith("{") else {}
    check("设置已持久化", (saved.get("data") or {}).get("title") == "Wtab书签冒烟", f"{status} {body[:160]}")

    status, body = call("/setting/refreshCache", {})
    check("POST /setting/refreshCache 刷新缓存", code_of(body) == 1, f"{status} {body[:160]}")

    status, body = call("/setting/mailTest", {"email": "smoke@example.com"})
    check("POST /setting/mailTest 未配置 SMTP 报错", code_of(body) == 0, f"{status} {body[:160]}")

    status, body = call("/setting/delExt", {})
    check("POST /setting/delExt 删扩展包", code_of(body) == 1, f"{status} {body[:160]}")

    if smoke_uid:
        status, body = call("/admin/userDelete", {"id": smoke_uid})
        check("POST /admin/userDelete 删除用户", code_of(body) == 1, f"{status} {body[:160]}")

        status, body = call("/admin/UserList", {"limit": 50, "search": {"mail": "smoke_user@example.com"}})
        gone = (json.loads(body).get("data") or {}).get("data") if code_of(body) == 1 else []
        check("用户已删除", not gone, f"{status} {body[:160]}")

    # ---- 页面元信息 ----
    status, body = call("/privacy")
    check("GET /privacy 渲染隐私页", status == 200 and "隐私政策" in body, f"{status}")

    status, body = call("/favicon")
    check("GET /favicon 返回图标或跳转默认图标", status in (200, 302), f"{status}")

    status, body = call("/manifest.json")
    manifest = json.loads(body) if status == 200 else {}
    check("GET /manifest.json 返回 PWA 清单", status == 200 and manifest.get("name") and manifest.get("start_url") == "/", f"{status} {body[:160]}")

    status, body = call("/index/all", {"ids": ["link"]})
    all_data = json.loads(body).get("data") if code_of(body) == 1 else {}
    check("POST /index/all 只返回未请求的模块", code_of(body) == 1 and "link" not in all_data and {"tabbar", "config", "site"} <= set(all_data), f"{status} {body[:200]}")

    status, body = call("/")
    check("页面 head 注入站点设置", status == 200 and "Wtab书签冒烟" in body, f"{status}")

    # 清掉测试写入的站点标题，避免污染当前实例（空值回退到 app_name）
    call("/setting/saveSetting", {"form": {"title": ""}})

    status, body = call("/user/loginOut", {})
    check("登出成功", code_of(body) == 1, f"{status} {body[:200]}")

    status, body = call("/user/get", {})
    check("登出后 /user/get 需登录", code_of(body) == 0, f"{status} {body[:200]}")

    status, body = call("/manager")
    check("未登录访问 /manager 跳登录页", status == 200 and "admin-shell" not in body, f"{status}")

    status, body = call("/admin/UserList", {"limit": 3})
    check("未登录访问 /admin/UserList 被拒", code_of(body) == 0, f"{status} {body[:200]}")

    status, body = call("/setting/getSetting", {"role": ["title"]})
    check("未登录访问 /setting/* 被拒", code_of(body) == 0, f"{status} {body[:200]}")

    print(("\n%d failed" % len(failures)) if failures else "\n全部通过")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
