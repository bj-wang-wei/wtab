"""一次性修复：空表单误写把 theme.timeView 置成 false 导致左上角时钟消失。

只在「timeView 为 false」的 Config 行上恢复为 true。默认值是 true，
误写特征（背景为空 / tabbar false / LinkTitle false）此前已被 _fix_theme.py 修回，
所以这里直接按 timeView 判断。
"""
import json

from app.database import SessionLocal
from app.models import Config

FIELDS = ("timeView", "timeWeek", "timeMonthDay", "time24", "timeSecond")

db = SessionLocal()
fixed = 0
for row in db.query(Config).all():
    cfg = json.loads(row.config) if isinstance(row.config, str) else (row.config or {})
    theme = cfg.get("theme") or {}
    if theme.get("timeView") is False:
        theme["timeView"] = True
        cfg["theme"] = theme
        row.config = json.dumps(cfg, ensure_ascii=False)
        fixed += 1
        print("fixed user_id", row.user_id, {k: theme.get(k) for k in FIELDS})
db.commit()
print("fixed", fixed)
db.close()
