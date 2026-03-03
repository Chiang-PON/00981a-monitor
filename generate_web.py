"""generate_web.py — 自動生成靜態網頁儀表板 (高密度緊湊排版)

讀取 history/ 下的 CSV 檔案，計算每日籌碼異動。
- 修正 UI 空虛感：下方詳細清單加入橫向分隔線，縮減行距與留白，提高資料密度。
- 調整字體大小與徽章 (Badge) 比例，呈現更緊湊、專業的表格閱讀體驗。
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
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Noto+Sans+TC:wght@400;500;600;700;800&display=swap" rel="stylesheet">
    <script src="https://cdn.tailwindcss.com"></script>
    <style>
        :root {
            --bg-page: #f0f4f8;
            --card-bg: #ffffff;
            --text-primary: #1e293b;
            --text-secondary: #64748b;
            --accent-buy: #dc2626;
            --accent-sell: #059669;
            --accent-neutral: #475569;
            --border-light: #e2e8f0;
            --shadow-card: 0 4px 6px -1px rgba(0,0,0,0.07), 0 2px 4px -2px rgba(0,0,0,0.05);
            --shadow-hover: 0 10px 15px -3px rgba(0,0,0,0.08), 0 4px 6px -4px rgba(0,0,0,0.05);
        }
        body {
            background: linear-gradient(180deg, #f8fafc 0%, var(--bg-page) 100%);
            color: var(--text-primary);
            font-family: "Noto Sans TC", -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
            min-height: 100vh;
        }
        .tab-btn {
            transition: all 0.2s ease;
            white-space: nowrap;
            font-size: 1rem;
            min-width: 4rem;
        }
        .tab-active {
            background: linear-gradient(135deg, #1e3a5f 0%, #0f172a 100%);
            color: #fff;
            font-weight: 700;
            border: none;
            box-shadow: var(--shadow-card);
        }
        .tab-inactive {
            background: var(--card-bg);
            color: var(--text-secondary);
            border: 2px solid var(--border-light);
        }
        .tab-inactive:hover {
            background: #f8fafc;
            color: var(--text-primary);
            border-color: #94a3b8;
        }
        .card {
            background: var(--card-bg);
            border-radius: 20px;
            padding: 2rem 2.5rem;
            box-shadow: var(--shadow-card);
            border: 1px solid var(--border-light);
        }
        .card:hover { box-shadow: var(--shadow-hover); }
        select {
            background: #f8fafc;
            color: var(--text-primary);
            border: 2px solid var(--border-light);
            padding: 0.6rem 1.2rem;
            border-radius: 10px;
            font-size: 1.05rem;
            font-weight: 600;
            outline: none;
            cursor: pointer;
            transition: all 0.2s;
        }
        select:hover, select:focus {
            border-color: #64748b;
            background: #fff;
        }
        .hide-scrollbar::-webkit-scrollbar { display: none; }
        .hide-scrollbar { -ms-overflow-style: none; scrollbar-width: none; }
        .data-row:hover { background-color: #f8fafc !important; }
        .section-label {
            font-size: 1.05rem;
            font-weight: 700;
            letter-spacing: 0.05em;
        }
        .header-accent {
            background: linear-gradient(90deg, #1e3a5f 0%, transparent 100%);
            height: 4px;
            border-radius: 2px;
            margin-top: 0.5rem;
        }
    </style>
</head>
<body class="pb-24 pt-6 md:pt-10">
    <div class="max-w-5xl mx-auto px-4 md:px-8">
        
        <header class="mb-8 md:mb-12">
            <div class="flex flex-col md:flex-row md:items-end md:justify-between gap-4">
                <div>
                    <h1 class="text-3xl md:text-4xl lg:text-5xl font-extrabold text-slate-800 tracking-tight leading-tight">
                        ETF 籌碼監控儀表板
                    </h1>
                    <p class="text-slate-500 mt-2 text-base md:text-lg font-medium">
                        主動式基金持股異動深度解析
                    </p>
                    <div class="header-accent w-24 md:w-32"></div>
                </div>
            </div>
        </header>

        <div class="mb-6">
            <p class="text-slate-500 text-sm font-medium mb-3">選擇 ETF</p>
            <div id="etf-tabs" class="flex overflow-x-auto hide-scrollbar gap-3 pb-2 px-1"></div>
        </div>

        <div class="card mb-8">
            <div class="flex flex-col sm:flex-row sm:justify-between sm:items-center gap-4 pb-6 mb-8 border-b-2 border-slate-100">
                <div class="flex flex-wrap items-baseline gap-3">
                    <h2 id="current-etf-title" class="text-3xl md:text-4xl font-extrabold text-slate-800">載入中...</h2>
                    <span id="current-date-display" class="text-xl md:text-2xl text-slate-400 font-semibold"></span>
                </div>
                <div class="flex items-center gap-3 bg-slate-50/80 px-4 py-3 rounded-xl border border-slate-100">
                    <span class="text-slate-600 font-semibold text-base">歷史日期</span>
                    <select id="date-selector" onchange="changeDate()"></select>
                </div>
            </div>

            <div class="mb-12">
                <h3 class="section-label text-slate-700 mb-5 flex items-center">
                    <span class="w-1.5 h-6 bg-slate-300 rounded-full mr-3"></span>
                    當日個股操作趨勢
                </h3>
                <div id="chart-container" class="w-full rounded-xl border-2 border-slate-100 overflow-hidden bg-slate-50/30">
                </div>
            </div>

            <div>
                <h3 class="section-label text-slate-700 mb-6 flex items-center">
                    <span class="w-1.5 h-6 bg-slate-300 rounded-full mr-3"></span>
                    異動明細總覽
                </h3>
                
                <div id="empty-state" class="text-center text-slate-400 py-16 bg-slate-50 rounded-xl border-2 border-dashed border-slate-200 hidden">
                    <span class="text-4xl block mb-3 text-slate-300">—</span>
                    <p class="text-lg font-medium">當日無任何籌碼異動</p>
                </div>
                
                <div class="grid grid-cols-1 md:grid-cols-2 gap-8 md:gap-12">
                    <div class="flex flex-col gap-8">
                        <div id="list-new" class="hidden">
                            <h4 class="text-red-600 font-bold text-lg md:text-xl mb-4 flex items-center">
                                <span class="w-2 h-6 bg-red-500 rounded-full mr-3"></span>
                                新進場建倉
                            </h4>
                            <div id="items-new" class="flex flex-col rounded-xl border-2 border-slate-100 overflow-hidden bg-white"></div>
                        </div>
                        <div id="list-inc" class="hidden">
                            <h4 class="text-red-500 font-bold text-lg md:text-xl mb-4 flex items-center">
                                <span class="w-2 h-6 bg-red-400 rounded-full mr-3"></span>
                                加碼買進
                            </h4>
                            <div id="items-inc" class="flex flex-col rounded-xl border-2 border-slate-100 overflow-hidden bg-white"></div>
                        </div>
                    </div>

                    <div class="flex flex-col gap-8">
                        <div id="list-dec" class="hidden">
                            <h4 class="text-emerald-600 font-bold text-lg md:text-xl mb-4 flex items-center">
                                <span class="w-2 h-6 bg-emerald-500 rounded-full mr-3"></span>
                                減碼獲利／停損
                            </h4>
                            <div id="items-dec" class="flex flex-col rounded-xl border-2 border-slate-100 overflow-hidden bg-white"></div>
                        </div>
                        <div id="list-out" class="hidden">
                            <h4 class="text-slate-500 font-bold text-lg md:text-xl mb-4 flex items-center">
                                <span class="w-2 h-6 bg-slate-400 rounded-full mr-3"></span>
                                完全出清
                            </h4>
                            <div id="items-out" class="flex flex-col rounded-xl border-2 border-slate-100 overflow-hidden bg-white"></div>
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
                document.body.innerHTML = "<h1 class='text-slate-500 text-center mt-20 text-xl font-bold'>目前尚無歷史資料。</h1>";
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
                btn.className = `tab-btn px-6 py-2.5 border rounded-full text-sm md:text-base cursor-pointer select-none ${isActive ? 'tab-active' : 'tab-inactive'}`;
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
                chartContainer.innerHTML = '<div class="text-slate-400 py-12 text-center text-lg font-medium">本日無操作資料</div>';
                return;
            }

            emptyState.classList.add('hidden');

            let formattedItems = [];
            
            [...(etfData.new_buy || []), ...(etfData.increased || [])].forEach(i => {
                formattedItems.push({ name: i.name, trueVal: i.diff });
            });
            [...(etfData.decreased || []), ...(etfData.sold_out || [])].forEach(i => {
                formattedItems.push({ name: i.name, trueVal: -i.diff });
            });

            formattedItems.sort((a, b) => b.trueVal - a.trueVal);
            const maxVal = Math.max(...formattedItems.map(i => Math.abs(i.trueVal)));

            let chartHTML = '<div class="flex flex-col">';
            
            formattedItems.forEach((item, index) => {
                const isBuy = item.trueVal > 0;
                const valStr = isBuy ? `+${item.trueVal.toLocaleString()}` : item.trueVal.toLocaleString();
                const textColor = isBuy ? 'text-rose-600' : 'text-emerald-600';
                const barColor = isBuy ? 'bg-rose-500' : 'bg-emerald-500';
                const bgClass = index % 2 === 0 ? 'bg-white' : 'bg-slate-50/40'; 
                
                const widthPct = Math.max((Math.abs(item.trueVal) / maxVal) * 100, 2);

                chartHTML += `
                <div class="data-row flex items-center text-base md:text-lg py-4 px-5 ${bgClass} border-b border-slate-100 last:border-0 transition-colors">
                    <div class="w-36 md:w-48 flex-shrink-0 flex justify-between items-center pr-5 border-r border-slate-200">
                        <span class="font-bold text-slate-700 w-24 md:w-32 truncate text-left text-[15px] md:text-[17px]">${item.name}</span>
                        <span class="font-mono font-extrabold ${textColor} text-right text-[15px] md:text-[17px]">${valStr}</span>
                    </div>
                    <div class="flex-grow flex items-center pl-5">
                        <div class="w-full bg-slate-200/60 rounded-r-lg h-7 md:h-8 overflow-hidden">
                            <div class="${barColor} h-full rounded-r-lg transition-all duration-300" style="width: ${widthPct}%"></div>
                        </div>
                    </div>
                </div>
                `;
            });
            chartHTML += '</div>';
            chartContainer.innerHTML = chartHTML;

            const fillSection = (sectionId, items, colorClass, sign) => {
                const wrap = document.getElementById(`list-${sectionId}`);
                const list = document.getElementById(`items-${sectionId}`);
                list.innerHTML = '';
                
                if(items && items.length > 0) {
                    wrap.classList.remove('hidden');
                    items.forEach(i => {
                        const valStr = `${sign}${i.diff.toLocaleString()}`;
                        list.innerHTML += `
                        <div class="flex justify-between items-center py-3 px-4 border-b border-slate-100 last:border-0 hover:bg-slate-50 transition-colors">
                            <span class="text-[16px] md:text-[17px] font-bold text-slate-700">${i.name}</span>
                            <span class="${colorClass} text-[15px] md:text-[16px] font-mono font-extrabold px-3 py-1 rounded-lg border border-slate-100 bg-slate-50/50">${valStr}</span>
                        </div>`;
                    });
                } else {
                    wrap.classList.add('hidden');
                }
            };

            fillSection('new', etfData.new_buy, 'text-rose-600', '+');
            fillSection('inc', etfData.increased, 'text-rose-600', '+');
            fillSection('dec', etfData.decreased, 'text-emerald-600', '-');
            
            const outWrap = document.getElementById('list-out');
            const outList = document.getElementById('items-out');
            outList.innerHTML = '';
            if(etfData.sold_out && etfData.sold_out.length > 0) {
                outWrap.classList.remove('hidden');
                etfData.sold_out.forEach(i => {
                    outList.innerHTML += `
                    <div class="flex justify-between items-center py-3 px-4 border-b border-slate-100 last:border-0 hover:bg-slate-50 transition-colors">
                        <span class="text-[16px] md:text-[17px] font-bold text-slate-700">${i.name}</span>
                        <span class="text-slate-500 text-[15px] md:text-[16px] font-mono font-extrabold px-3 py-1 rounded-lg border border-slate-100 bg-slate-50/50">出清 ${i.diff.toLocaleString()}</span>
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
    print("🚀 開始產出 Web Dashboard (高密度緊湊版)...")
    db = process_all_data()
    
    json_str = json.dumps(db, ensure_ascii=False)
    final_html = HTML_TEMPLATE.replace("__DB_JSON__", json_str)
    
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(final_html)
        
    print(f"✅ 成功產出 {OUTPUT_FILE}")

if __name__ == "__main__":
    main()