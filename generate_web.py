"""generate_web.py — 自動生成靜態網頁儀表板 (香檳金奢華 ＋ 彭博決策完全體)

讀取 history/ 下的 CSV 檔案，計算每日籌碼異動。
- 4 大決策功能：全家族共識、連續買賣超追蹤、關鍵權重顯示、個股反查雷達。
- 視覺史詩升級：導入香檳白、琥珀金棕、古銅褐奢華色調。
- 極致排版：收緊行距、完美對齊、徹底移除所有 Emoji，展現絕對專業。
"""

import os
import glob
import re
import json
import pandas as pd
from datetime import datetime

HISTORY_DIR = "history"
OUTPUT_FILE = "index.html"

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
                
                new_buy, sold_out, increased, decreased = [], [], [], []
                
                for c in (curr_codes - prev_codes):
                    row = df_curr[df_curr["code"].astype(str) == c].iloc[0]
                    shares = int(row["shares"] / 1000)
                    weight = float(row["weight"]) if "weight" in df_curr.columns else 0.0
                    new_buy.append({"name": clean_stock_name(row["name"]), "diff": shares, "weight": weight})
                    
                for c in (prev_codes - curr_codes):
                    row = df_prev[df_prev["code"].astype(str) == c].iloc[0]
                    shares = int(row["shares"] / 1000)
                    weight = float(row["weight"]) if "weight" in df_prev.columns else 0.0
                    sold_out.append({"name": clean_stock_name(row["name"]), "diff": shares, "weight": weight})
                    
                for c in common_codes:
                    row_curr = df_curr[df_curr["code"].astype(str) == c].iloc[0]
                    row_prev = df_prev[df_prev["code"].astype(str) == c].iloc[0]
                    diff = int(row_curr["shares"] / 1000) - int(row_prev["shares"] / 1000)
                    weight = float(row_curr["weight"]) if "weight" in df_curr.columns else 0.0
                    
                    if diff > 0:
                        increased.append({"name": clean_stock_name(row_curr["name"]), "diff": diff, "weight": weight})
                    elif diff < 0:
                        decreased.append({"name": clean_stock_name(row_curr["name"]), "diff": abs(diff), "weight": weight})
                        
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
    <title>ETF 籌碼決策終端</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=Noto+Sans+TC:wght@400;500;600;700;800&display=swap" rel="stylesheet">
    <script src="https://cdn.tailwindcss.com"></script>
    <style>
        /* 香檳金奢華配色體系 */
        :root {
            --bg-page: #fafaf5;
            --card-bg: #fdfdfa;
            --accent-gold: #c4a77d;
            --accent-gold-dark: #a68b63;
            --text-primary: #4a3a2a;
            --text-secondary: #8c7b6a;
            --border-light: #f3efea;
            --rose-accent: #dc2626;
            --emerald-accent: #059669;
        }

        body {
            background-color: var(--bg-page);
            color: var(--text-primary);
            font-family: "Inter", "Noto Sans TC", sans-serif;
            min-height: 100vh;
        }

        .tab-btn { transition: all 0.2s ease-in-out; white-space: nowrap; font-size: 0.95rem; }
        
        .tab-active {
            background: linear-gradient(135deg, #4a3a2a 0%, #2a1f14 100%);
            color: #ffffff;
            font-weight: 700;
            border-color: #2a1f14;
            box-shadow: 0 4px 6px -1px rgba(74, 58, 42, 0.2);
        }

        .tab-inactive {
            background-color: #ffffff;
            color: var(--text-secondary);
            border: 1px solid var(--border-light);
        }
        .tab-inactive:hover {
            background-color: #fffaf0;
            color: var(--text-primary);
            border-color: var(--accent-gold);
        }

        .card {
            background-color: var(--card-bg);
            border-radius: 16px;
            padding: 2.5rem;
            box-shadow: 0 10px 25px -5px rgba(196, 167, 125, 0.1), 0 8px 10px -6px rgba(196, 167, 125, 0.05);
            border: 1px solid var(--border-light);
        }

        select, input[type="text"] {
            background-color: #ffffff;
            color: var(--text-primary);
            border: 1px solid var(--border-light);
            outline: none;
            transition: border-color 0.2s;
        }
        select:hover, select:focus, input[type="text"]:focus {
            border-color: var(--accent-gold);
            background-color: #fffaf0;
        }
        
        .hide-scrollbar::-webkit-scrollbar { display: none; }
        .hide-scrollbar { -ms-overflow-style: none; scrollbar-width: none; }
        .data-row:hover { background-color: #fffaf0 !important; }
        
        .section-label {
            font-size: 1.05rem;
            font-weight: 700;
            letter-spacing: 0.05em;
        }
    </style>
</head>
<body class="pb-24 pt-8">
    <div class="max-w-5xl mx-auto px-4 md:px-6">
        
        <header class="mb-10">
            <h1 class="text-3xl md:text-4xl font-extrabold tracking-tight text-slate-800">ETF 籌碼決策終端</h1>
            <p class="text-slate-500 mt-2 text-sm md:text-base font-medium tracking-wide">主動式基金持股異動深度解析</p>
            <div class="h-1 w-24 bg-gradient-to-r from-[#c4a77d] to-[#e6d5b8] rounded-full mt-4"></div>
        </header>

        <div class="mb-8">
            <div id="etf-tabs" class="flex overflow-x-auto hide-scrollbar gap-2 pb-2 px-1"></div>
        </div>

        <div class="card mb-8">
            
            <div class="flex flex-col sm:flex-row sm:justify-between sm:items-center gap-4 pb-6 mb-8 border-b border-[#f3efea]">
                <div class="flex items-baseline gap-4">
                    <h2 id="current-etf-title" class="text-3xl font-extrabold text-[#4a3a2a] tracking-tight">載入中...</h2>
                    <span id="current-date-display" class="text-lg text-[#8c7b6a] font-medium tracking-wide"></span>
                </div>
                
                <div class="flex flex-wrap items-center gap-3">
                    <div class="relative flex items-center bg-white border border-[#f3efea] rounded-md px-3 py-2 focus-within:border-[#c4a77d] transition-colors shadow-sm w-full sm:w-auto">
                        <svg class="w-4 h-4 text-[#8c7b6a] mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"></path></svg>
                        <input type="text" id="search-input" onkeyup="handleSearch()" placeholder="個股雷達反查..." class="bg-transparent text-sm w-full sm:w-32 placeholder-[#b5a898] text-[#4a3a2a] font-medium">
                    </div>
                    
                    <div class="flex items-center bg-white border border-[#f3efea] rounded-md px-3 py-2 shadow-sm hover:border-[#c4a77d] transition-colors">
                        <select id="date-selector" onchange="changeDate()" class="bg-transparent text-sm font-bold text-[#4a3a2a] cursor-pointer pr-2 border-none p-0 m-0"></select>
                    </div>
                </div>
            </div>

            <div id="normal-view">
                <div class="mb-12">
                    <h3 class="section-label text-[#4a3a2a] mb-5 flex items-center">
                        <span class="w-1.5 h-5 bg-[#c4a77d] rounded-full mr-3"></span>
                        當日個股操作趨勢
                    </h3>
                    <div id="chart-container" class="w-full rounded-xl border border-[#f3efea] overflow-hidden bg-white shadow-sm">
                    </div>
                </div>

                <div>
                    <h3 class="section-label text-[#4a3a2a] mb-6 flex items-center border-b border-[#f3efea] pb-3">
                        <span class="w-1.5 h-5 bg-[#c4a77d] rounded-full mr-3"></span>
                        異動明細總覽
                    </h3>
                    
                    <div id="empty-state" class="text-center text-[#8c7b6a] py-16 bg-[#fafaf5] rounded-xl border border-dashed border-[#e6d5b8] hidden">
                        <p class="text-sm font-medium tracking-wide">當日無任何籌碼異動</p>
                    </div>
                    
                    <div class="grid grid-cols-1 md:grid-cols-2 gap-x-12 gap-y-10">
                        <div class="flex flex-col gap-8">
                            <div id="list-new" class="hidden">
                                <h4 class="text-[#dc2626] font-bold text-sm tracking-widest uppercase mb-3 border-l-2 border-[#dc2626] pl-2">新進場建倉</h4>
                                <div id="items-new" class="flex flex-col border-t border-[#f3efea] mt-1"></div>
                            </div>
                            <div id="list-inc" class="hidden">
                                <h4 class="text-[#dc2626] font-bold text-sm tracking-widest uppercase mb-3 border-l-2 border-[#f87171] pl-2">加碼買進</h4>
                                <div id="items-inc" class="flex flex-col border-t border-[#f3efea] mt-1"></div>
                            </div>
                        </div>

                        <div class="flex flex-col gap-8">
                            <div id="list-dec" class="hidden">
                                <h4 class="text-[#059669] font-bold text-sm tracking-widest uppercase mb-3 border-l-2 border-[#059669] pl-2">減碼調節</h4>
                                <div id="items-dec" class="flex flex-col border-t border-[#f3efea] mt-1"></div>
                            </div>
                            <div id="list-out" class="hidden">
                                <h4 class="text-[#8c7b6a] font-bold text-sm tracking-widest uppercase mb-3 border-l-2 border-[#8c7b6a] pl-2">完全出清</h4>
                                <div id="items-out" class="flex flex-col border-t border-[#f3efea] mt-1"></div>
                            </div>
                        </div>
                    </div>
                </div>
            </div>

            <div id="search-view" class="hidden">
                <h3 class="section-label text-[#4a3a2a] mb-6 flex items-center border-b border-[#f3efea] pb-3">
                    <span class="w-1.5 h-5 bg-[#c4a77d] rounded-full mr-3"></span>
                    雷達搜尋結果
                </h3>
                <div id="search-results-list" class="flex flex-col border-t border-[#f3efea] mt-1"></div>
            </div>

        </div>
    </div>

    <script>
        const db = __DB_JSON__;
        const availableDatesDesc = Object.keys(db).sort().reverse();
        const FAMILY_TAB = "全家族共識";
        
        let allETFs = new Set();
        Object.values(db).forEach(dateData => {
            Object.keys(dateData).forEach(etf => allETFs.add(etf));
        });
        
        let etfList = Array.from(allETFs).sort();
        etfList.unshift(FAMILY_TAB);
        
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
            handleSearch(); 
        }

        function selectETF(etf) {
            currentETF = etf;
            document.getElementById('search-input').value = ''; 
            renderTabs();
            handleSearch();
        }

        function renderTabs() {
            const container = document.getElementById('etf-tabs');
            container.innerHTML = '';
            etfList.forEach(etf => {
                const btn = document.createElement('button');
                const isActive = etf === currentETF;
                btn.className = `tab-btn px-5 py-2 rounded-full shadow-sm ${isActive ? 'tab-active' : 'tab-inactive'}`;
                btn.textContent = etf;
                btn.onclick = () => selectETF(etf);
                container.appendChild(btn);
            });
        }

        // 計算連續買賣超
        function getStreak(etf, stockName, startDate, type) {
            if (etf === FAMILY_TAB) return 0;
            let streak = 0;
            let startIndex = availableDatesDesc.indexOf(startDate);
            if (startIndex === -1) return 0;

            for (let i = startIndex; i < availableDatesDesc.length; i++) {
                const d = availableDatesDesc[i];
                const data = db[d] && db[d][etf];
                if (!data) break;

                let found = false;
                if (type === 'buy') {
                    found = [...(data.new_buy||[]), ...(data.increased||[])].some(x => x.name === stockName);
                } else {
                    found = [...(data.decreased||[]), ...(data.sold_out||[])].some(x => x.name === stockName);
                }

                if (found) streak++;
                else break;
            }
            return streak;
        }

        function updateDashboard() {
            document.getElementById('current-etf-title').textContent = currentETF;
            document.getElementById('current-date-display').textContent = currentDate;
            
            const dataToday = db[currentDate] || {};
            let etfData = { new_buy: [], increased: [], decreased: [], sold_out: [] };
            
            // 全家族共識聚合邏輯
            if (currentETF === FAMILY_TAB) {
                let agg = {};
                Object.keys(dataToday).forEach(etf => {
                    const d = dataToday[etf];
                    [...(d.new_buy||[]), ...(d.increased||[])].forEach(i => {
                        if(!agg[i.name]) agg[i.name] = { diff: 0 };
                        agg[i.name].diff += i.diff;
                    });
                    [...(d.decreased||[]), ...(d.sold_out||[])].forEach(i => {
                        if(!agg[i.name]) agg[i.name] = { diff: 0 };
                        agg[i.name].diff -= i.diff;
                    });
                });
                
                Object.keys(agg).forEach(name => {
                    if (agg[name].diff > 0) etfData.increased.push({ name: name, diff: agg[name].diff, weight: 0 });
                    else if (agg[name].diff < 0) etfData.decreased.push({ name: name, diff: Math.abs(agg[name].diff), weight: 0 });
                });
                etfData.increased.sort((a,b) => b.diff - a.diff);
                etfData.decreased.sort((a,b) => b.diff - a.diff);
            } else {
                etfData = dataToday[currentETF] || { new_buy: [], increased: [], decreased: [], sold_out: [] };
            }

            const emptyState = document.getElementById('empty-state');
            const sections = ['new', 'inc', 'dec', 'out'];
            const chartContainer = document.getElementById('chart-container');
            
            if(!etfData.new_buy.length && !etfData.increased.length && !etfData.decreased.length && !etfData.sold_out.length) {
                emptyState.classList.remove('hidden');
                sections.forEach(s => document.getElementById(`list-${s}`).classList.add('hidden'));
                chartContainer.innerHTML = '<div class="text-[#8c7b6a] py-10 text-center text-sm font-medium">本日無操作資料</div>';
                return;
            }

            emptyState.classList.add('hidden');

            let formattedItems = [];
            [...(etfData.new_buy || []), ...(etfData.increased || [])].forEach(i => { formattedItems.push({ name: i.name, trueVal: i.diff }); });
            [...(etfData.decreased || []), ...(etfData.sold_out || [])].forEach(i => { formattedItems.push({ name: i.name, trueVal: -i.diff }); });
            formattedItems.sort((a, b) => b.trueVal - a.trueVal);
            
            const maxVal = Math.max(...formattedItems.map(i => Math.abs(i.trueVal)));

            // 繪製圖表
            let chartHTML = '<div class="flex flex-col">';
            formattedItems.forEach((item, index) => {
                const isBuy = item.trueVal > 0;
                const valStr = isBuy ? `+${item.trueVal.toLocaleString()}` : item.trueVal.toLocaleString();
                const textColor = isBuy ? 'text-[#dc2626]' : 'text-[#059669]';
                const barColor = isBuy ? 'bg-[#dc2626]' : 'bg-[#059669]';
                const bgClass = index % 2 === 0 ? 'bg-white' : 'bg-[#fafaf5]'; 
                const widthPct = Math.max((Math.abs(item.trueVal) / maxVal) * 100, 1);

                chartHTML += `
                <div class="data-row flex items-center py-3 px-5 ${bgClass} border-b border-[#f3efea] last:border-0 transition-colors">
                    <div class="w-36 md:w-48 flex-shrink-0 flex justify-between items-center pr-4 border-r border-[#e6d5b8]">
                        <span class="font-bold text-[#4a3a2a] text-[14px] truncate text-left">${item.name}</span>
                        <span class="font-mono font-bold ${textColor} text-[14px] text-right">${valStr}</span>
                    </div>
                    <div class="flex-grow flex items-center pl-5">
                        <div class="w-full bg-[#f3efea] rounded-sm h-3 overflow-hidden opacity-90">
                            <div class="${barColor} h-full rounded-sm" style="width: ${widthPct}%"></div>
                        </div>
                    </div>
                </div>`;
            });
            chartHTML += '</div>';
            chartContainer.innerHTML = chartHTML;

            // 繪製清單 (整合權重與連續動作)
            const fillSection = (sectionId, items, colorClass, sign, type) => {
                const wrap = document.getElementById(`list-${sectionId}`);
                const list = document.getElementById(`items-${sectionId}`);
                list.innerHTML = '';
                
                if(items && items.length > 0) {
                    wrap.classList.remove('hidden');
                    items.forEach(i => {
                        let valStr = sectionId === 'out' ? `出清 ${i.diff.toLocaleString()}` : `${sign}${i.diff.toLocaleString()}`;
                        
                        let tagsHTML = '';
                        if (currentETF !== FAMILY_TAB) {
                            if (i.weight && i.weight > 0) {
                                tagsHTML += `<span class="ml-2 text-[#a68b63] text-[11px] font-medium tracking-wide">(${i.weight.toFixed(2)}%)</span>`;
                            }
                            
                            const streak = getStreak(currentETF, i.name, currentDate, type);
                            if (streak >= 3) {
                                const sc = type === 'buy' ? 'text-[#dc2626] bg-[#fef2f2] border-[#fecaca]' : 'text-[#059669] bg-[#ecfdf5] border-[#a7f3d0]';
                                const st = type === 'buy' ? '連買' : '連賣';
                                tagsHTML += `<span class="ml-2 px-1.5 py-[1px] border rounded-sm text-[10px] font-bold ${sc}">${st} ${streak} 日</span>`;
                            }
                        }

                        list.innerHTML += `
                        <div class="flex justify-between items-center py-2 px-2 border-b border-[#f3efea] last:border-0 hover:bg-[#fffaf0] transition-colors">
                            <div class="flex items-center">
                                <span class="text-[14px] font-bold text-[#4a3a2a]">${i.name}</span>
                                ${tagsHTML}
                            </div>
                            <span class="${colorClass} text-[13px] font-mono font-bold bg-white px-2 py-0.5 rounded shadow-sm border border-[#f3efea]">${valStr}</span>
                        </div>`;
                    });
                } else {
                    wrap.classList.add('hidden');
                }
            };

            fillSection('new', etfData.new_buy, 'text-[#dc2626]', '+', 'buy');
            fillSection('inc', etfData.increased, 'text-[#dc2626]', '+', 'buy');
            fillSection('dec', etfData.decreased, 'text-[#059669]', '-', 'sell');
            fillSection('out', etfData.sold_out, 'text-[#8c7b6a]', '', 'sell');
        }

        // 個股雷達搜尋
        function handleSearch() {
            const val = document.getElementById('search-input').value.trim().toLowerCase();
            const normalView = document.getElementById('normal-view');
            const searchView = document.getElementById('search-view');
            
            if (!val) {
                normalView.classList.remove('hidden');
                searchView.classList.add('hidden');
                updateDashboard(); 
                return;
            }

            normalView.classList.add('hidden');
            searchView.classList.remove('hidden');

            const resultsContainer = document.getElementById('search-results-list');
            resultsContainer.innerHTML = '';

            const dataToday = db[currentDate] || {};
            let found = false;

            Object.keys(dataToday).forEach(etf => {
                if (etf === FAMILY_TAB) return; 
                const d = dataToday[etf];
                let actions = [];
                [...(d.new_buy||[])].forEach(i => { if(i.name.toLowerCase().includes(val)) actions.push({act: '新進場', diff: i.diff, sign: '+'}); });
                [...(d.increased||[])].forEach(i => { if(i.name.toLowerCase().includes(val)) actions.push({act: '加碼', diff: i.diff, sign: '+'}); });
                [...(d.decreased||[])].forEach(i => { if(i.name.toLowerCase().includes(val)) actions.push({act: '減碼', diff: i.diff, sign: '-'}); });
                [...(d.sold_out||[])].forEach(i => { if(i.name.toLowerCase().includes(val)) actions.push({act: '出清', diff: i.diff, sign: '-'}); });

                actions.forEach(a => {
                    found = true;
                    const isBuy = a.sign === '+';
                    const colorClass = isBuy ? 'text-[#dc2626]' : 'text-[#059669]';
                    const bgClass = isBuy ? 'bg-[#fef2f2] border-[#fecaca]' : 'bg-[#ecfdf5] border-[#a7f3d0]';
                    const actStyle = a.act === '出清' ? 'text-[#8c7b6a] bg-[#f8fafc] border-[#e2e8f0]' : `${colorClass} ${bgClass}`;

                    resultsContainer.innerHTML += `
                    <div class="flex justify-between items-center py-3 px-4 border-b border-[#f3efea] hover:bg-[#fffaf0] transition-colors">
                        <div class="flex items-center gap-3">
                            <span class="font-bold text-[#4a3a2a] text-[14px] w-16">${etf}</span>
                            <span class="px-1.5 py-[1px] rounded border text-[11px] font-bold ${actStyle}">${a.act}</span>
                        </div>
                        <span class="${colorClass} font-mono font-bold text-[14px] bg-white px-2 py-0.5 rounded shadow-sm border border-[#f3efea]">${a.sign}${a.diff.toLocaleString()} 張</span>
                    </div>`;
                });
            });

            if (!found) {
                resultsContainer.innerHTML = '<div class="py-12 text-center text-[#8c7b6a] text-sm font-medium">當日無此股票的操作紀錄</div>';
            }
        }

        window.onload = init;
    </script>
</body>
</html>"""

def main():
    print("🚀 開始產出 Web Dashboard (香檳金彭博終端版)...")
    db = process_all_data()
    
    json_str = json.dumps(db, ensure_ascii=False)
    final_html = HTML_TEMPLATE.replace("__DB_JSON__", json_str)
    
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(final_html)
        
    print(f"✅ 成功產出 {OUTPUT_FILE}")

if __name__ == "__main__":
    main()