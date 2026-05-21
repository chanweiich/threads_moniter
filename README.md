# 政大社群輿情監控系統 (NCCU Threads Crisis Monitor)

## 📌 專案背景
本系統為專門為 **政大秘書處 (NCCU Secretariat)** 開發的實習專案，旨在透過 AI 自動化監控 Threads 平台上的校園動態與學生心聲。系統能即時攔截並評估潛在的公關危機，協助校方在重大爭議（如校園安全、住宿環境、學權問題）發酵前掌握先機並進行妥善處置。

## 🚀 核心功能
* **雙階段爬蟲**：每小時執行。第一階段搜尋頁滾動收集貼文基礎指標；第二階段逐篇訪問單一貼文頁面，捕捉瀏覽量（views），並內建擬人化隨機延遲的反偵測機制。
* **指標即時更新**：每小時重新訪問近 3 天所有貼文，更新 likes / 回覆 / 轉貼 / 分享 / **瀏覽量**。
* **AI 危機評分**：整合 Google Gemini API，自動分析貼文情緒與危機等級（0–5 分），僅對負面貼文評 1–5 分，正面/中立固定為 0。
* **趨勢追蹤**：每 6 小時對 crisis_score ≥ 3 的高風險貼文執行深度趨勢分析，結果存入 `trend_analysis` 表。
* **動態 Dashboard**：視覺化互動熱度趨勢、情緒 P/N 比、文字雲（jieba 中文斷詞）、監控貼文列表（含瀏覽量）。

## 🛠️ 技術棧 (Tech Stack)
* **後端**：`Python`、`Flask`
* **資料庫**：`SQLite` (`threads_posts.db`)
* **爬蟲**：`Playwright` + Google Chrome（持久化 browser session，headless 模式），選配 `playwright-stealth`；發文時間透過解析 `<time datetime="...">` 屬性取得 ISO 8601 UTC 精確時間戳
* **中文斷詞**：`jieba`（文字雲後端分詞）
* **AI 分析**：`Google Gemini 2.5 Flash`（透過 `google-genai` 與 Pydantic 結構解析）
* **前端**：原生 HTML/JS、`Chart.js`、`wordcloud2.js`、Bootstrap 5

## 🗂️ 專案結構
```
threads_moniter/
├── hourly_crawler/
│   ├── hourly_scheduler.py   # 排程入口：呼叫 scraper → (等10秒) → update → (等10秒) → trend
│   ├── hourly_scraper.py     # 雙階段爬蟲：搜尋頁收集 + 單篇深訪抓瀏覽量 + 危機分析
│   ├── login.py              # 首次登入引導：開啟 Chrome 視窗讓使用者手動登入並儲存 session
│   └── db_utils.py
├── dashboard/
│   ├── templates/
│   │   └── index.html        # 儀表板前端
│   └── app.py                # Flask 主程式（含 /api/wordcloud jieba 斷詞端點）
├── hourly_update.py          # 更新近 3 天貼文的 likes / 回覆 / 轉貼 / 分享 / 瀏覽量
├── trend_update.py           # 高風險貼文趨勢分析（每 6 小時）
├── threads_posts.db          # SQLite 資料庫
├── browser_data/             # Playwright 持久化登入 session
├── logs/                     # hourly_scheduler.log
└── requirements.txt
```

## 🗄️ 資料庫結構

### `posts`
| 欄位 | 類型 | 說明 |
|------|------|------|
| `id` | INTEGER | 主鍵 |
| `url` | TEXT | 貼文連結（唯一值）|
| `author` | TEXT | 帳號名稱 |
| `content` | TEXT | 貼文內容 |
| `post_date` | TEXT | 發文時間（ISO 8601 UTC 或相對時間）|
| `likes` | INTEGER | 愛心數 |
| `comments` | INTEGER | 留言數 |
| `reposts` | INTEGER | 轉發數 |
| `shares` | INTEGER | 分享數 |
| `views` | INTEGER | 瀏覽量 |
| `created_at` | TEXT | 首次爬取時間 |
| `updated_at` | TEXT | 最後更新時間 |

### `post_analysis`
| 欄位 | 說明 |
|------|------|
| `post_id` | 關聯 posts.id |
| `post_url` | 關聯 posts.url |
| `summary` | AI 摘要 |
| `sentiment` | 情緒（正面／中立／負面）|
| `crisis_score` | 危機分數 0–5 |

### `post_snapshots`
每次更新時記錄快照，用於趨勢計算。含 `post_id`、`url`、`likes`、`comments`、`views`、`captured_at`。

### `trend_analysis`
crisis_score ≥ 3 的高風險貼文之深度趨勢分析結果。

## 📦 安裝指南

> **前置需求**：必須安裝 **Google Chrome**（爬蟲使用 `channel="chrome"` 啟動真實 Chrome，非 Playwright 內建 Chromium）。

### 共同步驟

1. 下載本專案
```bash
git clone https://github.com/chanweiich/threads_moniter.git
cd threads_moniter
```

2. 建立虛擬環境

`macOS / Linux`
```bash
python3.10 -m venv .venv
source .venv/bin/activate
```

`Windows`
```bash
py -3.10 -m venv .venv
.venv\Scripts\activate
```

3. 安裝依賴套件
```bash
pip install -r requirements.txt
# 選配：安裝反偵測模組（建議安裝）
pip install playwright-stealth
```

4. 設定環境變數

在專案根目錄建立 `.env`：
```
GEMINI_API_KEY=您的_Gemini_API_金鑰
```
> **🔑 取得 API Key**：前往 [Google AI Studio](https://aistudio.google.com/apikey) 免費申請。

> **🚨 請勿將 `.env` 推送至 GitHub。**

5. 首次登入 Threads

爬蟲預設以 headless 模式執行，首次需透過 `login.py` 完成登入，session 會保存到 `browser_data/` 供後續爬蟲自動使用：
```bash
python hourly_crawler/login.py
```
執行後會開啟 Chrome 視窗，手動輸入帳號密碼（含 2FA），看到 Threads 首頁後回到終端機按 **Enter** 儲存 session。**此步驟只需執行一次。**

---

### Mac — 設定 cron 排程

```bash
# 建立設定腳本
PROJECT_ROOT="$(pwd)"
PYTHON_PATH="$PROJECT_ROOT/.venv/bin/python"
SCHEDULER_PATH="$PROJECT_ROOT/hourly_crawler/hourly_scheduler.py"
(crontab -l 2>/dev/null; echo "0 * * * * $PYTHON_PATH $SCHEDULER_PATH") | crontab -
echo "✅ Cron 任務已設定，每小時執行一次"
```

---

### Windows — 設定工作排程器

1. 開啟「工作排程器」(`taskschd.msc`)
2. 點選「建立基本工作」
3. 觸發程序：每天 → 重複工作每隔： **1 小時** ，持續時間為：不限制
4. 動作設定：
   - 程式：`<專案根目錄>\.venv\Scripts\python.exe`
   - 引數：`hourly_scheduler.py`
   - 起始位置：`<專案根目錄>\hourly_crawler`

---

### 啟動 Dashboard

```bash
cd dashboard
python app.py
```
在瀏覽器開啟 `http://127.0.0.1:5000`

## 🔄 排程執行流程

```
每小時觸發
  └─ hourly_scraper.py    （雙階段爬蟲 + 危機分析，timeout 30 分鐘）
       ↓ 等待 10 秒（釋放 browser_data 鎖定）
  └─ hourly_update.py     （更新近 3 天指標含瀏覽量，timeout 30 分鐘）
       ↓ 距上次 ≥ 6 小時才執行
       ↓ 等待 10 秒
  └─ trend_update.py      （高風險貼文趨勢分析，timeout 30 分鐘）
```

## ⚠️ 免責聲明
本系統僅供國立政治大學校園研究、實習專案與公關趨勢監測使用。所擷取之數據僅作為內部決策輔助，請嚴格遵守相關社群平台（Meta / Threads）之使用規範與隱私條款，嚴禁將爬蟲數據用於非法窺探或商業營利。
