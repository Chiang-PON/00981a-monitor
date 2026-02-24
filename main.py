"""main.py — 主動式 ETF 家族監控系統 (極簡質感卡片版)

追蹤 00980A ~ 00985A 的每日持股變化。
輸出升級為 LINE Flex Message (Carousel 卡片格式)。
極簡設計：移除 Emoji，新增日期標題，提升財經專業感。
"""

import argparse
import glob
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

# ═══════════════════════════════
# Logging
# ═══════════════════════════════
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("ETF-Monitor")

# ═══════════════════════════════
# 常數設定
# ═══════════════════════════════
LINE_TOKEN: str = os.environ.get("LINE_TOKEN", "")
ETF_LIST: list[str] = ["00980A", "00981A", "00982A", "00983A", "00984A", "00985A"]
URL_TEMPLATE: str = "https://www.pocket.tw/etf/tw/{}/fundholding/"
HISTORY_DIR: str = "history"
CRAWL_MAX_RETRIES: int = 2
CRAWL_PAGE_LOAD_WAIT: float = 5.0
CRAWL_SCROLL_WAIT: float = 3.0
CRAWL_SCROLL_ROUNDS: int = 3

# 台灣國定假日（2026 年）
TW_HOLIDAYS_2026: set[str] = {
    "2026-01-01", "2026-01-26", "2026-01-27", "2026-01-28", 
    "2026-01-29", "2026-01-30", "2026-02-02", "2026-02-27", 
    "2026-02-28", "2026-04-03", "2026-04-04", "2026-04-05", 
    "2026-04-06", "2026-05-01", "2026-06-19", "2026-09-25", 
    "2026-10-10",
}

# ═══════════════════════════════
# 名稱淨化
# ═══════════════════════════════
NAME_REPLACEMENTS: dict[str, str] = {
    "台灣積體電路製造": "台積電", "鴻海精密工業": "鴻海",
    "台達電子工業": "台達電", "緯穎科技服務": "緯穎",
    "聯發科技": "聯發科", "金像電子（股）公司": "金像電",
    "金像電子": "金像電", "廣達電腦": "廣達",
    "智邦科技": "智邦", "奇鋐科技": "奇鋐",
    "鴻勁精密": "鴻勁", "台燿科技": "台燿",
    "群聯電子": "群聯", "健策精密工業": "健策",
    "旺矽科技": "旺矽", "勤誠興業": "勤誠",
    "中國信託金融控股": "中信金", "京元電子": "京元電",
    "緯創資通": "緯創", "文曄科技": "文曄",
    "欣銓科技": "欣銓", "致伸科技": "致伸",
    "南亞科技": "南亞科", "健鼎科技": "健鼎",
    "凡甲科技": "凡甲", "崇越科技": "崇越",
    "瑞昱半導體": "瑞昱", "致茂電子": "致茂",
    "鈊象電子": "鈊象", "高力熱處理工業": "高力",
    "台光電子材料": "台光電", "華城電機": "華城",
    "穎崴科技": "穎崴", "中華精測科技": "精測",
    "川湖科技": "川湖", "亞德客國際集團": "亞德客",
    "玉山金融控股": "玉山金", "富邦金融控股": "富邦金",
    "華邦電子": "華邦電", "大成不銹鋼工業": "大成鋼",
    "聚陽實業": "聚陽", "達興材料": "達興材",
    "技嘉科技": "技嘉", "貿聯控股（BizLink Holding In": "貿聯-KY",
    "寶雅國際": "寶雅", "創意電子": "創意",
    "光紅建聖": "光紅建聖",
}

STRIP_PATTERN = re.compile(
    r"（股）公司|\(股\)公司|股份有限公司|有限公司|科技|工業|電子|電腦"
)

def clean_stock_name(name: str) -> str:
    name = name.replace("*", "").strip()
    for old, new in NAME_REPLACEMENTS.items():
        if old in name: return new
    name = STRIP_PATTERN.sub("", name)
    return name.strip()

# ═══════════════════════════════
# 假日偵測
# ═══════════════════════════════
def is_trading_day(date: Optional[datetime] = None) -> bool:
    if date is None: date = datetime.now()
    if date.weekday() >= 5: return False
    if date.strftime("%Y-%m-%d") in TW_HOLIDAYS_2026: return False
    return True

# ═══════════════════════════════
# 爬蟲功能
# ═══════════════════════════════
def fetch_data(etf_code: str) -> list[dict]:
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
            
            # 要剔除的非股票會計項目關鍵字
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
                            
                            name_upper = name.upper()
                            code_upper = code.upper()
                            should_skip = any(kw in name_upper or kw in code_upper for kw in skip_keywords)
                            
                            if code and not should_skip:
                                try:
                                    data.append({
                                        "code": code, "name": name,
                                        "weight": float(weight_str), "shares": int(shares_str),
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

# ═══════════════════════════════
# 資料處理 (返回結構化資料供 Flex 繪製)
# ═══════════════════════════════
def process_etf(etf_code: str) -> dict:
    today_str = datetime.now().strftime("%Y-%m-%d")
    today_file = os.path.join(HISTORY_DIR, f"{etf_code}_{today_str}.csv")

    today_data = fetch_data(etf_code)
    if not today_data: 
        return {
            "etf": etf_code,
            "has_action": False,
            "error": True,
            "new_buy": [], "sold_out": [], "increased": [], "decreased": []
        }

    today_df = pd.DataFrame(today_data)
    today_df.to_csv(today_file, index=False, encoding="utf-8-sig")

    all_files = sorted(glob.glob(os.path.join(HISTORY_DIR, f"{etf_code}_*.csv")))
    
    new_buy_list = []
    sold_out_list = []
    increased_list = []
    decreased_list = []

    if len(all_files) >= 2:
        try:
            last_df = pd.read_csv(all_files[-2], dtype={"code": str})
            today_codes = set(today_df["code"].astype(str))
            last_codes = set(last_df["code"].astype(str))
            common_codes = today_codes & last_codes

            for c in (today_codes - last_codes):
                row = today_df[today_df["code"].astype(str) == c].iloc[0]
                shares = int(row["shares"] / 1000)
                new_buy_list.append(f"+ {clean_stock_name(row['name'])} ｜ {shares:,} 張")
                
            for c in (last_codes - today_codes):
                row = last_df[last_df["code"].astype(str) == c].iloc[0]
                shares = int(row["shares"] / 1000)
                sold_out_list.append(f"- {clean_stock_name(row['name'])} ｜ 出清 {shares:,} 張")
                
            for c in common_codes:
                row_now = today_df[today_df["code"].astype(str) == c].iloc[0]
                row_last = last_df[last_df["code"].astype(str) == c].iloc[0]
                shares_diff = int(row_now["shares"] / 1000) - int(row_last["shares"] / 1000)
                
                if shares_diff != 0:
                    name = clean_stock_name(row_now["name"])
                    if shares_diff > 0:
                        increased_list.append((name, shares_diff))
                    else:
                        decreased_list.append((name, shares_diff))
        except Exception as e:
            logger.warning("[%s] 比較歷史資料失敗: %s", etf_code, e)

    increased_list.sort(key=lambda x: x[1], reverse=True)
    decreased_list.sort(key=lambda x: x[1])

    increased_strs = [f"+ {n} ｜ +{sd:,} 張" for n, sd in increased_list]
    decreased_strs = [f"- {n} ｜ {sd:,} 張" for n, sd in decreased_list]

    has_action = bool(new_buy_list or sold_out_list or increased_strs or decreased_strs)

    return {
        "etf": etf_code,
        "has_action": has_action,
        "error": False,
        "new_buy": new_buy_list,
        "sold_out": sold_out_list,
        "increased": increased_strs,
        "decreased": decreased_strs
    }

# ═══════════════════════════════
# 建立 LINE Flex Message
# ═══════════════════════════════
def build_flex_carousel(results: list[dict], report_date: str) -> dict:
    bubbles = []
    
    for res in results:
        etf_code = res["etf"]
        body_contents = []
        
        # 標題區塊 (深色質感 + 日期)
        header_box = {
            "type": "box",
            "layout": "vertical",
            "backgroundColor": "#1e272e", # 財經質感的深藍黑
            "paddingAll": "15px",
            "contents": [
                {
                    "type": "text",
                    "text": report_date,
                    "color": "#95a5a6",
                    "size": "xs",
                    "weight": "bold",
                    "margin": "none"
                },
                {
                    "type": "text",
                    "text": etf_code,
                    "weight": "bold",
                    "size": "xl",
                    "color": "#ffffff",
                    "margin": "sm"
                }
            ]
        }

        # 錯誤處理 (抓不到資料)
        if res.get("error"):
            body_contents.append({
                "type": "text",
                "text": "尚未公布或查無持股",
                "color": "#e74c3c",
                "size": "sm",
                "wrap": True,
                "align": "center",
                "margin": "xl"
            })
        # 無異動
        elif not res.get("has_action"):
            body_contents.append({
                "type": "text",
                "text": "今日籌碼無異動",
                "color": "#95a5a6",
                "size": "sm",
                "weight": "bold",
                "wrap": True,
                "align": "center",
                "margin": "xl"
            })
        # 有異動
        else:
            def add_section(title: str, title_color: str, items: list, margin_top: str = "md"):
                if not items: return
                # 標題
                body_contents.append({
                    "type": "text",
                    "text": title,
                    "color": title_color,
                    "weight": "bold",
                    "size": "sm",
                    "margin": margin_top
                })
                # 內容 (使用 \n 組合)
                body_contents.append({
                    "type": "text",
                    "text": "\n".join(items),
                    "color": "#333333",
                    "size": "sm",
                    "wrap": True,
                    "margin": "sm"
                })
                # 分隔線
                body_contents.append({
                    "type": "separator",
                    "margin": "md",
                    "color": "#eeeeee"
                })

            add_section("新進場", "#d35400", res["new_buy"])
            add_section("加碼", "#e74c3c", res["increased"])
            add_section("減碼", "#27ae60", res["decreased"])
            add_section("已離場", "#7f8c8d", res["sold_out"])

            # 移除最後一條多餘的分隔線
            if body_contents and body_contents[-1]["type"] == "separator":
                body_contents.pop()

        bubble = {
            "type": "bubble",
            "size": "kilo", 
            "header": header_box,
            "body": {
                "type": "box",
                "layout": "vertical",
                "paddingAll": "15px",
                "contents": body_contents
            }
        }
        bubbles.append(bubble)

    # 封裝成 Carousel
    return {
        "type": "flex",
        "altText": f"每日籌碼異動卡片已送達 ({report_date})",
        "contents": {
            "type": "carousel",
            "contents": bubbles
        }
    }

def send_flex_message(flex_payload: dict) -> None:
    """透過 LINE Broadcast API 發送 Flex Message"""
    if not LINE_TOKEN: return
    url = "https://api.line.me/v2/bot/message/broadcast"
    headers = {"Authorization": f"Bearer {LINE_TOKEN}", "Content-Type": "application/json"}
    payload = {"messages": [flex_payload]}
    
    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=10)
        if not resp.ok:
            logger.error(f"LINE 發送失敗: {resp.status_code} - {resp.text}")
        else:
            logger.info("✅ Flex Message 發送成功！")
    except Exception as e:
        logger.error("LINE 連線錯誤: %s", e)

# ═══════════════════════════════
# 主程式
# ═══════════════════════════════
def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true", help="強制執行（忽略假日）")
    args = parser.parse_args()

    if not args.force and not is_trading_day():
        logger.info("🏖️ 今天不是交易日，跳過執行")
        return

    os.makedirs(HISTORY_DIR, exist_ok=True)
    today_str = datetime.now().strftime("%Y-%m-%d")
    logger.info(f"📋 執行每日籌碼異動報告 ({today_str})")
    
    results = []
    for etf in ETF_LIST:
        try:
            res = process_etf(etf)
            results.append(res)
        except Exception as e:
            logger.error("處理 %s 發生錯誤: %s", etf, e)

    if results:
        flex_payload = build_flex_carousel(results, today_str)
        send_flex_message(flex_payload)
    else:
        # Fallback 純文字錯誤訊息
        if LINE_TOKEN:
            headers = {"Authorization": f"Bearer {LINE_TOKEN}", "Content-Type": "application/json"}
            requests.post(
                "https://api.line.me/v2/bot/message/broadcast", 
                headers=headers, 
                json={"messages": [{"type": "text", "text": "今日爬蟲全部失敗。"}]}
            )

if __name__ == "__main__":
    main()