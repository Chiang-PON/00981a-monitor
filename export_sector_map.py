#!/usr/bin/env python3
"""從 generate_web.SECTOR_MAP 匯出 sector_map.csv（UTF-8 BOM，Excel 可直接開）。"""
import csv
from pathlib import Path

from generate_web import SECTOR_MAP


def main() -> None:
    out = Path(__file__).resolve().parent / "sector_map.csv"
    rows = sorted(SECTOR_MAP.items(), key=lambda x: (x[1], x[0]))
    with out.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["簡稱", "產業"])
        for name, sector in rows:
            w.writerow([name, sector])
    print(f"[OK] {out}（{len(rows)} 列）")


if __name__ == "__main__":
    main()
