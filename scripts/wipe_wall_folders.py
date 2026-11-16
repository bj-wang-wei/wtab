"""临时：删除 Wallpaper.type=1 的所有分类行。"""
import os, sys
from sqlalchemy import create_engine, delete
from sqlalchemy.orm import Session

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE)

from app.config import settings
from app.models import Wallpaper

eng = create_engine(settings.database_url)
with Session(eng) as s:
    n = s.execute(delete(Wallpaper).where(Wallpaper.type == 1)).rowcount
    s.commit()
    print(f"deleted {n} folder rows")
