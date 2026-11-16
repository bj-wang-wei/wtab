"""SMTP / Resend 发信（对应原项目 extend/Mail.php）。设置键沿用原库：smtp_host/port/email/password/ssl/code_template；Resend 用 resend_api_key/resend_from。"""
from __future__ import annotations

import json
import smtplib
import urllib.error
import urllib.request
from email.header import Header
from email.mime.text import MIMEText

from sqlalchemy.orm import Session

from app.services import settings_store
from app.services.site import DEFAULTS as SITE_DEFAULTS


def smtp_config(db: Session) -> dict:
    return {
        "host": settings_store.get(db, "smtp_host", SITE_DEFAULTS["smtp_host"]),
        "port": int(settings_store.get(db, "smtp_port", SITE_DEFAULTS["smtp_port"]) or 587),
        "user": settings_store.get(db, "smtp_email", SITE_DEFAULTS["smtp_email"]),
        "password": settings_store.get(db, "smtp_password", ""),
        "ssl": str(settings_store.get(db, "smtp_ssl", "1")) == "1",
        "sender": settings_store.get(db, "title", "Wtab书签"),
    }


def resend_config(db: Session) -> dict:
    return {
        "key": settings_store.get(db, "resend_api_key", ""),
        # from 复用「发件邮箱」，需是 Resend 中已验证域名的地址
        "from": settings_store.get(db, "smtp_email", ""),
    }


RESEND_API = "https://api.resend.com/emails"


def _send_resend(cfg: dict, to: str, subject: str, html: str) -> bool:
    payload = json.dumps(
        {"from": cfg["from"], "to": [to], "subject": subject, "html": html}
    ).encode("utf-8")
    req = urllib.request.Request(
        RESEND_API,
        data=payload,
        method="POST",
        headers={
            "Authorization": f"Bearer {cfg['key']}",
            "Content-Type": "application/json",
            # Resend 前面有 Cloudflare，默认 Python-urllib UA 会被 1010 拦截
            "User-Agent": "wtab/1.0",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as res:
            return 200 <= res.status < 300
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")
        raise RuntimeError(f"Resend 发送失败：{detail[:200]}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Resend 连接失败：{exc.reason}") from exc


def send(db: Session, to: str, html: str, smtp: dict | None = None) -> bool:
    cfg = smtp_config(db)
    # 后台「邮件测试」按钮会把表单里的 SMTP 配置直接传进来（原项目 Mail::testMail 的 config 参数）
    if smtp:
        cfg.update({k: v for k, v in smtp.items() if k in cfg and v not in (None, "")})
    subject = f"{cfg['sender']}动态令牌"
    # 后台勾选「使用 Resend 发送」后只走 API Key，不再尝试 SMTP
    resend = resend_config(db)
    if not smtp and settings_store.get(db, "mail_use_resend", "0") == "1":
        if not resend["key"]:
            raise RuntimeError("已选择 Resend 发信，请先在后台填写「发送邮件 API Key」")
        return _send_resend(resend, to, subject, html)
    if not cfg["user"] or not cfg["host"]:
        raise RuntimeError("未配置发件邮箱，请先在后台设置 SMTP 或 Resend")
    msg = MIMEText(html, "html", "utf-8")
    msg["Subject"] = Header(subject, "utf-8")
    msg["From"] = f"{cfg['sender']} <{cfg['user']}>"
    msg["To"] = to

    try:
        if cfg["ssl"]:
            server = smtplib.SMTP_SSL(cfg["host"], cfg["port"], timeout=15)
        else:
            server = smtplib.SMTP(cfg["host"], cfg["port"], timeout=15)
            server.starttls()
    except smtplib.SMTPServerDisconnected as exc:
        raise RuntimeError(
            f"SMTP 连接被 {cfg['host']}:{cfg['port']} 关闭：多为网络/防火墙屏蔽 SMTP 端口，"
            "可改用 Resend 发送邮件 API Key"
        ) from exc
    try:
        server.login(cfg["user"], cfg["password"])
        server.sendmail(cfg["user"], [to], msg.as_string())
    except smtplib.SMTPAuthenticationError as exc:
        raise RuntimeError("SMTP 认证失败：请检查邮箱密码/授权码（Hotmail 需开启两步验证并使用应用密码）") from exc
    finally:
        try:
            server.quit()
        except Exception:  # noqa: BLE001 - 已发完，退出失败不影响结果
            pass
    return True


def code_html(db: Session, code: str, time_text: str) -> str:
    template = settings_store.get(db, "smtp_code_template", "") or SITE_DEFAULTS["smtp_code_template"]
    return template.replace("{$code}", code).replace("{$time}", time_text)
