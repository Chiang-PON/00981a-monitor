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
from collections import Counter

# ================= ⚙️ 設定區 =================
# 1. LINE Token
LINE_TOKEN = os.environ.get("LINE_TOKEN")

# 2. 要監控的 ETF 清單
ETF_LIST = ["00980A", "00981A", "00982A"]

# 3. 網址樣板
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
            try: driver.quit()
            except: pass

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

# ================= 📊 單一 ETF 處理邏輯 (含張數換算) =================
def process_etf(etf_code):
    print(f"\n======== 開始處理 {etf_code} ========")
    today_str = datetime.now().strftime('%Y-%m-%d')
    today_file = os.path.join(HISTORY_DIR, f"{etf_code}_{today_str}.csv")

    # 1. 抓取資料
    today_data = fetch_data(etf_code)
    if not today_data:
        print(f"⚠️ {etf_code} 抓不到資料，跳過。")
        return None

    today_df = pd.DataFrame(today_data)
    today_df.to_csv(today_file, index=False, encoding="utf-8-sig")
    print(f"💾 {etf_code} 資料已存檔")

    # 2. 比對歷史紀錄
    all_files = sorted(glob.glob(os.path.join(HISTORY_DIR, f"{etf_code}_*.csv")))
    
    new_buy_list = []
    sold_out_list = []
    weight_changes_msg = []
    changes_dict = {} 

    if len(all_files) >= 2:
        last_file = all_files[-2]
        last_df = pd.read_csv(last_file, dtype={'code': str})
        
        today_codes = set(today_df['code'].astype(str))
        last_codes = set(last_df['code'].astype(str))
        common_codes = today_codes & last_codes
        
        # 新買進 (新增顯示張數)
        for c in (today_codes - last_codes):
            row = today_df[today_df['code'].astype(str) == c].iloc[0]
            # 計算張數 (股數 / 1000)
            sheets = int(row['shares'] / 1000)
            # 格式範例: 台積電 (5.5%, 2,000張)
            new_buy_list.append(f"{row['name']} ({row['weight']}%, {sheets:,}張)")
            changes_dict[row['name']] = row['weight']
            
        # 已賣出
        for c in (last_codes - today_codes):
            row = last_df[last_df['code'].astype(str) == c].iloc[0]
            sold_out_list.append(row['name'])
            changes_dict[row['name']] = -row['weight']
            
        # 權重調整
        for c in common_codes:
            row_now = today_df[today_df['code'].astype(str) == c].iloc[0]
            row_last = last_df[last_df['code'].astype(str) == c].iloc[0]
            diff = row_now['weight'] - row_last['weight']
            
            changes_dict[row_now['name']] = diff
            
            if abs(diff) > 0.2:
                arrow = "⬆️" if diff > 0 else "⬇️"
                weight_changes_msg.append(f"{arrow} {row_now['name']}: {diff:+.2f}%")

    # 3. 發送個別戰報
    msg = f"📊 {etf_code} 戰報 ({today_str})\n"
    msg += "━━━━━━━━━━━━\n"
    
    has_action = False
    if new_buy_list:
        has_action = True
        msg += "🔥 新進場:\n" + "\n".join([f"   + {x}" for x in new_buy_list]) + "\n"
    if sold_out_list:
        has_action = True
        msg += "👋 已離場:\n" + "\n".join([f"   - {x}" for x in sold_out_list]) + "\n"
    if weight_changes_msg:
        has_action = True
        msg += "⚖️ 重點調整:\n" + "\n".join(weight_changes_msg) + "\n"
    if not has_action:
        msg += "✅ 成分股無重大異動。\n"

    msg += "\n【💰 前十大持股 (含張數)】\n"
    sorted_df = today_df.sort_values(by='weight', ascending=False)
    rank = 1
    for index, row in sorted_df.iterrows():
        if rank > 10: break
        # 計算張數並加上千分位
        sheets = int(row['shares'] / 1000)
        msg += f"{rank}. {row['name']}: {row['weight']}% ({sheets:,}張)\n"
        rank += 1
    
    send_line_message(msg)
    time.sleep(2)
    
    return {
        "etf": etf_code,
        "df": today_df,
        "changes": changes_dict
    }

# ================= 📈 產生總結報告 =================
def generate_summary_report(results):
    print("\n======== 正在產生總結報告 ========")
    if not results: return

    # 1. 計算共同持股
    all_stocks = {} 
    
    for res in results:
        df = res['df']
        for _, row in df.iterrows():
            if row['name'] not in all_stocks:
                all_stocks[row['name']] = []
            all_stocks[row['name']].append(row['weight'])
            
    common_holdings = []
    for name, weights in all_stocks.items():
        if len(weights) >= 2: 
            avg_w = sum(weights) / len(weights)
            common_holdings.append((name, avg_w, len(weights)))
            
    common_holdings.sort(key=lambda x: x[1], reverse=True)

    # 2. 分析集體動向
    collective_buy = []
    collective_sell = []
    
    all_changed_stocks = set()
    for res in results:
        all_changed_stocks.update(res['changes'].keys())
        
    for stock in all_changed_stocks:
        up_count = 0
        down_count = 0
        
        for res in results:
            diff = res['changes'].get(stock, 0)
            if diff > 0.05: 
                up_count += 1
            elif diff < -0.05:
                down_count += 1
                
        if up_count >= 2:
            collective_buy.append(f"{stock} (x{up_count})")
        if down_count >= 2:
            collective_sell.append(f"{stock} (x{down_count})")

    # 3. 組合總結訊息
    today_str = datetime.now().strftime('%Y-%m-%d')
    summary_msg = f"📑 主動式 ETF 家族總結 ({today_str})\n"
    summary_msg += "━━━━━━━━━━━━\n"
    
    if collective_buy:
        summary_msg += f"🚀 【集體看好】(同時加碼):\n" + "、".join(collective_buy) + "\n\n"
    
    if collective_sell:
        summary_msg += f"📉 【集體看壞】(同時減碼):\n" + "、".join(collective_sell) + "\n\n"
        
    if not collective_buy and not collective_sell:
        summary_msg += "⚖️ 今日無明顯集體操作方向。\n\n"

    summary_msg += "🔥 【共同重壓股】(平均權重):\n"
    for i, (name, avg_w, count) in enumerate(common_holdings[:5]): 
        summary_msg += f"{i+1}. {name}: {avg_w:.2f}% (持有數:{count})\n"

    print("---------------- 總結預覽 ----------------")
    print(summary_msg)
    print("----------------------------------------")
    
    send_line_message(summary_msg)

# ================= 🚀 主程式 =================
def main():
    print(f"📢 開始執行多檔監控: {ETF_LIST}")
    
    results = []
    
    for etf in ETF_LIST:
        try:
            res = process_etf(etf)
            if res:
                results.append(res)
        except Exception as e:
            print(f"❌ 處理 {etf} 時發生未知錯誤: {e}")
            
    if len(results) >= 2:
        try:
            generate_summary_report(results)
        except Exception as e:
            print(f"❌ 產生總結報告失敗: {e}")
            
    print("🎉 所有 ETF 處理完成！")

if __name__ == "__main__":
    main()
