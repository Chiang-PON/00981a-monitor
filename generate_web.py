"""generate_web.py — 自動生成靜態網頁儀表板 (Cyber-Terminal 戰情室版)

讀取 history/ 下的 CSV 檔案，計算每日籌碼異動。
- 視覺全面重構：致敬 WorldMonitor / 彭博終端機，採用純黑底色與霓虹發光特效。
- 導入 JetBrains Mono 等寬字體，強化科技感與數據對齊。
- 加入 LIVE 閃爍指示燈與即時終端機時間，提升沉浸式體驗。
- 無 Emoji，介面銳利化 (移除過度圓角)，呈現駭客級高質感。
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
<html lang="zh-TW" class="dark">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>MONITOR TERMINAL</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;700;800&family=Noto+Sans+TC:wght@400;500;700;900&display=swap" rel="stylesheet">
    <script src="https://cdn.tailwindcss.com"></script>
    <style>
        /* 💎 Cyber-Terminal 炫砲配色體系 */
        :root {
            --bg-base: #050505;
            --bg-panel: #0d0d0d;
            --bg-panel-hover: #141414;
            --border-dim: #262626;
            --text-main: #f4f4f5;
            --text-dim: #84848f;
            
            /* 霓虹特效色 */
            --neon-buy: #00ff9d; /* 科技螢光綠 */
            --neon-sell: #ff2a5f; /* 警示螢光紅 */
            --neon-blue: #00f0ff; /* 賽博龐克藍 */
        }

        body {
            background-color: var(--bg-base);
            color: var(--text-main);
            font-family: "Noto Sans TC", sans-serif;
            min-height: 100vh;
            /* 微弱的掃描線背景增加科技感 */
            background-image: linear-gradient(rgba(255, 255, 255, 0.02) 1px, transparent 1px);
            background-size: 100% 4px;
        }

        /* 強制數字與英文使用等寬字體 */
        .font-mono { font-family: "JetBrains Mono", monospace; }

        /* 💎 面板與框線 */
        .panel {
            background-color: var(--bg-panel);
            border: 1px solid var(--border-dim);
            box-shadow: 0 8px 32px rgba(0, 0, 0, 0.5);
        }

        /* 💎 發光文字特效 */
        .glow-buy { 
            color: var(--neon-buy); 
            text-shadow: 0 0 10px rgba(0, 255, 157, 0.3); 
        }
        .glow-sell { 
            color: var(--neon-sell); 
            text-shadow: 0 0 10px rgba(255, 42, 95, 0.3); 
        }
        .glow-blue { 
            color: var(--neon-blue); 
            text-shadow: 0 0 10px rgba(0, 240, 255, 0.3); 
        }

        /* 💎 發光資料條 */
        .bar-buy { 
            background-color: var(--neon-buy); 
            box-shadow: 0 0 12px rgba(0, 255, 157, 0.4); 
        }
        .bar-sell { 
            background-color: var(--neon-sell); 
            box-shadow: 0 0 12px rgba(255, 42, 95, 0.4); 
        }

        /* 💎 終端機按鈕 */
        .tab-btn {
            transition: all 0.2s;
            white-space: nowrap;
            font-size: 0.9rem;
            letter-spacing: 0.05em;
            text-transform: uppercase;
        }
        .tab-active {
            background: #1a1a1a;
            color: var(--neon-blue);
            border: 1px solid var(--neon-blue);
            box-shadow: 0 0 15px rgba(0, 240, 255, 0.15), inset 0 0 10px rgba(0, 240, 255, 0.05);
        }
        .tab-inactive {
            background-color: var(--bg-base);
            color: var(--text-dim);
            border: 1px solid var(--border-dim);
        }
        .tab-inactive:hover {
            border-color: #555;
            color: #fff;
        }

        /* 表單元素重置 */
        select, input[type="text"] {
            background-color: var(--bg-base);
            color: var(--text-main);
            border: 1px solid var(--border-dim);
            outline: none;
            transition: border-color 0.2s;
        }
        select:hover, select:focus, input[type="text"]:focus {
            border-color: var(--neon-blue);
            box-shadow: 0 0 8px rgba(0, 240, 255, 0.2);
        }
        
        .hide-scrollbar::-webkit-scrollbar { display: none; }
        .hide-scrollbar { -ms-overflow-style: none; scrollbar-width: none; }
        
        /* 懸停效果 */
        .data-row:hover { background-color: var(--bg-panel-hover) !important; }

        /* 呼吸燈動畫 */
        @keyframes pulse-dot {
            0% { transform: scale(0.95); box-shadow: 0 0 0 0 rgba(0, 255, 157, 0.7); }
            70% { transform: scale(1); box-shadow: 0 0 0 6px rgba(0, 255, 157, 0); }
            100% { transform: scale(0.95); box-shadow: 0 0 0 0 rgba(0, 255, 157, 0); }
        }
        .live-dot {
            height: 8px; width: 8px;
            background-color: var(--neon-buy);
            border-radius: 50%;
            display: inline-block;
            animation: pulse-dot 2s infinite;
        }
    </style>
</head>
<body class="pb-24 pt-6">

    <nav class="w-full border-b border-[#262626] bg-[#050505] fixed top-0 z-50 flex justify-between items-center px-4 md:px-8 py-3">
        <div class="flex items-center gap-4">
            <span class="live-dot"></span>
            <span class="font-mono text-sm tracking-widest font-bold glow-buy">SYSTEM.LIVE</span>
            <span class="text-[#444] hidden md:inline">|</span>
            <h1 class="text-lg font-black tracking-[0.2em] text-white">MONITOR <span class="text-[#444] font-mono text-xs">v3.0</span></h1>
        </div>
        <div class="flex items-center gap-4 font-mono text-xs text-[#84848f]">
            <span id="live-clock" class="hidden md:inline">Loading...</span>
        </div>
    </nav>

    <div class="max-w-6xl mx-auto px-4 md:px-6 mt-20">

        <div class="mb-6 flex overflow-x-auto hide-scrollbar gap-2 pb-2">
            <div id="etf-tabs" class="flex gap-2"></div>
        </div>

        <div class="panel p-5 md:p-8">
            
            <div class="flex flex-col sm:flex-row sm:justify-between sm:items-end gap-4 pb-5 mb-8 border-b border-[#262626]">
                <div class="flex flex-col gap-1">
                    <span class="font-mono text-xs text-[#555] tracking-widest uppercase">TARGET_ASSET</span>
                    <div class="flex items-baseline gap-3">
                        <h2 id="current-etf-title" class="text-3xl md:text-4xl font-black text-white tracking-wider">---</h2>
                        <span id="current-date-display" class="font-mono text-lg glow-blue"></span>
                    </div>
                </div>
                
                <div class="flex flex-wrap items-center gap-3">
                    <div class="relative flex items-center bg-[#0a0a0a] border border-[#262626] px-3 py-1.5 focus-within:border-[#00f0ff] transition-colors">
                        <span class="text-[#555] font-mono mr-2">></span>
                        <input type="text" id="search-input" onkeyup="handleSearch()" placeholder="SEARCH_TICKER..." class="bg-transparent text-sm w-full sm:w-36 font-mono placeholder-[#444] text-[#fff]">
                    </div>
                    
                    <div class="flex items-center bg-[#0a0a0a] border border-[#262626] px-2 py-1.5 hover:border-[#555] transition-colors">
                        <select id="date-selector" onchange="changeDate()" class="bg-transparent text-sm font-mono text-[#fff] cursor-pointer pr-2 border-none appearance-none"></select>
                    </div>
                </div>
            </div>

            <div id="normal-view">
                
                <div class="mb-12">
                    <h3 class="font-mono text-xs text-[#84848f] tracking-[0.2em] mb-4 flex items-center">
                        <span class="text-[#444] mr-2">///</span> VOLUME_FLOW
                    </h3>
                    <div id="chart-container" class="w-full bg-[#0a0a0a] border border-[#1a1a1a]">
                        </div>
                </div>

                <div>
                    <h3 class="font-mono text-xs text-[#84848f] tracking-[0.2em] mb-4 flex items-center border-b border-[#262626] pb-2">
                        <span class="text-[#444] mr-2">///</span> TICKER_BREAKDOWN
                    </h3>
                    
                    <div id="empty-state" class="text-center font-mono text-[#555] py-12 bg-[#0a0a0a] border border-dashed border-[#262626] hidden">
                        > NO_DATA_DETECTED_
                    </div>
                    
                    <div class="grid grid-cols-1 md:grid-cols-2 gap-x-8 gap-y-10">
                        <div class="flex flex-col gap-8">
                            <div id="list-new" class="hidden">
                                <h4 class="font-mono glow-buy text-sm tracking-widest mb-3 border-l-2 border-[var(--neon-buy)] pl-2">INITIATE_POSITION</h4>
                                <div id="items-new" class="flex flex-col border-t border-[#1a1a1a] mt-1"></div>
                            </div>
                            <div id="list-inc" class="hidden">
                                <h4 class="font-mono glow-buy text-sm tracking-widest mb-3 border-l-2 border-[var(--neon-buy)] pl-2">ACCUMULATE</h4>
                                <div id="items-inc" class="flex flex-col border-t border-[#1a1a1a] mt-1"></div>
                            </div>
                        </div>

                        <div class="flex flex-col gap-8">
                            <div id="list-dec" class="hidden">
                                <h4 class="font-mono glow-sell text-sm tracking-widest mb-3 border-l-2 border-[var(--neon-sell)] pl-2">REDUCE_EXPOSURE</h4>
                                <div id="items-dec" class="flex flex-col border-t border-[#1a1a1a] mt-1"></div>
                            </div>
                            <div id="list-out" class="hidden">
                                <h4 class="font-mono text-[#84848f] text-sm tracking-widest mb-3 border-l-2 border-[#555] pl-2">LIQUIDATE</h4>
                                <div id="items-out" class="flex flex-col border-t border-[#1a1a1a] mt-1"></div>
                            </div>
                        </div>
                    </div>
                </div>
            </div>

            <div id="search-view" class="hidden">
                <h3 class="font-mono text-xs text-[#84848f] tracking-[0.2em] mb-4 flex items-center border-b border-[#262626] pb-2">
                    <span class="text-[#444] mr-2">///</span> RADAR_SCAN_RESULTS
                </h3>
                <div id="search-results-list" class="flex flex-col border-t border-[#1a1a1a] mt-1"></div>
            </div>

        </div>
    </div>

    <script>
        // 💎 即時終端機時間
        function updateClock() {
            const now = new Date();
            const utc = now.toISOString().replace('T', ' ').substring(0, 19) + ' UTC';
            document.getElementById('live-clock').textContent = utc;
        }
        setInterval(updateClock, 1000);
        updateClock();

        const db = __DB_JSON__;
        const availableDatesDesc = Object.keys(db).sort().reverse();
        const FAMILY_TAB = "GLOBAL_CONSENSUS"; // 全家族共識改用英文代號更搭
        
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
                document.body.innerHTML = "<div class='text-center mt-20 font-mono text-[#555]'>> ERROR: NO_HISTORY_DATA_FOUND</div>";
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
                // 銳利邊角 (rounded-none 或 sm)
                btn.className = `tab-btn px-4 py-1.5 font-mono ${isActive ? 'tab-active' : 'tab-inactive'}`;
                // 特殊替換文字顯示
                btn.textContent = etf === FAMILY_TAB ? '[ CONSENSUS ]' : etf;
                btn.onclick = () => selectETF(etf);
                container.appendChild(btn);
            });
        }

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
            // 標題顯示處理
            const displayTitle = currentETF === FAMILY_TAB ? 'GLOBAL_CONSENSUS' : currentETF;
            document.getElementById('current-etf-title').textContent = displayTitle;
            document.getElementById('current-date-display').textContent = currentDate;
            
            const dataToday = db[currentDate] || {};
            let etfData = { new_buy: [], increased: [], decreased: [], sold_out: [] };
            
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
                chartContainer.innerHTML = '<div class="font-mono text-[#555] py-8 text-center text-xs">> SIGNAL_LOST</div>';
                return;
            }

            emptyState.classList.add('hidden');

            let formattedItems = [];
            [...(etfData.new_buy || []), ...(etfData.increased || [])].forEach(i => { formattedItems.push({ name: i.name, trueVal: i.diff }); });
            [...(etfData.decreased || []), ...(etfData.sold_out || [])].forEach(i => { formattedItems.push({ name: i.name, trueVal: -i.diff }); });
            formattedItems.sort((a, b) => b.trueVal - a.trueVal);
            
            const maxVal = Math.max(...formattedItems.map(i => Math.abs(i.trueVal)));

            // 💎 繪製終端機風格資料條
            let chartHTML = '<div class="flex flex-col">';
            formattedItems.forEach((item, index) => {
                const isBuy = item.trueVal > 0;
                const valStr = isBuy ? `+${item.trueVal.toLocaleString()}` : item.trueVal.toLocaleString();
                const textColor = isBuy ? 'glow-buy' : 'glow-sell';
                const barClass = isBuy ? 'bar-buy' : 'bar-sell';
                // 移除斑馬紋，改用純黑與極暗灰交錯
                const bgClass = index % 2 === 0 ? 'bg-[#0d0d0d]' : 'bg-[#0a0a0a]'; 
                const widthPct = Math.max((Math.abs(item.trueVal) / maxVal) * 100, 1);

                chartHTML += `
                <div class="data-row flex items-center py-2 px-4 ${bgClass} border-b border-[#1a1a1a] last:border-0 transition-colors">
                    <div class="w-36 md:w-48 flex-shrink-0 flex justify-between items-center pr-4 border-r border-[#262626]">
                        <span class="font-bold text-white text-[14px] truncate text-left">${item.name}</span>
                        <span class="font-mono font-bold ${textColor} text-[13px] text-right">${valStr}</span>
                    </div>
                    <div class="flex-grow flex items-center pl-4">
                        <div class="w-full bg-[#111] h-[6px] overflow-hidden">
                            <div class="${barClass} h-full" style="width: ${widthPct}%"></div>
                        </div>
                    </div>
                </div>`;
            });
            chartHTML += '</div>';
            chartContainer.innerHTML = chartHTML;

            // 💎 繪製清單
            const fillSection = (sectionId, items, colorClass, sign, type) => {
                const wrap = document.getElementById(`list-${sectionId}`);
                const list = document.getElementById(`items-${sectionId}`);
                list.innerHTML = '';
                
                if(items && items.length > 0) {
                    wrap.classList.remove('hidden');
                    items.forEach(i => {
                        let valStr = sectionId === 'out' ? `LIQ ${i.diff.toLocaleString()}` : `${sign}${i.diff.toLocaleString()}`;
                        
                        let tagsHTML = '';
                        if (currentETF !== FAMILY_TAB) {
                            if (i.weight && i.weight > 0) {
                                tagsHTML += `<span class="ml-2 font-mono text-[#555] text-[10px]">W:${i.weight.toFixed(2)}%</span>`;
                            }
                            
                            const streak = getStreak(currentETF, i.name, currentDate, type);
                            if (streak >= 3) {
                                const sc = type === 'buy' ? 'text-[var(--neon-buy)] border-[var(--neon-buy)]' : 'text-[var(--neon-sell)] border-[var(--neon-sell)]';
                                tagsHTML += `<span class="ml-2 px-1 border font-mono text-[9px] uppercase ${sc}">STRK:${streak}</span>`;
                            }
                        }

                        list.innerHTML += `
                        <div class="flex justify-between items-center py-2 border-b border-[#1a1a1a] last:border-0 hover:bg-[#111] px-2 -mx-2 transition-colors">
                            <div class="flex items-center">
                                <span class="text-[14px] font-bold text-white">${i.name}</span>
                                ${tagsHTML}
                            </div>
                            <span class="${colorClass} text-[13px] font-mono font-bold">${valStr}</span>
                        </div>`;
                    });
                } else {
                    wrap.classList.add('hidden');
                }
            };

            fillSection('new', etfData.new_buy, 'glow-buy', '+', 'buy');
            fillSection('inc', etfData.increased, 'glow-buy', '+', 'buy');
            fillSection('dec', etfData.decreased, 'glow-sell', '-', 'sell');
            fillSection('out', etfData.sold_out, 'text-[#666]', '', 'sell');
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
                [...(d.new_buy||[])].forEach(i => { if(i.name.toLowerCase().includes(val)) actions.push({act: 'INIT', diff: i.diff, sign: '+'}); });
                [...(d.increased||[])].forEach(i => { if(i.name.toLowerCase().includes(val)) actions.push({act: 'ACC', diff: i.diff, sign: '+'}); });
                [...(d.decreased||[])].forEach(i => { if(i.name.toLowerCase().includes(val)) actions.push({act: 'RED', diff: i.diff, sign: '-'}); });
                [...(d.sold_out||[])].forEach(i => { if(i.name.toLowerCase().includes(val)) actions.push({act: 'LIQ', diff: i.diff, sign: '-'}); });

                actions.forEach(a => {
                    found = true;
                    const isBuy = a.sign === '+';
                    const colorClass = isBuy ? 'glow-buy' : 'glow-sell';
                    const actStyle = a.act === 'LIQ' ? 'text-[#555] border-[#444]' : `border border-current ${colorClass}`;

                    resultsContainer.innerHTML += `
                    <div class="flex justify-between items-center py-2.5 border-b border-[#1a1a1a] hover:bg-[#111] px-2 -mx-2 transition-colors">
                        <div class="flex items-center gap-3">
                            <span class="font-bold text-white text-[14px] w-16 font-mono">${etf}</span>
                            <span class="px-1 py-[1px] text-[10px] font-mono ${actStyle}">${a.act}</span>
                        </div>
                        <span class="${colorClass} font-mono font-bold text-[14px]">${a.sign}${a.diff.toLocaleString()}</span>
                    </div>`;
                });
            });

            if (!found) {
                resultsContainer.innerHTML = '<div class="py-12 text-center text-[#555] font-mono text-xs">> RADAR_EMPTY</div>';
            }
        }

        window.onload = init;
    </script>
</body>
</html>"""

def main():
    print("🚀 開始產出 Web Dashboard (Cyber-Terminal 版)...")
    db = process_all_data()
    
    json_str = json.dumps(db, ensure_ascii=False)
    final_html = HTML_TEMPLATE.replace("__DB_JSON__", json_str)
    
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(final_html)
        
    print(f"✅ 成功產出 {OUTPUT_FILE}")

if __name__ == "__main__":
    main()