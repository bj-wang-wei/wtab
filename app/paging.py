"""ThinkPHP paginate() 的等价分页形状，供 /admin 共用。"""
from __future__ import annotations


def paginate(items: list, limit: int, page: int = 1) -> dict:
    limit = max(1, int(limit or 1))
    page = max(1, int(page or 1))
    total = len(items)
    start = (page - 1) * limit
    return {
        "total": total,
        "per_page": limit,
        "current_page": page,
        "last_page": max(1, -(-total // limit)),
        "data": items[start : start + limit],
    }
