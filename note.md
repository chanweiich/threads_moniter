Windows 工作排程器（每小時）
        │
        ▼
hourly_scheduler.py
        │
        ├─ 1. hourly_scraper.py（每次都跑）
        │       ├─ Playwright 搜尋關鍵字（帶 hl=zh-tw，介面為繁中）
        │       ├─ 爬取 24 小時內新貼文
        │       ├─ 互動數抓取：svg[aria-label] 中英雙語 selector，往上找 4 層容器
        │       │       likes   → "Like" / "Unlike" / "讚" / "按讚" / "收回讚"
        │       │       replies → "Reply" / "回覆" / "留言"
        │       │       reposts → "Repost" / "轉貼" / "轉發"
        │       │       shares  → "Share" / "分享" / "傳送"
        │       ├─ 新貼文 → INSERT posts (含 reposts/shares) + INSERT post_analysis（Gemini）
        │       ├─ 舊貼文 → UPDATE likes/comments/reposts/shares
        │       └─ INSERT post_snapshots（每次爬取記錄快照，用來計算互動增量）
        │
        ├─ 2. hourly_update.py（每次都跑）
        │       ├─ 查詢：created_at >= 3 天前的所有貼文 URL
        │       ├─ Playwright 逐一訪問每篇貼文（單篇頁，aria-label 最穩定）
        │       ├─ 同樣用中英雙語 getCount，往上找 4 層
        │       ├─ UPDATE posts 的 likes/comments/reposts/shares（主責，數值最準確）
        │       └─ INSERT post_snapshots
        │
        └─ 3. trend_update.py（距上次 > 6 小時才跑）
                ├─ 查詢：負面 + crisis_score >= 3 + 7天內 + 未在6小時內分析
                ├─ 按 crisis_score 由高到低排序
                ├─ Playwright 爬取每篇留言 + Gemini 趨勢分析
                └─ INSERT OR REPLACE 進 trend_analysis

【已知問題 / 注意事項】
- 搜尋頁（scraper）的 aria-label 比單篇頁（update）更容易受 Threads 改版影響，
  若指標持續回傳 0，優先檢查 aria-label 名稱是否變動。
- post_snapshots 目前只記錄 likes/comments，尚未擴充 reposts/shares 欄位。
