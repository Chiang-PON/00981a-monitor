"""main.py — 主動式 ETF 家族監控系統 (全台主動式大集結 + 爸爸專屬推播版)

追蹤全台灣所有主動式 ETF 的每日持股變化，作為網頁戰情室的底層數據庫。
- 數據擴充：收錄 00980A ~ 00995A 全部主動式 ETF。
- 分軌發送：網頁端收錄全部數據，LINE 推播僅發送長輩關注的特定清單。
- 核心升級：同步抓取 TWSE/TPEx 當日收盤價，精準計算真實資金流向。
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
from webdriver_manager.chrome import ChromeDriverManager

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("ETF-Monitor")

LINE_TOKEN: str = os.environ.get("LINE_TOKEN", "")

# 💎 1. 爬蟲全收錄清單 (負責建立龐大的網頁資料庫)
CRAWL_LIST: list[str] = [
    "0050",   # 大盤
    "00980A", "00981A", "00982A", "00983A", "00984A", 
    "00985A", "00986A", "00987A", "00988A", "00989A", 
    "00990A", "00991A", "00992A", "00993A", "00994A", 
    "00995A", # 涵蓋全台灣最新 16 檔主動式 ETF
    "009816"  # 你的專屬監控
]

# 💎 2. LINE 專屬推播清單 (爸爸只看這些)
LINE_NOTIFY_LIST: list[str] = [
    "0050", "00980A", "00981A", "00982A", "00984A", "00985A", "009816"
]

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
    name = name.replace("*", "").strip()
    for old, new in NAME_REPLACEMENTS.items():
        if old in name: return new
    name = STRIP_PATTERN.sub("", name)
    return name.strip()

def is_trading_day(date: Optional[datetime] = None) -> bool:
    if date is None: date = datetime.now()
    if date.weekday() >= 5: return False
    if date.strftime("%Y-%m-%d") in TW_HOLIDAYS_2026: return False
    return True

def fetch_tw_stock_prices() -> dict:
    prices = {}
    logger.info("開始抓取 TWSE/TPEx 報價以計算資金流向...")
    try:
        resp = requests.get("https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL", timeout=10)
        if resp.ok:
            for item in resp.json():
                try: prices[item["Code"]] = float(item["ClosingPrice"])
                except: pass
    except Exception as e:
        logger.warning(f"TWSE 報價抓取失敗: {e}")
        
    try:
        resp = requests.get("https://www.tpex.org.tw/openapi/v1/tpex_mainboard_quotes", timeout=10)
        if resp.ok:
            for item in resp.json():
                try: prices[item["SecuritiesCompanyCode"]] = float(item["Close"])
                except: pass
    except Exception as e:
        logger.warning(f"TPEx 報價抓取失敗: {e}")
        
    logger.info(f"成功抓取 {len(prices)} 檔股票報價。")
    return prices

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
            chrome_options.add_argument("user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

            service = Service(ChromeDriverManager().install())
            driver = webdriver.Chrome(service=service, options=chrome_options)
            driver.get(target_url)
            time.sleep(CRAWL_PAGE_LOAD_WAIT)

            last_height = driver.execute_script("return document.body.scrollHeight")
            for _ in range(CRAWL_SCROLL_ROUNDS):
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(CRAWL_SCROLL_WAIT)
                new_height = driver.execute_script("return document.body.scrollHeight")
                if new_height == last_height: break
                last_height = new_height

            soup = BeautifulSoup(driver.page_source, "html.parser")
            table = soup.find("table", class_="cm-table__table")
            data: list[dict] = []
            skip_keywords = ["CASH", "RECEIVABLE", "PAYABLE", "MARGIN", "加權股價指數", "C_NTD", "C_USD"]

            if table:
                tbody = table.find("tbody")
                if tbody:
                    rows = tbody.find_all("tr")
                    for row in rows:
                        cols = row.find_all("td")
                        if len(cols) >= 4:
                            code = cols[0].text.strip()
                            name_tag = cols[1].find("h2")
                            name = name_tag.text.strip() if name_tag else cols[1].text.strip()
                            weight_str = cols[2].text.strip().replace("%", "")
                            shares_str = cols[3].text.strip().replace(",", "")
                            
                            should_skip = any(kw in name.upper() or kw in code.upper() for kw in skip_keywords)
                            
                            if code and not should_skip:
                                try:
                                    current_price = prices_dict.get(code, 0.0)
                                    data.append({
                                        "code": code, "name": name,
                                        "weight": float(weight_str), "shares": int(shares_str),
                                        "price": current_price
                                    })
                                except: pass
            if data:
                logger.info("[%s] 成功抓取 %d 筆持股", etf_code, len(data))
                return data
        except Exception as e:
            logger.error("[%s] 爬蟲錯誤: %s", etf_code, e)
        finally:
            if driver:
                try: driver.quit()
                except: pass
        if attempt < CRAWL_MAX_RETRIES: time.sleep(5 * (attempt + 1))
    return []

def process_etf(etf_code: str, prices_dict: dict) -> dict:
    today_str = datetime.now().strftime("%Y-%m-%d")
    today_file = os.path.join(HISTORY_DIR, f"{etf_code}_{today_str}.csv")

    today_data = fetch_data(etf_code, prices_dict)
    if not today_data: 
        return {
            "etf": etf_code, "has_action": False, "error": True,
            "new_buy": [], "sold_out": [], "increased": [], "decreased": []
        }

    today_df = pd.DataFrame(today_data)
    today_df.to_csv(today_file, index=False, encoding="utf-8-sig")

    all_files = sorted(glob.glob(os.path.join(HISTORY_DIR, f"{etf_code}_*.csv")))
    new_buy_list, sold_out_list, increased_list, decreased_list = [], [], [], []

    if len(all_files) >= 2:
        try:
            last_df = pd.read_csv(all_files[-2], dtype={"code": str})
            today_codes = set(today_df["code"].astype(str))
            last_codes = set(last_df["code"].astype(str))
            common_codes = today_codes & last_codes

            for c in (today_codes - last_codes):
                row = today_df[today_df["code"].astype(str) == c].iloc[0]
                shares = int(row["shares"] / 1000)
                new_buy_list.append((f"+ {clean_stock_name(row['name'])}", f"{shares:,} 張"))
                
            for c in (last_codes - today_codes):
                row = last_df[last_df["code"].astype(str) == c].iloc[0]
                shares = int(row["shares"] / 1000)
                sold_out_list.append((f"- {clean_stock_name(row['name'])}", f"出清 {shares:,} 張"))
                
            for c in common_codes:
                row_now = today_df[today_df["code"].astype(str) == c].iloc[0]
                row_last = last_df[last_df["code"].astype(str) == c].iloc[0]
                shares_diff = int(row_now["shares"] / 1000) - int(row_last["shares"] / 1000)
                if shares_diff != 0:
                    name = clean_stock_name(row_now["name"])
                    if shares_diff > 0: increased_list.append((name, shares_diff))
                    else: decreased_list.append((name, shares_diff))
        except Exception as e:
            logger.warning("[%s] 比較歷史資料失敗: %s", etf_code, e)

    new_buy_list.sort(key=lambda x: int(x[1].replace(' 張','').replace(',','')), reverse=True)
    sold_out_list.sort(key=lambda x: int(x[1].replace('出清 ','').replace(' 張','').replace(',','')), reverse=True)
    increased_list.sort(key=lambda x: x[1], reverse=True)
    decreased_list.sort(key=lambda x: x[1])

    increased_tuples = [(f"+ {n}", f"+{sd:,} 張") for n, sd in increased_list]
    decreased_tuples = [(f"- {n}", f"{sd:,} 張") for n, sd in decreased_list]
    has_action = bool(new_buy_list or sold_out_list or increased_tuples or decreased_tuples)

    return {
        "etf": etf_code, "has_action": has_action, "error": False,
        "new_buy": new_buy_list, "sold_out": sold_out_list,
        "increased": increased_tuples, "decreased": decreased_tuples
    }

def build_single_bubble(res: dict, report_date: str) -> dict:
    etf_code = res["etf"]
    body_contents = []
    theme_text = ETF_THEMES.get(etf_code, "專屬監控 ETF")
    
    header_box = {
        "type": "box", "layout": "vertical", "backgroundColor": "#1e272e", "paddingAll": "15px",
        "contents": [
            {"type": "text", "text": report_date, "color": "#95a5a6", "size": "xs", "weight": "bold", "margin": "none"},
            {"type": "text", "text": etf_code, "weight": "bold", "size": "xl", "color": "#ffffff", "margin": "sm"},
            {"type": "text", "text": theme_text, "weight": "bold", "size": "sm", "color": "#2563eb", "margin": "xs"}
        ]
    }

    if res.get("error"):
        body_contents.append({"type": "text", "text": "尚未公布或查無持股", "color": "#e74c3c", "size": "sm", "wrap": True, "align": "center", "margin": "xl"})
    elif not res.get("has_action"):
        body_contents.append({"type": "text", "text": "今日無籌碼異動", "color": "#95a5a6", "size": "sm", "weight": "bold", "wrap": True, "align": "center", "margin": "xl"})
    else:
        def add_section(title: str, title_color: str, items: list, margin_top: str = "md"):
            if not items: return
            body_contents.append({"type": "text", "text": title, "color": title_color, "weight": "bold", "size": "sm", "margin": margin_top})
            item_boxes = []
            for i, (name, val) in enumerate(items):
                item_boxes.append({
                    "type": "box", "layout": "horizontal", "spacing": "sm", "margin": "xs",
                    "contents": [
                        { "type": "text", "text": name, "size": "sm", "color": "#333333", "flex": 5, "wrap": False },
                        { "type": "text", "text": "｜", "size": "sm", "color": "#bdc3c7", "flex": 1, "align": "center" },
                        { "type": "text", "text": val, "size": "sm", "color": "#333333", "flex": 4, "align": "end", "wrap": False }
                    ]
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
        "type": "bubble", "size": "kilo", "header": header_box,
        "body": {"type": "box", "layout": "vertical", "paddingAll": "15px", "contents": body_contents}
    }

def build_flex_payloads(results: list[dict], report_date: str) -> list[dict]:
    bubbles = [build_single_bubble(res, report_date) for res in results]
    flex_messages = []
    current_bubbles = []
    current_size = 0
    SAFE_SIZE_LIMIT = 40000

    quick_reply_block = {
        "items": [{ "type": "action", "action": { "type": "uri", "label": "開啟決策終端網頁", "uri": WEB_DASHBOARD_URL } }]
    }

    for bubble in bubbles:
        bubble_size = len(json.dumps(bubble, ensure_ascii=False).encode('utf-8'))
        if current_bubbles and (current_size + bubble_size > SAFE_SIZE_LIMIT):
            flex_messages.append({
                "type": "flex", "altText": f"每日籌碼異動 ({report_date})",
                "contents": {"type": "carousel", "contents": current_bubbles},
                "quickReply": quick_reply_block
            })
            current_bubbles = []
            current_size = 0

        current_bubbles.append(bubble)
        current_size += bubble_size

    if current_bubbles:
        flex_messages.append({
            "type": "flex", "altText": f"每日籌碼異動 ({report_date})",
            "contents": {"type": "carousel", "contents": current_bubbles},
            "quickReply": quick_reply_block
        })

    return flex_messages

def send_flex_messages(payloads: list[dict]) -> None:
    if not LINE_TOKEN: return
    url = "https://api.line.me/v2/bot/message/broadcast"
    headers = {"Authorization": f"Bearer {LINE_TOKEN}", "Content-Type": "application/json"}
    for i in range(0, len(payloads), 5):
        batch = payloads[i:i+5]
        payload = {"messages": batch}
        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=10)
            if not resp.ok: logger.error(f"LINE 發送失敗: {resp.status_code} - {resp.text}")
            else: logger.info(f"成功發送第 {i//5 + 1} 批 Flex Message！")
        except Exception as e: logger.error("LINE 連線錯誤: %s", e)

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true", help="強制執行（忽略假日）")
    args = parser.parse_args()

    if not args.force and not is_trading_day():
        logger.info("今天不是交易日，跳過執行")
        return

    os.makedirs(HISTORY_DIR, exist_ok=True)
    today_str = datetime.now().strftime("%Y-%m-%d")
    logger.info(f"執行每日籌碼異動報告 ({today_str})")
    
    # 執行報價抓取，供後續使用
    prices_dict = fetch_tw_stock_prices()
    
    results_for_line = []
    
    # 💎 走訪全台灣所有主動式 ETF
    for etf in CRAWL_LIST:
        try:
            res = process_etf(etf, prices_dict)
            # 💎 只有在爸爸專屬清單內的，才會進入 LINE 推播陣列
            if etf in LINE_NOTIFY_LIST:
                results_for_line.append(res)
        except Exception as e:
            logger.error("處理 %s 發生錯誤: %s", etf, e)

    if results_for_line:
        payloads = build_flex_payloads(results_for_line, today_str)
        send_flex_messages(payloads)
    else:
        if LINE_TOKEN:
            headers = {"Authorization": f"Bearer {LINE_TOKEN}", "Content-Type": "application/json"}
            requests.post(
                "https://api.line.me/v2/bot/message/broadcast", 
                headers=headers, json={"messages": [{"type": "text", "text": "今日爬蟲無資料。"}]}
            )

if __name__ == "__main__":
    main()