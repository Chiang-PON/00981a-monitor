import time
import os
import glob
import pandas as pd
import requests
import sys
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.options import Options
from bs4 import BeautifulSoup
from datetime import datetime

# ================= ⚙️ 設定區 =================
# 1. LINE Token (從 GitHub Secrets 讀取)
LINE_TOKEN = os.environ.get("LINE_TOKEN")

# 2. 要監控的 ETF 清單 (你想加幾支都可以寫在這裡)
ETF_LIST = ["00980A", "00981A", "00982A"]

# 3. 網址樣板 ({} 會被自動替換成代號)
URL_TEMPLATE = "https://www.pocket.tw/etf/tw/{}/fundholding/"

# ================= 📂 路徑設定 =================
HISTORY_DIR = "history"
if not os.path.exists(HISTORY_DIR):
    os.makedirs(HISTORY_DIR)

# ================= 🕸️ 爬蟲功能 =================
def fetch_data(etf_code):
    target_url = URL_TEMPLATE.format(etf_code)
    print(f"🔵 [{etf_code}] 啟動爬蟲...")
    
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
        
        print(f"🚀 前往: {target_url}")
        driver.get(target_url)
        time.sleep(5) 
        
        # 模擬捲動
        print(f"🖱️ [{etf_code}] 模擬捲動頁面...")
        last_height = driver.execute_script("return document.body.scrollHeight")
        for i in range(3):
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(3)
            new_height = driver.execute_script("return document.body.scrollHeight")
            if new_height == last_height:
                break
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
                        data.append({
                            "code": code,
                            "name": name,
                            "weight": float(weight),
                            "shares": int(shares)
                        })
        
        print(f"✅ [{etf_code}] 成功抓取 {len(data)} 筆資料")
        return data

    except Exception as e:
        print(f"💥 [{etf_code}] 爬蟲發生錯誤: {e}")
        return []
    finally:
        if driver:
            driver.quit()

# ================= 📡 LINE 通知功能 =================
def send_line_message(msg):
    if not LINE_TOKEN:
        print("❌ 未設定 LINE TOKEN，跳過發送")
        return

    url = "https://api.line.me/v2/bot/message/broadcast"
    headers = {
        "Authorization": f"Bearer {LINE_TOKEN}",
        "Content-Type": "application/json"
    }
    payload = {
        "messages": [{"type": "text", "text": msg}]
    }
    try:
        requests.post(url, headers=headers, json=payload)
        print("✅ LINE 通知已發送")
    except Exception as e:
        print(f"❌ LINE 連線錯誤: {e}")

# ================= 📊 單一 ETF 處理邏輯 =================
def process_etf(etf_code):
    print(f"\n======== 開始處理 {etf_code} ========")
    today_str = datetime.now().strftime('%Y-%m-%d')
    # 檔名加上 ETF 代號，避免搞混 (例如: history/00981A_2026-02-11.csv)
    today_file = os.path.join(HISTORY_DIR, f"{etf_code}_{today_str}.csv")

    # 1. 抓取資料
    today_data = fetch_data(etf_code)
    if not today_data:
        print(f"⚠️ {etf_code} 抓不到資料，跳過。")
        return

    today_df = pd.DataFrame(today_data)
    
    # 2. 存檔
    today_df.to_csv(today_file, index=False, encoding="utf-8-sig")
    print(f"💾 {etf_code} 資料已存檔: {today_file}")

    # 3. 比對歷史紀錄
    # 只抓取「這個代號」的歷史檔案 (00981A_*.csv)
    all_files = sorted(glob.glob(os.path.join(HISTORY_DIR, f"{etf_code}_*.csv")))
    
    new_buy_list = []
    sold_out_list = []
    weight_changes = []

    if len(all_files) >= 2:
        last_file = all_files[-2] # 倒數第二個是昨天
        print(f"🔍 [{etf_code}] 比對對象: {os.path.basename(last_file)}")
        
        last_df = pd.read_csv(last_file, dtype={'code': str})
        
        today_codes = set(today_df['code'].astype(str))
        last_codes = set(last_df['code'].astype(str))

        # A. 買進與賣出
        new_buy_codes = today_codes - last_codes
        sold_out_codes = last_codes - today_codes
        common_codes = today_codes & last_codes
        
        for c in new_buy_codes:
            row = today_df[today_df['code'].astype(str) == c].iloc[0]
            new_buy_list.append(f"{row['name']} ({row['weight']}%)")
            
        for c in sold_out_codes:
            row = last_df[last_df['code'].astype(str) == c].iloc[0]
            sold_out_list.append(row['name'])
            
        # B. 權重變化
        for c in common_codes:
            row_now = today_df[today_df['code'].astype(str) == c].iloc[0]
            row_last = last_df[last_df['code'].astype(str) == c].iloc[0]
            diff = row_now['weight'] - row_last['weight']
            
            if abs(diff) > 0.2:
                arrow = "⬆️" if diff > 0 else "⬇️"
                weight_changes.append(f"{arrow} {row_now['name']}: {diff:+.2f}%")
    else:
        print(f"ℹ️ {etf_code} 資料不足，無法比對 (可能是第一天執行)。")

    # 4. 組合訊息
    msg = f"📊 {etf_code} 戰報 ({today_str})\n"
    msg += "━━━━━━━━━━━━\n"
    
    has_action = False
    if new_buy_list:
        has_action = True
        msg += "🔥 新進場:\n" + "\n".join([f"   + {x}" for x in new_buy_list]) + "\n"
    if sold_out_list:
        has_action = True
        msg += "👋 已離場:\n" + "\n".join([f"   - {x}" for x in sold_out_list]) + "\n"
    if weight_changes:
        has_action = True
        msg += "⚖️ 重點調整:\n" + "\n".join(weight_changes) + "\n"
    if not has_action:
        msg += "✅ 成分股無重大異動。\n"

    msg += "\n【💰 持股權重 (前10大)】\n"
    sorted_df = today_df.sort_values(by='weight', ascending=False)
    rank = 1
    for index, row in sorted_df.iterrows():
        if rank > 10: # 3支股票訊息會很多，建議縮減到前10名
            break
        msg += f"{rank}. {row['name']}: {row['weight']}%\n"
        rank += 1
    
    # 傳送 Line
    send_line_message(msg)
    time.sleep(2) # 休息一下再發下一則，避免太快被 Line 擋

# ================= 🚀 主程式 (迴圈執行) =================
def main():
    print(f"📢 開始執行多檔監控: {ETF_LIST}")
    
    for etf in ETF_LIST:
        try:
            process_etf(etf)
        except Exception as e:
            print(f"❌ 處理 {etf} 時發生未知錯誤: {e}")
            
    print("🎉 所有 ETF 處理完成！")

if __name__ == "__main__":
    main()
