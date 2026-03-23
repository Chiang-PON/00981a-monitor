# 專案名稱：ETF 籌碼決策戰情室 v7.2 - 凱基大聯盟 (18 分點無痛擴充模組)

## 👤 角色設定
你是一位資深的 Python 與前端工程師。請在「絕對不破壞原有架構、不影響原有 LINE Notify 推播功能」的前提下，將 18 間凱基分點的爬蟲與解析邏輯「局部注入」到現有的 `main.py` 與 `generate_web.py` 中。

## 🎯 核心目標
不要整份重寫檔案！請用新增函數、修改特定迴圈的方式，將玩股網券商分點的爬取與前端渲染邏輯整合進現有系統。

---

## 🛠️ 修改 1：`main.py` 後端爬蟲注入

1. **新增常數**：在檔案上方加入 18 間分點清單。
```python
BROKER_LIST = {
    "9207": "凱基永和", "920A": "凱基板橋", "920D": "凱基市府", "920F": "凱基站前",
    "9216": "凱基信義", "9217": "凱基松山", "9218": "凱基大直", "921F": "凱基天母",
    "921J": "凱基土城", "921S": "凱基新莊", "9229": "凱基中山", "9234": "凱基竹北",
    "9238": "凱基士林", "9239": "凱基市政", "9257": "凱基林口", "9272": "凱基竹科",
    "9285": "凱基中壢", "9287": "凱基內湖"
}
新增券商爬蟲函數 fetch_broker_data(broker_code, driver)：

目標 URL：https://www.wantgoo.com/stock/major-investors/broker-buy-sell-rank?during=1&majorId=9200&branchId={broker_code}&orderBy=count

使用傳入的 driver 讀取網頁，並以 WebDriverWait 等待 #buyTable tr 出現。

抓取買超 (#buyTable) 與賣超 (#sellTable) 的資料。欄位需包含 code, name, net_shares, net_amount。

賣超的張數與金額請轉換為負數。

新增統籌函數 crawl_all_brokers()：

初始化一次帶有 --headless=new 以及防爬蟲參數 (--disable-blink-features=AutomationControlled 等) 的 Chrome WebDriver。

迴圈遍歷 BROKER_LIST，共用同一個 driver 呼叫 fetch_broker_data。

將抓到的資料存成 {broker_code}_{today_str}.csv。

主程式注入：在 main() 函數中，跑完 ETF process_etf 的迴圈後，新增一行呼叫 crawl_all_brokers()。

🛠️ 修改 2：generate_web.py 前端渲染注入
同步常數：在檔案最上方加入與後端相同的 BROKER_LIST 字典。

Python 解析層 (process_all_data) 注入：

在讀取所有 CSV 的迴圈中，新增條件判斷：若檔案名稱前綴 (如 920A) 存在於 BROKER_LIST 中，代表它是券商流量資料。

免相減邏輯：不需要拿前一天資料相減。直接讀取當日 CSV，將 net_shares > 0 放入 increased，< 0 放入 decreased。

輸出的 JSON 資料結構需與 ETF 完全一致，以供前端相容。

JavaScript 選單動態生成注入：

網頁 JS 的下拉選單組合邏輯中，請先加入 GLOBAL_CONSENSUS 與一般 ETF。

接著判斷：若目前資料庫有抓到任何券商資料，則加入 KAIJI_CONSENSUS (凱基大聯盟) 選項，並依序加入有資料的券商名稱。

最後加入 AI_AGENT。