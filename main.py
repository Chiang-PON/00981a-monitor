import time
import os
import glob
import pandas as pd
import requests
import sys
import re
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.options import Options
from bs4 import BeautifulSoup
from datetime import datetime
from collections import Counter

# ================= 設定區 =================
LINE_TOKEN = os.environ.get("LINE_TOKEN")
ETF_LIST = ["00980A", "00981A", "00982A"]
URL_TEMPLATE = "https://www.pocket.tw/etf/tw/{}/fundholding/"

# ================= 名稱淨化功能 =================
def clean_stock_name(name):
    name = name.replace('*', '')
    replacements = {
        "台灣積體電路製造": "台積電", "鴻海精密工業": "鴻海",
        "台達電子工業": "台達電", "緯穎科技服務": "緯穎",
        "聯發科技": "聯發科", "金像電子": "金像電",
        "廣達電腦": "廣達", "智邦科技": "智邦",
        "奇鋐科技": "奇鋐", "鴻勁精密": "鴻勁",
        "台燿科技": "台燿", "群聯電子": "群聯",
        "健策精密工業": "健策", "旺矽科技": "旺矽",
        "勤誠興業": "勤誠", "中國信託金融控股": "中信金",
        "京元電子": "京元電"
    }
    for old, new in replacements.items():
        if old in name: return new
    name = re.sub(r'（股）公司|\(股\)公司|股份有限公司|有限公司|科技|工業|電子|電腦', '', name)
    return name.strip()

# ================= 📂 路徑設定 =================
HISTORY_DIR = "history"
if not os.path.exists(HISTORY_DIR):
    os.makedirs(HISTORY_DIR)

# ================= 🕸️ 爬蟲功能 =================
def fetch_data(etf_code):
    target_url = URL_TEMPLATE.format(etf_code)
    print(f"[{etf_code}] 啟動爬蟲...")
    chrome_options = Options()
    chrome_options.add_argument("--headless") 
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--window-size=1920,1080")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

    driver = None
    try:
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=chrome_options)
        driver.get(target_url)
        time.sleep(5) 
        
        last_height = driver.execute_script("return document.body.scrollHeight")
        for i in range(3):
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(3)
            new_height = driver.execute_script("return document.body.scrollHeight")
            if new_height == last_height: break
            last_height = new_height
            
        soup = BeautifulSoup(driver.page_source, "html.parser")
        table = soup.find("table", class_="cm-table__table")
        data = []
        if table:
            rows = table.find("tbody").find_all("tr")
            for row in rows:
                cols = row.find_all("td")
                if len(cols) >= 4:
                    code = cols[0].text.strip()
                    name_tag = cols[1].find("h2")
                    name = name_tag.text.strip() if name_tag else cols[1].text.strip()
                    weight = cols[2].text.strip().replace("%", "")
                    shares = cols[3].text.strip().replace(",", "")
                    if code.isdigit():
                        data.append({"code": code, "name": name, "weight": float(weight), "shares": int(shares)})
        return data
    except Exception as e:
        print(f"[{etf_code}] 爬蟲發生錯誤: {e}")
        return []
    finally:
        if driver:
            try: driver.quit()
            except: pass

# ================= 📡 LINE 通知功能 =================
def send_line_message(msg):
    if not LINE_TOKEN: return
    url = "https://api.line.me/v2/bot/message/broadcast"
    headers = {"Authorization": f"Bearer {LINE_TOKEN}", "Content-Type": "application/json"}
    payload = {"messages": [{"type": "text", "text": msg}]}
    try:
        requests.post(url, headers=headers, json=payload)
    except Exception as e:
        print(f"LINE 連線錯誤: {e}")

# ================= 📊 單一 ETF 處理邏輯 =================
def process_etf(etf_code):
    print(f"\n======== 開始處理 {etf_code} ========")
    today_str = datetime.now().strftime('%Y-%m-%d')
    today_file = os.path.join(HISTORY_DIR, f"{etf_code}_{today_str}.csv")

    today_data = fetch_data(etf_code)
    if not today_data: return None

    today_df = pd.DataFrame(today_data)
    today_df.to_csv(today_file, index=False, encoding="utf-8-sig")

    all_files = sorted(glob.glob(os.path.join(HISTORY_DIR, f"{etf_code}_*.csv")))
    
    new_buy_list = []
    sold_out_list = []
    increased_list = []
    decreased_list = []
    changes_dict = {} # 記錄「張數差異」

    if len(all_files) >= 2:
        last_file = all_files[-2]
        last_df = pd.read_csv(last_file, dtype={'code': str})
        
        today_codes = set(today_df['code'].astype(str))
        last_codes = set(last_df['code'].astype(str))
        common_codes = today_codes & last_codes
        
        # 新進場 (記錄買了幾張)
        for c in (today_codes - last_codes):
            row = today_df[today_df['code'].astype(str) == c].iloc[0]
            sheets = int(row['shares'] / 1000)
            clean_name = clean_stock_name(row['name'])
            new_buy_list.append(f"　+ {clean_name} ｜ {sheets:,} 張")
            changes_dict[row['name']] = sheets 
            
        # 已離場 (記錄賣了幾張)
        for c in (last_codes - today_codes):
            row = last_df[last_df['code'].astype(str) == c].iloc[0]
            sheets = int(row['shares'] / 1000)
            clean_name = clean_stock_name(row['name'])
            sold_out_list.append(f"　- {clean_name} ｜ 出清 {sheets:,} 張")
            changes_dict[row['name']] = -sheets 
            
        # 張數異動 (只看張數，不看權重)
        for c in common_codes:
            row_now = today_df[today_df['code'].astype(str) == c].iloc[0]
            row_last = last_df[last_df['code'].astype(str) == c].iloc[0]
            
            shares_now = int(row_now['shares'] / 1000)
            shares_last = int(row_last['shares'] / 1000)
            shares_diff = shares_now - shares_last
            
            # 只要張數有變，就記錄下來
            if shares_diff != 0:
                changes_dict[row_now['name']] = shares_diff
                clean_name = clean_stock_name(row_now['name'])
                if shares_diff > 0:
                    increased_list.append((clean_name, shares_diff))
                else:
                    decreased_list.append((clean_name, shares_diff))
                    
    # 依照張數多寡排序
    increased_list.sort(key=lambda x: x[1], reverse=True)
    decreased_list.sort(key=lambda x: x[1])

    msg = f"▪️ {etf_code}\n"
    msg += "┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈\n"
    
    has_action = False
    if new_buy_list:
        has_action = True
        msg += f"✦ [ {etf_code} 新進場 ]\n" + "\n".join(new_buy_list) + "\n\n"
    if sold_out_list:
        has_action = True
        msg += f"✖️ [ {etf_code} 已離場 ]\n" + "\n".join(sold_out_list) + "\n\n"
        
    if increased_list or decreased_list:
        has_action = True
        msg += f"[ {etf_code} 張數異動 ]\n"
        if increased_list:
            msg += "🔺 加碼\n"
            for n, sd in increased_list: 
                msg += f"　+ {n} ｜ +{sd:,} 張\n"
        if decreased_list:
            msg += "🟩 減碼\n"
            for n, sd in decreased_list: 
                msg += f"　- {n} ｜ {sd:,} 張\n"
        msg += "\n"
        
    if not has_action:
        msg += f"✔️ {etf_code} 今日籌碼無重大異動。\n\n"

    msg += f"[ {etf_code} 前十大持股 ]\n"
    sorted_df = today_df.sort_values(by='weight', ascending=False)
    rank = 1
    for index, row in sorted_df.iterrows():
        if rank > 10: break
        sheets = int(row['shares'] / 1000)
        clean_name = clean_stock_name(row['name'])
        rank_str = str(rank).zfill(2)
        # 前十大保留權重與張數，方便你檢視整體佔比
        msg += f"{rank_str}. {clean_name} ｜ {row['weight']:.2f}% ｜ {sheets:,} 張\n"
        rank += 1
    
    return {"etf": etf_code, "df": today_df, "changes": changes_dict, "msg_string": msg.strip()}

# ================= 📈 產生總結報告 =================
def generate_summary_report(results):
    if not results: return ""
    all_stocks = {} 
    for res in results:
        df = res['df']
        for _, row in df.iterrows():
            if row['name'] not in all_stocks: all_stocks[row['name']] = []
            all_stocks[row['name']].append(row['weight'])
            
    common_holdings = []
    for name, weights in all_stocks.items():
        if len(weights) >= 2: 
            avg_w = sum(weights) / len(weights)
            common_holdings.append((name, avg_w, len(weights)))
    common_holdings.sort(key=lambda x: x[1], reverse=True)

    collective_buy = []
    collective_sell = []
    all_changed_stocks = set()
    for res in results: all_changed_stocks.update(res['changes'].keys())
        
    for stock in all_changed_stocks:
        up_count = 0
        down_count = 0
        for res in results:
            # 現在這裡抓出來的是「張數差異」
            shares_diff = res['changes'].get(stock, 0)
            if shares_diff > 0: up_count += 1
            elif shares_diff < 0: down_count += 1
                
        clean_name = clean_stock_name(stock)
        if up_count >= 2: collective_buy.append(f"{clean_name} (x{up_count})")
        if down_count >= 2: collective_sell.append(f"{clean_name} (x{down_count})")

    today_str = datetime.now().strftime('%Y-%m-%d')
    summary_msg = f"⚡ 主動式 ETF 家族彙總 ({today_str})\n"
    summary_msg += "┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈\n"
    
    if collective_buy:
        summary_msg += "🔺 [ 家族集體加碼 ]\n" + "、".join(collective_buy) + "\n\n"
    if collective_sell:
        summary_msg += "🟩 [ 家族集體減碼 ]\n" + "、".join(collective_sell) + "\n\n"
    if not collective_buy and not collective_sell:
        summary_msg += "➖ 今日籌碼無明顯集體操作方向。\n\n"

    summary_msg += "[ 家族核心重壓股 ]\n"
    for i, (name, avg_w, count) in enumerate(common_holdings[:5]): 
        clean_name = clean_stock_name(name)
        rank_str = str(i+1).zfill(2)
        summary_msg += f"{rank_str}. {clean_name} ｜ {avg_w:.2f}% ｜ 共 {count} 檔持有\n"

    return summary_msg.strip()

# ================= 🚀 主程式 =================
def main():
    results = []
    final_message_blocks = []
    for etf in ETF_LIST:
        try:
            res = process_etf(etf)
            if res: results.append(res)
        except Exception as e:
            print(f"處理 {etf} 時發生錯誤: {e}")
            
    if len(results) >= 2:
        try:
            summary = generate_summary_report(results)
            if summary: final_message_blocks.append(summary)
        except Exception: pass
            
    for res in results:
        final_message_blocks.append(res["msg_string"])
        
    if final_message_blocks:
        separator = "\n\n━━━━━━━━━━━━━━━\n\n"
        final_combined_message = separator.join(final_message_blocks)
        send_line_message(final_combined_message)

if __name__ == "__main__":
    main()
