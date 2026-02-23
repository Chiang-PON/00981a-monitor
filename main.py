"""main.py — 主動式 ETF 家族監控系統 v2.0

追蹤 00980A / 00981A / 00982A 的每日持股變化，
透過 LINE 推播分析報告。

功能：
- 每日持股異動偵測（新進場 / 離場 / 加碼 / 減碼）
- 權重變化追蹤（weight% 變化）
- N 日趨勢分析（連續加碼 / 減碼偵測）
- 週報模式（每週五彙整整週異動）
- 假日偵測（週末 + 國定假日自動跳過）
- LINE 訊息自動分割（5000 字限制）
- 前十大持股排行

用法：
    python main.py              # 每日報告（預設）
    python main.py --mode weekly # 週報模式
    python main.py --force       # 強制執行（忽略假日）
"""

import argparse
import glob
import logging
import os
import re
import time
from datetime import datetime, timedelta
from typing import Optional

import pandas as pd
import requests
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager

# ═══════════════════════════════
# Logging
# ═══════════════════════════════
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("ETF-Monitor")

# ═══════════════════════════════
# 常數設定
# ═══════════════════════════════
LINE_TOKEN: str = os.environ.get("LINE_TOKEN", "")
ETF_LIST: list[str] = ["00980A", "00981A", "00982A"]
URL_TEMPLATE: str = "https://www.pocket.tw/etf/tw/{}/fundholding/"
HISTORY_DIR: str = "history"
LINE_MAX_LENGTH: int = 4800  # 預留 200 字空間
CRAWL_MAX_RETRIES: int = 2
CRAWL_PAGE_LOAD_WAIT: float = 5.0
CRAWL_SCROLL_WAIT: float = 3.0
CRAWL_SCROLL_ROUNDS: int = 3
TREND_LOOKBACK_DAYS: int = 5  # N 日趨勢回顧天數
CONTINUOUS_THRESHOLD: int = 3  # 連續 N 天才標示

# 台灣國定假日（2026 年，可每年更新）
TW_HOLIDAYS_2026: set[str] = {
    "2026-01-01",  # 元旦
    "2026-01-26",  # 除夕（農曆）
    "2026-01-27",  # 春節
    "2026-01-28",  # 春節
    "2026-01-29",  # 春節
    "2026-01-30",  # 春節（彈性）
    "2026-02-02",  # 春節（彈性）
    "2026-02-27",  # 和平紀念日（彈性）
    "2026-02-28",  # 和平紀念日
    "2026-04-03",  # 兒童節（彈性）
    "2026-04-04",  # 清明節
    "2026-04-05",  # 兒童節
    "2026-04-06",  # 兒童節（彈性）
    "2026-05-01",  # 勞動節
    "2026-06-19",  # 端午節
    "2026-09-25",  # 中秋節
    "2026-10-10",  # 國慶日
}

# ═══════════════════════════════
# 名稱淨化
# ═══════════════════════════════
NAME_REPLACEMENTS: dict[str, str] = {
    "台灣積體電路製造": "台積電",
    "鴻海精密工業": "鴻海",
    "台達電子工業": "台達電",
    "緯穎科技服務": "緯穎",
    "聯發科技": "聯發科",
    "金像電子（股）公司": "金像電",
    "金像電子": "金像電",
    "廣達電腦": "廣達",
    "智邦科技": "智邦",
    "奇鋐科技": "奇鋐",
    "鴻勁精密": "鴻勁",
    "台燿科技": "台燿",
    "群聯電子": "群聯",
    "健策精密工業": "健策",
    "旺矽科技": "旺矽",
    "勤誠興業": "勤誠",
    "中國信託金融控股": "中信金",
    "京元電子": "京元電",
    "緯創資通": "緯創",
    "文曄科技": "文曄",
    "欣銓科技": "欣銓",
    "致伸科技": "致伸",
    "南亞科技": "南亞科",
    "健鼎科技": "健鼎",
    "凡甲科技": "凡甲",
    "崇越科技": "崇越",
    "瑞昱半導體": "瑞昱",
    "致茂電子": "致茂",
    "鈊象電子": "鈊象",
    "高力熱處理工業": "高力",
    "台光電子材料": "台光電",
    "華城電機": "華城",
    "穎崴科技": "穎崴",
    "中華精測科技": "精測",
    "川湖科技": "川湖",
    "亞德客國際集團": "亞德客",
    "玉山金融控股": "玉山金",
    "富邦金融控股": "富邦金",
    "華邦電子": "華邦電",
    "大成不銹鋼工業": "大成鋼",
    "聚陽實業": "聚陽",
    "達興材料": "達興材",
    "技嘉科技": "技嘉",
    "貿聯控股（BizLink Holding In": "貿聯-KY",
    "寶雅國際": "寶雅",
    "創意電子": "創意",
    "光紅建聖": "光紅建聖",
}

STRIP_PATTERN = re.compile(
    r"（股）公司|\(股\)公司|股份有限公司|有限公司|科技|工業|電子|電腦"
)


def clean_stock_name(name: str) -> str:
    """淨化股票名稱，移除冗長公司後綴。"""
    name = name.replace("*", "").strip()
    for old, new in NAME_REPLACEMENTS.items():
        if old in name:
            return new
    name = STRIP_PATTERN.sub("", name)
    return name.strip()


# ═══════════════════════════════
# 假日偵測
# ═══════════════════════════════
def is_trading_day(date: Optional[datetime] = None) -> bool:
    """判斷是否為交易日（排除週末 + 國定假日）。"""
    if date is None:
        date = datetime.now()
    # 週末
    if date.weekday() >= 5:
        return False
    # 國定假日
    date_str = date.strftime("%Y-%m-%d")
    if date_str in TW_HOLIDAYS_2026:
        return False
    return True


# ═══════════════════════════════
# 爬蟲功能（含重試機制）
# ═══════════════════════════════
def fetch_data(etf_code: str) -> list[dict]:
    """爬取 ETF 持股資料，含自動重試。"""
    target_url = URL_TEMPLATE.format(etf_code)

    for attempt in range(CRAWL_MAX_RETRIES + 1):
        driver = None
        try:
            logger.info("[%s] 啟動爬蟲 (第 %d 次)...", etf_code, attempt + 1)

            chrome_options = Options()
            chrome_options.add_argument("--headless")
            chrome_options.add_argument("--disable-gpu")
            chrome_options.add_argument("--window-size=1920,1080")
            chrome_options.add_argument("--no-sandbox")
            chrome_options.add_argument("--disable-dev-shm-usage")
            chrome_options.add_argument(
                "user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            )

            service = Service(ChromeDriverManager().install())
            driver = webdriver.Chrome(service=service, options=chrome_options)
            driver.get(target_url)
            time.sleep(CRAWL_PAGE_LOAD_WAIT)

            # 捲動載入
            last_height = driver.execute_script("return document.body.scrollHeight")
            for _ in range(CRAWL_SCROLL_ROUNDS):
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(CRAWL_SCROLL_WAIT)
                new_height = driver.execute_script("return document.body.scrollHeight")
                if new_height == last_height:
                    break
                last_height = new_height

            soup = BeautifulSoup(driver.page_source, "html.parser")
            table = soup.find("table", class_="cm-table__table")
            data: list[dict] = []

            if table:
                tbody = table.find("tbody")
                if tbody:
                    rows = tbody.find_all("tr")
                    for row in rows:
                        cols = row.find_all("td")
                        if len(cols) >= 4:
                            code = cols[0].text.strip()
                            name_tag = cols[1].find("h2")
                            name = name_tag.text.strip() if name_tag else cols[1].text.strip()
                            weight_str = cols[2].text.strip().replace("%", "")
                            shares_str = cols[3].text.strip().replace(",", "")
                            if code.isdigit():
                                try:
                                    data.append({
                                        "code": code,
                                        "name": name,
                                        "weight": float(weight_str),
                                        "shares": int(shares_str),
                                    })
                                except (ValueError, TypeError) as e:
                                    logger.warning("[%s] 資料轉換失敗: code=%s, err=%s", etf_code, code, e)

            if data:
                logger.info("[%s] 成功抓取 %d 筆持股", etf_code, len(data))
                return data

            logger.warning("[%s] 抓取到 0 筆資料", etf_code)

        except Exception as e:
            logger.error("[%s] 爬蟲錯誤 (第 %d 次): %s", etf_code, attempt + 1, e)
        finally:
            if driver:
                try:
                    driver.quit()
                except Exception:
                    pass

        if attempt < CRAWL_MAX_RETRIES:
            wait = 5 * (attempt + 1)
            logger.info("[%s] 等待 %d 秒後重試...", etf_code, wait)
            time.sleep(wait)

    logger.error("[%s] 爬蟲全部失敗", etf_code)
    return []


# ═══════════════════════════════
# LINE 通知（自動分割）
# ═══════════════════════════════
def send_line_message(msg: str) -> None:
    """發送 LINE 訊息，超過長度自動分割。"""
    if not LINE_TOKEN:
        logger.warning("LINE_TOKEN 未設定，跳過推播")
        return

    url = "https://api.line.me/v2/bot/message/broadcast"
    headers = {
        "Authorization": f"Bearer {LINE_TOKEN}",
        "Content-Type": "application/json",
    }

    # 自動分割
    chunks = _split_message(msg)
    logger.info("共 %d 則訊息待發送", len(chunks))

    for i, chunk in enumerate(chunks):
        payload = {"messages": [{"type": "text", "text": chunk}]}
        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=10)
            if resp.ok:
                logger.info("✅ 第 %d/%d 則發送成功", i + 1, len(chunks))
            else:
                logger.error("❌ 第 %d/%d 則發送失敗: %s %s", i + 1, len(chunks), resp.status_code, resp.text)
        except Exception as e:
            logger.error("LINE 連線錯誤: %s", e)


def _split_message(msg: str, max_len: int = LINE_MAX_LENGTH) -> list[str]:
    """將長訊息按段落分割，每段不超過 max_len。"""
    if len(msg) <= max_len:
        return [msg]

    chunks: list[str] = []
    # 用分隔線切割
    separator = "━━━━━━━━━━━━━━━"
    blocks = msg.split(separator)

    current = ""
    for block in blocks:
        test = current + separator + block if current else block
        if len(test) <= max_len:
            current = test
        else:
            if current:
                chunks.append(current.strip())
            current = block
    if current:
        chunks.append(current.strip())

    return chunks if chunks else [msg[:max_len]]


# ═══════════════════════════════
# 歷史資料讀取
# ═══════════════════════════════
def _get_history_files(etf_code: str) -> list[str]:
    """取得某 ETF 所有歷史 CSV，按日期排序。"""
    return sorted(glob.glob(os.path.join(HISTORY_DIR, f"{etf_code}_*.csv")))


def _load_csv(filepath: str) -> Optional[pd.DataFrame]:
    """安全讀取 CSV。"""
    try:
        return pd.read_csv(filepath, dtype={"code": str})
    except Exception as e:
        logger.warning("讀取 CSV 失敗: %s (%s)", filepath, e)
        return None


# ═══════════════════════════════
# 單一 ETF 處理
# ═══════════════════════════════
def process_etf(etf_code: str) -> Optional[dict]:
    """爬取、儲存、比對單一 ETF 的持股變化。"""
    logger.info("======== 開始處理 %s ========", etf_code)
    today_str = datetime.now().strftime("%Y-%m-%d")
    today_file = os.path.join(HISTORY_DIR, f"{etf_code}_{today_str}.csv")

    today_data = fetch_data(etf_code)
    if not today_data:
        return None

    today_df = pd.DataFrame(today_data)
    today_df.to_csv(today_file, index=False, encoding="utf-8-sig")
    logger.info("[%s] 已儲存 %s", etf_code, today_file)

    all_files = _get_history_files(etf_code)

    new_buy_list: list[str] = []
    sold_out_list: list[str] = []
    increased_list: list[tuple[str, int, float]] = []  # (name, shares_diff, weight_diff)
    decreased_list: list[tuple[str, int, float]] = []
    changes_dict: dict[str, int] = {}

    if len(all_files) >= 2:
        last_df = _load_csv(all_files[-2])
        if last_df is not None:
            today_codes = set(today_df["code"].astype(str))
            last_codes = set(last_df["code"].astype(str))
            common_codes = today_codes & last_codes

            # 新進場
            for c in today_codes - last_codes:
                row = today_df[today_df["code"].astype(str) == c].iloc[0]
                sheets = int(row["shares"] / 1000)
                name = clean_stock_name(row["name"])
                new_buy_list.append(f"　+ {name} ｜ {sheets:,} 張 ｜ {row['weight']:.2f}%")
                changes_dict[row["name"]] = sheets

            # 已離場
            for c in last_codes - today_codes:
                row = last_df[last_df["code"].astype(str) == c].iloc[0]
                sheets = int(row["shares"] / 1000)
                name = clean_stock_name(row["name"])
                sold_out_list.append(f"　- {name} ｜ 出清 {sheets:,} 張")
                changes_dict[row["name"]] = -sheets

            # 張數 + 權重異動
            for c in common_codes:
                row_now = today_df[today_df["code"].astype(str) == c].iloc[0]
                row_last = last_df[last_df["code"].astype(str) == c].iloc[0]

                shares_now = int(row_now["shares"] / 1000)
                shares_last = int(row_last["shares"] / 1000)
                shares_diff = shares_now - shares_last

                weight_diff = round(row_now["weight"] - row_last["weight"], 2)

                if shares_diff != 0:
                    changes_dict[row_now["name"]] = shares_diff
                    name = clean_stock_name(row_now["name"])
                    if shares_diff > 0:
                        increased_list.append((name, shares_diff, weight_diff))
                    else:
                        decreased_list.append((name, shares_diff, weight_diff))

    # 排序
    increased_list.sort(key=lambda x: x[1], reverse=True)
    decreased_list.sort(key=lambda x: x[1])

    # ── 組合訊息 ──
    msg = f"▪️ {etf_code}\n"
    msg += "┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈\n"

    has_action = False

    if new_buy_list:
        has_action = True
        msg += f"✦ [ 新進場 ]\n" + "\n".join(new_buy_list) + "\n\n"

    if sold_out_list:
        has_action = True
        msg += f"✖️ [ 已離場 ]\n" + "\n".join(sold_out_list) + "\n\n"

    if increased_list or decreased_list:
        has_action = True
        msg += "[ 張數異動 ]\n"
        if increased_list:
            msg += "🔺 加碼\n"
            for name, sd, wd in increased_list:
                wd_str = f"+{wd}" if wd > 0 else f"{wd}"
                msg += f"　+ {name} ｜ +{sd:,} 張 ({wd_str}%)\n"
        if decreased_list:
            msg += "🟩 減碼\n"
            for name, sd, wd in decreased_list:
                wd_str = f"+{wd}" if wd > 0 else f"{wd}"
                msg += f"　- {name} ｜ {sd:,} 張 ({wd_str}%)\n"
        msg += "\n"

    if not has_action:
        msg += "✔️ 今日籌碼無重大異動。\n\n"

    # 前十大持股
    msg += "[ 前十大持股 ]\n"
    sorted_df = today_df.sort_values(by="weight", ascending=False)
    for rank, (_, row) in enumerate(sorted_df.iterrows(), 1):
        if rank > 10:
            break
        sheets = int(row["shares"] / 1000)
        name = clean_stock_name(row["name"])
        msg += f"{rank:02d}. {name} ｜ {row['weight']:.2f}% ｜ {sheets:,} 張\n"

    return {
        "etf": etf_code,
        "df": today_df,
        "changes": changes_dict,
        "msg_string": msg.strip(),
    }


# ═══════════════════════════════
# N 日趨勢 + 連續加減碼偵測
# ═══════════════════════════════
def generate_trend_report(results: list[dict]) -> str:
    """分析各 ETF 過去 N 天的連續加碼/減碼趨勢。"""
    continuous_buy: list[str] = []
    continuous_sell: list[str] = []

    for etf_code in ETF_LIST:
        files = _get_history_files(etf_code)
        if len(files) < TREND_LOOKBACK_DAYS:
            continue

        recent_files = files[-TREND_LOOKBACK_DAYS:]
        dfs = [_load_csv(f) for f in recent_files]
        dfs = [df for df in dfs if df is not None]

        if len(dfs) < TREND_LOOKBACK_DAYS:
            continue

        # 追蹤每檔股票的連續方向
        all_codes: set[str] = set()
        for df in dfs:
            all_codes.update(df["code"].astype(str).tolist())

        for code in all_codes:
            daily_shares: list[Optional[int]] = []
            stock_name = ""
            for df in dfs:
                match = df[df["code"].astype(str) == code]
                if match.empty:
                    daily_shares.append(None)
                else:
                    daily_shares.append(int(match.iloc[0]["shares"] / 1000))
                    stock_name = match.iloc[0]["name"]

            if not stock_name:
                continue

            # 計算連續加碼/減碼天數
            consecutive_up = 0
            consecutive_down = 0
            for i in range(1, len(daily_shares)):
                if daily_shares[i] is None or daily_shares[i - 1] is None:
                    break
                diff = daily_shares[i] - daily_shares[i - 1]
                if diff > 0:
                    consecutive_up += 1
                elif diff < 0:
                    consecutive_down += 1
                else:
                    break  # 沒變就中斷

            name = clean_stock_name(stock_name)

            if consecutive_up >= CONTINUOUS_THRESHOLD:
                # 計算總增加
                first_valid = next(s for s in daily_shares if s is not None)
                last_valid = next(s for s in reversed(daily_shares) if s is not None)
                total_diff = last_valid - first_valid
                continuous_buy.append(
                    f"　🔥 {name}（{etf_code}）連 {consecutive_up} 天加碼 ｜ +{total_diff:,} 張"
                )

            if consecutive_down >= CONTINUOUS_THRESHOLD:
                first_valid = next(s for s in daily_shares if s is not None)
                last_valid = next(s for s in reversed(daily_shares) if s is not None)
                total_diff = last_valid - first_valid
                continuous_sell.append(
                    f"　❄️ {name}（{etf_code}）連 {consecutive_down} 天減碼 ｜ {total_diff:,} 張"
                )

    if not continuous_buy and not continuous_sell:
        return ""

    msg = "📈 [ 連續操作偵測 ]\n"
    if continuous_buy:
        msg += "持續加碼中：\n" + "\n".join(continuous_buy) + "\n"
    if continuous_sell:
        msg += "持續減碼中：\n" + "\n".join(continuous_sell) + "\n"

    return msg.strip()


# ═══════════════════════════════
# 家族彙總報告
# ═══════════════════════════════
def generate_summary_report(results: list[dict]) -> str:
    """跨 ETF 彙總分析：家族集體操作 + 核心重壓股。"""
    if not results:
        return ""

    # 統計跨 ETF 共同持股
    all_stocks: dict[str, list[float]] = {}
    for res in results:
        df = res["df"]
        for _, row in df.iterrows():
            all_stocks.setdefault(row["name"], []).append(row["weight"])

    common_holdings: list[tuple[str, float, int]] = []
    for name, weights in all_stocks.items():
        if len(weights) >= 2:
            avg_w = sum(weights) / len(weights)
            common_holdings.append((name, avg_w, len(weights)))
    common_holdings.sort(key=lambda x: x[1], reverse=True)

    # 集體加碼/減碼
    collective_buy: list[str] = []
    collective_sell: list[str] = []
    all_changed_stocks: set[str] = set()
    for res in results:
        all_changed_stocks.update(res["changes"].keys())

    for stock in all_changed_stocks:
        up_count = 0
        down_count = 0
        for res in results:
            shares_diff = res["changes"].get(stock, 0)
            if shares_diff > 0:
                up_count += 1
            elif shares_diff < 0:
                down_count += 1

        name = clean_stock_name(stock)
        if up_count >= 2:
            collective_buy.append(f"{name} (x{up_count})")
        if down_count >= 2:
            collective_sell.append(f"{name} (x{down_count})")

    today_str = datetime.now().strftime("%Y-%m-%d")
    weekday_names = ["一", "二", "三", "四", "五", "六", "日"]
    weekday = weekday_names[datetime.now().weekday()]

    msg = f"⚡ 主動式 ETF 家族彙總\n"
    msg += f"📅 {today_str}（{weekday}）\n"
    msg += "┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈\n"

    if collective_buy:
        msg += "🔺 [ 家族集體加碼 ]\n" + "、".join(collective_buy) + "\n\n"
    if collective_sell:
        msg += "🟩 [ 家族集體減碼 ]\n" + "、".join(collective_sell) + "\n\n"
    if not collective_buy and not collective_sell:
        msg += "➖ 今日無明顯集體操作方向。\n\n"

    msg += "[ 家族核心重壓股 ]\n"
    for i, (name, avg_w, count) in enumerate(common_holdings[:5], 1):
        name_clean = clean_stock_name(name)
        msg += f"{i:02d}. {name_clean} ｜ {avg_w:.2f}% ｜ 共 {count} 檔持有\n"

    return msg.strip()


# ═══════════════════════════════
# 週報模式
# ═══════════════════════════════
def generate_weekly_report() -> str:
    """彙整本週（週一～今天）所有 ETF 的異動。"""
    today = datetime.now()
    # 找到本週一
    monday = today - timedelta(days=today.weekday())
    monday_str = monday.strftime("%Y-%m-%d")
    today_str = today.strftime("%Y-%m-%d")

    msg = f"📊 週報 ({monday_str} ~ {today_str})\n"
    msg += "━━━━━━━━━━━━━━━\n\n"

    for etf_code in ETF_LIST:
        files = _get_history_files(etf_code)
        # 篩選本週的檔案
        week_files = [f for f in files if _extract_date(f) >= monday_str]

        if len(week_files) < 2:
            msg += f"▪️ {etf_code}：本週資料不足\n\n"
            continue

        first_df = _load_csv(week_files[0])
        last_df = _load_csv(week_files[-1])

        if first_df is None or last_df is None:
            continue

        first_codes = set(first_df["code"].astype(str))
        last_codes = set(last_df["code"].astype(str))

        # 本週新進場
        new_in = last_codes - first_codes
        # 本週離場
        gone_out = first_codes - last_codes
        # 共同持股的張數變化
        common = first_codes & last_codes

        week_increased: list[tuple[str, int, float]] = []
        week_decreased: list[tuple[str, int, float]] = []

        for c in common:
            row_now = last_df[last_df["code"].astype(str) == c].iloc[0]
            row_start = first_df[first_df["code"].astype(str) == c].iloc[0]

            sheets_diff = int(row_now["shares"] / 1000) - int(row_start["shares"] / 1000)
            weight_diff = round(row_now["weight"] - row_start["weight"], 2)

            if sheets_diff != 0:
                name = clean_stock_name(row_now["name"])
                if sheets_diff > 0:
                    week_increased.append((name, sheets_diff, weight_diff))
                else:
                    week_decreased.append((name, sheets_diff, weight_diff))

        week_increased.sort(key=lambda x: x[1], reverse=True)
        week_decreased.sort(key=lambda x: x[1])

        msg += f"▪️ {etf_code}（共 {len(week_files)} 個交易日）\n"
        msg += "┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈\n"

        if new_in:
            new_names = []
            for c in new_in:
                match = last_df[last_df["code"].astype(str) == c]
                if not match.empty:
                    new_names.append(clean_stock_name(match.iloc[0]["name"]))
            if new_names:
                msg += f"✦ 本週新進場：{'、'.join(new_names)}\n"

        if gone_out:
            gone_names = []
            for c in gone_out:
                match = first_df[first_df["code"].astype(str) == c]
                if not match.empty:
                    gone_names.append(clean_stock_name(match.iloc[0]["name"]))
            if gone_names:
                msg += f"✖️ 本週離場：{'、'.join(gone_names)}\n"

        if week_increased:
            msg += "🔺 本週加碼 TOP5：\n"
            for name, sd, wd in week_increased[:5]:
                msg += f"　+ {name} ｜ +{sd:,} 張\n"

        if week_decreased:
            msg += "🟩 本週減碼 TOP5：\n"
            for name, sd, wd in week_decreased[:5]:
                msg += f"　- {name} ｜ {sd:,} 張\n"

        if not new_in and not gone_out and not week_increased and not week_decreased:
            msg += "✔️ 本週無顯著異動\n"

        msg += "\n"

    return msg.strip()


def _extract_date(filepath: str) -> str:
    """從檔名提取日期字串。"""
    basename = os.path.basename(filepath)
    # 格式: ETF_CODE_YYYY-MM-DD.csv
    match = re.search(r"(\d{4}-\d{2}-\d{2})", basename)
    return match.group(1) if match else ""


# ═══════════════════════════════
# 主程式
# ═══════════════════════════════
def main() -> None:
    parser = argparse.ArgumentParser(description="主動式 ETF 家族監控系統")
    parser.add_argument(
        "--mode",
        choices=["daily", "weekly"],
        default="daily",
        help="執行模式: daily=每日報告, weekly=週報",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="強制執行（忽略假日偵測）",
    )
    args = parser.parse_args()

    # 假日偵測
    if not args.force and not is_trading_day():
        logger.info("🏖️ 今天不是交易日，跳過執行")
        return

    # 確保 history 目錄存在
    os.makedirs(HISTORY_DIR, exist_ok=True)

    if args.mode == "weekly":
        logger.info("📊 執行週報模式")
        report = generate_weekly_report()
        if report:
            send_line_message(report)
        return

    # ── 每日模式 ──
    logger.info("📋 執行每日報告模式")
    results: list[dict] = []

    for etf in ETF_LIST:
        try:
            res = process_etf(etf)
            if res:
                results.append(res)
        except Exception as e:
            logger.error("處理 %s 時發生錯誤: %s", etf, e, exc_info=True)

    final_blocks: list[str] = []

    # 1. 家族彙總（需至少 2 檔有資料）
    if len(results) >= 2:
        try:
            summary = generate_summary_report(results)
            if summary:
                final_blocks.append(summary)
        except Exception as e:
            logger.error("彙總報告錯誤: %s", e, exc_info=True)

    # 2. 連續加減碼偵測
    try:
        trend = generate_trend_report(results)
        if trend:
            final_blocks.append(trend)
    except Exception as e:
        logger.error("趨勢報告錯誤: %s", e, exc_info=True)

    # 3. 各 ETF 報告
    for res in results:
        final_blocks.append(res["msg_string"])

    # 發送
    if final_blocks:
        separator = "\n\n━━━━━━━━━━━━━━━\n\n"
        final_message = separator.join(final_blocks)
        send_line_message(final_message)
    else:
        logger.warning("沒有任何資料可發送")
        send_line_message(
            f"⚠️ 主動式 ETF 監控\n"
            f"📅 {datetime.now().strftime('%Y-%m-%d')}\n\n"
            f"今日爬蟲全部失敗，請檢查資料來源。"
        )


if __name__ == "__main__":
    main()
