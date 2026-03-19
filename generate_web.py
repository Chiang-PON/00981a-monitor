"""generate_web.py — 自動生成靜態網頁儀表板 (最終決策完全體 + 雙軌戰情室)

整合外資 4 大核心邏輯：
1. 真實資金換算：結合報價計算出真實的「投入金額(億/萬)」，取代純看張數。
2. 產業板塊輪動：加入台股產業地圖，自動結算資金淨流入/流出板塊。
3. 雷達微型圖 (Sparklines)：搜尋結果旁直接顯示過去 5 天的連續買賣動能柱狀圖。
4. 權重變動率：不僅顯示當前權重，更顯示對比前一日的增減幅 (+0.5%)。
- UI 升級：上方 ETF 切換按鈕改為「矩陣式排列 (Flex-wrap)」，解決標籤過多時需要滑動的問題。
"""

import os
import glob
import re
import json
import pandas as pd
from datetime import datetime

HISTORY_DIR = "history"
OUTPUT_FILE = "index.html"

# 💎 內建台股產業地圖 (Sector Map)
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
                    new_buy.append({"name": c_name, "diff": shares, "weight": weight, "w_diff": weight, "amount": amount_10k, "sector": SECTOR_MAP.get(c_name, "其他")})
                    
                for c in (prev_codes - curr_codes):
                    row = df_prev[df_prev["code"].astype(str) == c].iloc[0]
                    shares, weight, price = extract_info(row, df_prev)
                    c_name = clean_stock_name(row["name"])
                    amount_10k = (shares * price) / 10 if price > 0 else 0
                    sold_out.append({"name": c_name, "diff": shares, "weight": 0.0, "w_diff": -weight, "amount": amount_10k, "sector": SECTOR_MAP.get(c_name, "其他")})
                    
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
                        increased.append({"name": c_name, "diff": diff, "weight": weight_curr, "w_diff": w_diff, "amount": amount_10k, "sector": sector})
                    elif diff < 0:
                        decreased.append({"name": c_name, "diff": abs(diff), "weight": weight_curr, "w_diff": w_diff, "amount": amount_10k, "sector": sector})
                        
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
    <title>MONITOR TERMINAL</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;700;800&family=Noto+Sans+TC:wght@400;500;700;900&display=swap" rel="stylesheet">
    <script src="https://cdn.tailwindcss.com"></script>
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

        @keyframes pulse-dot { 0% { transform: scale(0.95); box-shadow: 0 0 0 0 rgba(220, 38, 38, 0.7); } 70% { transform: scale(1); box-shadow: 0 0 0 6px rgba(220, 38, 38, 0); } 100% { transform: scale(0.95); box-shadow: 0 0 0 0 rgba(220, 38, 38, 0); } }
        [data-theme="dark"] @keyframes pulse-dot { 0% { transform: scale(0.95); box-shadow: 0 0 0 0 rgba(255, 42, 95, 0.7); } 70% { transform: scale(1); box-shadow: 0 0 0 6px rgba(255, 42, 95, 0); } 100% { transform: scale(0.95); box-shadow: 0 0 0 0 rgba(255, 42, 95, 0); } }
        .live-dot { height: 8px; width: 8px; background-color: var(--color-buy); border-radius: 50%; display: inline-block; animation: pulse-dot 2s infinite; }
        .hide-scrollbar::-webkit-scrollbar { display: none; }
        .hide-scrollbar { -ms-overflow-style: none; scrollbar-width: none; }
        input, select { outline: none; }
    </style>
</head>
<body class="pb-24 pt-6">

    <nav class="w-full theme-nav border-b fixed top-0 z-50 flex justify-between items-center px-4 md:px-8 py-3 transition-colors">
        <div class="flex items-center gap-4">
            <span class="live-dot"></span>
            <span class="font-mono text-sm tracking-widest font-bold text-buy">SYSTEM.LIVE</span>
            <span class="theme-text-dim hidden md:inline">|</span>
            <h1 class="text-lg font-black tracking-[0.2em] theme-text">MONITOR <span class="theme-text-dim font-mono text-xs">v6.1</span></h1>
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
        
        <div id="etf-tabs" class="flex flex-wrap gap-2.5 mb-8"></div>

        <div class="theme-panel border rounded-xl p-5 md:p-8 transition-colors">
            
            <div class="flex flex-col sm:flex-row sm:justify-between sm:items-end gap-4 pb-5 mb-6 theme-border border-b">
                <div class="flex flex-col gap-1">
                    <span class="font-mono text-xs theme-text-dim tracking-widest uppercase">TARGET_ASSET</span>
                    <div class="flex items-baseline gap-3">
                        <h2 id="current-etf-title" class="text-3xl md:text-4xl font-black theme-text tracking-wider">---</h2>
                        <span id="current-date-display" class="font-mono text-lg text-accent"></span>
                    </div>
                </div>
                
                <div class="flex flex-wrap items-center gap-3">
                    <div class="theme-bg-input border rounded-md flex items-center px-3 py-1.5 transition-colors">
                        <span class="theme-text-dim font-mono mr-2">></span>
                        <input type="text" id="search-input" onkeyup="handleSearch()" placeholder="SEARCH_TICKER..." class="bg-transparent text-sm w-full sm:w-36 font-mono placeholder-gray-400 theme-text border-none">
                    </div>
                    <div class="theme-bg-input border rounded-md flex items-center px-2 py-1.5 transition-colors">
                        <select id="date-selector" onchange="changeDate()" class="bg-transparent text-sm font-mono theme-text cursor-pointer pr-2 border-none appearance-none"></select>
                    </div>
                </div>
            </div>

            <div id="sector-flow-container" class="mb-8 flex gap-3 overflow-x-auto hide-scrollbar pb-2"></div>

            <div id="normal-view">
                <div class="mb-12">
                    <h3 class="font-mono text-xs theme-text-dim tracking-[0.2em] mb-4 flex items-center">
                        <span class="theme-text-dim opacity-50 mr-2">///</span> VOLUME_FLOW
                    </h3>
                    <div id="chart-container" class="w-full theme-bg-base border theme-border rounded-lg overflow-hidden"></div>
                </div>

                <div>
                    <h3 class="font-mono text-xs theme-text-dim tracking-[0.2em] mb-4 flex items-center border-b theme-border pb-2">
                        <span class="theme-text-dim opacity-50 mr-2">///</span> TICKER_BREAKDOWN
                    </h3>
                    <div id="empty-state" class="text-center font-mono theme-text-dim py-12 theme-bg-base border border-dashed theme-border rounded-lg hidden">
                        > NO_DATA_DETECTED_
                    </div>
                    <div class="grid grid-cols-1 md:grid-cols-2 gap-x-8 gap-y-10">
                        <div class="flex flex-col gap-8">
                            <div id="list-new" class="hidden">
                                <h4 class="font-mono text-buy text-sm font-bold tracking-widest mb-3 border-l-2 border-buy pl-2">INITIATE_POSITION</h4>
                                <div id="items-new" class="flex flex-col border-t theme-border mt-1"></div>
                            </div>
                            <div id="list-inc" class="hidden">
                                <h4 class="font-mono text-buy text-sm font-bold tracking-widest mb-3 border-l-2 border-buy pl-2">ACCUMULATE</h4>
                                <div id="items-inc" class="flex flex-col border-t theme-border mt-1"></div>
                            </div>
                        </div>
                        <div class="flex flex-col gap-8">
                            <div id="list-dec" class="hidden">
                                <h4 class="font-mono text-sell text-sm font-bold tracking-widest mb-3 border-l-2 border-sell pl-2">REDUCE_EXPOSURE</h4>
                                <div id="items-dec" class="flex flex-col border-t theme-border mt-1"></div>
                            </div>
                            <div id="list-out" class="hidden">
                                <h4 class="font-mono theme-text-dim text-sm font-bold tracking-widest mb-3 border-l-2 theme-border pl-2">LIQUIDATE</h4>
                                <div id="items-out" class="flex flex-col border-t theme-border mt-1"></div>
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
                    <span class="theme-text-dim opacity-50 mr-2">///</span> AI_AGENT_PROMPT_GENERATOR
                </h3>
                <div class="flex flex-col gap-4">
                    <div class="flex flex-wrap items-center gap-3">
                        <div class="theme-bg-input border rounded-md flex items-center px-3 py-2 transition-colors flex-1 min-w-[200px]">
                            <span class="theme-text-dim font-mono mr-2 text-sm">TICKER</span>
                            <input type="text" id="ai-ticker-input" placeholder="2330 或 台積電" class="bg-transparent text-sm flex-1 font-mono theme-text border-none">
                        </div>
                        <button onclick="generateAIPrompt()" class="tab-btn px-4 py-2 font-mono rounded-sm border border-accent text-accent hover:bg-accent hover:theme-text transition-colors">
                            [GENERATE_PROMPT]
                        </button>
                    </div>
                    <div class="theme-bg-input border rounded-lg p-3 transition-colors">
                        <textarea id="ai-prompt-output" rows="16" readonly class="w-full bg-transparent font-mono text-sm theme-text resize-none border-none focus:outline-none" placeholder="點擊 [GENERATE_PROMPT] 產生深度分析提示詞..."></textarea>
                    </div>
                </div>
            </div>

        </div>
    </div>

    <script>
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
        
        let allETFs = new Set();
        Object.values(db).forEach(dateData => { Object.keys(dateData).forEach(etf => allETFs.add(etf)); });
        let etfList = Array.from(allETFs).sort();
        etfList.unshift(FAMILY_TAB);
        etfList.push("AI_AGENT");
        
        let currentDate = availableDatesDesc[0];
        let currentETF = etfList[0]; 

        function init() {
            if(availableDatesDesc.length === 0) return;
            const sel = document.getElementById('date-selector');
            availableDatesDesc.forEach(date => {
                const opt = document.createElement('option');
                opt.value = date; opt.textContent = date;
                sel.appendChild(opt);
            });
            renderTabs();
            updateDashboard();
        }

        function changeDate() { currentDate = document.getElementById('date-selector').value; handleSearch(); }
        function selectETF(etf) {
            currentETF = etf;
            document.getElementById('search-input').value = '';
            renderTabs();
            const normalView = document.getElementById('normal-view');
            const searchView = document.getElementById('search-view');
            const aiView = document.getElementById('ai-agent-view');
            const sfContainer = document.getElementById('sector-flow-container');
            if (etf === 'AI_AGENT') {
                normalView.classList.add('hidden');
                searchView.classList.add('hidden');
                aiView.classList.remove('hidden');
                sfContainer.classList.add('hidden');
            } else {
                aiView.classList.add('hidden');
                normalView.classList.remove('hidden');
                sfContainer.classList.remove('hidden');
                handleSearch();
            }
        }

        function renderTabs() {
            const container = document.getElementById('etf-tabs');
            container.innerHTML = '';
            etfList.forEach(etf => {
                const btn = document.createElement('button');
                const isActive = etf === currentETF;
                btn.className = `tab-btn px-4 py-1.5 font-mono rounded-sm border ${isActive ? 'tab-active theme-border' : 'tab-inactive'}`;
                btn.textContent = etf === FAMILY_TAB ? '[ CONSENSUS ]' : (etf === 'AI_AGENT' ? '[ AI_AGENT ]' : etf);
                btn.onclick = () => selectETF(etf);
                container.appendChild(btn);
            });
        }

        function formatAmount(amount_10k) {
            if (!amount_10k) return "";
            let val = Math.abs(amount_10k);
            if (val >= 10000) return `(約 ${(val/10000).toFixed(2)} 億)`;
            return `(約 ${Math.round(val).toLocaleString()} 萬)`;
        }

        function getSparklineHTML(etf, stockName) {
            let data = [];
            for(let i = 4; i >= 0; i--) {
                let index = availableDatesDesc.indexOf(currentDate) + i;
                if (index >= availableDatesDesc.length || index < 0) continue;
                const d = availableDatesDesc[index];
                const etfData = db[d] && db[d][etf];
                let diff = 0;
                if(etfData) {
                    let item = [...(etfData.new_buy||[]), ...(etfData.increased||[])].find(x => x.name === stockName);
                    if(item) diff = item.diff;
                    else {
                        item = [...(etfData.decreased||[]), ...(etfData.sold_out||[])].find(x => x.name === stockName);
                        if(item) diff = -item.diff;
                    }
                }
                data.push(diff);
            }
            let max = Math.max(...data.map(Math.abs)) || 1;
            let html = '<div class="flex items-end gap-[2px] h-5 w-12 ml-2">';
            data.forEach(val => {
                let h = Math.max((Math.abs(val)/max)*100, 15);
                if (val === 0) h = 15;
                let bg = val > 0 ? 'bg-buy opacity-80' : (val < 0 ? 'bg-sell opacity-80' : 'bg-neutral opacity-50');
                html += `<div class="w-2 ${bg} rounded-[1px]" style="height: ${h}%"></div>`;
            });
            html += '</div>';
            return html;
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
                if (type === 'buy') found = [...(data.new_buy||[]), ...(data.increased||[])].some(x => x.name === stockName);
                else found = [...(data.decreased||[]), ...(data.sold_out||[])].some(x => x.name === stockName);
                if (found) streak++;
                else break;
            }
            return streak;
        }

        function updateDashboard() {
            const displayTitle = currentETF === FAMILY_TAB ? 'GLOBAL_CONSENSUS' : currentETF;
            document.getElementById('current-etf-title').textContent = displayTitle;
            document.getElementById('current-date-display').textContent = currentDate;
            
            const dataToday = db[currentDate] || {};
            let etfData = { new_buy: [], increased: [], decreased: [], sold_out: [] };
            let sectorAgg = {}; 
            
            if (currentETF === FAMILY_TAB) {
                let agg = {};
                Object.keys(dataToday).forEach(etf => {
                    const d = dataToday[etf];
                    [...(d.new_buy||[]), ...(d.increased||[])].forEach(i => {
                        if(!agg[i.name]) agg[i.name] = { diff: 0, amount: 0, sector: i.sector };
                        agg[i.name].diff += i.diff; agg[i.name].amount += i.amount;
                        if(!sectorAgg[i.sector]) sectorAgg[i.sector] = 0;
                        sectorAgg[i.sector] += i.amount;
                    });
                    [...(d.decreased||[]), ...(d.sold_out||[])].forEach(i => {
                        if(!agg[i.name]) agg[i.name] = { diff: 0, amount: 0, sector: i.sector };
                        agg[i.name].diff -= i.diff; agg[i.name].amount -= i.amount;
                        if(!sectorAgg[i.sector]) sectorAgg[i.sector] = 0;
                        sectorAgg[i.sector] -= i.amount;
                    });
                });
                
                Object.keys(agg).forEach(name => {
                    if (agg[name].diff > 0) etfData.increased.push({ name: name, diff: agg[name].diff, amount: agg[name].amount, sector: agg[name].sector, weight:0, w_diff:0 });
                    else if (agg[name].diff < 0) etfData.decreased.push({ name: name, diff: Math.abs(agg[name].diff), amount: Math.abs(agg[name].amount), sector: agg[name].sector, weight:0, w_diff:0 });
                });
            } else {
                etfData = dataToday[currentETF] || { new_buy: [], increased: [], decreased: [], sold_out: [] };
                [...(etfData.new_buy||[]), ...(etfData.increased||[])].forEach(i => {
                    if(!sectorAgg[i.sector]) sectorAgg[i.sector] = 0; sectorAgg[i.sector] += i.amount;
                });
                [...(etfData.decreased||[]), ...(etfData.sold_out||[])].forEach(i => {
                    if(!sectorAgg[i.sector]) sectorAgg[i.sector] = 0; sectorAgg[i.sector] -= i.amount;
                });
            }

            const sfContainer = document.getElementById('sector-flow-container');
            sfContainer.innerHTML = '';
            let topSectors = Object.entries(sectorAgg).sort((a, b) => Math.abs(b[1]) - Math.abs(a[1])).filter(x => x[1] !== 0).slice(0, 3);
            if(topSectors.length > 0) {
                let sfHTML = '';
                topSectors.forEach(s => {
                    let isFlowIn = s[1] > 0;
                    let cColor = isFlowIn ? 'text-buy' : 'text-sell';
                    let cBorder = isFlowIn ? 'border-buy' : 'border-sell';
                    let sign = isFlowIn ? '+' : '-';
                    sfHTML += `
                    <div class="flex flex-col border-l-[3px] ${cBorder} pl-3 py-1.5 theme-bg-input rounded-r pr-4 min-w-[120px]">
                        <span class="text-[11px] font-bold theme-text-dim mb-0.5">${s[0]}</span>
                        <span class="font-mono text-sm font-bold ${cColor}">${sign}${formatAmount(s[1]).replace('(','').replace(')','')}</span>
                    </div>`;
                });
                sfContainer.innerHTML = sfHTML;
                sfContainer.classList.remove('hidden');
            } else {
                sfContainer.classList.add('hidden');
            }

            etfData.increased.sort((a,b) => b.diff - a.diff);
            etfData.decreased.sort((a,b) => b.diff - a.diff);

            const emptyState = document.getElementById('empty-state');
            const sections = ['new', 'inc', 'dec', 'out'];
            const chartContainer = document.getElementById('chart-container');
            
            if(!etfData.new_buy.length && !etfData.increased.length && !etfData.decreased.length && !etfData.sold_out.length) {
                emptyState.classList.remove('hidden');
                sections.forEach(s => document.getElementById(`list-${s}`).classList.add('hidden'));
                chartContainer.innerHTML = '<div class="font-mono theme-text-dim py-8 text-center text-xs">> SIGNAL_LOST</div>';
                return;
            }

            emptyState.classList.add('hidden');

            let formattedItems = [];
            [...(etfData.new_buy || []), ...(etfData.increased || [])].forEach(i => { formattedItems.push({ name: i.name, trueVal: i.diff, amount: i.amount }); });
            [...(etfData.decreased || []), ...(etfData.sold_out || [])].forEach(i => { formattedItems.push({ name: i.name, trueVal: -i.diff, amount: i.amount }); });
            
            formattedItems.sort((a, b) => {
                if (a.amount && b.amount) return b.amount - a.amount;
                return b.trueVal - a.trueVal;
            });
            
            const maxVal = Math.max(...formattedItems.map(i => Math.abs(i.trueVal)));

            let chartHTML = '<div class="flex flex-col">';
            formattedItems.forEach((item, index) => {
                const isBuy = item.trueVal > 0;
                const valStr = isBuy ? `+${item.trueVal.toLocaleString()}` : item.trueVal.toLocaleString();
                const textColor = isBuy ? 'text-buy' : 'text-sell';
                const barClass = isBuy ? 'bg-buy' : 'bg-sell';
                const bgClass = index % 2 === 0 ? 'row-even' : 'row-odd'; 
                const widthPct = Math.max((Math.abs(item.trueVal) / maxVal) * 100, 1);

                chartHTML += `
                <div class="row-hover flex items-center py-2.5 px-4 ${bgClass} border-b theme-border last:border-0 transition-colors">
                    <div class="w-48 md:w-60 flex-shrink-0 flex justify-between items-center pr-4 border-r theme-border">
                        <span class="font-bold theme-text text-[14px] truncate text-left w-16">${item.name}</span>
                        <div class="flex flex-col items-end">
                            <span class="font-mono font-bold ${textColor} text-[13px] text-right">${valStr}</span>
                            <span class="font-mono theme-text-dim text-[10px] opacity-80">${formatAmount(item.amount)}</span>
                        </div>
                    </div>
                    <div class="flex-grow flex items-center pl-4">
                        <div class="w-full bar-track h-[6px] rounded-sm overflow-hidden">
                            <div class="${barClass} h-full" style="width: ${widthPct}%"></div>
                        </div>
                    </div>
                </div>`;
            });
            chartHTML += '</div>';
            chartContainer.innerHTML = chartHTML;

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
                                let wDiffStr = '';
                                if (i.w_diff !== undefined && i.w_diff !== 0) {
                                    let wSign = i.w_diff > 0 ? '+' : '';
                                    wDiffStr = `<span class="${i.w_diff > 0 ? 'text-buy':'text-sell'} ml-1">(${wSign}${i.w_diff.toFixed(2)}%)</span>`;
                                }
                                tagsHTML += `<span class="ml-2 font-mono theme-text-dim text-[10px] opacity-80">W:${i.weight.toFixed(2)}%${wDiffStr}</span>`;
                            }
                            
                            const streak = getStreak(currentETF, i.name, currentDate, type);
                            if (streak >= 3) {
                                const sc = type === 'buy' ? 'text-buy border-buy' : 'text-sell border-sell';
                                tagsHTML += `<span class="ml-2 px-1 border font-mono text-[9px] uppercase ${sc}">STRK:${streak}</span>`;
                            }
                        }

                        let amountStr = i.amount > 0 ? `<span class="mr-3 font-mono theme-text-dim text-[11px] opacity-70">${formatAmount(i.amount)}</span>` : '';

                        list.innerHTML += `
                        <div class="flex justify-between items-center py-2.5 border-b theme-border last:border-0 row-hover px-2 -mx-2 transition-colors">
                            <div class="flex items-center">
                                <span class="text-[14px] font-bold theme-text">${i.name}</span>
                                ${tagsHTML}
                            </div>
                            <div class="flex items-center">
                                ${amountStr}
                                <span class="${colorClass} text-[14px] font-mono font-bold">${valStr}</span>
                            </div>
                        </div>`;
                    });
                } else {
                    wrap.classList.add('hidden');
                }
            };

            fillSection('new', etfData.new_buy, 'text-buy', '+', 'buy');
            fillSection('inc', etfData.increased, 'text-buy', '+', 'buy');
            fillSection('dec', etfData.decreased, 'text-sell', '-', 'sell');
            fillSection('out', etfData.sold_out, 'theme-text-dim', '', 'sell');
        }

        function handleSearch() {
            const val = document.getElementById('search-input').value.trim().toLowerCase();
            const normalView = document.getElementById('normal-view');
            const searchView = document.getElementById('search-view');
            const aiView = document.getElementById('ai-agent-view');
            const sfContainer = document.getElementById('sector-flow-container');
            
            if (currentETF === 'AI_AGENT') {
                normalView.classList.add('hidden');
                searchView.classList.add('hidden');
                aiView.classList.remove('hidden');
                sfContainer.classList.add('hidden');
                return;
            }
            if (!val) {
                normalView.classList.remove('hidden');
                searchView.classList.add('hidden');
                aiView.classList.add('hidden');
                sfContainer.classList.remove('hidden');
                updateDashboard(); 
                return;
            }

            normalView.classList.add('hidden');
            aiView.classList.add('hidden');
            sfContainer.classList.add('hidden');
            searchView.classList.remove('hidden');

            const resultsContainer = document.getElementById('search-results-list');
            resultsContainer.innerHTML = '';

            const dataToday = db[currentDate] || {};
            let found = false;

            Object.keys(dataToday).forEach(etf => {
                if (etf === FAMILY_TAB) return; 
                const d = dataToday[etf];
                let actions = [];
                [...(d.new_buy||[])].forEach(i => { if(i.name.toLowerCase().includes(val)) actions.push({name: i.name, act: 'INIT', diff: i.diff, sign: '+'}); });
                [...(d.increased||[])].forEach(i => { if(i.name.toLowerCase().includes(val)) actions.push({name: i.name, act: 'ACC', diff: i.diff, sign: '+'}); });
                [...(d.decreased||[])].forEach(i => { if(i.name.toLowerCase().includes(val)) actions.push({name: i.name, act: 'RED', diff: i.diff, sign: '-'}); });
                [...(d.sold_out||[])].forEach(i => { if(i.name.toLowerCase().includes(val)) actions.push({name: i.name, act: 'LIQ', diff: i.diff, sign: '-'}); });

                actions.forEach(a => {
                    found = true;
                    const isBuy = a.sign === '+';
                    const colorClass = isBuy ? 'text-buy' : 'text-sell';
                    const actStyle = a.act === 'LIQ' ? 'theme-text-dim theme-border' : `border border-current ${colorClass}`;
                    
                    const sparkline = getSparklineHTML(etf, a.name);

                    resultsContainer.innerHTML += `
                    <div class="flex justify-between items-center py-3 border-b theme-border row-hover px-2 -mx-2 transition-colors">
                        <div class="flex items-center gap-3 flex-1 min-w-0">
                            <span class="font-bold theme-text text-[14px] w-14 font-mono flex-shrink-0">${etf}</span>
                            <span class="theme-text text-[14px] truncate">${a.name}</span>
                            <span class="px-1.5 py-[1px] rounded-sm text-[10px] font-mono flex-shrink-0 ${actStyle}">${a.act}</span>
                            ${sparkline}
                        </div>
                        <span class="${colorClass} font-mono font-bold text-[14px] flex-shrink-0 ml-2">${a.sign}${a.diff.toLocaleString()}</span>
                    </div>`;
                });
            });

            if (!found) {
                resultsContainer.innerHTML = '<div class="py-12 text-center theme-text-dim font-mono text-sm">> RADAR_EMPTY</div>';
            }
        }

        const AI_PROMPT_TEMPLATE = `1. 財務報表分析：
分析 [TICKER] 過去 5 年的財務報表。重點拆解：營收增長、淨利趨勢、自由現金流、利潤率與債務水平。請說明該公司的財務狀況是在增強還是轉弱？

2. 估值分析：
對 [TICKER] 進行估值分析。包含：本益比 (P/E) 比較、現金流折現 (DCF) 估算、行業平均估值對比，最後給出該股是被低估還是高估的結論。

3. 成長潛力分析：
分析 [TICKER] 的成長潛力。考慮市場規模、產業增長率、新產品線、以及其在 AI 或新技術上的優勢，預測未來 5-10 年的成長空間。

4. 多空對峙辯論：
請模擬兩位分析師針對 [TICKER] 進行辯論。一位看多 (Bull)，一位看空 (Bear)。兩人必須提出有數據支持的論點，最後給出一個平衡的總結。

5. 投資建議評估：
評估今天是否該買入 [TICKER]。給出短期 (1 年) 與長期 (5 年以上) 展望、主要催化劑與風險，最後給出明確建議：買入、持有或避開。`;

        function generateAIPrompt() {
            const ticker = document.getElementById('ai-ticker-input').value.trim() || '2330';
            const output = document.getElementById('ai-prompt-output');
            output.value = AI_PROMPT_TEMPLATE.replace(/\[TICKER\]/g, ticker);
        }

        window.onload = init;
    </script>
</body>
</html>"""

def main():
    print("[INFO] 開始產出 Web Dashboard (v6.1 雙軌決策完全體)...")
    db = process_all_data()
    
    json_str = json.dumps(db, ensure_ascii=False)
    final_html = HTML_TEMPLATE.replace("__DB_JSON__", json_str)
    
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(final_html)
        
    print(f"[OK] 成功產出 {OUTPUT_FILE}")

if __name__ == "__main__":
    main()