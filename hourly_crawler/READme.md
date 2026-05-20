## 📂 每小時爬蟲模組 (Hourly Scraper)

此模組每小時自動爬取 Threads 貼文，並存入 SQLite 資料庫。

### 🗂️ 相關檔案

| 檔案 | 說明 |
|------|------|
| `hourly_scheduler.py` | 排程執行入口（由 Windows 工作排程器 / cron 每小時呼叫）|
| `hourly_scraper.py` | 雙階段爬蟲主程式 |
| `db_utils.py` | 資料庫查詢工具 |

### 🤖 爬蟲運作方式

**第一階段**：搜尋頁滾動（最多 30 次），收集貼文基礎資訊（作者、內容、發文時間、likes / 回覆 / 轉貼 / 分享）。

**第二階段**：逐篇訪問單一貼文 URL，捕捉「瀏覽量」（views）。每篇等待 3.5–6.5 秒，每 4 篇額外暫停 8–14 秒（防偵測）。

### 🗄️ 資料庫結構 (`posts` 資料表)

| 欄位 | 類型 | 說明 |
|------|------|------|
| `id` | INTEGER | 主鍵（自動遞增）|
| `url` | TEXT | 貼文連結（唯一值）|
| `author` | TEXT | 帳號名稱 |
| `content` | TEXT | 貼文內容 |
| `post_date` | TEXT | 發文時間（ISO 8601 UTC，如 `2026-05-19T07:44:00.000Z`）|
| `likes` | INTEGER | 愛心數 |
| `comments` | INTEGER | 留言數 |
| `reposts` | INTEGER | 轉發數 |
| `shares` | INTEGER | 分享數 |
| `views` | INTEGER | 瀏覽量（僅對帳號本人可見，其他帳號通常為 0）|
| `created_at` | TEXT | 首次爬取時間 |
| `updated_at` | TEXT | 最後更新時間 |

### 🚀 手動執行

```bash
cd hourly_crawler
python hourly_scheduler.py
```

### 📊 查詢資料

推薦使用 [TablePlus](https://tableplus.com/) 或 [DB Browser for SQLite](https://sqlitebrowser.org/) 開啟 `threads_posts.db`。

JOIN 範例：
```sql
SELECT p.url, p.author, p.content, p.likes, p.views,
       a.summary, a.sentiment, a.crisis_score
FROM posts p
LEFT JOIN post_analysis a ON p.url = a.post_url
ORDER BY p.updated_at DESC;
```
