import json
from app.config import STATIC_DIR

for name in ("defaultTab.json",):
    p = STATIC_DIR / name
    if not p.exists():
        print(name, "MISSING")
        continue
    d = json.loads(p.read_text(encoding="utf-8"))
    th = (d.get("config") or {}).get("theme") or {}
    print(name, "keys=", sorted(d.keys()),
          "| bg=", repr(th.get("backgroundImage")),
          "| tabbar=", th.get("tabbar"),
          "| LinkTitle=", th.get("LinkTitle"),
          "| icons=", len(d.get("link") or []), "/", len(d.get("tabbar") or []))
