"""generate_web.py — 自動生成靜態網頁儀表板 (原生資料條完美對齊修復版)

讀取 history/ 下的 CSV 檔案，計算每日籌碼異動。
- 捨棄 Chart.js，改用原生 HTML/CSS Data Bars 達成完美的「名字靠左、數字靠右」版面。
- 修復：下方詳細清單的減碼數字正確顯示為負號 (-)。
- 極簡淺色主題，無 Emoji，完美支援手機響應式排版。
"""

import os
import glob
import re
import json
import pandas as pd
from datetime import datetime

HISTORY_DIR = "history"
OUTPUT_FILE = "index.html"

# 名稱淨化
NAME_REPLACEMENTS = {
    "台灣積體電路製造": "台積電", "鴻海精密工業": "鴻海", "台達電子工業": "台達電", 
    "緯穎科技服務": "緯穎", "聯發科技": "聯發科", "金像電子（股）公司": "金像電", 
    "金像電子": "金像電", "廣達電腦": "廣達", "智邦科技": "智邦", "奇鋐科技": "奇鋐",
    "鴻勁精密": "鴻勁", "台燿科技": "台燿", "群聯電子": "群聯", "健策精密工業": "健策",
    "旺矽科技": "旺矽", "勤誠興業": "勤誠", "中國信託金融控股": "中信金", "京元電子": "京元電",
    "緯創資通": "緯創", "文曄科技": "文曄", "欣銓科技": "欣銓", "致伸科技": "致伸",
    "南亞科技": "南亞科", "健鼎科技": "健鼎", "凡甲科技": "凡甲", "崇越科技": "崇越",
    "瑞昱半導體": "瑞昱", "致茂電子": "致茂", "鈊象電子": "鈊象", "高力熱處理工業": "高力",
    "台光電子材料": "台光電", "華城電機": "華城", "穎崴科技": "穎崴", "中華精測科技": "精測",
    "川湖科技": "川湖", "亞德客國際集團": "亞德客", "玉山金融控股": "玉山金", 
    "富邦金融控股": "富邦金", "華邦電子": "華邦電", "大成不銹鋼工業": "大成鋼",
    "聚陽實業": "聚陽", "達興材料": "達興材", "技嘉科技": "技嘉", 
    "貿聯控股（BizLink Holding In": "貿聯-KY", "寶雅國際": "寶雅", "創意電子": "創意",
    "光紅建聖": "光紅建聖",
}
STRIP_PATTERN = re.compile(r"（股）公司|\(股\)公司|股份有限公司|有限公司|科技|工業|電子|電腦")

def clean_stock_name(name: str) -> str:
    name = name.replace("*", "").strip()
    for old, new in NAME_REPLACEMENTS.items():
        if old in name: return new
    name = STRIP_PATTERN.sub("", name)
    return name.strip()

def process_all_data():
    all_files = glob.glob(os.path.join(HISTORY_DIR, "*.csv"))
    if not all_files:
        return {}

    file_map = {}
    for f in all_files:
        basename = os.path.basename(f).replace(".csv", "")
        parts = basename.split("_")
        if len(parts) >= 2:
            etf_code = parts[0]
            date_str = parts[1]
            if etf_code not in file_map:
                file_map[etf_code] = []
            file_map[etf_code].append((date_str, f))

    database = {}
    
    for etf_code, files in file_map.items():
        files.sort(key=lambda x: x[0])
        
        for i in range(1, len(files)):
            prev_date, prev_file = files[i-1]
            curr_date, curr_file = files[i]
            
            if curr_date not in database:
                database[curr_date] = {}
                
            try:
                df_prev = pd.read_csv(prev_file, dtype={"code": str})
                df_curr = pd.read_csv(curr_file, dtype={"code": str})
                
                prev_codes = set(df_prev["code"].astype(str))
                curr_codes = set(df_curr["code"].astype(str))
                common_codes = prev_codes & curr_codes
                
                new_buy = []
                sold_out = []
                increased = []
                decreased = []
                
                for c in (curr_codes - prev_codes):
                    row = df_curr[df_curr["code"].astype(str) == c].iloc[0]
                    shares = int(row["shares"] / 1000)
                    new_buy.append({"name": clean_stock_name(row["name"]), "diff": shares})
                    
                for c in (prev_codes - curr_codes):
                    row = df_prev[df_prev["code"].astype(str) == c].iloc[0]
                    shares = int(row["shares"] / 1000)
                    sold_out.append({"name": clean_stock_name(row["name"]), "diff": shares})
                    
                for c in common_codes:
                    row_curr = df_curr[df_curr["code"].astype(str) == c].iloc[0]
                    row_prev = df_prev[df_prev["code"].astype(str) == c].iloc[0]
                    diff = int(row_curr["shares"] / 1000) - int(row_prev["shares"] / 1000)
                    
                    if diff > 0:
                        increased.append({"name": clean_stock_name(row_curr["name"]), "diff": diff})
                    elif diff < 0:
                        decreased.append({"name": clean_stock_name(row_curr["name"]), "diff": abs(diff)})
                        
                new_buy.sort(key=lambda x: x["diff"], reverse=True)
                sold_out.sort(key=lambda x: x["diff"], reverse=True)
                increased.sort(key=lambda x: x["diff"], reverse=True)
                decreased.sort(key=lambda x: x["diff"], reverse=True)
                
                database[curr_date][etf_code] = {
                    "new_buy": new_buy,
                    "sold_out": sold_out,
                    "increased": increased,
                    "decreased": decreased
                }
            except Exception as e:
                print(f"處理 {curr_file} 失敗: {e}")

    return database

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-TW">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>ETF 籌碼監控儀表板</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <style>
        body { background-color: #f8fafc; color: #0f172a; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; }
        .tab-btn { transition: all 0.2s ease-in-out; white-space: nowrap; }
        .tab-active { background-color: #0f172a; color: #ffffff; font-weight: bold; border-color: #0f172a; }
        .tab-inactive { background-color: #ffffff; color: #64748b; border-color: #cbd5e1; }
        .card { background-color: #ffffff; border-radius: 12px; padding: 24px; box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05), 0 2px 4px -1px rgba(0, 0, 0, 0.03); border: 1px solid #e2e8f0; }
        select { background-color: #ffffff; color: #0f172a; border: 1px solid #cbd5e1; padding: 6px 12px; border-radius: 6px; font-size: 0.95rem; outline: none; cursor: pointer; font-weight: 500; }
        select:focus { border-color: #94a3b8; }
        
        .hide-scrollbar::-webkit-scrollbar { display: none; }
        .hide-scrollbar { -ms-overflow-style: none; scrollbar-width: none; }
    </style>
</head>
<body class="pb-20 pt-6">
    <div class="max-w-4xl mx-auto p-4 md:p-6">
        
        <header class="mb-8">
            <h1 class="text-3xl font-extrabold text-slate-900 tracking-tight">ETF 籌碼監控儀表板</h1>
            <p class="text-slate-500 mt-2 text-sm">主動式基金持股異動深度解析</p>
        </header>

        <div id="etf-tabs" class="flex overflow-x-auto hide-scrollbar gap-2 mb-8 pb-2"></div>

        <div class="card mb-8">
            <div class="flex flex-col sm:flex-row sm:justify-between sm:items-end border-b border-slate-200 pb-4 mb-6 gap-4">
                <div class="flex items-baseline gap-3">
                    <h2 id="current-etf-title" class="text-3xl font-bold text-slate-800 tracking-tight">載入中...</h2>
                    <span id="current-date-display" class="text-lg text-slate-500 font-medium"></span>
                </div>
                <div class="flex items-center gap-2">
                    <span class="text-sm text-slate-500">切換日期</span>
                    <select id="date-selector" onchange="changeDate()"></select>
                </div>
            </div>

            <div class="mb-10">
                <h3 class="text-lg font-semibold text-slate-700 mb-4">當日個股操作趨勢</h3>
                <div id="chart-container" class="w-full">
                    </div>
            </div>

            <div>
                <h3 class="text-lg font-semibold text-slate-700 mb-4 border-b border-slate-200 pb-2">當日異動明細</h3>
                
                <div id="empty-state" class="text-center text-slate-400 py-10 hidden">當日無籌碼異動</div>
                
                <div class="grid grid-cols-1 md:grid-cols-2 gap-8">
                    <div class="space-y-6">
                        <div id="list-new" class="hidden">
                            <h4 class="text-red-600 font-bold text-base mb-3 bg-red-50 inline-block px-3 py-1 rounded">新進場</h4>
                            <div id="items-new" class="space-y-2 text-slate-700"></div>
                        </div>
                        <div id="list-inc" class="hidden">
                            <h4 class="text-red-600 font-bold text-base mb-3 bg-red-50 inline-block px-3 py-1 rounded">加碼</h4>
                            <div id="items-inc" class="space-y-2 text-slate-700"></div>
                        </div>
                    </div>

                    <div class="space-y-6">
                        <div id="list-dec" class="hidden">
                            <h4 class="text-green-600 font-bold text-base mb-3 bg-green-50 inline-block px-3 py-1 rounded">減碼</h4>
                            <div id="items-dec" class="space-y-2 text-slate-700"></div>
                        </div>
                        <div id="list-out" class="hidden">
                            <h4 class="text-slate-500 font-bold text-base mb-3 bg-slate-100 inline-block px-3 py-1 rounded">已離場</h4>
                            <div id="items-out" class="space-y-2 text-slate-500"></div>
                        </div>
                    </div>
                </div>
            </div>
        </div>

    </div>

    <script>
        const db = __DB_JSON__;
        const availableDatesDesc = Object.keys(db).sort().reverse();
        
        let allETFs = new Set();
        Object.values(db).forEach(dateData => {
            Object.keys(dateData).forEach(etf => allETFs.add(etf));
        });
        const etfList = Array.from(allETFs).sort();
        
        let currentDate = availableDatesDesc[0];
        let currentETF = etfList[0];

        function init() {
            if(availableDatesDesc.length === 0) {
                document.body.innerHTML = "<h1 class='text-slate-500 text-center mt-20 text-xl'>目前尚無歷史資料。</h1>";
                return;
            }
            
            const sel = document.getElementById('date-selector');
            availableDatesDesc.forEach(date => {
                const opt = document.createElement('option');
                opt.value = date;
                opt.textContent = date;
                sel.appendChild(opt);
            });
            
            renderTabs();
            updateDashboard();
        }

        function changeDate() {
            currentDate = document.getElementById('date-selector').value;
            updateDashboard();
        }

        function selectETF(etf) {
            currentETF = etf;
            renderTabs();
            updateDashboard();
        }

        function renderTabs() {
            const container = document.getElementById('etf-tabs');
            container.innerHTML = '';
            
            etfList.forEach(etf => {
                const btn = document.createElement('button');
                const isActive = etf === currentETF;
                btn.className = `tab-btn px-6 py-2 border rounded-full text-sm md:text-base cursor-pointer select-none shadow-sm ${isActive ? 'tab-active' : 'tab-inactive'}`;
                btn.textContent = etf;
                btn.onclick = () => selectETF(etf);
                container.appendChild(btn);
            });
        }

        function updateDashboard() {
            document.getElementById('current-etf-title').textContent = currentETF;
            document.getElementById('current-date-display').textContent = currentDate;
            updateChartAndList();
        }

        function updateChartAndList() {
            const dataToday = db[currentDate] || {};
            const etfData = dataToday[currentETF];
            const emptyState = document.getElementById('empty-state');
            const sections = ['new', 'inc', 'dec', 'out'];
            const chartContainer = document.getElementById('chart-container');
            
            if(!etfData || (!etfData.new_buy.length && !etfData.increased.length && !etfData.decreased.length && !etfData.sold_out.length)) {
                emptyState.classList.remove('hidden');
                sections.forEach(s => document.getElementById(`list-${s}`).classList.add('hidden'));
                chartContainer.innerHTML = '<div class="text-slate-400 py-4">本日無操作資料</div>';
                return;
            }

            emptyState.classList.add('hidden');

            // 準備資料
            let formattedItems = [];
            
            [...(etfData.new_buy || []), ...(etfData.increased || [])].forEach(i => {
                formattedItems.push({ name: i.name, trueVal: i.diff });
            });
            [...(etfData.decreased || []), ...(etfData.sold_out || [])].forEach(i => {
                formattedItems.push({ name: i.name, trueVal: -i.diff });
            });

            // 依照買賣力道排序
            formattedItems.sort((a, b) => b.trueVal - a.trueVal);
            
            const maxVal = Math.max(...formattedItems.map(i => Math.abs(i.trueVal)));

            // 動態生成原生 HTML 資料條
            let chartHTML = '<div class="flex flex-col space-y-1.5 mt-2">';
            
            formattedItems.forEach(item => {
                const isBuy = item.trueVal > 0;
                // 自動處理字串的正負號顯示
                const valStr = isBuy ? `+${item.trueVal.toLocaleString()}` : item.trueVal.toLocaleString();
                const textColor = isBuy ? 'text-red-600' : 'text-green-600';
                const bgColor = isBuy ? 'bg-red-500' : 'bg-green-500';
                
                // 避免長條圖過小看不見，設定最低 0.5% 寬度
                const widthPct = Math.max((Math.abs(item.trueVal) / maxVal) * 100, 0.5);

                chartHTML += `
                <div class="flex items-center text-sm md:text-base py-1 hover:bg-slate-50 rounded-md transition-colors">
                    
                    <div class="w-48 md:w-60 flex-shrink-0 flex items-center pr-3 md:pr-4 border-r border-slate-300 mr-3 md:mr-4">
                        <span class="font-medium text-slate-700 w-24 md:w-32 truncate text-left">${item.name}</span>
                        
                        <span class="font-mono font-bold ${textColor} flex-grow text-right tracking-tight">${valStr}</span>
                    </div>

                    <div class="flex-grow h-5 md:h-6 flex items-center pr-2">
                        <div class="${bgColor} h-full rounded-sm opacity-80" style="width: ${widthPct}%"></div>
                    </div>
                </div>
                `;
            });
            chartHTML += '</div>';
            chartContainer.innerHTML = chartHTML;

            // 💎 更新下方詳細清單 (修正正負號邏輯)
            const fillSection = (sectionId, items, colorClass, sign) => {
                const wrap = document.getElementById(`list-${sectionId}`);
                const list = document.getElementById(`items-${sectionId}`);
                list.innerHTML = '';
                
                if(items && items.length > 0) {
                    wrap.classList.remove('hidden');
                    items.forEach(i => {
                        const valStr = `${sign}${i.diff.toLocaleString()}`;
                        list.innerHTML += `<div class="flex justify-between items-center border-b border-slate-100 pb-2 mb-2">
                            <span class="font-medium">${i.name}</span>
                            <span class="${colorClass} font-mono font-semibold">${valStr}</span>
                        </div>`;
                    });
                } else {
                    wrap.classList.add('hidden');
                }
            };

            // 確保這裡分別傳入正確的符號
            fillSection('new', etfData.new_buy, 'text-red-600', '+');
            fillSection('inc', etfData.increased, 'text-red-600', '+');
            fillSection('dec', etfData.decreased, 'text-green-600', '-');
            
            const outWrap = document.getElementById('list-out');
            const outList = document.getElementById('items-out');
            outList.innerHTML = '';
            if(etfData.sold_out && etfData.sold_out.length > 0) {
                outWrap.classList.remove('hidden');
                etfData.sold_out.forEach(i => {
                    outList.innerHTML += `<div class="flex justify-between items-center border-b border-slate-100 pb-2 mb-2">
                        <span class="font-medium">${i.name}</span>
                        <span class="text-slate-500 font-mono font-semibold">出清 ${i.diff.toLocaleString()}</span>
                    </div>`;
                });
            } else {
                outWrap.classList.add('hidden');
            }
        }

        window.onload = init;
    </script>
</body>
</html>"""

def main():
    print("🚀 開始產出 Web Dashboard (原生完美對齊資料條修復版)...")
    db = process_all_data()
    
    json_str = json.dumps(db, ensure_ascii=False)
    final_html = HTML_TEMPLATE.replace("__DB_JSON__", json_str)
    
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(final_html)
        
    print(f"✅ 成功產出 {OUTPUT_FILE}")

if __name__ == "__main__":
    main()