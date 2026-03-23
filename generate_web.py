"""generate_web.py - ETF Monitor Terminal v7.0 (Broker-Grade UI + Multi-Day Aggregation)

整合外資核心邏輯：
1. 券商級 UI：下拉選單、天數聚合 (1/5/10/20/30日)、金額/張數切換、買超/賣超排行表。
2. 多日籌碼動態加總：前端 aggregateData() 引擎累加 N 日 diff 與 amount。
3. AI_AGENT 引擎：前端直接呼叫 OpenAI gpt-4o，API Key 存於 localStorage。
4. 即時股價注入、台股紅綠色彩、Light/Dark 雙軌主題保留。
"""

import os
import glob
import re
import json
import pandas as pd
from datetime import datetime

HISTORY_DIR = "history"
OUTPUT_FILE = "index.html"

SECTOR_MAP = {
    "台積電": "半導體", "聯發科": "半導體", "京元電": "半導體", "日月光投控": "半導體", "瑞昱": "半導體", "聯電": "半導體", "世芯-KY": "半導體", "力旺": "半導體", "聯詠": "半導體", "南亞科": "半導體", "欣銓": "半導體", "精測": "半導體", "穎崴": "半導體", "旺矽": "半導體", "群聯": "半導體",
    "鴻海": "電腦週邊", "廣達": "電腦週邊", "緯創": "電腦週邊", "緯穎": "電腦週邊", "技嘉": "電腦週邊", "華碩": "電腦週邊", "英業達": "電腦週邊", "仁寶": "電腦週邊", "奇鋐": "電腦週邊", "雙鴻": "電腦週邊", "勤誠": "電腦週邊", "富世達": "電腦週邊",
    "台達電": "電子零組件", "健策": "電子零組件", "欣興": "電子零組件", "南電": "電子零組件", "金像電": "電子零組件", "國巨": "電子零組件", "台光電": "電子零組件", "台燿": "電子零組件", "聯茂": "電子零組件", "建準": "電子零組件", "川湖": "電子零組件", "凡甲": "電子零組件",
    "智邦": "通信網路", "華星光": "通信網路", "前鼎": "通信網路", "兆赫": "通信網路", "光紅建聖": "通信網路", "啟碁": "通信網路",
    "中信金": "金融保險", "富邦金": "金融保險", "國泰金": "金融保險", "兆豐金": "金融保險", "玉山金": "金融保險", "元大金": "金融保險", "開發金": "金融保險", "台新金": "金融保險", "華南金": "金融保險",
    "華城": "電機機械", "士電": "電機機械", "中興電": "電機機械", "亞力": "電機機械", "亞德客-KY": "電機機械",
    "長榮": "航運", "華航": "航運", "陽明": "航運", "萬海": "航運",
    "寶雅": "貿易百貨", "統一超": "貿易百貨", "全家": "貿易百貨",
    "鈊象": "文化創意", "大成鋼": "鋼鐵", "聚陽": "紡織纖維", "達興材": "化學"
}

NAME_REPLACEMENTS = {
    "台灣積體電路製造": "台積電", "鴻海精密工業": "鴻海", "台達電子工業": "台達電", "緯穎科技服務": "緯穎", "聯發科技": "聯發科", "金像電子（股）公司": "金像電", "金像電子": "金像電", "廣達電腦": "廣達", "智邦科技": "智邦", "奇鋐科技": "奇鋐", "鴻勁精密": "鴻勁", "台燿科技": "台燿", "群聯電子": "群聯", "健策精密工業": "健策", "旺矽科技": "旺矽", "勤誠興業": "勤誠", "中國信託金融控股": "中信金", "京元電子": "京元電", "緯創資通": "緯創", "文曄科技": "文曄", "欣銓科技": "欣銓", "致伸科技": "致伸", "南亞科技": "南亞科", "健鼎科技": "健鼎", "凡甲科技": "凡甲", "崇越科技": "崇越", "瑞昱半導體": "瑞昱", "致茂電子": "致茂", "鈊象電子": "鈊象", "高力熱處理工業": "高力", "台光電子材料": "台光電", "華城電機": "華城", "穎崴科技": "穎崴", "中華精測科技": "精測", "川湖科技": "川湖", "亞德客國際集團": "亞德客-KY", "玉山金融控股": "玉山金", "富邦金融控股": "富邦金", "華邦電子": "華邦電", "大成不銹鋼工業": "大成鋼", "聚陽實業": "聚陽", "達興材料": "達興材", "技嘉科技": "技嘉", "貿聯控股（BizLink Holding In": "貿聯-KY", "寶雅國際": "寶雅", "創意電子": "創意", "光紅建聖": "光紅建聖", "亞德客": "亞德客-KY"
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
    if not all_files: return {}

    file_map = {}
    for f in all_files:
        basename = os.path.basename(f).replace(".csv", "")
        parts = basename.split("_")
        if len(parts) >= 2:
            etf_code = parts[0]
            date_str = parts[1]
            if etf_code not in file_map: file_map[etf_code] = []
            file_map[etf_code].append((date_str, f))

    database = {}
    
    for etf_code, files in file_map.items():
        files.sort(key=lambda x: x[0])
        
        for i in range(1, len(files)):
            prev_date, prev_file = files[i-1]
            curr_date, curr_file = files[i]
            
            if curr_date not in database: database[curr_date] = {}
                
            try:
                df_prev = pd.read_csv(prev_file, dtype={"code": str})
                df_curr = pd.read_csv(curr_file, dtype={"code": str})
                for df in (df_prev, df_curr):
                    if "price" not in df.columns: df["price"] = 0.0
                    if "weight" not in df.columns: df["weight"] = 0.0
                
                prev_codes = set(df_prev["code"].astype(str))
                curr_codes = set(df_curr["code"].astype(str))
                common_codes = prev_codes & curr_codes
                
                new_buy, sold_out, increased, decreased = [], [], [], []
                
                def extract_info(row, df_ref):
                    shares = int(row["shares"] / 1000)
                    weight = 0.0
                    if "weight" in df_ref.columns and pd.notna(row.get("weight")):
                        try: weight = float(row["weight"])
                        except: pass
                    price = 0.0
                    if "price" in df_ref.columns and pd.notna(row.get("price")):
                        try: price = float(row["price"])
                        except: pass
                    return shares, weight, price

                for c in (curr_codes - prev_codes):
                    row = df_curr[df_curr["code"].astype(str) == c].iloc[0]
                    shares, weight, price = extract_info(row, df_curr)
                    c_name = clean_stock_name(row["name"])
                    amount_10k = (shares * price) / 10 if price > 0 else 0
                    new_buy.append({"name": c_name, "code": str(c), "diff": shares, "weight": weight, "w_diff": weight, "amount": amount_10k, "sector": SECTOR_MAP.get(c_name, "其他")})
                    
                for c in (prev_codes - curr_codes):
                    row = df_prev[df_prev["code"].astype(str) == c].iloc[0]
                    shares, weight, price = extract_info(row, df_prev)
                    c_name = clean_stock_name(row["name"])
                    amount_10k = (shares * price) / 10 if price > 0 else 0
                    sold_out.append({"name": c_name, "code": str(c), "diff": shares, "weight": 0.0, "w_diff": -weight, "amount": amount_10k, "sector": SECTOR_MAP.get(c_name, "其他")})
                    
                for c in common_codes:
                    row_curr = df_curr[df_curr["code"].astype(str) == c].iloc[0]
                    row_prev = df_prev[df_prev["code"].astype(str) == c].iloc[0]
                    
                    shares_curr, weight_curr, price_curr = extract_info(row_curr, df_curr)
                    shares_prev, weight_prev, _ = extract_info(row_prev, df_prev)
                    
                    diff = shares_curr - shares_prev
                    w_diff = weight_curr - weight_prev
                    c_name = clean_stock_name(row_curr["name"])
                    amount_10k = (abs(diff) * price_curr) / 10 if price_curr > 0 else 0
                    sector = SECTOR_MAP.get(c_name, "其他")
                    
                    if diff > 0:
                        increased.append({"name": c_name, "code": str(c), "diff": diff, "weight": weight_curr, "w_diff": w_diff, "amount": amount_10k, "sector": sector})
                    elif diff < 0:
                        decreased.append({"name": c_name, "code": str(c), "diff": abs(diff), "weight": weight_curr, "w_diff": w_diff, "amount": amount_10k, "sector": sector})
                        
                def sort_key(x):
                    return (-x["diff"], -x.get("amount", 0))
                new_buy.sort(key=sort_key)
                sold_out.sort(key=sort_key)
                increased.sort(key=sort_key)
                decreased.sort(key=sort_key)
                
                database[curr_date][etf_code] = {
                    "new_buy": new_buy, "sold_out": sold_out,
                    "increased": increased, "decreased": decreased
                }
            except Exception as e:
                print(f"處理 {curr_file} 失敗: {e}")

    return database

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-TW">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>ETF 籌碼決策戰情室 v7.0</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;700;800&family=Noto+Sans+TC:wght@400;500;700;900&display=swap" rel="stylesheet">
    <script src="https://cdn.tailwindcss.com"></script>
    <script src="https://cdn.jsdelivr.net/npm/marked/marked.min.js"></script>
    <style>
        :root {
            --bg-base: #f4f4f5; --bg-nav: #ffffff; --bg-panel: #ffffff; --bg-panel-hover: #fafafa; --bg-row-even: #ffffff; --bg-row-odd: #fafafa;
            --border-dim: #e4e4e7; --border-focus: #2563eb; --text-main: #18181b; --text-dim: #71717a;
            --color-buy: #dc2626; --color-sell: #059669; --color-accent: #2563eb;
            --shadow-buy: none; --shadow-sell: none; --shadow-accent: none; --box-shadow-buy: none; --box-shadow-sell: none;
            --shadow-panel: 0 4px 6px -1px rgba(0, 0, 0, 0.05), 0 2px 4px -2px rgba(0, 0, 0, 0.05); --bar-track: #f4f4f5;
        }

        [data-theme="dark"] {
            --bg-base: #050505; --bg-nav: #050505; --bg-panel: #0d0d0d; --bg-panel-hover: #141414; --bg-row-even: #0d0d0d; --bg-row-odd: #0a0a0a;
            --border-dim: #262626; --border-focus: #00f0ff; --text-main: #f4f4f5; --text-dim: #84848f;
            --color-buy: #ff2a5f; --color-sell: #00ff9d; --color-accent: #00f0ff;
            --shadow-buy: 0 0 10px rgba(255, 42, 95, 0.4); --shadow-sell: 0 0 10px rgba(0, 255, 157, 0.4); --shadow-accent: 0 0 10px rgba(0, 240, 255, 0.4);
            --box-shadow-buy: 0 0 12px rgba(255, 42, 95, 0.3); --box-shadow-sell: 0 0 12px rgba(0, 255, 157, 0.3);
            --shadow-panel: 0 8px 32px rgba(0, 0, 0, 0.5); --bar-track: #111111;
        }

        body { background-color: var(--bg-base); color: var(--text-main); font-family: "Noto Sans TC", sans-serif; min-height: 100vh; transition: background-color 0.3s ease, color 0.3s ease; }
        [data-theme="dark"] body { background-image: linear-gradient(rgba(255, 255, 255, 0.02) 1px, transparent 1px); background-size: 100% 4px; }
        .font-mono { font-family: "JetBrains Mono", monospace; }

        .theme-nav { background-color: var(--bg-nav); border-color: var(--border-dim); }
        .theme-panel { background-color: var(--bg-panel); border-color: var(--border-dim); box-shadow: var(--shadow-panel); }
        .theme-border { border-color: var(--border-dim); }
        .theme-text { color: var(--text-main); }
        .theme-text-dim { color: var(--text-dim); }
        .theme-bg-input { background-color: var(--bg-base); color: var(--text-main); border-color: var(--border-dim); }
        .theme-bg-input:focus-within, .theme-bg-input:hover { border-color: var(--border-focus); }
        .row-even { background-color: var(--bg-row-even); border-color: var(--border-dim); }
        .row-odd { background-color: var(--bg-row-odd); border-color: var(--border-dim); }
        .row-hover:hover { background-color: var(--bg-panel-hover); }
        .bar-track { background-color: var(--bar-track); }

        .text-buy { color: var(--color-buy); text-shadow: var(--shadow-buy); }
        .text-sell { color: var(--color-sell); text-shadow: var(--shadow-sell); }
        .text-accent { color: var(--color-accent); text-shadow: var(--shadow-accent); }
        .bg-buy { background-color: var(--color-buy); box-shadow: var(--box-shadow-buy); }
        .bg-sell { background-color: var(--color-sell); box-shadow: var(--box-shadow-sell); }
        .bg-accent { background-color: var(--color-accent); box-shadow: var(--shadow-accent); }
        .border-buy { border-color: var(--color-buy); }
        .border-sell { border-color: var(--color-sell); }
        .border-accent { border-color: var(--color-accent); }
        
        .bg-neutral { background-color: #e4e4e7; }
        [data-theme="dark"] .bg-neutral { background-color: #262626; }

        .tab-btn { transition: all 0.2s; white-space: nowrap; font-size: 0.9rem; letter-spacing: 0.05em; text-transform: uppercase; }
        .tab-active { background-color: var(--text-main); color: var(--bg-panel); font-weight: 700; }
        [data-theme="dark"] .tab-active { background: #1a1a1a; color: var(--color-accent); border: 1px solid var(--color-accent); box-shadow: 0 0 15px rgba(0, 240, 255, 0.15), inset 0 0 10px rgba(0, 240, 255, 0.05); }
        .tab-inactive { background-color: var(--bg-base); color: var(--text-dim); border: 1px solid var(--border-dim); }
        .tab-inactive:hover { border-color: var(--text-main); color: var(--text-main); }

        .tab-ai-agent { background: linear-gradient(135deg, #1e3a5f 0%, #2563eb 50%, #00f0ff 100%); color: #fff; border: 1px solid rgba(0, 240, 255, 0.5); font-weight: 700; box-shadow: 0 0 12px rgba(0, 240, 255, 0.3); }
        [data-theme="dark"] .tab-ai-agent { background: linear-gradient(135deg, #0f172a 0%, #1e40af 50%, #06b6d4 100%); border-color: rgba(6, 182, 212, 0.6); box-shadow: 0 0 15px rgba(6, 182, 212, 0.4); color: var(--text-main); }
        .tab-ai-agent:hover { filter: brightness(1.15); }
        .tab-ai-agent.tab-active { background: linear-gradient(135deg, #0f172a 0%, #1e40af 100%); border-color: var(--color-accent); box-shadow: 0 0 20px rgba(0, 240, 255, 0.5); color: var(--color-accent); }

        @keyframes pulse-dot { 0% { transform: scale(0.95); box-shadow: 0 0 0 0 rgba(220, 38, 38, 0.7); } 70% { transform: scale(1); box-shadow: 0 0 0 6px rgba(220, 38, 38, 0); } 100% { transform: scale(0.95); box-shadow: 0 0 0 0 rgba(220, 38, 38, 0); } }
        [data-theme="dark"] @keyframes pulse-dot { 0% { transform: scale(0.95); box-shadow: 0 0 0 0 rgba(255, 42, 95, 0.7); } 70% { transform: scale(1); box-shadow: 0 0 0 6px rgba(255, 42, 95, 0); } 100% { transform: scale(0.95); box-shadow: 0 0 0 0 rgba(255, 42, 95, 0); } }
        .live-dot { height: 8px; width: 8px; background-color: var(--color-buy); border-radius: 50%; display: inline-block; animation: pulse-dot 2s infinite; }
        .hide-scrollbar::-webkit-scrollbar { display: none; }
        .hide-scrollbar { -ms-overflow-style: none; scrollbar-width: none; }
        input, select { outline: none; }
        
        #ai-report-output h1, #ai-report-output h2, #ai-report-output h3 { margin-top: 1em; margin-bottom: 0.5em; font-weight: 700; }
        #ai-report-output p { margin-bottom: 0.75em; }
        #ai-report-output ul, #ai-report-output ol { margin-left: 1.5em; margin-bottom: 0.75em; }

        .unit-btn { background-color: var(--bg-base); color: var(--text-dim); }
        .unit-btn:hover { color: var(--text-main); }
        .unit-btn-amount.unit-active { background-color: var(--color-buy); color: #fff; }
        .unit-btn-shares.unit-active { background-color: var(--color-accent); color: #fff; }
        [data-theme="dark"] .unit-btn-amount.unit-active { background-color: var(--color-buy); color: #fff; }
        [data-theme="dark"] .unit-btn-shares.unit-active { background-color: var(--color-accent); color: #fff; }
    </style>
</head>
<body class="pb-24 pt-6">

    <nav class="w-full theme-nav border-b fixed top-0 z-50 flex justify-between items-center px-4 md:px-8 py-3 transition-colors">
        <div class="flex items-center gap-4">
            <span class="live-dot"></span>
            <span class="font-mono text-sm tracking-widest font-bold text-buy">SYSTEM.LIVE</span>
            <span class="theme-text-dim hidden md:inline">|</span>
            <h1 class="text-lg font-black tracking-[0.2em] theme-text">戰情室 <span class="theme-text-dim font-mono text-xs">v7.0</span></h1>
        </div>
        <div class="flex items-center gap-4 font-mono text-xs theme-text-dim">
            <span id="live-clock" class="hidden md:inline">Loading...</span>
            <button onclick="toggleTheme()" class="p-1.5 rounded-md theme-border border hover:theme-text transition-colors" title="切換深淺模式">
                <svg id="icon-sun" class="w-4 h-4 hidden" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 3v1m0 16v1m9-9h-1M4 12H3m15.364 6.364l-.707-.707M6.343 6.343l-.707-.707m12.728 0l-.707.707M6.343 17.657l-.707.707M16 12a4 4 0 11-8 0 4 4 0 018 0z"></path></svg>
                <svg id="icon-moon" class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M20.354 15.354A9 9 0 018.646 3.646 9.003 9.003 0 0012 21a9.003 9.003 0 008.354-5.646z"></path></svg>
            </button>
        </div>
    </nav>

    <div class="max-w-6xl mx-auto px-4 md:px-6 mt-20">

        <div class="theme-panel border rounded-xl p-5 md:p-8 transition-colors">

            <div id="control-panel" class="mb-6">
                <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 mb-4">
                    <div>
                        <label class="block font-mono text-xs theme-text-dim mb-1.5 uppercase tracking-wider">目標標的</label>
                        <select id="etf-selector" onchange="onETFChange()" class="theme-bg-input border theme-border rounded-lg w-full px-3 py-2.5 text-sm font-mono theme-text cursor-pointer transition-colors focus:border-focus">
                        </select>
                    </div>
                </div>
                <div id="timeframe-unit-row" class="flex flex-wrap items-center gap-4">
                    <div>
                        <label class="block font-mono text-xs theme-text-dim mb-1.5 uppercase tracking-wider">天數</label>
                        <select id="timeframe-selector" onchange="onTimeframeChange()" class="theme-bg-input border theme-border rounded-lg px-3 py-2.5 text-sm font-mono theme-text cursor-pointer transition-colors focus:border-focus">
                            <option value="1">近1日</option>
                            <option value="5">近5日</option>
                            <option value="10">近10日</option>
                            <option value="20">近20日</option>
                            <option value="30">近30日</option>
                        </select>
                    </div>
                    <div>
                        <label class="block font-mono text-xs theme-text-dim mb-1.5 uppercase tracking-wider">單位</label>
                        <div class="flex rounded-lg overflow-hidden border theme-border" role="group">
                            <button type="button" id="unit-btn-amount" onclick="setUnit('amount')" class="unit-btn unit-btn-amount px-4 py-2.5 text-sm font-mono font-bold border-r theme-border transition-colors">
                                金額
                            </button>
                            <button type="button" id="unit-btn-shares" onclick="setUnit('shares')" class="unit-btn unit-btn-shares px-4 py-2.5 text-sm font-mono font-bold transition-colors">
                                張數
                            </button>
                        </div>
                    </div>
                </div>
            </div>

            <div id="header-main" class="flex flex-col sm:flex-row sm:justify-between sm:items-end gap-4 pb-5 mb-6 theme-border border-b">
                <div class="flex flex-col gap-1">
                    <span class="font-mono text-xs theme-text-dim tracking-widest uppercase">TARGET_ASSET</span>
                    <div class="flex items-baseline gap-3">
                        <h2 id="current-etf-title" class="text-3xl md:text-4xl font-black theme-text tracking-wider">---</h2>
                        <span id="current-date-display" class="font-mono text-lg text-accent"></span>
                    </div>
                </div>
                <div id="header-controls" class="flex flex-wrap items-center gap-3">
                    <div class="theme-bg-input border rounded-md flex items-center px-3 py-1.5 transition-colors">
                        <span class="theme-text-dim font-mono mr-2">></span>
                        <input type="text" id="search-input" onkeyup="handleSearch()" placeholder="SEARCH_TICKER..." class="bg-transparent text-sm w-full sm:w-36 font-mono placeholder-gray-400 theme-text border-none">
                    </div>
                    <div class="theme-bg-input border rounded-md flex items-center px-2 py-1.5 transition-colors">
                        <select id="date-selector" onchange="onDateChange()" class="bg-transparent text-sm font-mono theme-text cursor-pointer pr-2 border-none appearance-none"></select>
                    </div>
                </div>
            </div>

            <div id="sector-flow-container" class="mb-8 flex gap-3 overflow-x-auto hide-scrollbar pb-2"></div>

            <div id="normal-view">
                <div id="empty-state" class="text-center font-mono theme-text-dim py-12 theme-bg-base border border-dashed theme-border rounded-lg hidden">
                    > NO_DATA_DETECTED_
                </div>
                <div id="data-table-container" class="hidden">
                    <div class="grid grid-cols-1 md:grid-cols-2 gap-8">
                        <div>
                            <h4 class="font-mono text-buy text-sm font-bold tracking-widest mb-3 border-l-4 border-buy pl-3 py-1">買超排行</h4>
                            <div class="theme-bg-base border theme-border rounded-lg overflow-hidden">
                                <table class="w-full text-sm">
                                    <thead>
                                        <tr class="theme-bg-input border-b theme-border">
                                            <th class="text-left py-3 px-4 font-mono font-bold theme-text-dim w-16">排名</th>
                                            <th class="text-left py-3 px-4 font-mono font-bold theme-text-dim">股票</th>
                                            <th class="text-right py-3 px-4 font-mono font-bold theme-text-dim">淨買超</th>
                                        </tr>
                                    </thead>
                                    <tbody id="buy-rank-tbody"></tbody>
                                </table>
                            </div>
                        </div>
                        <div>
                            <h4 class="font-mono text-sell text-sm font-bold tracking-widest mb-3 border-l-4 border-sell pl-3 py-1">賣超排行</h4>
                            <div class="theme-bg-base border theme-border rounded-lg overflow-hidden">
                                <table class="w-full text-sm">
                                    <thead>
                                        <tr class="theme-bg-input border-b theme-border">
                                            <th class="text-left py-3 px-4 font-mono font-bold theme-text-dim w-16">排名</th>
                                            <th class="text-left py-3 px-4 font-mono font-bold theme-text-dim">股票</th>
                                            <th class="text-right py-3 px-4 font-mono font-bold theme-text-dim">淨賣超</th>
                                        </tr>
                                    </thead>
                                    <tbody id="sell-rank-tbody"></tbody>
                                </table>
                            </div>
                        </div>
                    </div>
                </div>
            </div>

            <div id="search-view" class="hidden">
                <h3 class="font-mono text-xs theme-text-dim tracking-[0.2em] mb-4 flex items-center border-b theme-border pb-2">
                    <span class="theme-text-dim opacity-50 mr-2">///</span> RADAR_SCAN_RESULTS
                </h3>
                <div id="search-results-list" class="flex flex-col border-t theme-border mt-1"></div>
            </div>

            <div id="ai-agent-view" class="hidden">
                <h3 class="font-mono text-xs theme-text-dim tracking-[0.2em] mb-4 flex items-center border-b theme-border pb-2">
                    <span class="theme-text-dim opacity-50 mr-2">///</span> AI_ANALYSIS_PROTOCOL
                </h3>
                
                <div class="mb-6 flex flex-wrap gap-3 items-center">
                    <div class="theme-bg-input border rounded-md flex items-center px-3 py-2 transition-colors flex-1 min-w-[250px]">
                        <span class="theme-text-dim font-mono mr-2 text-sm">KEY</span>
                        <input type="password" id="api-key-input" placeholder="輸入 OpenAI API Key (僅存於本地瀏覽器)" class="bg-transparent text-sm flex-1 font-mono theme-text border-none focus:outline-none">
                    </div>
                    <button onclick="saveApiKey()" class="tab-btn px-4 py-2 font-mono rounded-sm border theme-border hover:theme-text transition-colors">
                        [ SAVE_KEY ]
                    </button>
                    <span id="api-key-status" class="font-mono text-xs theme-text-dim ml-2"></span>
                </div>

                <div class="flex flex-col gap-4 mb-6">
                    <div class="flex flex-wrap items-center gap-3">
                        <div class="theme-bg-input border rounded-md flex items-center px-3 py-2 transition-colors flex-1 min-w-[200px] focus-within:border-accent">
                            <span class="theme-text-dim font-mono mr-2 text-sm">TICKER</span>
                            <input type="text" id="ai-ticker-input" placeholder="輸入股票代號 (例: 2330 或 台積電)" class="bg-transparent text-sm flex-1 font-mono theme-text border-none focus:outline-none">
                        </div>
                        <button id="btn-run-ai" onclick="runAIAnalysis()" class="tab-btn px-4 py-2 font-mono rounded-sm border border-accent text-accent hover:bg-accent hover:text-white transition-colors shadow-sm">
                            [ EXECUTE_ANALYSIS ]
                        </button>
                    </div>
                </div>
                
                <div class="theme-bg-input border rounded-lg p-5 transition-colors min-h-[300px]">
                    <div id="ai-report-output" class="w-full bg-transparent font-mono text-sm theme-text leading-relaxed">等待執行分析... (請先於上方設定 API Key 並輸入代號)</div>
                </div>
            </div>

        </div>
    </div>

    <script>
        // Theme Logic
        function initTheme() {
            const savedTheme = localStorage.getItem('theme') || 'light';
            document.documentElement.setAttribute('data-theme', savedTheme);
            updateThemeIcons(savedTheme);
        }
        function toggleTheme() {
            const html = document.documentElement;
            const currentTheme = html.getAttribute('data-theme');
            const newTheme = currentTheme === 'dark' ? 'light' : 'dark';
            html.setAttribute('data-theme', newTheme);
            localStorage.setItem('theme', newTheme);
            updateThemeIcons(newTheme);
        }
        function updateThemeIcons(theme) {
            if (theme === 'dark') {
                document.getElementById('icon-sun').classList.remove('hidden');
                document.getElementById('icon-moon').classList.add('hidden');
            } else {
                document.getElementById('icon-sun').classList.add('hidden');
                document.getElementById('icon-moon').classList.remove('hidden');
            }
        }
        initTheme();

        // Live Clock
        function updateClock() {
            const now = new Date();
            const utc = now.toISOString().replace('T', ' ').substring(0, 19) + ' UTC';
            document.getElementById('live-clock').textContent = utc;
        }
        setInterval(updateClock, 1000);
        updateClock();

        const db = __DB_JSON__;
        const availableDatesDesc = Object.keys(db).sort().reverse();
        const availableDatesAsc = [...availableDatesDesc].reverse();
        const FAMILY_TAB = "GLOBAL_CONSENSUS";
        const AI_TAB = "AI_AGENT";

        let allETFs = new Set();
        Object.values(db).forEach(dateData => { Object.keys(dateData).forEach(etf => allETFs.add(etf)); });
        let etfList = Array.from(allETFs).filter(e => e !== AI_TAB).sort();
        etfList.unshift(FAMILY_TAB);
        etfList.push(AI_TAB);

        let currentETF = etfList[0];
        let currentDate = availableDatesDesc[0];
        let currentUnit = 'amount';
        let currentDays = 5;

        function aggregateData(etf, days) {
            if (availableDatesDesc.length === 0) return { buy: [], sell: [] };
            let dateIndex = availableDatesDesc.indexOf(currentDate);
            if (dateIndex === -1) dateIndex = 0;
            const dateSlice = availableDatesDesc.slice(dateIndex, dateIndex + Math.min(days, availableDatesDesc.length - dateIndex));
            const agg = {};
            const etfListToUse = (etf === FAMILY_TAB) ? etfList.filter(e => e !== FAMILY_TAB && e !== AI_TAB) : [etf];

            dateSlice.forEach(d => {
                const dataOfDay = db[d] || {};
                etfListToUse.forEach(e => {
                    const dayData = dataOfDay[e];
                    if (!dayData) return;
                    [...(dayData.new_buy || []), ...(dayData.increased || [])].forEach(i => {
                        const key = i.name;
                        if (!agg[key]) agg[key] = { name: key, code: i.code || '', sector: i.sector || '其他', diff: 0, amount: 0 };
                        agg[key].diff += i.diff;
                        agg[key].amount += (i.amount || 0);
                    });
                    [...(dayData.decreased || []), ...(dayData.sold_out || [])].forEach(i => {
                        const key = i.name;
                        if (!agg[key]) agg[key] = { name: key, code: i.code || '', sector: i.sector || '其他', diff: 0, amount: 0 };
                        agg[key].diff -= i.diff;
                        agg[key].amount -= (i.amount || 0);
                    });
                });
            });

            const buy = Object.values(agg).filter(x => x.diff > 0);
            const sell = Object.values(agg).filter(x => x.diff < 0).map(x => ({ ...x, diff: Math.abs(x.diff), amount: Math.abs(x.amount) }));
            return { buy, sell };
        }

        function onETFChange() {
            currentETF = document.getElementById('etf-selector').value;
            document.getElementById('search-input').value = '';
            const isAI = currentETF === AI_TAB;
            document.getElementById('timeframe-unit-row').classList.toggle('hidden', isAI);
            document.getElementById('header-controls').classList.toggle('hidden', isAI);
            document.getElementById('sector-flow-container').classList.toggle('hidden', isAI);
            document.getElementById('normal-view').classList.toggle('hidden', isAI);
            document.getElementById('search-view').classList.add('hidden');
            document.getElementById('ai-agent-view').classList.toggle('hidden', !isAI);
            document.getElementById('current-etf-title').textContent = isAI ? 'AI_AGENT' : (currentETF === FAMILY_TAB ? 'GLOBAL_CONSENSUS' : currentETF);
            document.getElementById('current-date-display').textContent = isAI ? 'PROTOCOL_ACTIVE' : dateRangeLabel();
            if (!isAI) refreshTable();
        }

        function onTimeframeChange() {
            currentDays = parseInt(document.getElementById('timeframe-selector').value, 10);
            document.getElementById('current-date-display').textContent = dateRangeLabel();
            refreshTable();
        }

        function onDateChange() {
            currentDate = document.getElementById('date-selector').value;
            document.getElementById('current-date-display').textContent = dateRangeLabel();
            refreshTable();
        }

        function dateRangeLabel() {
            const idx = availableDatesDesc.indexOf(currentDate);
            const slice = availableDatesDesc.slice(idx, idx + Math.min(currentDays, availableDatesDesc.length - idx));
            if (slice.length === 0) return currentDate;
            return slice.length === 1 ? slice[0] : slice[slice.length - 1] + ' ~ ' + slice[0];
        }

        function setUnit(u) {
            currentUnit = u;
            document.getElementById('unit-btn-amount').classList.toggle('unit-active', u === 'amount');
            document.getElementById('unit-btn-shares').classList.toggle('unit-active', u === 'shares');
            refreshTable();
        }

        // API Key LocalStorage Logic
        function initApiKey() {
            const key = localStorage.getItem('openai_api_key');
            if (key) {
                document.getElementById('api-key-input').value = key;
                document.getElementById('api-key-status').textContent = "STATUS: KEY_LOADED";
                document.getElementById('api-key-status').className = "font-mono text-xs ml-2 text-buy";
            } else {
                document.getElementById('api-key-status').textContent = "STATUS: NO_KEY";
                document.getElementById('api-key-status').className = "font-mono text-xs ml-2 theme-text-dim";
            }
        }

        function saveApiKey() {
            const key = document.getElementById('api-key-input').value.trim();
            if (key) {
                localStorage.setItem('openai_api_key', key);
                document.getElementById('api-key-status').textContent = "STATUS: KEY_SAVED";
                document.getElementById('api-key-status').className = "font-mono text-xs ml-2 text-buy";
            } else {
                localStorage.removeItem('openai_api_key');
                document.getElementById('api-key-status').textContent = "STATUS: KEY_CLEARED";
                document.getElementById('api-key-status').className = "font-mono text-xs ml-2 text-sell";
            }
        }

        function init() {
            if (availableDatesDesc.length === 0) return;
            const etfSel = document.getElementById('etf-selector');
            etfList.forEach(etf => {
                const opt = document.createElement('option');
                opt.value = etf;
                opt.textContent = etf === FAMILY_TAB ? 'GLOBAL_CONSENSUS (全家族共識)' : (etf === AI_TAB ? 'AI_AGENT' : etf);
                etfSel.appendChild(opt);
            });
            const dateSel = document.getElementById('date-selector');
            availableDatesDesc.forEach(date => {
                const opt = document.createElement('option');
                opt.value = date;
                opt.textContent = date;
                dateSel.appendChild(opt);
            });
            document.getElementById('etf-selector').value = currentETF;
            document.getElementById('timeframe-selector').value = currentDays;
            setUnit(currentUnit);
            document.getElementById('current-etf-title').textContent = currentETF === FAMILY_TAB ? 'GLOBAL_CONSENSUS' : (currentETF === AI_TAB ? 'AI_AGENT' : currentETF);
            document.getElementById('current-date-display').textContent = dateRangeLabel();
            onETFChange();
            initApiKey();
        }

        function refreshTable() {
            if (currentETF === AI_TAB) return;
            const { buy, sell } = aggregateData(currentETF, currentDays);
            const sortBy = currentUnit === 'amount' ? 'amount' : 'diff';
            buy.sort((a, b) => (b[sortBy] || 0) - (a[sortBy] || 0));
            sell.sort((a, b) => (b[sortBy] || 0) - (a[sortBy] || 0));

            const emptyState = document.getElementById('empty-state');
            const dataContainer = document.getElementById('data-table-container');
            if (buy.length === 0 && sell.length === 0) {
                emptyState.classList.remove('hidden');
                dataContainer.classList.add('hidden');
                return;
            }
            emptyState.classList.add('hidden');
            dataContainer.classList.remove('hidden');

            const sfContainer = document.getElementById('sector-flow-container');
            const sectorTotals = {};
            buy.forEach(i => {
                const s = i.sector || '其他';
                if (!sectorTotals[s]) sectorTotals[s] = 0;
                sectorTotals[s] += currentUnit === 'amount' ? i.amount : i.diff;
            });
            sell.forEach(i => {
                const s = i.sector || '其他';
                if (!sectorTotals[s]) sectorTotals[s] = 0;
                sectorTotals[s] -= currentUnit === 'amount' ? i.amount : i.diff;
            });
            let topSectors = Object.entries(sectorTotals).filter(x => x[1] !== 0).sort((a, b) => Math.abs(b[1]) - Math.abs(a[1])).slice(0, 3);
            sfContainer.innerHTML = '';
            topSectors.forEach(s => {
                const isFlowIn = s[1] > 0;
                const cColor = isFlowIn ? 'text-buy' : 'text-sell';
                const cBorder = isFlowIn ? 'border-buy' : 'border-sell';
                const sign = isFlowIn ? '+' : '-';
                const valStr = currentUnit === 'amount' ? formatAmount(Math.abs(s[1])).replace(/[()]/g, '') : Math.abs(s[1]).toLocaleString();
                sfContainer.innerHTML += `<div class="flex flex-col border-l-[3px] ${cBorder} pl-3 py-1.5 theme-bg-input rounded-r pr-4 min-w-[120px]"><span class="text-[11px] font-bold theme-text-dim mb-0.5">${s[0]}</span><span class="font-mono text-sm font-bold ${cColor}">${sign}${valStr}</span></div>`;
            });
            if (topSectors.length === 0) sfContainer.classList.add('hidden');
            else sfContainer.classList.remove('hidden');

            const formatVal = (item, isBuy) => {
                if (currentUnit === 'amount') return (isBuy ? '+' : '-') + ' ' + formatAmount(item.amount);
                return (isBuy ? '+' : '-') + (item.diff || 0).toLocaleString();
            };

            const buyTbody = document.getElementById('buy-rank-tbody');
            buyTbody.innerHTML = buy.map((item, i) => {
                const codeHtml = item.code ? `<span class="font-mono text-[10px] theme-text-dim ml-1">${item.code}</span>` : '';
                return `<tr class="row-hover border-b theme-border last:border-0"><td class="py-2.5 px-4 font-mono theme-text-dim">${i + 1}</td><td class="py-2.5 px-4"><span class="font-bold theme-text">${item.name}</span>${codeHtml}</td><td class="py-2.5 px-4 text-right font-mono font-bold text-buy">${formatVal(item, true)}</td></tr>`;
            }).join('');

            const sellTbody = document.getElementById('sell-rank-tbody');
            sellTbody.innerHTML = sell.map((item, i) => {
                const codeHtml = item.code ? `<span class="font-mono text-[10px] theme-text-dim ml-1">${item.code}</span>` : '';
                return `<tr class="row-hover border-b theme-border last:border-0"><td class="py-2.5 px-4 font-mono theme-text-dim">${i + 1}</td><td class="py-2.5 px-4"><span class="font-bold theme-text">${item.name}</span>${codeHtml}</td><td class="py-2.5 px-4 text-right font-mono font-bold text-sell">${formatVal(item, false)}</td></tr>`;
            }).join('');
        }

        function formatAmount(amount_10k) {
            if (!amount_10k) return "";
            let val = Math.abs(amount_10k);
            if (val >= 10000) return `(約 ${(val/10000).toFixed(2)} 億)`;
            return `(約 ${Math.round(val).toLocaleString()} 萬)`;
        }

        function handleSearch() {
            const val = document.getElementById('search-input').value.trim().toLowerCase();
            const normalView = document.getElementById('normal-view');
            const searchView = document.getElementById('search-view');
            const aiView = document.getElementById('ai-agent-view');
            const sfContainer = document.getElementById('sector-flow-container');

            if (currentETF === AI_TAB) return;
            if (!val) {
                normalView.classList.remove('hidden');
                searchView.classList.add('hidden');
                sfContainer.classList.remove('hidden');
                refreshTable();
                return;
            }

            normalView.classList.add('hidden');
            sfContainer.classList.add('hidden');
            searchView.classList.remove('hidden');

            const resultsContainer = document.getElementById('search-results-list');
            resultsContainer.innerHTML = '';

            const { buy, sell } = aggregateData(currentETF, currentDays);
            const allMatches = [...buy.filter(i => (i.name + (i.code || '')).toLowerCase().includes(val)).map(i => ({ ...i, sign: '+', isBuy: true })),
                ...sell.filter(i => (i.name + (i.code || '')).toLowerCase().includes(val)).map(i => ({ ...i, sign: '-', isBuy: false }))];
            allMatches.sort((a, b) => (b.diff || 0) - (a.diff || 0));

            if (allMatches.length === 0) {
                resultsContainer.innerHTML = '<div class="py-12 text-center theme-text-dim font-mono text-sm">> RADAR_EMPTY</div>';
                return;
            }

            allMatches.forEach(a => {
                const colorClass = a.isBuy ? 'text-buy' : 'text-sell';
                const valStr = currentUnit === 'amount' ? (a.sign + ' ' + formatAmount(a.amount)) : (a.sign + (a.diff || 0).toLocaleString());
                const codeHtml = a.code ? `<span class="font-mono text-[10px] theme-text-dim ml-1">${a.code}</span>` : '';
                resultsContainer.innerHTML += `<div class="flex justify-between items-center py-3 border-b theme-border row-hover px-4 transition-colors"><div class="flex items-center gap-2"><span class="theme-text text-[14px] font-bold">${a.name}</span>${codeHtml}</div><span class="${colorClass} font-mono font-bold text-[14px]">${valStr}</span></div>`;
            });
        }

        async function runAIAnalysis() {
            const ticker = document.getElementById('ai-ticker-input').value.trim();
            const output = document.getElementById('ai-report-output');
            const btn = document.getElementById('btn-run-ai');
            const apiKey = localStorage.getItem('openai_api_key');

            if (!apiKey) {
                output.innerHTML = "<span class='text-sell font-bold'>[ ERROR ] 請先於上方設定 OpenAI API Key，並點擊 [ SAVE_KEY ]。</span>";
                return;
            }
            if (!ticker) {
                output.innerHTML = "<span class='text-sell font-bold'>[ ERROR ] 請輸入股票代號或名稱 (例如：2330)。</span>";
                return;
            }

            output.innerHTML = "<span class='theme-text-dim'>[ SYSTEM ] 啟動決策引擎...<br>[ SYSTEM ] 正在向證交所/櫃買中心攔截即時報價...</span>";
            btn.disabled = true;
            btn.textContent = "[ PROCESSING... ]";
            btn.classList.add("opacity-50", "cursor-not-allowed");

            let currentPrice = "未知 (請依賴歷史基本面評估)";

            try {
                try {
                    const twseResp = await fetch('https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL');
                    if (twseResp.ok) {
                        const twseData = await twseResp.json();
                        const stock = twseData.find(s => (s.Code && String(s.Code) === ticker) || (s.Name && String(s.Name).includes(ticker)));
                        if (stock && stock.ClosingPrice) {
                            currentPrice = stock.ClosingPrice + " 元 (TWSE即時)";
                        }
                    }
                } catch (e) { /* TWSE fail, try TPEx */ }

                if (currentPrice === "未知 (請依賴歷史基本面評估)") {
                    try {
                        const tpexResp = await fetch('https://www.tpex.org.tw/openapi/v1/tpex_mainboard_quotes');
                        if (tpexResp.ok) {
                            const tpexData = await tpexResp.json();
                            const stock = tpexData.find(s => (s.SecuritiesCompanyCode && String(s.SecuritiesCompanyCode) === ticker) || (s.CompanyName && String(s.CompanyName).includes(ticker)));
                            if (stock && stock.Close) {
                                currentPrice = stock.Close + " 元 (TPEx即時)";
                            }
                        }
                    } catch (e) { /* TPEx fail */ }
                }

                output.innerHTML = "<span class='theme-text-dim'>[ SYSTEM ] 報價取得完成。正在呼叫 OpenAI gpt-4o...</span>";

                const promptText = `【系統注入即時數據】
目標標的：${ticker}
今日收盤價：${currentPrice}

【系統強制指令】
你是一位頂尖的外資券商首席分析師。請「直接使用」上述系統提供的最新股價進行估值。嚴禁嘗試聯網搜尋，也「絕對不要」在報告中因為無法獲取最新資訊而道歉或提示。請完全依賴你的核心訓練知識，展現專業自信，完成以下 5 大維度的深度報告：

1. 財務報表分析：
分析該公司過去的營收增長、淨利趨勢、自由現金流與利潤率。判斷其財務體質。

2. 估值分析：
使用系統提供的今日收盤價（${currentPrice}），結合該公司的歷史 P/E 區間與產業平均，推算目前股價是被低估還是高估。

3. 成長潛力分析：
評估該公司的商業模式、護城河、未來 5-10 年在 AI 或新技術浪潮下的成長空間與潛在市場規模。

4. 多空對峙辯論：
模擬兩位分析師進行辯論。一位看多 (Bull) 提出潛在利多；一位看空 (Bear) 提出結構性風險與隱憂。

5. 投資建議評估：
給出明確的結論：針對目前市價，給出「買入 (Buy)」、「持有 (Hold)」或「避開 (Avoid)」的評級，並列出核心催化劑。

請全程使用 Markdown 格式輸出，語氣必須果斷、客觀、專業。`;

                const response = await fetch('https://api.openai.com/v1/chat/completions', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'Authorization': `Bearer ${apiKey}`
                    },
                    body: JSON.stringify({
                        model: "gpt-4o",
                        messages: [
                            { role: "system", content: "你是一位外資券商首席分析師，精通基本面與量化估值。請以繁體中文輸出高專業度報告，善用 Markdown 格式進行排版。" },
                            { role: "user", content: promptText }
                        ],
                        temperature: 0.5
                    })
                });

                const data = await response.json();

                if (!response.ok) {
                    throw new Error(data.error?.message || "未知的 API 錯誤");
                }

                const rawContent = data.choices[0].message.content;
                output.innerHTML = (typeof marked !== 'undefined' ? (marked.parse || marked)(rawContent) : rawContent);
            } catch (error) {
                output.innerHTML = `<span class='text-sell font-bold'>[ API ERROR ]<br>${error.message}</span>`;
            } finally {
                btn.disabled = false;
                btn.textContent = "[ EXECUTE_ANALYSIS ]";
                btn.classList.remove("opacity-50", "cursor-not-allowed");
            }
        }

        window.onload = init;
    </script>
</body>
</html>"""

def main():
    print("[INFO] 開始產出 Web Dashboard (v7.0 券商級 UI 多日聚合版)...")
    db = process_all_data()
    
    json_str = json.dumps(db, ensure_ascii=False)
    final_html = HTML_TEMPLATE.replace("__DB_JSON__", json_str)
    
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(final_html)
        
    print(f"[OK] 成功產出 {OUTPUT_FILE}")

if __name__ == "__main__":
    main()