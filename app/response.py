"""统一响应体，与原项目 BaseController->returnMsg() 保持一致的 {code,msg,data}。"""
from __future__ import annotations

from typing import Any

from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse


def _encode(data: Any) -> Any:
    # datetime / Decimal / ORM 对象统一转成 JSON 可序列化形式
    return jsonable_encoder(data)


def ok(data: Any = None, msg: str = "操作成功") -> JSONResponse:
    return JSONResponse({"code": 1, "msg": msg, "data": _encode(data)})


def fail(msg: str = "操作失败", data: Any = None, code: int = 0) -> JSONResponse:
    return JSONResponse({"code": code, "msg": msg, "data": _encode(data)})
