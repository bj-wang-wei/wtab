"""一次性修复：把被空设置表单覆盖掉的背景/导航栏/名称恢复为默认值。

原因：saveSettings() 早前不检查抽屉是否打开，空表单保存会把
theme.backgroundImage 写成 ""、theme.tabbar / LinkTitle 写成 false。
"""
import json

from app.config import STATIC_DIR
from app.database import SessionLocal
from app.models import Config

default_theme = json.loads((STATIC_DIR / "defaultTab.json").read_text(encoding="utf-8"))["config"]["theme"]

db = SessionLocal()
fixed = 0
for row in db.query(Config).all():
    cfg = json.loads(row.config) if isinstance(row.config, str) else (row.config or {})
    theme = cfg.setdefault("theme", {})
    if theme.get("backgroundImage") or theme.get("tabbar") is not False:
        continue
    # 只有三项同时是"空表单默认"时才认为是误写
    if theme.get("tabbar") is False and theme.get("LinkTitle") is False:
        theme["backgroundImage"] = default_theme["backgroundImage"]
        theme["tabbar"] = default_theme["tabbar"]
        theme["LinkTitle"] = default_theme["LinkTitle"]
        row.config = json.dumps(cfg, ensure_ascii=False)
        fixed += 1
        print("fixed user_id", row.user_id, {k: theme[k] for k in ("backgroundImage", "tabbar", "LinkTitle")})
db.commit()
db.close()
print("fixed", fixed)
