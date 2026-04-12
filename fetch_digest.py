#!/usr/bin/env python3
"""fetch_digest.py — 每日批次抓取財經 RSS 與台／美／港股指数（非即時，供嵌入 index.html）

使用方式：
  python3 fetch_digest.py

排程（macOS crontab 例：每天 08:00）：
  0 8 * * * cd /path/to/00981a-monitor && /usr/bin/python3 fetch_digest.py >> /tmp/fetch_digest.log 2>&1

產出 digest.json 後，再執行 generate_web.py 即可把快照嵌入單一 HTML（手機用檔案或靜態網址皆可）。
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import re
import ssl
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
OUTPUT_FILE = SCRIPT_DIR / "digest.json"

RSS_FEEDS: list[tuple[str, str]] = [
    ("https://money.udn.com/rssfeed/news/1001", "經濟日報"),
    ("https://news.ltn.com.tw/rss/business.xml", "自由時報財經"),
    ("https://www.cna.com.tw/rss/aall.aspx", "中央社"),
    ("https://technews.tw/feed/", "TechNews"),
]

STOOQ_MAP: dict[str, dict[str, str]] = {
    "^SPX": {"label": "S&P 500", "ccy": "USD"},
    "^NDX": {"label": "Nasdaq 100", "ccy": "USD"},
    "^DJI": {"label": "道瓊", "ccy": "USD"},
    "^HSI": {"label": "恆生指數", "ccy": "HKD"},
}

USER_AGENT = "Mozilla/5.0 (compatible; 00981a-monitor-digest/1.0; +local)"
_SSL_WARNED = False


def http_get(url: str, timeout: int = 22) -> str | None:
    """先驗證 SSL；僅在憑證錯誤時改不驗證重試（macOS 直裝 Python 常見）。"""
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=ssl.create_default_context()) as r:
            return r.read().decode("utf-8", errors="replace")
    except (urllib.error.URLError, ssl.SSLError, OSError) as e:
        err = str(e).upper()
        global _SSL_WARNED
        if "CERTIFICATE" in err or "SSL" in err or "CERTIFICATE_VERIFY_FAILED" in err:
            if not _SSL_WARNED:
                print("[WARN] SSL 憑證驗證失敗，後續改不驗證連線（建議：pip install certifi 或 Install Certificates.command）")
                _SSL_WARNED = True
            try:
                with urllib.request.urlopen(req, timeout=timeout, context=ssl._create_unverified_context()) as r:
                    return r.read().decode("utf-8", errors="replace")
            except (urllib.error.URLError, ssl.SSLError, TimeoutError, OSError):
                return None
        return None
    except TimeoutError:
        return None


def strip_tags_text(s: str) -> str:
    s = re.sub(r"<[^>]+>", "", s)
    return s.replace("&nbsp;", " ").strip()


def parse_pub_ts(pub_raw: str) -> float:
    if not pub_raw:
        return 0.0
    try:
        dt = parsedate_to_datetime(pub_raw.strip())
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.timestamp()
    except (TypeError, ValueError, OverflowError):
        return 0.0


def parse_rss_items(xml_str: str, source: str) -> list[dict]:
    items: list[dict] = []
    try:
        root = ET.fromstring(xml_str)
    except ET.ParseError:
        return items

    channel = root.find("channel")
    if channel is not None:
        for item in channel.findall("item"):
            title = strip_tags_text(item.findtext("title", "") or "")
            link = (item.findtext("link", "") or "").strip()
            pub_raw = item.findtext("pubDate", "") or ""
            ts = parse_pub_ts(pub_raw)
            pub_iso = None
            if ts > 0:
                pub_iso = datetime.fromtimestamp(ts, tz=timezone.utc).astimezone().isoformat(timespec="seconds")
            if title and link:
                items.append(
                    {
                        "title": title,
                        "link": link,
                        "source": source,
                        "published": pub_iso,
                        "ts": ts,
                    }
                )
        return items

    atom = "{http://www.w3.org/2005/Atom}"
    for entry in root.findall(f"{atom}entry"):
        title_el = entry.find(f"{atom}title")
        title = strip_tags_text((title_el.text or "").strip() if title_el is not None else "")
        link = ""
        for link_el in entry.findall(f"{atom}link"):
            href = link_el.attrib.get("href", "")
            if href:
                link = href
                break
        upd_el = entry.find(f"{atom}updated")
        updated = (upd_el.text or "").strip() if upd_el is not None else ""
        ts = 0.0
        pub_iso = None
        if updated:
            try:
                dt = datetime.fromisoformat(updated.replace("Z", "+00:00"))
                ts = dt.timestamp()
                pub_iso = dt.astimezone().isoformat(timespec="seconds")
            except ValueError:
                pass
        if title and link:
            items.append({"title": title, "link": link, "source": source, "published": pub_iso, "ts": ts})

    return items


def fetch_news(max_items: int = 24) -> dict:
    all_rows: list[dict] = []
    for url, src in RSS_FEEDS:
        body = http_get(url)
        if not body:
            continue
        for it in parse_rss_items(body, src):
            all_rows.append(it)
    all_rows.sort(key=lambda x: x.get("ts") or 0.0, reverse=True)
    seen: set[str] = set()
    out: list[dict] = []
    for row in all_rows:
        key = hashlib.md5(row["link"].encode("utf-8")).hexdigest()
        if key in seen:
            continue
        seen.add(key)
        row.pop("ts", None)
        out.append(row)
        if len(out) >= max_items:
            break
    return {
        "ok": True,
        "items": out,
        "disclaimer": "新聞標題與連結來自公開 RSS，版權歸各媒體；僅供參考。",
    }


def parse_twse_pct_cell(raw: str) -> float | None:
    s = strip_tags_text(str(raw))
    s = s.replace(",", "").replace("%", "").strip()
    if s in ("", "--", "-", "nan"):
        return None
    try:
        return float(s)
    except ValueError:
        return None


def fetch_twse_mi_table() -> tuple[str | None, list | None]:
    """證交所 MI_INDEX 最近有資料的交易日；回傳 (date_yyyymmdd, data_rows)。"""
    for i in range(12):
        d = (datetime.now() - timedelta(days=i)).strftime("%Y%m%d")
        url = f"https://www.twse.com.tw/rwd/zh/afterTrading/MI_INDEX?response=json&date={d}&type=IND"
        body = http_get(url, 18)
        if not body:
            continue
        try:
            j = json.loads(body)
        except json.JSONDecodeError:
            continue
        if j.get("stat") != "OK":
            continue
        table = (j.get("tables") or [{}])[0]
        data = table.get("data") or []
        if data:
            return d, data
    return None, None


def weighted_from_data(data: list, d: str) -> dict | None:
    for row in data:
        if not isinstance(row, (list, tuple)) or len(row) < 5:
            continue
        if "發行量加權" not in str(row[0]):
            continue
        close = strip_tags_text(str(row[1]))
        chg_pts = strip_tags_text(str(row[3]))
        chg_pct = strip_tags_text(str(row[4]))
        pct = chg_pct if "%" in chg_pct else f"{chg_pct}%"
        return {
            "symbol": "TWSE",
            "label": "加權指數（TWSE）",
            "price": close,
            "change": chg_pts,
            "changePercent": pct,
            "currency": "TWD",
            "source": "twse",
            "asOf": d,
        }
    return None


def fetch_twse_weighted() -> dict | None:
    d, data = fetch_twse_mi_table()
    if not d or not data:
        return None
    return weighted_from_data(data, d)


def _twse_sector_excluded(name: str) -> bool:
    """排除大盤／主題指數，保留產業「類指數」等。"""
    n = name.strip()
    for p in (
        "發行量加權",
        "寶島",
        "台灣50",
        "臺灣公司治理",
        "臺灣中型100",
        "臺灣就業99",
        "臺灣高薪100",
        "未含金融",
        "未含電子",
        "未含金融電子",
        "小型股300",
        "臺灣發達",
        "臺灣高股息",
        "台灣50權重",
    ):
        if n.startswith(p) or p in n:
            return True
    return False


def sector_indices_from_data(data: list, d: str) -> dict:
    """產業／類股指數漲跌（證交所 MI_INDEX；漲跌%為相對前一交易日）。"""
    if not data:
        return {
            "ok": False,
            "items": [],
            "asOf": None,
            "error": "無法取得證交所 MI_INDEX",
            "disclaimer": "資料來源：臺灣證交所 MI_INDEX；方塊面積為 |漲跌幅|，紅漲綠跌。僅供參考。",
        }
    items: list[dict] = []
    for row in data:
        if not isinstance(row, (list, tuple)) or len(row) < 5:
            continue
        name = strip_tags_text(str(row[0]))
        if not name:
            continue
        if _twse_sector_excluded(name):
            continue
        if "類指數" not in name and "臺灣資訊科技指數" not in name and "台灣資訊科技指數" not in name:
            continue
        pct = parse_twse_pct_cell(row[4])
        if pct is None:
            continue
        close = strip_tags_text(str(row[1]))
        chg_pts = strip_tags_text(str(row[3]))
        items.append(
            {
                "name": name,
                "shortName": name.replace("類指數", "").replace("臺灣", "").replace("台灣", "").strip() or name,
                "changePct": round(pct, 2),
                "absPct": round(abs(pct), 4),
                "up": pct > 0,
                "close": close,
                "changePts": chg_pts,
            }
        )
    items.sort(key=lambda x: -x["absPct"])
    return {
        "ok": bool(items),
        "items": items[:32],
        "asOf": d,
        "disclaimer": "證交所「價格指數」表：各類指數漲跌%為相對前一交易日；方塊面積 ∝ |漲跌幅|，紅漲綠跌。僅供參考。",
    }


def fetch_stooq_batch() -> list[dict]:
    syms = "+".join(STOOQ_MAP.keys())
    url = f"https://stooq.com/q/l/?s={syms}&f=sd2t2ohlcv&h"
    body = http_get(url, 22)
    if not body:
        return []
    lines = [ln.strip() for ln in body.strip().splitlines() if ln.strip()]
    if len(lines) < 2:
        return []
    out: list[dict] = []
    for line in lines[1:]:
        row = next(csv.reader(io.StringIO(line)))
        if len(row) < 8:
            continue
        sym = row[0]
        meta = STOOQ_MAP.get(sym, {"label": sym, "ccy": ""})
        if row[1] == "N/D":
            out.append(
                {
                    "symbol": sym,
                    "label": meta["label"],
                    "price": None,
                    "change": None,
                    "changePercent": None,
                    "currency": meta["ccy"],
                    "source": "stooq",
                    "asOf": None,
                    "note": "暫無報價（休市或延遲）",
                }
            )
            continue
        open_ = float(row[3])
        close = float(row[6])
        dt = f"{row[1]} {row[2]}"
        d_pts = close - open_
        d_pct = (d_pts / open_ * 100.0) if open_ != 0.0 else 0.0
        sign = "+" if d_pts >= 0 else ""
        out.append(
            {
                "symbol": sym,
                "label": meta["label"],
                "price": f"{close:.2f}",
                "change": f"{sign}{d_pts:.2f}",
                "changePercent": f"{d_pct:.2f}",
                "changeNote": "開→收",
                "currency": meta["ccy"],
                "source": "stooq",
                "asOf": dt,
            }
        )
    return out


def build_markets_from_tw_and_stooq(tw: dict | None) -> dict:
    items: list[dict] = []
    if tw:
        items.append(tw)
    items.extend(fetch_stooq_batch())
    return {
        "ok": bool(items),
        "items": items,
        "disclaimer": "國際指數為 Stooq 延遲資料；漲跌為該交易日開→收。台股加權為證交所公開資料。僅供參考。",
    }


def main() -> None:
    print("[INFO] 抓取財經快訊 RSS …")
    news = fetch_news(24)
    print("[INFO] 抓取指數與產業類指數（證交所 MI_INDEX 單次請求）…")
    d, mi_data = fetch_twse_mi_table()
    tw = weighted_from_data(mi_data, d) if mi_data else None
    markets = build_markets_from_tw_and_stooq(tw)
    if mi_data:
        sectors = sector_indices_from_data(mi_data, d)
    else:
        sectors = {
            "ok": False,
            "items": [],
            "asOf": None,
            "error": "無法取得證交所 MI_INDEX",
            "disclaimer": "產業方塊圖需證交所資料。",
        }
    digest = {
        "ok": True,
        "fetchedAt": datetime.now().isoformat(timespec="seconds"),
        "news": news,
        "markets": markets,
        "sectors": sectors,
    }
    OUTPUT_FILE.write_text(json.dumps(digest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        f"[OK] 已寫入 {OUTPUT_FILE.name}（新聞 {len(news['items'])} 則，指數 {len(markets['items'])} 筆，產業類 {len(sectors.get('items') or [])} 筆）"
    )
    print("[INFO] 請執行 python3 generate_web.py 將 digest 嵌入 index.html")


if __name__ == "__main__":
    main()
