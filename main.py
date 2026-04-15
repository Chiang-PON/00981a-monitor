"""main.py - ETF Monitor Terminal v7.3 (Backend Crawler Engine)

主動式 ETF 家族監控系統 + 凱基大聯盟 18 主力分點監控
- 雲端/本機雙軌：GitHub Actions 自動略過券商爬蟲，本機解除 Headless 突破 Cloudflare
- 凱基大聯盟：18 間凱基證券核心主力分點 (wantgoo 券商買賣超)
- LINE 專屬推播：首則為全家族 ETF 合併近 1 日買／賣超前五（金額），其餘為 LINE_NOTIFY_LIST 各檔
"""

import argparse
import glob
import json
import logging
import os
import re
import time
from datetime import datetime
from typing import Optional

import pandas as pd
import requests
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager

from broker_config import BROKER_LIST
from generate_web import family_consensus_top5_for_date

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("ETF-Monitor")

# 判斷是否在 GitHub 雲端環境
IS_GITHUB_ACTION: bool = os.environ.get("GITHUB_ACTIONS") == "true"

LINE_TOKEN: str = os.environ.get("LINE_TOKEN", "")

# 1. 資料庫全收錄 (18 檔)
CRAWL_LIST: list[str] = [
    "0050",
    "00980A", "00981A", "00982A", "00983A", "00984A",
    "00985A", "00986A", "00987A", "00988A", "00989A",
    "00990A", "00991A", "00992A", "00993A", "00994A",
    "00995A",
    "009816",
]

# 2. LINE 專屬推播 (僅 6 檔)
LINE_NOTIFY_LIST: list[str] = [
    "00980A", "00981A", "00982A", "00985A", "009816", "00992A"
]

# 3. 凱基大聯盟 18 大主力分點 — BROKER_LIST 見 broker_config.py

WANTGOO_MAJOR_ID: str = "9200"
WANTGOO_URL_TEMPLATE: str = (
    "https://www.wantgoo.com/stock/major-investors/broker-buy-sell-rank"
    "?during=1&majorId={}&branchId={}&orderBy=count"
)

ETF_THEMES: dict[str, str] = {
    "0050": "大盤指標 (元大台灣50)", "00980A": "成長配息 (野村智慧優選)",
    "00981A": "科技增長 (統一台股增長)", "00982A": "強勢動能 (群益精選強棒)",
    "00983A": "創新科技 (中信ARK創新)", "00984A": "高息成長 (安聯台灣高息)",
    "00985A": "增強市值 (野村台灣增強50)", "00986A": "龍頭成長 (台新龍頭成長)",
    "00987A": "優勢成長 (台新優勢成長)", "00988A": "全球創新 (統一全球創新)",
    "00989A": "美國科技 (摩根美國科技)", "00990A": "AI新經濟 (元大AI新經濟)",
    "00991A": "未來50 (復華未來50)", "00992A": "科技創新 (群益科技創新)",
    "00993A": "安聯台灣 (安聯台灣)", "00994A": "台股優選 (第一金台股優)",
    "00995A": "台灣卓越 (中信台灣卓越)", "009816": "專屬監控 (009816)"
}

URL_TEMPLATE: str = "https://www.pocket.tw/etf/tw/{}/fundholding/"
HISTORY_DIR: str = "history"
WEB_DASHBOARD_URL: str = "https://chiang-pon.github.io/00981a-monitor/"
CRAWL_MAX_RETRIES: int = 2
CRAWL_PAGE_LOAD_WAIT: float = 5.0
CRAWL_SCROLL_WAIT: float = 3.0
CRAWL_SCROLL_ROUNDS: int = 3

TW_HOLIDAYS_2026: set[str] = {
    "2026-01-01", "2026-01-26", "2026-01-27", "2026-01-28", "2026-01-29", "2026-01-30",
    "2026-02-02", "2026-02-27", "2026-02-28", "2026-04-03", "2026-04-04", "2026-04-05",
    "2026-04-06", "2026-05-01", "2026-06-19", "2026-09-25", "2026-10-10",
}

NAME_REPLACEMENTS: dict[str, str] = {
    "台灣積體電路製造": "台積電", "鴻海精密工業": "鴻海", "台達電子工業": "台達電",
    "緯穎科技服務": "緯穎", "聯發科技": "聯發科", "金像電子（股）公司": "金像電",
    "金像電子": "金像電", "廣達電腦": "廣達", "智邦科技": "智邦", "奇鋐科技": "奇鋐",
    "鴻勁精密": "鴻勁", "台燿科技": "台燿", "群聯電子": "群聯", "健策精密工業": "健策",
    "旺矽科技": "旺矽", "勤誠興業": "勤誠", "中國信託金融控股": "中信金", "京元電子": "京元電",
    "緯創資通": "緯創", "文曄科技": "文曄", "欣銓科技": "欣銓", "致伸科技": "致伸",
    "南亞科技": "南亞科", "健鼎科技": "健鼎", "凡甲科技": "凡甲", "崇越科技": "崇越",
    "瑞昱半導體": "瑞昱", "致茂電子": "致茂", "鈊象電子": "鈊象", "高力熱處理工業": "高力",
    "台光電子材料": "台光電", "華城電機": "華城", "穎崴科技": "穎崴", "中華精測科技": "精測",
    "川湖科技": "川湖", "亞德客國際集團": "亞德客", "玉山金融控股": "玉山金", "富邦金融控股": "富邦金",
    "華邦電子": "華邦電", "大成不銹鋼工業": "大成鋼", "聚陽實業": "聚陽", "達興材料": "達興材",
    "技嘉科技": "技嘉", "貿聯控股（BizLink Holding In": "貿聯-KY", "寶雅國際": "寶雅",
    "創意電子": "創意", "光紅建聖": "光紅建聖",
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


def is_trading_day(date: Optional[datetime] = None) -> bool:
    if date is None:
        date = datetime.now()
    if date.weekday() >= 5:
        return False
    if date.strftime("%Y-%m-%d") in TW_HOLIDAYS_2026:
        return False
    return True


def fetch_tw_stock_prices() -> dict:
    """抓取 TWSE 與 TPEx 當日收盤價，供真實資金計算"""
    prices: dict[str, float] = {}
    logger.info("開始抓取 TWSE/TPEx 報價以計算資金流向...")
    try:
        resp = requests.get(
            "https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL",
            timeout=10,
        )
        if resp.ok:
            for item in resp.json():
                try:
                    prices[item["Code"]] = float(item["ClosingPrice"])
                except (KeyError, ValueError, TypeError):
                    pass
    except Exception as e:
        logger.warning("TWSE 報價抓取失敗: %s", e)

    try:
        resp = requests.get(
            "https://www.tpex.org.tw/openapi/v1/tpex_mainboard_quotes",
            timeout=10,
        )
        if resp.ok:
            for item in resp.json():
                try:
                    code = item.get("SecuritiesCompanyCode") or item.get("Code")
                    close = item.get("Close") or item.get("ClosingPrice")
                    if code and close is not None:
                        prices[str(code)] = float(close)
                except (KeyError, ValueError, TypeError):
                    pass
    except Exception as e:
        logger.warning("TPEx 報價抓取失敗: %s", e)

    logger.info("成功抓取 %d 檔股票報價。", len(prices))
    return prices


def _ensure_csv_columns(df: pd.DataFrame) -> pd.DataFrame:
    """向下相容：若無 price/weight 欄位，補 0.0"""
    if "price" not in df.columns:
        df["price"] = 0.0
    if "weight" not in df.columns:
        df["weight"] = 0.0
    return df


def _shares_thousands_int(val) -> int:
    """將持股股數轉為「千張」整數；None/NaN/空字串視為 0。僅對 str 做千分位逗號清理。"""
    if val is None:
        return 0
    try:
        if pd.isna(val):
            return 0
    except (TypeError, ValueError):
        pass
    if isinstance(val, str):
        val = val.replace(",", "").strip()
        if not val or val.lower() == "nan":
            return 0
    try:
        v = float(pd.to_numeric(val, errors="coerce"))
    except (TypeError, ValueError):
        return 0
    if pd.isna(v):
        return 0
    try:
        return int(v / 1000)
    except (TypeError, ValueError, OverflowError):
        return 0


def fetch_data(etf_code: str, prices_dict: dict) -> list[dict]:
    target_url = URL_TEMPLATE.format(etf_code)
    for attempt in range(CRAWL_MAX_RETRIES + 1):
        driver = None
        try:
            logger.info("[%s] 啟動爬蟲 (第 %d 次)...", etf_code, attempt + 1)
            chrome_options = Options()
            chrome_options.add_argument("--headless")
            chrome_options.add_argument("--disable-gpu")
            chrome_options.add_argument("--window-size=1920,1080")
            chrome_options.add_argument("--no-sandbox")
            chrome_options.add_argument("--disable-dev-shm-usage")
            chrome_options.add_argument(
                "user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
            )

            service = Service(ChromeDriverManager().install())
            driver = webdriver.Chrome(service=service, options=chrome_options)
            driver.get(target_url)
            time.sleep(CRAWL_PAGE_LOAD_WAIT)

            last_height = driver.execute_script("return document.body.scrollHeight")
            for _ in range(CRAWL_SCROLL_ROUNDS):
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(CRAWL_SCROLL_WAIT)
                new_height = driver.execute_script("return document.body.scrollHeight")
                if new_height == last_height:
                    break
                last_height = new_height

            soup = BeautifulSoup(driver.page_source, "html.parser")
            table = soup.find("table", class_="cm-table__table")
            data: list[dict] = []
            skip_keywords = [
                "CASH", "RECEIVABLE", "PAYABLE", "MARGIN",
                "加權股價指數", "C_NTD", "C_USD",
            ]

            if table and table.find("tbody"):
                for row in table.find("tbody").find_all("tr"):
                    cols = row.find_all("td")
                    if len(cols) >= 4:
                        code = cols[0].text.strip()
                        name_tag = cols[1].find("h2")
                        name = name_tag.text.strip() if name_tag else cols[1].text.strip()
                        weight_str = cols[2].text.strip().replace("%", "")
                        shares_str = cols[3].text.strip().replace(",", "")

                        should_skip = any(
                            kw in name.upper() or kw in code.upper()
                            for kw in skip_keywords
                        )
                        if code and not should_skip:
                            try:
                                current_price = prices_dict.get(code, 0.0)
                                data.append({
                                    "code": code,
                                    "name": name,
                                    "weight": float(weight_str),
                                    "shares": int(shares_str),
                                    "price": current_price,
                                })
                            except (ValueError, TypeError):
                                pass

            if data:
                logger.info("[%s] 成功抓取 %d 筆持股", etf_code, len(data))
                return data
        except Exception as e:
            logger.error("[%s] 爬蟲錯誤: %s", etf_code, e)
        finally:
            if driver:
                try:
                    driver.quit()
                except Exception:
                    pass
        if attempt < CRAWL_MAX_RETRIES:
            time.sleep(5 * (attempt + 1))
    return []


def _create_chrome_driver(headless: bool = True, anti_detect: bool = False) -> webdriver.Chrome:
    """建立 Chrome WebDriver 實例。anti_detect 用於 wantgoo 等需繞過偵測的網站。"""
    chrome_options = Options()
    if headless:
        chrome_options.add_argument("--headless=new")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--window-size=1920,1080")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument(
        "user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
        " (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    )
    if anti_detect:
        chrome_options.add_argument("--disable-blink-features=AutomationControlled")
        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        chrome_options.add_experimental_option("useAutomationExtension", False)
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=chrome_options)
    if anti_detect:
        driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
            "source": "Object.defineProperty(navigator, 'webdriver', { get: () => undefined })"
        })
    return driver


def _parse_broker_table(soup: BeautifulSoup, table_id: str, negate: bool) -> list[dict]:
    """解析 wantgoo 買超或賣超表格。cols[5] 為千元，已除以 10 轉為戰情室萬元。negate=True 時將淨張數與淨金額轉為負數。"""
    table = soup.find("tbody", id=table_id)
    if not table:
        return []
    result: list[dict] = []
    for row in table.find_all("tr"):
        cols = row.find_all("td")
        if len(cols) < 6:
            continue
        stock_name_tag = cols[1].find("a")
        stock_name = stock_name_tag.text.strip() if stock_name_tag else cols[1].text.strip()
        stock_href = stock_name_tag.get("href", "") if stock_name_tag else ""
        code = ""
        if stock_href:
            parts = stock_href.rstrip("/").split("/")
            if parts:
                code = parts[-1].split("-")[0] or ""
        avg_price = 0.0
        if len(cols) > 6:
            try:
                avg_price_str = cols[6].text.strip().replace(",", "")
                avg_price = float(avg_price_str) if avg_price_str else 0.0
            except (ValueError, TypeError):
                avg_price = 0.0
        try:
            buy_shares_str = cols[2].text.strip().replace(",", "")
            sell_shares_str = cols[3].text.strip().replace(",", "")
            net_shares_str = cols[4].text.strip().replace(",", "")
            net_amount_str = cols[5].text.strip().replace(",", "").replace("萬", "")

            buy_shares = int(float(buy_shares_str)) if buy_shares_str else 0
            sell_shares = int(float(sell_shares_str)) if sell_shares_str else 0
            net_shares = int(float(net_shares_str)) if net_shares_str else 0

            # 玩股網金額欄為「千元」，除以 10 轉為戰情室標準「萬元」
            net_amount = (float(net_amount_str) / 10.0) if net_amount_str else 0.0
        except (ValueError, TypeError):
            continue
        if not stock_name or stock_name.upper() in ("CASH", "C_NTD", "C_USD"):
            continue
        if negate:
            net_shares = -abs(net_shares)
            net_amount = -abs(net_amount)
        result.append({
            "code": code if code and code.isdigit() else "",
            "name": stock_name,
            "buy_shares": buy_shares,
            "sell_shares": sell_shares,
            "net_shares": net_shares,
            "net_amount": net_amount,
            "avg_price": avg_price,
        })
    return result


def fetch_broker_data(broker_code: str, driver: webdriver.Chrome) -> list[dict]:
    """從 wantgoo 抓取單一分點買超(#buyTable)與賣超(#sellTable)資料，共用傳入的 WebDriver。"""
    url = WANTGOO_URL_TEMPLATE.format(WANTGOO_MAJOR_ID, broker_code)
    try:
        logger.info("[%s %s] 抓取中...", broker_code, BROKER_LIST.get(broker_code, ""))
        driver.get(url)
        wait = WebDriverWait(driver, 15)
        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "#buyTable tr")))
        time.sleep(1)

        soup = BeautifulSoup(driver.page_source, "html.parser")
        data = _parse_broker_table(soup, "buyTable", negate=False)
        sell_data = _parse_broker_table(soup, "sellTable", negate=True)
        data.extend(sell_data)
        if data:
            logger.info("[%s] 成功抓取 %d 筆 (買超+賣超)", broker_code, len(data))
        return data
    except Exception as e:
        logger.error("[%s] wantgoo 抓取失敗: %s", broker_code, e)
        return []


def crawl_all_brokers() -> None:
    """使用單一 WebDriver 實例依序爬取 18 間凱基分點。具備雲端/本機環境感知能力。"""
    if not BROKER_LIST:
        return

    if IS_GITHUB_ACTION:
        logger.warning("檢測到雲端環境 (美國 IP)，為避免 Cloudflare 封鎖，略過券商分點爬取。")
        logger.warning("請在 Mac 本機端執行 python main.py 來更新凱基大聯盟！")
        return

    logger.info("偵測到本機環境！啟動突破防護機制，開始抓取 18 間凱基分點...")
    driver = None
    try:
        chrome_options = Options()
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--window-size=1920,1080")
        chrome_options.add_argument("--disable-blink-features=AutomationControlled")
        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        chrome_options.add_experimental_option("useAutomationExtension", False)

        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=chrome_options)
        driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
            "source": "Object.defineProperty(navigator, 'webdriver', { get: () => undefined })"
        })

        today_str = datetime.now().strftime("%Y-%m-%d")
        for broker_code, broker_name in BROKER_LIST.items():
            data = fetch_broker_data(broker_code, driver)
            if data:
                out_path = os.path.join(HISTORY_DIR, f"{broker_code}_{today_str}.csv")
                df = pd.DataFrame(data)
                df.to_csv(out_path, index=False, encoding="utf-8-sig")
            time.sleep(2)
    finally:
        if driver:
            try:
                driver.quit()
            except Exception:
                pass


def process_etf(etf_code: str, prices_dict: dict) -> dict:
    today_str = datetime.now().strftime("%Y-%m-%d")
    today_file = os.path.join(HISTORY_DIR, f"{etf_code}_{today_str}.csv")

    today_data = fetch_data(etf_code, prices_dict)
    if not today_data:
        return {
            "etf": etf_code,
            "has_action": False,
            "error": True,
            "new_buy": [],
            "sold_out": [],
            "increased": [],
            "decreased": [],
        }

    today_df = pd.DataFrame(today_data)
    today_df.to_csv(today_file, index=False, encoding="utf-8-sig")

    all_files = sorted(glob.glob(os.path.join(HISTORY_DIR, f"{etf_code}_*.csv")))
    new_buy_list: list[tuple[str, str]] = []
    sold_out_list: list[tuple[str, str]] = []
    increased_list: list[tuple[str, int]] = []
    decreased_list: list[tuple[str, int]] = []

    if len(all_files) >= 2:
        try:
            last_df = pd.read_csv(all_files[-2], dtype={"code": str})
            last_df = _ensure_csv_columns(last_df)
            today_df = _ensure_csv_columns(today_df)
            for _df in (today_df, last_df):
                if "shares" in _df.columns:
                    _df["shares"] = pd.to_numeric(_df["shares"], errors="coerce").fillna(0)
                if "weight" in _df.columns:
                    _df["weight"] = pd.to_numeric(_df["weight"], errors="coerce").fillna(0.0)
                if "price" in _df.columns:
                    _df["price"] = pd.to_numeric(_df["price"], errors="coerce").fillna(0.0)
                if "name" in _df.columns:
                    _df["name"] = _df["name"].apply(
                        lambda x: "" if x is None or (isinstance(x, float) and pd.isna(x)) else str(x)
                    )
            today_codes = set(today_df["code"].astype(str))
            last_codes = set(last_df["code"].astype(str))
            common_codes = today_codes & last_codes

            for c in (today_codes - last_codes):
                row = today_df[today_df["code"].astype(str) == c].iloc[0]
                shares = _shares_thousands_int(row["shares"])
                new_buy_list.append((f"+ {clean_stock_name(row['name'])}", f"{shares:,} 張"))

            for c in (last_codes - today_codes):
                row = last_df[last_df["code"].astype(str) == c].iloc[0]
                shares = _shares_thousands_int(row["shares"])
                sold_out_list.append((f"- {clean_stock_name(row['name'])}", f"出清 {shares:,} 張"))

            for c in common_codes:
                row_now = today_df[today_df["code"].astype(str) == c].iloc[0]
                row_last = last_df[last_df["code"].astype(str) == c].iloc[0]
                shares_diff = _shares_thousands_int(row_now["shares"]) - _shares_thousands_int(row_last["shares"])
                if shares_diff != 0:
                    name = clean_stock_name(row_now["name"])
                    if shares_diff > 0:
                        increased_list.append((name, shares_diff))
                    else:
                        decreased_list.append((name, shares_diff))
        except Exception as e:
            logger.warning("[%s] 比較歷史資料失敗: %s", etf_code, e)

    def _parse_shares(s) -> int:
        if s is None:
            return 0
        try:
            if pd.isna(s):
                return 0
        except (TypeError, ValueError):
            pass
        if not isinstance(s, str):
            try:
                v = float(pd.to_numeric(s, errors="coerce"))
                return int(v) if not pd.isna(v) else 0
            except (TypeError, ValueError):
                return 0
        t = s.replace(" 張", "").replace(",", "").replace("出清 ", "").replace("+", "").strip() or "0"
        try:
            return int(float(t))
        except (TypeError, ValueError):
            return 0

    new_buy_list.sort(key=lambda x: _parse_shares(x[1]), reverse=True)
    sold_out_list.sort(key=lambda x: _parse_shares(x[1]), reverse=True)
    increased_list.sort(key=lambda x: x[1], reverse=True)
    decreased_list.sort(key=lambda x: x[1])

    increased_tuples = [(f"+ {n}", f"+{sd:,} 張") for n, sd in increased_list]
    decreased_tuples = [(f"- {n}", f"{sd:,} 張") for n, sd in decreased_list]
    has_action = bool(new_buy_list or sold_out_list or increased_tuples or decreased_tuples)

    return {
        "etf": etf_code,
        "has_action": has_action,
        "error": False,
        "new_buy": new_buy_list,
        "sold_out": sold_out_list,
        "increased": increased_tuples,
        "decreased": decreased_tuples,
    }


def format_amount_display(amount_10k: float) -> str:
    """與 template.html formatAmount 一致（萬元）。"""
    if not amount_10k:
        return "—"
    val = abs(float(amount_10k))
    if val >= 10000:
        return f"約 {val / 10000:.2f} 億"
    return f"約 {round(val):,} 萬"


def build_family_consensus_bubble(buy5: list[dict], sell5: list[dict], report_date: str) -> dict:
    """全家族 ETF 合併近 1 交易日買／賣超前五（金額），置於每日推播第一則。"""
    sz = "xs"
    header_box = {
        "type": "box",
        "layout": "vertical",
        "backgroundColor": "#0f172a",
        "paddingAll": "12px",
        "contents": [
            {"type": "text", "text": report_date, "color": "#94a3b8", "size": "xs", "weight": "bold", "margin": "none"},
            {
                "type": "text",
                "text": "全家族 ETF 合併",
                "weight": "bold",
                "size": "sm",
                "color": "#ffffff",
                "margin": "xs",
            },
            {
                "type": "text",
                "text": "近 1 交易日 買超／賣超 前五（淨額）",
                "size": sz,
                "color": "#38bdf8",
                "wrap": True,
                "margin": "xs",
            },
        ],
    }

    def rank_rows(title: str, title_color: str, rows: list[dict], is_buy: bool) -> list:
        out: list = [
            {"type": "text", "text": title, "color": title_color, "weight": "bold", "size": sz, "margin": "md"},
        ]
        if not rows:
            out.append({"type": "text", "text": "（無）", "color": "#94a3b8", "size": sz, "margin": "xs"})
            return out
        amt_color = "#dc2626" if is_buy else "#059669"
        sign = "+" if is_buy else "−"
        for i, it in enumerate(rows, start=1):
            nm = str(it.get("name") or "—").strip()
            cd = str(it.get("code") or "").strip()
            left = f"{i}. {nm}" + (f" ({cd})" if cd else "")
            amt = format_amount_display(float(it.get("amount") or 0))
            out.append(
                {
                    "type": "box",
                    "layout": "horizontal",
                    "spacing": "sm",
                    "margin": "xs",
                    "contents": [
                        {"type": "text", "text": left, "size": sz, "color": "#334155", "flex": 6, "wrap": True},
                        {
                            "type": "text",
                            "text": f"{sign} {amt}",
                            "size": sz,
                            "color": amt_color,
                            "flex": 4,
                            "align": "end",
                            "wrap": False,
                        },
                    ],
                }
            )
        return out

    body_contents: list = []
    body_contents.extend(rank_rows("買超", "#dc2626", buy5, True))
    body_contents.append({"type": "separator", "margin": "md", "color": "#e2e8f0"})
    body_contents.extend(rank_rows("賣超", "#059669", sell5, False))
    body_contents.append(
        {
            "type": "text",
            "text": "資料為本機多檔 ETF 合併加總，非即時撮合。",
            "color": "#94a3b8",
            "size": "xs",
            "wrap": True,
            "margin": "md",
        }
    )

    return {
        "type": "bubble",
        "size": "kilo",
        "header": header_box,
        "body": {"type": "box", "layout": "vertical", "paddingAll": "12px", "contents": body_contents},
    }


def build_single_bubble(res: dict, report_date: str) -> dict:
    etf_code = res["etf"]
    body_contents = []
    theme_text = ETF_THEMES.get(etf_code, "專屬監控 ETF")
    body_sz = "xs"

    header_box = {
        "type": "box",
        "layout": "vertical",
        "backgroundColor": "#1e272e",
        "paddingAll": "15px",
        "contents": [
            {"type": "text", "text": report_date, "color": "#95a5a6", "size": "xs", "weight": "bold", "margin": "none"},
            {"type": "text", "text": etf_code, "weight": "bold", "size": "lg", "color": "#ffffff", "margin": "sm"},
            {"type": "text", "text": theme_text, "weight": "bold", "size": "xs", "color": "#2563eb", "margin": "xs"},
        ],
    }

    if res.get("error"):
        body_contents.append({
            "type": "text",
            "text": "尚未公布或查無持股",
            "color": "#e74c3c",
            "size": body_sz,
            "wrap": True,
            "align": "center",
            "margin": "xl",
        })
    elif not res.get("has_action"):
        body_contents.append({
            "type": "text",
            "text": "今日無籌碼異動",
            "color": "#95a5a6",
            "size": body_sz,
            "weight": "bold",
            "wrap": True,
            "align": "center",
            "margin": "xl",
        })
    else:
        def add_section(title: str, title_color: str, items: list, margin_top: str = "md"):
            if not items:
                return
            body_contents.append({
                "type": "text",
                "text": title,
                "color": title_color,
                "weight": "bold",
                "size": body_sz,
                "margin": margin_top,
            })
            item_boxes = []
            for i, (name, val) in enumerate(items):
                item_boxes.append({
                    "type": "box",
                    "layout": "horizontal",
                    "spacing": "sm",
                    "margin": "xs",
                    "contents": [
                        {"type": "text", "text": name, "size": body_sz, "color": "#333333", "flex": 5, "wrap": True},
                        {"type": "text", "text": "|", "size": body_sz, "color": "#bdc3c7", "flex": 1, "align": "center"},
                        {"type": "text", "text": val, "size": body_sz, "color": "#333333", "flex": 4, "align": "end", "wrap": False},
                    ],
                })
                if (i + 1) % 5 == 0 and (i + 1) < len(items):
                    item_boxes.append({"type": "separator", "color": "#f2f2f2", "margin": "sm"})
            body_contents.append({"type": "box", "layout": "vertical", "contents": item_boxes})
            body_contents.append({"type": "separator", "margin": "md", "color": "#eeeeee"})

        add_section("新進場", "#dc2626", res["new_buy"])
        add_section("加碼", "#dc2626", res["increased"])
        add_section("減碼", "#059669", res["decreased"])
        add_section("已離場", "#71717a", res["sold_out"])

        if body_contents and body_contents[-1]["type"] == "separator":
            body_contents.pop()

    return {
        "type": "bubble",
        "size": "kilo",
        "header": header_box,
        "body": {"type": "box", "layout": "vertical", "paddingAll": "15px", "contents": body_contents},
    }


def build_flex_payloads(
    results: list[dict],
    report_date: str,
    lead_bubble: dict | None = None,
) -> list[dict]:
    bubbles: list[dict] = []
    if lead_bubble is not None:
        bubbles.append(lead_bubble)
    bubbles.extend([build_single_bubble(res, report_date) for res in results])
    flex_messages = []
    current_bubbles = []
    current_size = 0
    SAFE_SIZE_LIMIT = 40000

    quick_reply_block = {
        "items": [{"type": "action", "action": {"type": "uri", "label": "開啟決策終端網頁", "uri": WEB_DASHBOARD_URL}}],
    }

    for bubble in bubbles:
        bubble_size = len(json.dumps(bubble, ensure_ascii=False).encode("utf-8"))
        if current_bubbles and (current_size + bubble_size > SAFE_SIZE_LIMIT):
            flex_messages.append({
                "type": "flex",
                "altText": f"每日籌碼異動 ({report_date})",
                "contents": {"type": "carousel", "contents": current_bubbles},
                "quickReply": quick_reply_block,
            })
            current_bubbles = []
            current_size = 0
        current_bubbles.append(bubble)
        current_size += bubble_size

    if current_bubbles:
        flex_messages.append({
            "type": "flex",
            "altText": f"每日籌碼異動 ({report_date})",
            "contents": {"type": "carousel", "contents": current_bubbles},
            "quickReply": quick_reply_block,
        })

    return flex_messages


def send_flex_messages(payloads: list[dict]) -> None:
    if not LINE_TOKEN:
        return
    url = "https://api.line.me/v2/bot/message/broadcast"
    headers = {"Authorization": f"Bearer {LINE_TOKEN}", "Content-Type": "application/json"}
    for i in range(0, len(payloads), 5):
        batch = payloads[i : i + 5]
        payload = {"messages": batch}
        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=10)
            if not resp.ok:
                logger.error("LINE 發送失敗: %s - %s", resp.status_code, resp.text)
            else:
                logger.info("成功發送第 %d 批 Flex Message", i // 5 + 1)
        except Exception as e:
            logger.error("LINE 連線錯誤: %s", e)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true", help="強制執行（忽略假日）")
    args = parser.parse_args()

    if not args.force and not is_trading_day():
        logger.info("今天不是交易日，跳過執行")
        return

    os.makedirs(HISTORY_DIR, exist_ok=True)
    today_str = datetime.now().strftime("%Y-%m-%d")
    logger.info("執行每日籌碼異動報告 (%s)", today_str)

    prices_dict = fetch_tw_stock_prices()
    results_for_line: list[dict] = []

    for etf in CRAWL_LIST:
        try:
            res = process_etf(etf, prices_dict)
            if etf in LINE_NOTIFY_LIST:
                results_for_line.append(res)
        except Exception as e:
            logger.error("處理 %s 發生錯誤: %s", etf, e)

    crawl_all_brokers()

    if results_for_line:
        try:
            buy5, sell5 = family_consensus_top5_for_date(today_str, list(CRAWL_LIST))
            lead = build_family_consensus_bubble(buy5, sell5, today_str)
        except Exception as e:
            logger.warning("全家族合併前五計算失敗，略過首則 bubble: %s", e)
            lead = None
        payloads = build_flex_payloads(results_for_line, today_str, lead_bubble=lead)
        send_flex_messages(payloads)
    elif LINE_TOKEN:
        headers = {"Authorization": f"Bearer {LINE_TOKEN}", "Content-Type": "application/json"}
        try:
            requests.post(
                "https://api.line.me/v2/bot/message/broadcast",
                headers=headers,
                json={"messages": [{"type": "text", "text": "今日爬蟲無資料。"}]},
                timeout=10,
            )
        except Exception as e:
            logger.error("LINE 發送失敗: %s", e)


if __name__ == "__main__":
    main()
