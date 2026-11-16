import json
from app.database import SessionLocal
from app.models import Setting, Config, Tabbar, User, Link

db = SessionLocal()
print("defaultTab setting:", repr(db.get(Setting, "defaultTab").value if db.get(Setting, "defaultTab") else None))
print("users:", [(u.id, u.mail, u.manager) for u in db.query(User).all()])
for u in db.query(User).all():
    c = db.query(Config).filter_by(user_id=u.id).first()
    t = db.query(Tabbar).filter_by(user_id=u.id).first()
    l = db.query(Link).filter_by(user_id=u.id).first()
    theme = (json.loads(c.config) if isinstance(c.config, str) else (c.config or {})).get("theme", {}) if c else None
    tabs = (json.loads(t.tabs) if isinstance(t.tabs, str) else (t.tabs or [])) if t else []
    ln = (json.loads(l.link) if isinstance(l.link, str) else (l.link or [])) if l else []
    print(u.id, u.mail,
          "| theme:", "none" if not c else {k: theme.get(k) for k in ("backgroundImage", "tabbar", "LinkTitle")},
          "| tabbar items:", len(tabs),
          "| links:", len(ln))
db.close()
