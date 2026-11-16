"""对比原项目 public/static 与本项目 static，列出缺失/多余文件。"""
from __future__ import annotations

import sys
from pathlib import Path

SRC = Path(r"C:\Users\z\AppData\Local\Temp\opencode\wtab-src\public\static")
DST = Path(__file__).resolve().parent.parent / "static"


def rel(root: Path) -> set[str]:
    return {p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file()}


def main() -> int:
    if not SRC.exists():
        print("source not found:", SRC)
        return 2
    a, b = rel(SRC), rel(DST)
    missing = sorted(a - b)
    extra = sorted(b - a)
    print(f"source={len(a)} local={len(b)} missing={len(missing)} extra={len(extra)}")
    for p in missing:
        print("MISSING", p)
    for p in extra[:50]:
        print("EXTRA", p)
    return 1 if missing else 0


if __name__ == "__main__":
    sys.exit(main())
