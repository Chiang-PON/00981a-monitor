import time
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager

def test_wantgoo_scraper():
    url = "https://www.wantgoo.com/stock/major-investors/broker-buy-sell-rank?during=1&majorId=9200&branchId=920A&orderBy=count"
    
    print("🚀 開始測試抓取玩股網: 凱基-板橋 (920A)...")

    chrome_options = Options()
    # ⚠️ 【關鍵1】暫時把 headless 註解掉，我們要親眼看瀏覽器發生什麼事
    # chrome_options.add_argument("--headless") 
    
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--window-size=1920,1080")
    
    # ⚠️ 【關鍵2】終極偽裝術：關閉 webdriver 標記
    chrome_options.add_argument("--disable-blink-features=AutomationControlled")
    chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
    chrome_options.add_experimental_option('useAutomationExtension', False)
    
    # 偽裝成最新版 Mac Chrome
    chrome_options.add_argument("user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36")

    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=chrome_options)
    
    # 再次抹除 webdriver 特徵 (執行一段隱藏 JS)
    driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
        "source": """
        Object.defineProperty(navigator, 'webdriver', {
          get: () => undefined
        })
        """
    })

    try:
        print("🌍 開啟網頁中...")
        driver.get(url)
        print("⏳ 正在監視 #buyTable 是否長出資料 (最多等 15 秒)...")
        
        wait = WebDriverWait(driver, 15)
        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "#buyTable tr")))
        
        time.sleep(1)

        soup = BeautifulSoup(driver.page_source, "html.parser")
        buy_table = soup.find("tbody", id="buyTable")

        if not buy_table:
            print("❌ 找不到 id='buyTable'！")
            return

        rows = buy_table.find_all("tr")
        print(f"\n✅ 成功突破！抓到買超表格，共 {len(rows)} 筆資料。\n")
        
        print(f"{'排名':<4} | {'股票名稱':<10} | {'買進':<6} | {'賣出':<6} | {'淨買超張數':<8} | {'淨買超金額(萬)':<10}")
        print("-" * 65)

        for row in rows[:10]:
            cols = row.find_all("td")
            if len(cols) >= 6:
                rank = cols[0].text.strip()
                stock_name_tag = cols[1].find("a")
                stock_name = stock_name_tag.text.strip() if stock_name_tag else cols[1].text.strip()
                buy_vol = cols[2].text.strip()
                sell_vol = cols[3].text.strip()
                net_buy_shares = cols[4].text.strip()
                net_buy_amount = cols[5].text.strip()
                
                print(f"{rank:<4} | {stock_name:<10} | {buy_vol:<6} | {sell_vol:<6} | {net_buy_shares:<8} | {net_buy_amount:<10}")

    except Exception as e:
        print(f"\n❌ 依然發生錯誤: {e}")
        print("👉 請看一下跳出來的 Chrome 視窗，是不是卡在 Cloudflare 驗證（轉圈圈或要求點擊）？")
    finally:
        # 為了讓你能在當機時看清楚畫面，這裡暫時不自動關閉瀏覽器
        # driver.quit()
        input("\n請按 Enter 鍵關閉瀏覽器...")

if __name__ == "__main__":
    test_wantgoo_scraper()