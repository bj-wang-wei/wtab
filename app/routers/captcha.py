"""图形验证码：随机 4 位字符渲染成 SVG，答案存在签名 Session 里，5 分钟有效、一次性。"""
import random
import time

from fastapi import APIRouter, Request
from fastapi.responses import Response

router = APIRouter()

CHARS = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ"  # 去掉 0O1lI 之类易混字符
TTL = 300
WIDTH, HEIGHT = 132, 44


def _svg(code: str) -> str:
    colors = ["#2b3a55", "#3a4a6b", "#26406b", "#4f8cff"]
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}" height="{HEIGHT}" '
        f'viewBox="0 0 {WIDTH} {HEIGHT}"><rect width="{WIDTH}" height="{HEIGHT}" fill="#f2f4f8"/>'
    ]
    for _ in range(3):  # 干扰线
        parts.append(
            f'<line x1="{random.randint(0, WIDTH)}" y1="{random.randint(0, HEIGHT)}" '
            f'x2="{random.randint(0, WIDTH)}" y2="{random.randint(0, HEIGHT)}" '
            'stroke="rgba(120,140,170,.55)" stroke-width="1"/>'
        )
    for i, ch in enumerate(code):
        x = 16 + i * 27
        y = 31 + random.randint(-4, 4)
        rot = random.randint(-18, 18)
        parts.append(
            f'<text x="{x}" y="{y}" font-family="Verdana,DejaVu Sans,sans-serif" font-size="24" '
            f'font-weight="bold" fill="{random.choice(colors)}" transform="rotate({rot} {x} {y})">'
            f"{ch}</text>"
        )
    parts.append("</svg>")
    return "".join(parts)


@router.get("/captcha")
def captcha(request: Request):
    code = "".join(random.choice(CHARS) for _ in range(4))
    request.session["captcha"] = {"code": code, "ts": int(time.time())}
    return Response(
        _svg(code),
        media_type="image/svg+xml",
        headers={"Cache-Control": "no-store, max-age=0"},
    )


def verify(request: Request, code: str) -> bool:
    """校验并作废当前验证码（无论对错都只能试一次）。"""
    saved = request.session.pop("captcha", None)
    if not saved or time.time() - saved.get("ts", 0) > TTL:
        return False
    return saved.get("code", "").upper() == (code or "").upper()
