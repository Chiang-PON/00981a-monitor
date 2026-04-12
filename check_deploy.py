#!/usr/bin/env python3
"""靜態部署前檢查（不需伺服器）：必要檔是否存在、index 是否已由 generate_web 產出。

用法：
  python3 check_deploy.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent

REQUIRED_FILES = ("index.html", "trend.html", "tailwind-built.css", "template.html", "trend_template.html")


def main() -> int:
    missing = [f for f in REQUIRED_FILES if not (ROOT / f).is_file()]
    if missing:
        print("[FAIL] 缺少檔案:", ", ".join(missing))
        print("       請確認已在此目錄執行 npm run build:css（若改過版面）與 python3 generate_web.py")
        return 1

    index = (ROOT / "index.html").read_text(encoding="utf-8", errors="replace")
    if (
        "__DB_JSON__" in index
        or "__META_JSON__" in index
        or "__DIGEST_JSON__" in index
        or "__HOLDINGS_TREND_JSON__" in index
    ):
        print("[FAIL] index.html 仍含占位符（__DB_JSON__ 等），請執行 python3 generate_web.py")
        return 1

    if "tailwind-built.css" not in index:
        print("[WARN] index.html 未引用 tailwind-built.css，線上可能無樣式")

    trend = (ROOT / "trend.html").read_text(encoding="utf-8", errors="replace")
    if (
        "__DB_JSON__" in trend
        or "__META_JSON__" in trend
        or "__BROKER_JSON__" in trend
        or "__HOLDINGS_TREND_JSON__" in trend
    ):
        print("[FAIL] trend.html 仍含占位符，請執行 python3 generate_web.py")
        return 1

    print("[OK] 可部署檢查通過（請一併上傳 index.html、trend.html、tailwind-built.css）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
