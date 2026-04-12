"""generate_web.py - ETF Monitor Terminal v8.0 (程式碼重構與優化)

1. 前後端分離：HTML 模板抽離至 template.html
2. Pandas 效能優化：set_index O(1) 查找、向量化運算
3. AI Agent 錯誤處理強化：HTTP 401/429/500 友善提示
4. Chart.js：template.html 以 __HOLDINGS_TREND_JSON__ 嵌入持股／分點歷史序列
"""

import os
import glob
import re
import json
from datetime import datetime

import pandas as pd
from pathlib import Path

from broker_config import BROKER_LIST

HISTORY_DIR = "history"
OUTPUT_FILE = "index.html"
TEMPLATE_FILE = "template.html"
# 每檔股票走勢序列最多保留筆數（依交易日），避免嵌入 HTML 過大
MAX_TREND_POINTS = 252

SECTOR_MAP = {
    "台積電": "半導體", "聯發科": "半導體", "京元電": "半導體", "日月光投控": "半導體", "瑞昱": "半導體", "聯電": "半導體", "世芯-KY": "半導體", "力旺": "半導體", "聯詠": "半導體", "南亞科": "半導體", "欣銓": "半導體", "精測": "半導體", "穎崴": "半導體", "旺矽": "半導體", "群聯": "半導體",
    "鴻海": "電腦週邊", "廣達": "電腦週邊", "緯創": "電腦週邊", "緯穎": "電腦週邊", "技嘉": "電腦週邊", "華碩": "電腦週邊", "英業達": "電腦週邊", "仁寶": "電腦週邊", "奇鋐": "電腦週邊", "雙鴻": "電腦週邊", "勤誠": "電腦週邊", "富世達": "電腦週邊",
    "台達電": "電子零組件", "健策": "電子零組件", "欣興": "電子零組件", "南電": "電子零組件", "金像電": "電子零組件", "國巨": "電子零組件", "台光電": "電子零組件", "台燿": "電子零組件", "聯茂": "電子零組件", "建準": "電子零組件", "川湖": "電子零組件", "凡甲": "電子零組件",
    "智邦": "通信網路", "華星光": "通信網路", "前鼎": "通信網路", "兆赫": "通信網路", "光紅建聖": "通信網路", "啟碁": "通信網路",
    "中信金": "金融保險", "富邦金": "金融保險", "國泰金": "金融保險", "兆豐金": "金融保險", "玉山金": "金融保險", "元大金": "金融保險", "開發金": "金融保險", "台新金": "金融保險", "華南金": "金融保險",
    "華城": "電機機械", "士電": "電機機械", "中興電": "電機機械", "亞力": "電機機械", "亞德客-KY": "電機機械",
    "長榮": "航運", "華航": "航運", "陽明": "航運", "萬海": "航運",
    "寶雅": "貿易百貨", "統一超": "貿易百貨", "全家": "貿易百貨",
    "鈊象": "文化創意", "大成鋼": "鋼鐵", "聚陽": "紡織纖維", "達興材": "化學"
}

NAME_REPLACEMENTS = {
    "台灣積體電路製造": "台積電", "鴻海精密工業": "鴻海", "台達電子工業": "台達電", "緯穎科技服務": "緯穎", "聯發科技": "聯發科", "金像電子（股）公司": "金像電", "金像電子": "金像電", "廣達電腦": "廣達", "智邦科技": "智邦", "奇鋐科技": "奇鋐", "鴻勁精密": "鴻勁", "台燿科技": "台燿", "群聯電子": "群聯", "健策精密工業": "健策", "旺矽科技": "旺矽", "勤誠興業": "勤誠", "中國信託金融控股": "中信金", "京元電子": "京元電", "緯創資通": "緯創", "文曄科技": "文曄", "欣銓科技": "欣銓", "致伸科技": "致伸", "南亞科技": "南亞科", "健鼎科技": "健鼎", "凡甲科技": "凡甲", "崇越科技": "崇越", "瑞昱半導體": "瑞昱", "致茂電子": "致茂", "鈊象電子": "鈊象", "高力熱處理工業": "高力", "台光電子材料": "台光電", "華城電機": "華城", "穎崴科技": "穎崴", "中華精測科技": "精測", "川湖科技": "川湖", "亞德客國際集團": "亞德客-KY", "玉山金融控股": "玉山金", "富邦金融控股": "富邦金", "華邦電子": "華邦電", "大成不銹鋼工業": "大成鋼", "聚陽實業": "聚陽", "達興材料": "達興材", "技嘉科技": "技嘉", "貿聯控股（BizLink Holding In": "貿聯-KY", "寶雅國際": "寶雅", "創意電子": "創意", "光紅建聖": "光紅建聖", "亞德客": "亞德客-KY"
}
STRIP_PATTERN = re.compile(r"（股）公司|\(股\)公司|股份有限公司|有限公司|科技|工業|電子|電腦")


def clean_stock_name(name: str) -> str:
    if name is None:
        return ""
    try:
        if pd.isna(name):
            return ""
    except (TypeError, ValueError):
        pass
    if not isinstance(name, str):
        name = str(name)
    if name.lower() == "nan":
        return ""
    name = name.replace("*", "").strip()
    for old, new in NAME_REPLACEMENTS.items():
        if old in name:
            return new
    name = STRIP_PATTERN.sub("", name)
    return name.strip()


def _scalar_numeric(val, default=0.0):
    """將單一值或單列 Series 轉為 float；NaN 為 default。"""
    v = pd.to_numeric(val, errors="coerce")
    if isinstance(v, pd.Series):
        v = v.iloc[0] if len(v) else default
    if pd.isna(v):
        return default
    return float(v)


def _scalar_int(val, default=0) -> int:
    """安全轉 int；避免 int(Series) 與 int(NaN)。"""
    v = pd.to_numeric(val, errors="coerce")
    if isinstance(v, pd.Series):
        v = v.iloc[0] if len(v) else default
    if pd.isna(v):
        return default
    try:
        return int(v)
    except (TypeError, ValueError):
        return default


def _shares_thousands(val) -> int:
    """持股股數（股）轉千張；NaN 為 0。"""
    v = pd.to_numeric(val, errors="coerce")
    if isinstance(v, pd.Series):
        v = v.iloc[0] if len(v) else 0
    if pd.isna(v):
        return 0
    try:
        return int(float(v) / 1000)
    except (TypeError, ValueError, OverflowError):
        return 0


def _normalize_index_row(row):
    """若 .loc[c] 因重複 index 得到 DataFrame，取第一列為 Series。"""
    if isinstance(row, pd.DataFrame):
        return row.iloc[0]
    return row


def _row_to_item(row: pd.Series, c_name: str, code: str, diff: int, amount: float, w_diff: float = 0.0) -> dict:
    w = _scalar_numeric(row.get("weight", 0), 0.0) if "weight" in row.index else 0.0
    return {
        "name": c_name,
        "code": str(code),
        "diff": diff,
        "amount": amount,
        "sector": SECTOR_MAP.get(c_name, "其他"),
        "weight": w,
        "w_diff": w_diff,
        "price": _scalar_numeric(row.get("price", 0), 0.0),
    }


def collect_daily_real_prices(file_map: dict[str, list[tuple[str, str]]]) -> dict[str, dict[str, float]]:
    """從各 ETF 持股 CSV 建立每日真實成交價：{ "YYYY-MM-DD": { "2330": 800.0, ... } }。"""
    daily_real_prices: dict[str, dict[str, float]] = {}
    for etf_code, files in file_map.items():
        if etf_code in BROKER_LIST:
            continue
        files.sort(key=lambda x: x[0])
        for date_str, f in files:
            try:
                df = pd.read_csv(f, dtype={"code": str})
                if "code" not in df.columns or "price" not in df.columns:
                    continue
                df["price"] = pd.to_numeric(df["price"], errors="coerce").fillna(0.0)
                for _, row in df.iterrows():
                    p = _scalar_numeric(row.get("price", 0), 0.0)
                    if p <= 0:
                        continue
                    c = str(row.get("code", "") or "").strip()
                    if not c:
                        continue
                    daily_real_prices.setdefault(date_str, {})[c] = p
            except Exception as e:
                print(f"收集 ETF 價格 {etf_code} {f} 失敗: {e}")
    return daily_real_prices


def _broker_row_amount_10k(net_shares: int, net_amount: float, real_p: float, csv_avg: float) -> float:
    """分點單列金額（萬元）：與張數一致。優先 ETF 參考價，其次玩股網均價，最後 CSV 淨金額（萬元）。"""
    mag = abs(net_shares)
    if real_p > 0:
        return mag * real_p / 10.0
    if csv_avg > 0:
        return mag * csv_avg / 10.0
    return abs(net_amount)


def _code_lookup_candidates(code_val: str) -> list[str]:
    """ETF 持股與分點 CSV 的股票代碼格式可能不同（前導零、字串），查價時多試幾種鍵。"""
    s = str(code_val or "").strip()
    if not s:
        return []
    out: list[str] = []
    seen: set[str] = set()

    def add(x: str) -> None:
        if x and x not in seen:
            seen.add(x)
            out.append(x)

    add(s)
    if s.isdigit():
        n = int(s)
        add(str(n))
        if n < 100000:
            add(f"{n:04d}")
            add(f"{n:05d}")
    return out


def _lookup_real_price(
    daily_real_prices: dict[str, dict[str, float]], date_str: str, code_val: str
) -> float:
    d = daily_real_prices.get(date_str) or {}
    for c in _code_lookup_candidates(code_val):
        p = d.get(c)
        if p is not None and p > 0:
            return float(p)
    return 0.0


def process_broker_file(
    etf_code: str,
    files: list[tuple[str, str]],
    database: dict[str, dict],
    daily_real_prices: dict[str, dict[str, float]],
) -> None:
    """處理分點 CSV：股價優先使用 ETF 匯總之真實價格，不再用金額／張數反推。"""
    files.sort(key=lambda x: x[0])
    for date_str, f in files:
        try:
            df = pd.read_csv(f, dtype={"code": str})
            if "net_shares" not in df.columns or "net_amount" not in df.columns:
                continue
            df["net_shares"] = pd.to_numeric(df["net_shares"], errors="coerce").fillna(0).astype(int)
            df["net_amount"] = pd.to_numeric(df["net_amount"], errors="coerce").fillna(0.0)
            if "buy_shares" not in df.columns:
                df["buy_shares"] = 0
            if "sell_shares" not in df.columns:
                df["sell_shares"] = 0
            df["buy_shares"] = pd.to_numeric(df["buy_shares"], errors="coerce").fillna(0).astype(int)
            df["sell_shares"] = pd.to_numeric(df["sell_shares"], errors="coerce").fillna(0).astype(int)
            if "avg_price" not in df.columns:
                df["avg_price"] = 0.0
            df["avg_price"] = pd.to_numeric(df["avg_price"], errors="coerce").fillna(0.0)
            if "name" in df.columns:
                df["name"] = df["name"].apply(
                    lambda x: "" if x is None or (isinstance(x, float) and pd.isna(x)) else str(x)
                )
            if date_str not in database:
                database[date_str] = {}
            increased, decreased = [], []
            for _, row in df.iterrows():
                net_shares = _scalar_int(row.get("net_shares", 0), 0)
                net_amount = _scalar_numeric(row.get("net_amount", 0), 0.0)
                buy_shares = _scalar_int(row.get("buy_shares", 0), 0)
                sell_shares = _scalar_int(row.get("sell_shares", 0), 0)
                csv_avg = _scalar_numeric(row.get("avg_price", 0), 0.0)
                c_name = clean_stock_name(row.get("name", ""))
                code_val = str(row.get("code", "") or "").strip()
                sector = SECTOR_MAP.get(c_name, "其他")
                real_p = _lookup_real_price(daily_real_prices, date_str, code_val)
                if real_p > 0:
                    avg_price_val = real_p
                    price_val = real_p
                else:
                    avg_price_val = csv_avg
                    price_val = csv_avg
                amt_mag = _broker_row_amount_10k(net_shares, net_amount, real_p, csv_avg)
                base_item = {
                    "name": c_name,
                    "code": code_val,
                    "sector": sector,
                    "weight": 0,
                    "w_diff": 0,
                    "avg_price": avg_price_val,
                    "price": price_val,
                    "buy_shares": buy_shares,
                    "sell_shares": sell_shares,
                }
                if net_shares > 0:
                    increased.append({**base_item, "diff": net_shares, "amount": amt_mag})
                elif net_shares < 0:
                    decreased.append({**base_item, "diff": abs(net_shares), "amount": amt_mag})
            increased.sort(key=lambda x: (-x["diff"], -x.get("amount", 0)))
            decreased.sort(key=lambda x: (-x["diff"], -x.get("amount", 0)))
            database[date_str][etf_code] = {"new_buy": [], "sold_out": [], "increased": increased, "decreased": decreased}
        except Exception as e:
            print(f"處理經紀 {etf_code} {f} 失敗: {e}")


def process_etf_file(
    etf_code: str,
    files: list[tuple[str, str]],
    database: dict[str, dict],
    daily_real_prices: dict[str, dict[str, float]],
) -> None:
    """ETF 前後日差分；並將當日 CSV 中 price>0 寫入 daily_real_prices（與 collect 重複時以本次為準）。"""
    files.sort(key=lambda x: x[0])
    for i in range(1, len(files)):
        prev_date, prev_file = files[i - 1]
        curr_date, curr_file = files[i]

        if curr_date not in database:
            database[curr_date] = {}

        try:
            df_prev = pd.read_csv(prev_file, dtype={"code": str})
            df_curr = pd.read_csv(curr_file, dtype={"code": str})
            for df in (df_prev, df_curr):
                if "price" not in df.columns:
                    df["price"] = 0.0
                if "weight" not in df.columns:
                    df["weight"] = 0.0
                if "weight" in df.columns:
                    df["weight"] = pd.to_numeric(df["weight"], errors="coerce").fillna(0.0)
                if "price" in df.columns:
                    df["price"] = pd.to_numeric(df["price"], errors="coerce").fillna(0.0)
                if "shares" in df.columns:
                    df["shares"] = pd.to_numeric(df["shares"], errors="coerce").fillna(0)
                if "name" in df.columns:
                    df["name"] = df["name"].apply(
                        lambda x: "" if x is None or (isinstance(x, float) and pd.isna(x)) else str(x)
                    )

            # 當日真實價寫入全域表（供分點與後續查詢）
            for _, row in df_curr.iterrows():
                p = _scalar_numeric(row.get("price", 0), 0.0)
                if p <= 0:
                    continue
                cc = str(row.get("code", "") or "").strip()
                if cc:
                    daily_real_prices.setdefault(curr_date, {})[cc] = p

            df_prev["code"] = df_prev["code"].astype(str)
            df_curr["code"] = df_curr["code"].astype(str)
            prev_idx = df_prev.set_index("code")
            curr_idx = df_curr.set_index("code")

            prev_codes = set(prev_idx.index)
            curr_codes = set(curr_idx.index)
            common_codes = prev_codes & curr_codes

            new_buy, sold_out, increased, decreased = [], [], [], []

            for c in (curr_codes - prev_codes):
                row = _normalize_index_row(curr_idx.loc[c])
                shares = _shares_thousands(row["shares"])
                price = _scalar_numeric(row.get("price", 0), 0.0)
                c_name = clean_stock_name(row.get("name", ""))
                amount_10k = (shares * price) / 10 if price > 0 else 0
                new_buy.append(_row_to_item(row, c_name, c, shares, amount_10k, _scalar_numeric(row.get("weight", 0), 0.0)))

            for c in (prev_codes - curr_codes):
                row = _normalize_index_row(prev_idx.loc[c])
                shares = _shares_thousands(row["shares"])
                price = _scalar_numeric(row.get("price", 0), 0.0)
                weight = _scalar_numeric(row.get("weight", 0), 0.0)
                c_name = clean_stock_name(row.get("name", ""))
                amount_10k = (shares * price) / 10 if price > 0 else 0
                sold_out.append({
                    "name": c_name,
                    "code": str(c),
                    "diff": shares,
                    "weight": 0.0,
                    "w_diff": -weight,
                    "amount": amount_10k,
                    "sector": SECTOR_MAP.get(c_name, "其他"),
                    "price": price,
                })

            for c in common_codes:
                row_curr = _normalize_index_row(curr_idx.loc[c])
                row_prev = _normalize_index_row(prev_idx.loc[c])
                shares_curr = _shares_thousands(row_curr["shares"])
                shares_prev = _shares_thousands(row_prev["shares"])
                diff = shares_curr - shares_prev
                if diff == 0:
                    continue
                weight_curr = _scalar_numeric(row_curr.get("weight", 0), 0.0)
                weight_prev = _scalar_numeric(row_prev.get("weight", 0), 0.0)
                w_diff = weight_curr - weight_prev
                price_curr = _scalar_numeric(row_curr.get("price", 0), 0.0)
                c_name = clean_stock_name(row_curr.get("name", ""))
                amount_10k = (abs(diff) * price_curr) / 10 if price_curr > 0 else 0
                if diff > 0:
                    increased.append(_row_to_item(row_curr, c_name, c, diff, amount_10k, w_diff))
                else:
                    decreased.append(_row_to_item(row_curr, c_name, c, abs(diff), amount_10k, w_diff))

            sort_key = lambda x: (-x["diff"], -x.get("amount", 0))
            new_buy.sort(key=sort_key)
            sold_out.sort(key=sort_key)
            increased.sort(key=sort_key)
            decreased.sort(key=sort_key)

            database[curr_date][etf_code] = {
                "new_buy": new_buy,
                "sold_out": sold_out,
                "increased": increased,
                "decreased": decreased,
            }
        except Exception as e:
            print(f"處理 {curr_file} 失敗: {e}")


def collect_file_map() -> dict[str, list[tuple[str, str]]]:
    """history 目錄下 CSV：{ 標的代碼: [(日期字串, 路徑), ...] }。"""
    all_files = glob.glob(os.path.join(HISTORY_DIR, "*.csv"))
    file_map: dict[str, list[tuple[str, str]]] = {}
    for f in all_files:
        basename = Path(f).stem
        parts = basename.split("_")
        if len(parts) >= 2:
            code, date_str = parts[0], parts[1]
            if code not in file_map:
                file_map[code] = []
            file_map[code].append((date_str, f))
    return file_map


def build_holdings_trend_series(file_map: dict[str, list[tuple[str, str]]]) -> dict:
    """從原始 CSV 建立持股／分點淨張時間序列，供前端 Chart.js（與單日 diff 資料庫互補）。"""
    out_etf: dict = {}
    out_broker: dict = {}
    for etf_code, files in file_map.items():
        files_sorted = sorted(files, key=lambda x: x[0])
        if etf_code in BROKER_LIST:
            acc: dict[str, dict] = {}
            for date_str, fpath in files_sorted:
                try:
                    df = pd.read_csv(fpath, dtype={"code": str})
                    if "net_shares" not in df.columns:
                        continue
                    df["net_shares"] = pd.to_numeric(df["net_shares"], errors="coerce").fillna(0).astype(int)
                    if "name" in df.columns:
                        df["name"] = df["name"].apply(
                            lambda x: "" if x is None or (isinstance(x, float) and pd.isna(x)) else str(x)
                        )
                    for _, row in df.iterrows():
                        code_val = str(row.get("code", "") or "").strip()
                        if not code_val:
                            continue
                        c_name = clean_stock_name(row.get("name", ""))
                        sec = SECTOR_MAP.get(c_name, "其他")
                        net = _scalar_int(row.get("net_shares", 0), 0)
                        if code_val not in acc:
                            acc[code_val] = {"n": c_name, "sec": sec, "pts": []}
                        acc[code_val]["pts"].append({"d": date_str, "n": net})
                except Exception as e:
                    print(f"趨勢序列 分點 {etf_code} {fpath}: {e}")
            for _k, v in acc.items():
                v["pts"] = v["pts"][-MAX_TREND_POINTS:]
            out_broker[etf_code] = acc
        else:
            acc = {}
            for date_str, fpath in files_sorted:
                try:
                    df = pd.read_csv(fpath, dtype={"code": str})
                    if "code" not in df.columns or "shares" not in df.columns:
                        continue
                    df["shares"] = pd.to_numeric(df["shares"], errors="coerce").fillna(0)
                    if "weight" not in df.columns:
                        df["weight"] = 0.0
                    df["weight"] = pd.to_numeric(df["weight"], errors="coerce").fillna(0.0)
                    if "name" in df.columns:
                        df["name"] = df["name"].apply(
                            lambda x: "" if x is None or (isinstance(x, float) and pd.isna(x)) else str(x)
                        )
                    for _, row in df.iterrows():
                        c = str(row.get("code", "") or "").strip()
                        if not c:
                            continue
                        c_name = clean_stock_name(row.get("name", ""))
                        sec = SECTOR_MAP.get(c_name, "其他")
                        sk = _shares_thousands(row.get("shares", 0))
                        w = _scalar_numeric(row.get("weight", 0), 0.0)
                        if c not in acc:
                            acc[c] = {"n": c_name, "sec": sec, "pts": []}
                        acc[c]["pts"].append({"d": date_str, "s": sk, "w": round(w, 4)})
                except Exception as e:
                    print(f"趨勢序列 ETF {etf_code} {fpath}: {e}")
            for _k, v in acc.items():
                v["pts"] = v["pts"][-MAX_TREND_POINTS:]
            out_etf[etf_code] = acc
    return {"etf": out_etf, "broker": out_broker}


def process_all_data() -> dict:
    file_map = collect_file_map()
    if not file_map:
        return {}

    daily_real_prices: dict[str, dict[str, float]] = collect_daily_real_prices(file_map)
    database: dict[str, dict] = {}

    for etf_code, files in file_map.items():
        if etf_code in BROKER_LIST:
            process_broker_file(etf_code, files, database, daily_real_prices)
        else:
            process_etf_file(etf_code, files, database, daily_real_prices)

    return database


def load_template() -> str:
    script_dir = Path(__file__).resolve().parent
    template_path = script_dir / TEMPLATE_FILE
    if not template_path.exists():
        raise FileNotFoundError(f"找不到模板檔: {template_path}")
    with open(template_path, "r", encoding="utf-8") as f:
        return f.read()


def load_digest(script_dir: Path) -> dict:
    """每日批次快照（fetch_digest.py）；若無檔案則嵌入空物件。"""
    path = script_dir / "digest.json"
    if not path.is_file():
        return {
            "ok": False,
            "fetchedAt": None,
            "news": {
                "ok": False,
                "items": [],
                "disclaimer": "",
                "error": "尚未產生：請先執行 python3 fetch_digest.py 再產生網頁",
            },
            "markets": {
                "ok": False,
                "items": [],
                "disclaimer": "",
                "error": "尚未產生：請先執行 python3 fetch_digest.py 再產生網頁",
            },
            "sectors": {
                "ok": False,
                "items": [],
                "error": "尚未產生：請先執行 python3 fetch_digest.py 再產生網頁",
            },
        }
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {
            "ok": False,
            "fetchedAt": None,
            "news": {"ok": False, "items": [], "error": "digest.json 讀取失敗"},
            "markets": {"ok": False, "items": [], "error": "digest.json 讀取失敗"},
            "sectors": {"ok": False, "items": [], "error": "digest.json 讀取失敗"},
        }


def main() -> None:
    print("[INFO] 開始產出 Web Dashboard (v8.0 程式碼重構與優化)...")
    db = process_all_data()
    file_map = collect_file_map()
    trend_obj = build_holdings_trend_series(file_map) if file_map else {"etf": {}, "broker": {}}
    template = load_template()
    script_dir = Path(__file__).resolve().parent

    json_str = json.dumps(db, ensure_ascii=False)
    broker_str = json.dumps(BROKER_LIST, ensure_ascii=False)
    trend_str = json.dumps(trend_obj, ensure_ascii=False)
    meta = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "data_through": max(db.keys()) if db else None,
    }
    meta_str = json.dumps(meta, ensure_ascii=False)
    digest = load_digest(script_dir)
    if digest.get("fetchedAt"):
        print(f"[INFO] 嵌入 digest.json（快照 {digest['fetchedAt']}）")
    else:
        print("[INFO] 未偵測 digest.json 快照，總覽新聞／指數為占位（可執行 fetch_digest.py）")
    digest_str = json.dumps(digest, ensure_ascii=False)
    print("[INFO] 已嵌入持股／分點走勢序列（Chart.js 用）")
    final_html = (
        template.replace("__DB_JSON__", json_str)
        .replace("__BROKER_JSON__", broker_str)
        .replace("__META_JSON__", meta_str)
        .replace("__DIGEST_JSON__", digest_str)
        .replace("__HOLDINGS_TREND_JSON__", trend_str)
    )

    output_path = script_dir / OUTPUT_FILE
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(final_html)

    print(f"[OK] 成功產出 {OUTPUT_FILE}")
    print("[INFO] 若曾修改 template 的 Tailwind class，請先於專案目錄執行：npm run build:css")
    print("[INFO] 上傳 GitHub Pages 前可執行：python3 check_deploy.py")


if __name__ == "__main__":
    main()
