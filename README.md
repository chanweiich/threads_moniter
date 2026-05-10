# 政大社群輿情監控系統 (NCCU Threads Crisis Monitor)

## 📌 專案背景
本系統為專門為 **政大秘書處 (NCCU Secretariat)** 開發的實習專案，旨在透過 AI 自動化監控 Threads 平台上的校園動態與學生心聲。系統能即時攔截並評估潛在的公關危機，協助校方在重大爭議（如校園安全、住宿環境、學權問題）發酵前掌握先機並進行妥善處置。

## 🚀 核心功能
* **定時關鍵字爬蟲**：每小時自動搜尋關鍵字（含政大專屬黑話如 `種茶大學`、`自強七舍`、`會研所`），抓取 24 小時內新貼文並存入 SQLite。
* **指標即時更新**：每小時重新訪問近 3 天所有貼文，更新 likes / 回覆 / 轉貼 / 分享數。
* **AI 危機評分**：整合 Google Gemini API，自動分析貼文情緒與危機等級（0–5 分），僅對負面貼文評 1–5 分，正面/中立固定為 0。
* **趨勢追蹤**：每 6 小時對 crisis_score ≥ 3 的高風險貼文執行深度趨勢分析，結果存入 `trend_analysis` 表。
* **動態 Dashboard**：即時視覺化排行榜、數據統計圖表與輿情溫度警報標籤。

## 🛠️ 技術棧 (Tech Stack)
* **後端架構**：`Python`, `Flask`
* **資料庫**：`SQLite` (`threads_posts.db`)
* **自動化爬蟲**：`Playwright` (Chromium，持久化 browser session)
* **AI 分析決策**：`Google Gemini 2.5 Flash` (透過 `google-genai` 與 Pydantic 結構解析)
* **前端與數據視覺化**：原生 HTML/JS 搭配 `Chart.js` 及 Bootstrap

## 🗂️ 專案結構
```
threads_moniter/
├── hourly_crawler/
│   ├── hourly_scheduler.py   # 排程器：每小時呼叫 scraper + update，每 6 小時呼叫 trend
│   ├── hourly_scraper.py     # 爬取搜尋結果新貼文，寫入 DB 並進行危機分析
│   └── db_utils.py
├── dashboard/
|   ├── templates/
|   |   └──index.html         # 操作介面模板
│   └── app.py                # Flask Dashboard 主程式
├── hourly_update.py          # 更新近 3 天貼文的 likes/回覆/轉貼/分享
├── trend_update.py           # 高風險貼文趨勢分析（每 6 小時）
├── nccu_risk_keywords.json   # 搜尋關鍵字設定
├── threads_posts.db          # SQLite 資料庫
├── browser_data/             # Playwright 持久化登入 session
├── logs/                     # hourly_scheduler.log
├── requirements.txt
└──note.md                    # 紀錄hourly_scheduler.py, hourly_scraper.py, hourly_update.py, trend_update.py 之間的關係、各自的職責、負責產出的table
```


## 📦 安裝指南

若未曾登入過 Threads，請先手動啟動瀏覽器登入一次，登入狀態會保存在 `browser_data/` 資料夾。

### **`Mac`**

1. 下載本專案
```bash
git clone https://github.com/chanweiich/threads_moniter.git
cd threads_moniter
```

2. 建立並啟動虛擬環境
```bash
python3 -m venv .venv
source .venv/bin/activate
```

3. 安裝依賴套件與瀏覽器
```bash
pip install -r requirements.txt
playwright install chromium
```

4. 設定環境變數 (.env)

在專案根目錄建立 `.env` 檔案：
```bash
GEMINI_API_KEY=您的_Gemini_API_金鑰
```
> **🔑 取得 API Key**：前往 [Google AI Studio](https://aistudio.google.com/apikey) 免費申請。

> **🚨 【安全性警語】：請務必確保 `.env` 檔案保留在本地，絕對不可推送到 GitHub。**

5. 設定 Mac 排程器（cron）
```bash
# 建立設定腳本
nano setup_cron.sh

# 貼上以下內容
PROJECT_ROOT="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PYTHON_PATH="$PROJECT_ROOT/.venv/bin/python"
SCHEDULER_PATH="$PROJECT_ROOT/hourly_crawler/hourly_scheduler.py"
(crontab -l 2>/dev/null; echo "0 * * * * $PYTHON_PATH $SCHEDULER_PATH") | crontab -
echo "✅ Cron 任務已設定，每小時執行一次"

# 儲存後賦予執行權限並執行
chmod +x setup_cron.sh
./setup_cron.sh
```

6. 啟動 Dashboard
```bash
cd dashboard
python app.py
```
接著在瀏覽器中開啟 `http://127.0.0.1:5000`

---

### **`Windows`**

1. 下載本專案
```bash
git clone https://github.com/chanweiich/threads_moniter.git
cd threads_moniter
```

2. 建立並啟動虛擬環境
```bash
py -m venv .venv
.venv\Scripts\activate
```

3. 安裝依賴套件與瀏覽器
```bash
pip install -r requirements.txt
playwright install chromium
```

4. 設定環境變數 (.env)

在專案根目錄建立 `.env` 檔案：
```
GEMINI_API_KEY=您的_Gemini_API_金鑰
```
> **🔑 取得 API Key**：前往 [Google AI Studio](https://aistudio.google.com/apikey) 免費申請。

> **🚨 【安全性警語】：請務必確保 `.env` 檔案保留在本地，絕對不可推送到 GitHub。**

5. 設定 Windows 工作排程器
- 開啟「工作排程器」(`taskschd.msc`)
- 點選「建立基本工作」
- 設定觸發程序：每天 → 每隔 1 小時 重複
- 設定動作（路徑請依實際安裝位置調整）：
  - 程式：`<專案根目錄>\.venv\Scripts\python.exe`
  - 引數：`hourly_scheduler.py`
  - 起始位置：`<專案根目錄>\hourly_crawler`

6. 啟動 Dashboard
```bash
cd dashboard
python app.py
```
接著在瀏覽器中開啟 `http://127.0.0.1:5000`

## ⚠️ 免責聲明
本系統僅供國立政治大學校園研究、實習專案與公關趨勢監測使用。所擷取之數據僅作為內部決策輔助，請嚴格遵守相關社群平台（Meta / Threads）之使用規範與隱私條款，嚴禁將爬蟲數據用於非法窺探或商業營利。
