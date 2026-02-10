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

# ================= ⚙️ 修改 A：從環境變數讀取 Token =================
# 這樣做最安全，等一下我們會在 GitHub 網站上設定這個變數
LINE_TOKEN = os.environ.get("TFnGs2oCTg2XFx36148i1ocMmKAUSh7C9M1qCY7v0bfnhQC2dmdN5IcNqs5L7/tZ/d247+jYOcVPeZUZk3hy14TOYSBQHPiVOZINSMzQT67DScN+tO53WJ9iQjMOJ0Dk901WX+AP/gVNE4cgyZRJ7QdB04t89/1O/w1cDnyilFU=")

# 如果你在自己電腦跑，不想設定環境變數，可以把上面那行註解掉，用下面這行：
# LINE_TOKEN = "你的_LINE_TOKEN_直接貼在這裡" 

TARGET_URL = "https://www.pocket.tw/etf/tw/00981A/fundholding/"

# ================= 📂 路徑設定 =================
# 在雲端上，直接用相對路徑最穩
HISTORY_DIR = "history"
if not os.path.exists(HISTORY_DIR):
    os.makedirs(HISTORY_DIR)

# ================= 🕸️ 爬蟲功能 =================
def fetch_data():
    print("🔵 啟動爬蟲 (Selenium Headless)...")
    
    chrome_options = Options()
    chrome_options.add_argument("--headless") 
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--window-size=1920,1080")
    
    # ================= ⚙️ 修改 B：新增這兩行給雲端用 =================
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    # ===============================================================

    chrome_options.add_argument("user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

    try:
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=chrome_options)
        
        print(f"🚀 前往: {TARGET_URL}")
        driver.get(TARGET_URL)
        time.sleep(5) 
        
        # 模擬捲動
        print("🖱️ 模擬捲動頁面...")
        last_height = driver.execute_script("return document.body.scrollHeight")
        for i in range(3):
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(3)
            new_height = driver.execute_script("return document.body.scrollHeight")
            if new_height == last_height:
                break
            last_height = new_height
            
        soup = BeautifulSoup(driver.page_source, "html.parser")
        driver.quit()

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
        
        print(f"✅ 成功抓取 {len(data)} 筆持股資料")
        return data

    except Exception as e:
        print(f"💥 爬蟲發生錯誤: {e}")
        try: driver.quit()
        except: pass
        return []

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
        response = requests.post(url, headers=headers, json=payload)
        if response.status_code == 200:
            print("✅ LINE 通知發送成功")
        else:
            print(f"❌ LINE 發送失敗: {response.text}")
    except Exception as e:
        print(f"❌ LINE 連線錯誤: {e}")

# ================= 🚀 主程式邏輯 =================
def main():
    today_str = datetime.now().strftime('%Y-%m-%d')
    today_file = os.path.join(HISTORY_DIR, f"{today_str}.csv")

    today_data = fetch_data()
    if not today_data:
        print("⚠️ 抓不到資料，程式停止。")
        return

    today_df = pd.DataFrame(today_data)
    today_df.to_csv(today_file, index=False, encoding="utf-8-sig")
    print(f"💾 今日資料已存檔: {today_file}")

    # 尋找歷史檔案
    all_files = sorted(glob.glob(os.path.join(HISTORY_DIR, "*.csv")))
    
    new_buy_list = []
    sold_out_list = []
    weight_changes = []

    if len(all_files) >= 2:
        last_file = all_files[-2]
        print(f"🔍 正在比對: {os.path.basename(last_file)} vs 今日")
        
        last_df = pd.read_csv(last_file, dtype={'code': str})
        today_map = today_df.set_index('code').to_dict('index')
        last_map = last_df.set_index('code').to_dict('index')
        today_codes = set(today_df['code'].astype(str))
        last_codes = set(last_df['code'].astype(str))

        new_buy_codes = today_codes - last_codes
        sold_out_codes = last_codes - today_codes
        common_codes = today_codes & last_codes
        
        for c in new_buy_codes:
            row = today_df[today_df['code'].astype(str) == c].iloc[0]
            new_buy_list.append(f"{row['name']} ({row['weight']}%)")
            
        for c in sold_out_codes:
            row = last_df[last_df['code'].astype(str) == c].iloc[0]
            sold_out_list.append(row['name'])
            
        for c in common_codes:
            row_now = today_df[today_df['code'].astype(str) == c].iloc[0]
            row_last = last_df[last_df['code'].astype(str) == c].iloc[0]
            diff = row_now['weight'] - row_last['weight']
            
            if abs(diff) > 0.2:
                arrow = "⬆️" if diff > 0 else "⬇️"
                weight_changes.append(f"{arrow} {row_now['name']}: {row_last['weight']}% ➝ {row_now['weight']}%")
    else:
        print("ℹ️ 這是第一筆資料，無法進行比對。")
    
    msg = f"📊 00981A 戰報 ({today_str})\n"
    msg += "\n【⚡️ 籌碼異動】\n"
    
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
        msg += "✅ 今日無新增或剔除成分股。\n"

    msg += "\n【💰 今日持股權重 (前20大)】\n"
    sorted_df = today_df.sort_values(by='weight', ascending=False)
    rank = 1
    for index, row in sorted_df.iterrows():
        if rank > 20: 
            msg += f"...(還有 {len(sorted_df)-20} 檔)\n"
            break
        msg += f"{rank}. {row['name']}: {row['weight']}%\n"
        rank += 1

    send_line_message(msg)

if __name__ == "__main__":
    main()