"""generate_web.py — 自動生成靜態網頁儀表板

讀取 history/ 下的 CSV 檔案，計算每日籌碼異動，
並產出一個包含 Tailwind CSS 的 index.html 單頁應用程式。
"""

import os
import glob
import re
import json
import pandas as pd
from datetime import datetime

HISTORY_DIR = "history"
OUTPUT_FILE = "index.html"

# 名稱淨化 (與 main.py 保持一致)
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
    """解析所有 CSV，建立 {date: {etf: {details}}} 的結構"""
    all_files = glob.glob(os.path.join(HISTORY_DIR, "*.csv"))
    if not all_files:
        return {}

    # 提取所有 ETF 代號與日期
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
        # 依日期排序
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
                
                # 新進場
                for c in (curr_codes - prev_codes):
                    row = df_curr[df_curr["code"].astype(str) == c].iloc[0]
                    shares = int(row["shares"] / 1000)
                    new_buy.append({"name": clean_stock_name(row["name"]), "diff": shares})
                    
                # 已離場
                for c in (prev_codes - curr_codes):
                    row = df_prev[df_prev["code"].astype(str) == c].iloc[0]
                    shares = int(row["shares"] / 1000)
                    sold_out.append({"name": clean_stock_name(row["name"]), "diff": shares})
                    
                # 增減碼
                for c in common_codes:
                    row_curr = df_curr[df_curr["code"].astype(str) == c].iloc[0]
                    row_prev = df_prev[df_prev["code"].astype(str) == c].iloc[0]
                    diff = int(row_curr["shares"] / 1000) - int(row_prev["shares"] / 1000)
                    
                    if diff > 0:
                        increased.append({"name": clean_stock_name(row_curr["name"]), "diff": diff})
                    elif diff < 0:
                        decreased.append({"name": clean_stock_name(row_curr["name"]), "diff": abs(diff)})
                        
                # 排序
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
    <title>主動式 ETF 家族籌碼戰報</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <style>
        body { background-color: #121212; color: #e0e0e0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; }
        .tab-btn { transition: all 0.2s ease-in-out; }
        .tab-active { background-color: #f39c12; color: #121212; font-weight: bold; border-color: #f39c12; }
        .tab-inactive { background-color: #1e272e; color: #bdc3c7; border-color: #333; }
        .card { background-color: #1e272e; border-radius: 12px; padding: 20px; box-shadow: 0 4px 6px rgba(0,0,0,0.3); }
        select { background-color: #2c3e50; color: white; border: 1px solid #34495e; padding: 10px; border-radius: 8px; font-size: 1.1rem; outline: none; }
    </style>
</head>
<body class="pb-20">
    <div class="max-w-4xl mx-auto p-4 md:p-6">
        
        <div class="flex flex-col md:flex-row justify-between items-center mb-8 gap-4 border-b border-gray-700 pb-4">
            <div>
                <h1 class="text-3xl font-bold text-white tracking-wide">📊 每日籌碼戰報</h1>
                <p class="text-gray-400 mt-2 text-sm">您的專屬法人級投資儀表板</p>
            </div>
            <div>
                <select id="date-selector" onchange="changeDate()"></select>
            </div>
        </div>

        <div class="card mb-8 border border-gray-700">
            <h2 class="text-xl font-bold text-white mb-4 flex items-center gap-2">
                <span class="text-2xl">🔥</span> 家族今日重點總結
            </h2>
            <div class="grid grid-cols-1 md:grid-cols-2 gap-6">
                <div class="bg-gray-800 rounded-lg p-4">
                    <h3 class="text-red-400 font-bold mb-3 border-b border-gray-600 pb-2">🔺 家族大買 Top 5</h3>
                    <ul id="top-buys" class="space-y-2"></ul>
                </div>
                <div class="bg-gray-800 rounded-lg p-4">
                    <h3 class="text-green-400 font-bold mb-3 border-b border-gray-600 pb-2">🟩 家族大賣 Top 5</h3>
                    <ul id="top-sells" class="space-y-2"></ul>
                </div>
            </div>
        </div>

        <div>
            <h2 class="text-xl font-bold text-white mb-4">🗂️ 各檔 ETF 詳細籌碼</h2>
            
            <div id="etf-tabs" class="flex flex-wrap gap-2 mb-6"></div>

            <div id="etf-content" class="card border border-gray-700">
                <div id="empty-state" class="text-center text-gray-400 py-10 hidden">今日無籌碼異動</div>
                
                <div id="list-new" class="mb-6 hidden">
                    <h3 class="text-[#d35400] font-bold text-lg mb-2">✦ 新進場</h3>
                    <div id="items-new" class="space-y-2 text-gray-300 text-lg"></div>
                </div>
                
                <div id="list-inc" class="mb-6 hidden">
                    <h3 class="text-red-500 font-bold text-lg mb-2">🔺 加碼</h3>
                    <div id="items-inc" class="space-y-2 text-gray-300 text-lg"></div>
                </div>
                
                <div id="list-dec" class="mb-6 hidden">
                    <h3 class="text-green-500 font-bold text-lg mb-2">🟩 減碼</h3>
                    <div id="items-dec" class="space-y-2 text-gray-300 text-lg"></div>
                </div>
                
                <div id="list-out" class="hidden">
                    <h3 class="text-gray-400 font-bold text-lg mb-2">✖️ 已離場</h3>
                    <div id="items-out" class="space-y-2 text-gray-500 text-lg"></div>
                </div>
            </div>
        </div>

    </div>

    <script>
        // 由 Python 注入的資料
        const db = __DB_JSON__;
        const availableDates = Object.keys(db).sort().reverse();
        
        let currentDate = availableDates[0];
        let currentETF = null;

        function init() {
            if(availableDates.length === 0) {
                document.body.innerHTML = "<h1 class='text-white text-center mt-20 text-2xl'>尚未累積足夠的歷史資料來產生圖表。</h1>";
                return;
            }
            
            const sel = document.getElementById('date-selector');
            availableDates.forEach(date => {
                const opt = document.createElement('option');
                opt.value = date;
                opt.textContent = "📅 " + date;
                sel.appendChild(opt);
            });
            
            render();
        }

        function changeDate() {
            currentDate = document.getElementById('date-selector').value;
            currentETF = null; // 重置選擇的 ETF
            render();
        }

        function render() {
            const dataToday = db[currentDate] || {};
            const etfs = Object.keys(dataToday).sort();
            
            if(!currentETF || !etfs.includes(currentETF)) {
                currentETF = etfs[0];
            }

            renderDashboard(dataToday);
            renderTabs(etfs);
            renderETFDetails(dataToday[currentETF]);
        }

        function renderDashboard(dataToday) {
            let buyMap = {};
            let sellMap = {};

            Object.values(dataToday).forEach(etfData => {
                [...(etfData.new_buy||[]), ...(etfData.increased||[])].forEach(item => {
                    buyMap[item.name] = (buyMap[item.name] || 0) + item.diff;
                });
                [...(etfData.sold_out||[]), ...(etfData.decreased||[])].forEach(item => {
                    sellMap[item.name] = (sellMap[item.name] || 0) + item.diff;
                });
            });

            const topBuys = Object.entries(buyMap).sort((a,b)=>b[1]-a[1]).slice(0, 5);
            const topSells = Object.entries(sellMap).sort((a,b)=>b[1]-a[1]).slice(0, 5);

            renderList('top-buys', topBuys, 'text-red-400', '+');
            renderList('top-sells', topSells, 'text-green-400', '-');
        }

        function renderList(elementId, items, colorClass, sign) {
            const el = document.getElementById(elementId);
            el.innerHTML = '';
            if(items.length === 0) {
                el.innerHTML = '<li class="text-gray-500 italic">無顯著動作</li>';
                return;
            }
            items.forEach(item => {
                el.innerHTML += `<li class="flex justify-between items-center text-lg">
                    <span>${item[0]}</span>
                    <span class="${colorClass} font-mono">${sign}${item[1].toLocaleString()} 張</span>
                </li>`;
            });
        }

        function renderTabs(etfs) {
            const container = document.getElementById('etf-tabs');
            container.innerHTML = '';
            
            if(etfs.length === 0) return;

            etfs.forEach(etf => {
                const btn = document.createElement('button');
                const isActive = etf === currentETF;
                btn.className = `tab-btn px-5 py-2 border rounded-full text-sm md:text-base cursor-pointer select-none ${isActive ? 'tab-active' : 'tab-inactive'}`;
                btn.textContent = etf;
                btn.onclick = () => {
                    currentETF = etf;
                    render();
                };
                container.appendChild(btn);
            });
        }

        function renderETFDetails(etfData) {
            const emptyState = document.getElementById('empty-state');
            const sections = ['new', 'inc', 'dec', 'out'];
            
            if(!etfData || (!etfData.new_buy.length && !etfData.increased.length && !etfData.decreased.length && !etfData.sold_out.length)) {
                emptyState.classList.remove('hidden');
                sections.forEach(s => document.getElementById(`list-${s}`).classList.add('hidden'));
                return;
            }

            emptyState.classList.add('hidden');

            const fillSection = (sectionId, items, sign, isOut=false) => {
                const wrap = document.getElementById(`list-${sectionId}`);
                const list = document.getElementById(`items-${sectionId}`);
                list.innerHTML = '';
                if(items && items.length > 0) {
                    wrap.classList.remove('hidden');
                    items.forEach(i => {
                        const valStr = isOut ? `出清 ${i.diff.toLocaleString()}` : `${sign}${i.diff.toLocaleString()}`;
                        list.innerHTML += `<div class="flex justify-between items-center border-b border-gray-800 pb-1">
                            <span>${i.name}</span>
                            <span class="font-mono">${valStr} 張</span>
                        </div>`;
                    });
                } else {
                    wrap.classList.add('hidden');
                }
            };

            fillSection('new', etfData.new_buy, '+');
            fillSection('inc', etfData.increased, '+');
            fillSection('dec', etfData.decreased, '-');
            fillSection('out', etfData.sold_out, '', true);
        }

        window.onload = init;
    </script>
</body>
</html>"""

def main():
    print("🚀 開始產出 Web Dashboard...")
    db = process_all_data()
    
    # 將 Python 字典轉為 JSON 字串，嵌入 HTML
    json_str = json.dumps(db, ensure_ascii=False)
    final_html = HTML_TEMPLATE.replace("__DB_JSON__", json_str)
    
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(final_html)
        
    print(f"✅ 成功產出 {OUTPUT_FILE}")

if __name__ == "__main__":
    main()