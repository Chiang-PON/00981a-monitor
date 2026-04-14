"""openai_global_war.py — 以 OpenAI 產生「全球戰情」各國繁中總結（批次、不預測股價）

環境變數（或專案目錄 .env，見 _load_dotenv_file）：
  OPENAI_API_KEY   必填才會執行
  OPENAI_MODEL     預設 gpt-4o-mini

輸出寫入 digest["globalWarAi"]，前端優先顯示；失敗或未設 Key 時前端退回規則摘要。
"""

from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any

try:
    import requests
except ImportError:
    requests = None

# 與 template.html GLOBAL_WAR_COUNTRIES / GLOBAL_WAR_NEWS_KEYWORDS 對齊
GLOBAL_WAR_DEFS: list[dict[str, Any]] = [
    {"key": "TW", "label": "台灣", "symbols": ["TWSE"]},
    {"key": "US", "label": "美國", "symbols": ["^SPX", "^NDX", "^DJI"]},
    {"key": "CA", "label": "加拿大", "symbols": ["^GSPTSE"]},
    {"key": "HK", "label": "香港", "symbols": ["^HSI"]},
    {"key": "SG", "label": "新加坡", "symbols": ["^STI"]},
    {"key": "KR", "label": "南韓", "symbols": ["^KOSPI"]},
    {"key": "JP", "label": "日本", "symbols": ["^N225"]},
    {"key": "AU", "label": "澳洲", "symbols": ["^AXJO"]},
    {"key": "IN", "label": "印度", "symbols": ["^BSESN"]},
    {"key": "CN", "label": "中國", "symbols": ["^SSEC"]},
    {"key": "DE", "label": "德國", "symbols": ["^DAX"]},
    {"key": "GB", "label": "英國", "symbols": ["^UKX"]},
    {"key": "FR", "label": "法國", "symbols": ["^CAC"]},
]

GLOBAL_WAR_NEWS_KEYWORDS: dict[str, list[str]] = {
    "CA": [
        "加拿大",
        "加股",
        "多倫多",
        "TSX",
        "加拿大央行",
    ],
    "AU": [
        "澳洲",
        "澳大利亞",
        "澳股",
        "雪梨",
        "澳洲央行",
        "RBA",
    ],
    "IN": [
        "印度",
        "印度股",
        "孟買",
        "Sensex",
        "Nifty",
    ],
    "CN": [
        "中國",
        "A股",
        "上證",
        "深證",
        "滬深",
        "人民幣",
    ],
    "TW": [
        "台灣",
        "台股",
        "台幣",
        "新台幣",
        "加權",
        "台積電",
        "證交所",
        "櫃買",
        "櫃檯",
        "TWSE",
        "Taiwan",
        "外資買超",
        "投信買超",
        "元大",
        "國泰",
        "富邦",
        "凱基",
    ],
    "US": [
        "美國",
        "美股",
        "道瓊",
        "那斯達克",
        "Nasdaq",
        "S&P",
        "標普",
        "Fed",
        "聯準會",
        "川普",
        "美元",
        "美債",
        "白宮",
        "華爾街",
        "波音",
        "蘋果公司",
        "輝達",
        "NVIDIA",
        "特斯拉",
    ],
    "HK": ["香港", "恆生", "港股", "陸港股", "港交所", "恒生"],
    "SG": ["新加坡", "星洲", "星國"],
    "KR": ["韓國", "韓股", "KOSPI", "南韓", "首爾"],
    "JP": ["日本", "日經", "日股", "日圓", "日銀", "東證"],
    "DE": ["德國", "DAX", "柏林", "法蘭克福", "歐央行"],
    "GB": ["英國", "英鎊", "富時", "倫敦", "脫歐"],
    "FR": ["法國", "法股", "巴黎"],
}


def _score_title(title: str, country_key: str) -> int:
    kw = GLOBAL_WAR_NEWS_KEYWORDS.get(country_key, [])
    return sum(1 for k in kw if k in title)


def assign_news_buckets(news_items: list[dict]) -> dict[str, list[str]]:
    buckets: dict[str, list[str]] = {d["key"]: [] for d in GLOBAL_WAR_DEFS}
    sorted_items = sorted(
        news_items,
        key=lambda x: str(x.get("published") or ""),
        reverse=True,
    )
    for it in sorted_items:
        title = (it.get("title") or "").strip()
        if not title:
            continue
        tag = it.get("country")
        if tag in buckets:
            buckets[tag].append(title)
            continue
        best_k = None
        best_s = 0
        for d in GLOBAL_WAR_DEFS:
            s = _score_title(title, d["key"])
            if s > best_s:
                best_s = s
                best_k = d["key"]
        if best_k and best_s > 0:
            buckets[best_k].append(title)
    return buckets


def _compact_indices_for_country(markets: dict, symbols: list[str]) -> list[dict[str, Any]]:
    sym_set = set(symbols)
    out: list[dict[str, Any]] = []
    for it in markets.get("items") or []:
        if it.get("symbol") not in sym_set:
            continue
        out.append(
            {
                "symbol": it.get("symbol"),
                "label": it.get("label"),
                "price": it.get("price"),
                "change": it.get("change"),
                "changePercent": it.get("changePercent"),
                "currency": it.get("currency"),
                "note": it.get("note"),
            }
        )
    return out


def _tw_sector_top3(sectors: dict) -> list[dict[str, Any]]:
    if not sectors.get("ok") or not sectors.get("items"):
        return []
    rows = sorted(
        sectors["items"],
        key=lambda x: abs(x.get("absPct") or 0),
        reverse=True,
    )[:3]
    return [
        {
            "name": r.get("shortName") or r.get("name"),
            "changePct": r.get("changePct"),
        }
        for r in rows
    ]


def build_openai_payload(digest: dict) -> dict[str, Any]:
    markets = digest.get("markets") or {}
    news_items = (digest.get("news") or {}).get("items") or []
    sectors = digest.get("sectors") or {}
    buckets = assign_news_buckets(news_items)
    countries: list[dict[str, Any]] = []
    for d in GLOBAL_WAR_DEFS:
        key = d["key"]
        symbols = list(d["symbols"])
        entry: dict[str, Any] = {
            "key": key,
            "label": d["label"],
            "indices": _compact_indices_for_country(markets, symbols),
            "news_titles": (buckets.get(key) or [])[:14],
        }
        if key == "TW":
            entry["tw_sector_top3"] = _tw_sector_top3(sectors)
        countries.append(entry)
    return {"countries": countries}


def _openai_chat_json(api_key: str, model: str, system: str, user: str) -> dict[str, Any]:
    if requests is None:
        raise RuntimeError("需要 requests 套件：pip install requests")
    url = "https://api.openai.com/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    body = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "response_format": {"type": "json_object"},
        "temperature": 0.35,
    }
    r = requests.post(url, headers=headers, json=body, timeout=120)
    r.raise_for_status()
    data = r.json()
    content = data["choices"][0]["message"]["content"]
    return json.loads(content)


SYSTEM_PROMPT = """你是財經新聞編輯。使用者會提供 JSON：各國「主要指數快照」與「新聞標題列表」（可能含台灣證交所產業類前 3）。
請用繁體中文，為輸入 JSON 中 countries 陣列裡**每一個**國家 key 各寫 2～4 句「今日戰情總結」。

硬性規則：
- 只根據提供的指數數字與標題／產業名稱整理語意，不得預測未來股價、不得給買賣建議。
- 不得捏造未在輸入中出現的具體數字、事件或公司名稱；若該國指數與新聞皆無實質內容，可簡短說明「本稿池資料有限」。
- 語氣客觀、簡潔，像戰情室簡報。
- 排版：一句一個完整意思；優先使用「。」結句，必要時用「；」分開兩個短句，避免全部黏成單一句超長段落。

必須只輸出 JSON 物件：**鍵必須與輸入 countries 內每筆的 key 欄位完全一致**，值為該國總結字串。"""


def _load_dotenv_file() -> None:
    """讀取與本檔同目錄的 .env（不覆寫已存在之環境變數）。.env 應已列入 .gitignore。"""
    path = Path(__file__).resolve().parent / ".env"
    if not path.is_file():
        return
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, _, val = line.partition("=")
        key = key.strip()
        val = val.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = val


def enrich_digest_with_global_war_ai(digest: dict) -> dict:
    """若設 OPENAI_API_KEY 則呼叫 API，回傳 digest；否則寫入 globalWarAi skipped。"""
    _load_dotenv_file()
    api_key = (os.environ.get("OPENAI_API_KEY") or "").strip()
    if not api_key:
        digest["globalWarAi"] = {
            "ok": False,
            "skipped": True,
            "reason": "未設定 OPENAI_API_KEY（可在專案目錄建立 .env，或執行前 export）",
        }
        return digest

    model = (os.environ.get("OPENAI_MODEL") or "gpt-4o-mini").strip()
    payload = build_openai_payload(digest)
    user_payload = json.dumps(payload, ensure_ascii=False)
    try:
        result = _openai_chat_json(api_key, model, SYSTEM_PROMPT, user_payload)
    except Exception as e:
        digest["globalWarAi"] = {
            "ok": False,
            "error": str(e),
            "model": model,
        }
        return digest

    keys = [d["key"] for d in GLOBAL_WAR_DEFS]
    summaries: dict[str, str] = {}
    for k in keys:
        v = result.get(k)
        if isinstance(v, str) and v.strip():
            summaries[k] = v.strip()

    digest["globalWarAi"] = {
        "ok": True,
        "generatedAt": datetime.now().isoformat(timespec="seconds"),
        "model": model,
        "disclaimer": "以下為 AI 依本日快照與新聞標題生成之摘要，僅供參考，非投資建議，亦不構成股價預測。",
        "summaries": summaries,
    }
    return digest
