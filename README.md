# 政大社群輿情監控系統 (NCCU Threads Crisis Monitor)

## 📌 專案背景
本系統為專門為 **政大秘書處 (NCCU Secretariat)** 開發的實習專案，旨在透過 AI 自動化監控 Threads 平台上的校園動態與學生心聲。系統能即時攔截並評估潛在的公關危機，協助校方在重大爭議（如校園安全、住宿環境、學權問題）發酵前掌握先機並進行妥善處置。

## 🚀 核心功能
* **多維度爬蟲**：支援精準關鍵字與政大專屬黑話（如：`種茶大學`、`自強七舍`、`會研所` 等）的自動巡邏與掃描。
* **AI 危機評分**：無縫整合 Google Gemini API，自動深度判讀貼文情緒走向與潛在公關危機等級（1-10 分），並針對高風險議題給予加權預警。
* **人工通報入口**：提供友善的互動介面，支援管理員手動輸入特定單篇貼文網址，系統將強制破除反爬蟲機制，即時將其強制作為重點追蹤對象。
* **動態 Dashboard**：即時視覺化排行榜、數據統計圖表與輿情溫度的動態警報標籤（如 `🔥 持續監控中`、`炎上預警`）。

## 🛠️ 技術棧 (Tech Stack)
* **後端架構**：`Python`, `Flask`
* **自動化爬蟲**：`Playwright` (搭配 Stealth 隱蔽模組)
* **AI 分析決策**：`Google Gemini 2.5 Pro / Flash` (透過 `google-genai` 與 Pydantic 結構解析)
* **前端與數據視覺化**：原生 HTML/JS 搭配 `Chart.js` 及 Bootstrap

## 📦 安裝指南
本專案依賴嚴格的 Python 隔離環境運行，請按照以下步驟部署：

### 1. 下載本專案
```bash
git clone https://github.com/chanweiich/threads_moniter.git
cd threads_moniter
```

### 2. 建立並啟動虛擬環境 (.venv)
請在專案根目錄中執行：

`Mac`
```bash
python3 -m venv .venv
source .venv/bin/activate
```

`Windows`
```bash
py -m venv .venv
.venv\Scripts\activate
# 確保名稱一致(複製一份python.exe，命名為 python3.exe)
copy .venv\Scripts\python.exe .venv\Scripts\python3.exe
```

### 3. 安裝套件依賴與瀏覽器內核
```bash
pip install -r requirements.txt
playwright install chromium
```

### 4. 設定環境變數 (.env)
本系統目前優先採用 **Groq API (Llama 3)** 以確保極速分析與穩定性。請在專案根目錄建立 `.env` 檔案，寫入以下內容：

```ini
GROQ_API_KEY=您的_Groq_API_金鑰
GEMINI_API_KEY=您的_Gemini_API_金鑰 (備援用)
```

> **🔑 取得 API Key**：您可以前往 [Groq Console](https://console.groq.com/keys) 免費註冊並取得金鑰。

**🚨 【安全性警語】：請務必確保 `.env` 檔案保留在本地，絕對不可推送到 GitHub。**

**待修改**
```
python hourly_scheduler.py
python analyze_crisis.py
cd dashboard
python app.py
```

### 5. 運行系統
* **啟動爬蟲與分析排程器**
```bash
python3 analyze_crisis.py
python3 track_trends.py
python3 scheduler.py
```
若未曾於電腦登入threads：

彈出瀏覽視窗時，請在該視窗另開一分頁輸入threads.net，輸入帳號登入threads。

* **啟動網頁戰情室 (Dashboard)**
另外開啟一個terminal
```bash
cd dashboard
python3 app.py
```
接著在瀏覽器中開啟 `http://127.0.0.1:5000`。

## ⚠️ 免責聲明
本系統僅供國立政治大學校園研究、實習專案與公關趨勢監測使用。所擷取之數據僅作為內部決策輔助，請嚴格遵守相關社群平台（Meta / Threads）之使用規範與隱私條款，嚴禁將爬蟲數據用於非法窺探或商業營利。

---

## 📂 每小時爬蟲模組 (Hourly Scraper)

此模組每小時自動爬取 Threads 貼文，並存入 SQLite 資料庫供其他組員使用。

### 🗂️ 相關檔案

| 檔案 | 說明 |
|------|------|
| `hourly_scraper.py` | 爬蟲主程式 |
| `hourly_scheduler.py` | 排程執行入口（給 Windows 工作排程器用） |
| `db_utils.py` | 資料庫查詢工具 |
| `threads_posts.db` | SQLite 資料庫檔案 |

### 🗄️ 資料庫結構 (`posts` 資料表)

| 欄位 | 類型 | 說明 |
|------|------|------|
| `id` | INTEGER | 主鍵 (自動遞增) |
| `url` | TEXT | 貼文連結 (唯一值) |
| `author` | TEXT | 帳號名稱 |
| `content` | TEXT | 貼文內容 |
| `post_date` | TEXT | 上傳時間 |
| `likes` | INTEGER | 愛心數 |
| `comments` | INTEGER | 留言數 |
| `reposts` | INTEGER | 轉發數 |
| `shares` | INTEGER | 分享數 |
| `created_at` | TEXT | 首次爬取時間 |
| `updated_at` | TEXT | 最後更新時間 |

### 🚀 執行方式

#### 手動執行一次
```
python -m venv .venv  
.venv\Scripts\activate
python hourly_scheduler.py
```

#### 首次執行需登入
1. 執行後瀏覽器會自動開啟
2. 如果偵測到未登入，終端機會提示你手動登入
3. 在瀏覽器中用 IG 帳號登入 Threads
4. 登入完成後，回到終端機按 **Enter** 繼續
5. 登入狀態會保存在 `browser_data/` 資料夾，之後不用重新登入

#### 設定 Windows 工作排程器（每小時自動執行）
1. 開啟「工作排程器」(`taskschd.msc`)
2. 點選「建立基本工作」
3. 設定觸發程序：每天 → 每隔 **1 小時** 重複
4. 設定動作：
   - 程式：`C:\Users\ggc\Desktop\threads_moniter\.venv\Scripts\python.exe`
   - 引數：`hourly_scheduler.py`
   - 起始位置：`C:\Users\ggc\Desktop\threads_moniter`

### 📊 如何取得資料

#### 使用 GUI 工具
推薦使用 [TablePlus](https://tableplus.com/) 或 [DB Browser for SQLite](https://sqlitebrowser.org/)：
1. 下載並安裝
2. 選擇 SQLite 連線
3. 開啟 `threads_posts.db` 檔案
4. 即可視覺化瀏覽與查詢資料


### 📋 給 AI 分析的說明

AI 分析可建立 `post_analysis` 資料表：

```sql
CREATE TABLE post_analysis (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    post_url TEXT UNIQUE,           -- 關聯 posts.url
    summary TEXT,                   -- 摘要
    sentiment TEXT,                 -- 情緒 ('正面', '中立', '負面')
    crisis_score INTEGER,           -- 危機分數 (1-10)
    analyzed_at TEXT DEFAULT CURRENT_TIMESTAMP
);
```

查詢範例（JOIN 兩張表）：
```sql
SELECT p.*, a.summary, a.sentiment, a.crisis_score
FROM posts p
LEFT JOIN post_analysis a ON p.url = a.post_url
ORDER BY p.updated_at DESC;
```
