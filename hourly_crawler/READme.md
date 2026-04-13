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
