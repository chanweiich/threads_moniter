"""
每小時 Threads 爬蟲模組
使用與 scrape_threads.py 相同的爬取邏輯，將資料存入 SQLite 資料庫
支援 Windows 工作排程器單次執行模式
"""
import asyncio
import sqlite3
import os
import re
import json  # 僅用於 json.dumps/loads 序列化 SQLite TEXT 欄位中的 list，非 JSON 檔案
import time
from datetime import datetime
from playwright.async_api import async_playwright
from pydantic import BaseModel, Field
from dotenv import load_dotenv

# 載入根目錄的 .env
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(BASE_DIR, ".env"))

DB_PATH = os.path.join(BASE_DIR, "threads_posts.db")


class BatchItemAnalysis(BaseModel):
    id: int = Field(description="The matching index/ID passed in the prompt")
    summary: str
    sentiment: str
    crisis_score: int

class BatchCrisisResponse(BaseModel):
    results: list[BatchItemAnalysis]


def parse_number_text(text):
    """將文字轉換為數字 (例如：'1.1萬' -> 11000)"""
    if not isinstance(text, str):
        return int(text) if text else 0
    if not text or text == "N/A":
        return 0
    text = text.replace(',', '')
    if '萬' in text:
        try:
            return int(float(text.replace('萬', '').strip()) * 10000)
        except:
            return 0
    try:
        return int(text)
    except:
        return 0


def is_within_time_limit(time_text, days=7):
    """
    判斷貼文時間是否在指定天數內
    Threads 時間格式範例：
    - 相對時間：'1小時', '2h', '30分鐘', '2天', '5d'
    - 絕對日期：'2026-3-4', '2026-03-04'
    """
    if not time_text:
        return False

    time_text = time_text.strip().lower()

    if time_text in ['剛剛', 'now', 'just now']:
        return True

    if re.search(r'(\d+)\s*(s|秒)', time_text):
        return True

    if re.search(r'(\d+)\s*(m|分)', time_text):
        return True

    match = re.search(r'(\d+)\s*(h|小時|時)', time_text)
    if match:
        return True

    match = re.search(r'(\d+)\s*(d|天)', time_text)
    if match:
        num_days = int(match.group(1))
        return num_days <= days

    match = re.search(r'(\d+)\s*(w|週|周)', time_text)
    if match:
        num_weeks = int(match.group(1))
        return num_weeks * 7 <= days

    match = re.search(r'(\d{4})-(\d{1,2})-(\d{1,2})', time_text)
    if match:
        try:
            year, month, day = int(match.group(1)), int(match.group(2)), int(match.group(3))
            post_date = datetime(year, month, day)
            diff = datetime.now() - post_date
            return diff.days <= days
        except:
            return False

    return False


def get_db_connection():
    """取得 SQLite 連線"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_database():
    """初始化 SQLite 資料庫，建立 posts 資料表"""
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS posts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            url TEXT UNIQUE NOT NULL,
            author TEXT,
            content TEXT,
            post_date TEXT,
            likes INTEGER DEFAULT 0,
            comments INTEGER DEFAULT 0,
            reposts INTEGER DEFAULT 0,
            shares INTEGER DEFAULT 0,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS post_analysis (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            post_url TEXT UNIQUE,
            summary TEXT,
            sentiment TEXT,
            crisis_score INTEGER,
            analyzed_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS post_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            url TEXT NOT NULL,
            likes INTEGER DEFAULT 0,
            comments INTEGER DEFAULT 0,
            captured_at TEXT NOT NULL
        )
    ''')

    cursor.execute('CREATE INDEX IF NOT EXISTS idx_url ON posts(url)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_author ON posts(author)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_updated ON posts(updated_at)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_snapshots_url ON post_snapshots(url)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_snapshots_captured ON post_snapshots(captured_at)')

    conn.commit()
    conn.close()
    print(f"[OK] SQLite database initialized: {DB_PATH}")


def save_to_database(posts_data, keywords):
    """將爬取的貼文資料存入 SQLite，回傳統計數字與新增貼文清單"""
    conn = get_db_connection()
    cursor = conn.cursor()

    new_posts_list = []
    updated_posts = 0
    current_time = datetime.now().isoformat()

    for post in posts_data:
        url = post.get('url', '')
        if not url:
            continue

        likes    = parse_number_text(post.get('likes', '0'))
        comments = parse_number_text(post.get('replies', '0'))
        reposts  = parse_number_text(post.get('reposts', '0'))
        shares   = parse_number_text(post.get('shares', '0'))

        cursor.execute("SELECT id FROM posts WHERE url = ?", (url,))
        row = cursor.fetchone()

        if row:
            cursor.execute('''
                UPDATE posts
                SET likes = ?, comments = ?, reposts = ?, shares = ?, updated_at = ?
                WHERE url = ?
            ''', (likes, comments, reposts, shares, current_time, url))
            updated_posts += 1
        else:
            cursor.execute('''
                INSERT INTO posts (url, author, content, post_date, likes, comments, reposts, shares, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (url, post.get('author'), post.get('content'), post.get('time'),
                  likes, comments, reposts, shares, current_time, current_time))
            new_posts_list.append(post)

        cursor.execute("SELECT id FROM posts WHERE url = ?", (url,))
        snap_post_row = cursor.fetchone()
        snap_post_id = snap_post_row[0] if snap_post_row else None
        cursor.execute('''
            INSERT INTO post_snapshots (post_id, url, likes, comments, captured_at)
            VALUES (?, ?, ?, ?, ?)
        ''', (snap_post_id, url, likes, comments, current_time))

    conn.commit()
    conn.close()

    return {
        'total': len(posts_data),
        'new': len(new_posts_list),
        'new_posts': new_posts_list
    }


def analyze_new_posts(new_posts):
    """批次分析新貼文的危機分數，結果存入 post_analysis 表 (SQLite)"""
    if not new_posts:
        print("[OK] 沒有新貼文需要分析")
        return

    if not os.environ.get("GEMINI_API_KEY"):
        print("⚠️ 未設定 GEMINI_API_KEY，跳過危機分析")
        return

    from google import genai
    client = genai.Client()

    print(f"\n🤖 開始批次分析 {len(new_posts)} 篇新貼文...")

    BATCH_SIZE = 5
    for batch_start in range(0, len(new_posts), BATCH_SIZE):
        batch = new_posts[batch_start:batch_start + BATCH_SIZE]

        prompt_lines = ["請分析以下多篇 Threads 貼文的內容，並以 JSON Array 的形式回傳結果。\n"]
        for idx, post in enumerate(batch):
            global_idx = batch_start + idx
            prompt_lines.append(f"【ID: {global_idx}】\n內容：{post.get('content', '')}\n---\n")

        prompt_lines.append("""
你是一位政大秘書處的資深公關專家。請針對這篇來自 Threads 的貼文進行危機評估：
情緒 (Sentiment)：正面、中立或負面。
評分規則 (crisis_score)：
  - 情緒為「正面」或「中立」→ crisis_score 固定為 0，代表無危機風險。
  - 情緒為「負面」→ 評為 1~5 分：
      1 = 輕微抱怨或情緒宣洩，無明顯擴散跡象
      2 = 小範圍批評，有討論但影響有限
      3 = 中度不滿，涉及制度／服務／政策，具一定討論熱度
      4 = 嚴重不滿，可能引發連鎖反應或媒體關注
      5 = 重大公關危機（如校園安全事故、大規模抗議、學術誠信醜聞）
摘要 (Summary)：簡短說明學生在討論什麼。

請嚴格依照結構提供 JSON：
```json
{
  "results": [
    {
      "id": "匹配上方傳入的整數 ID",
      "summary": "簡短說明學生在討論什麼",
      "sentiment": "正面/中立/負面",
      "crisis_score": 0
    }
  ]
}
```""")

        full_prompt = "".join(prompt_lines)
        print(f"  🔄 批次 {batch_start // BATCH_SIZE + 1}：分析 {len(batch)} 篇貼文...")

        success = False
        for attempt in range(2):
            try:
                response = client.models.generate_content(
                    model='gemini-2.5-flash',
                    contents=full_prompt,
                    config=genai.types.GenerateContentConfig(
                        response_mime_type="application/json",
                        response_schema=BatchCrisisResponse,
                        temperature=0.2
                    )
                )
                response_text = response.text
                start_idx = response_text.find('{')
                end_idx = response_text.rfind('}')
                if start_idx != -1 and end_idx != -1:
                    response_text = response_text[start_idx:end_idx + 1]

                analysis_obj = BatchCrisisResponse.model_validate_json(response_text)
                result_map = {item.id: item for item in analysis_obj.results}

                conn = sqlite3.connect(DB_PATH)
                cursor = conn.cursor()
                for idx, post in enumerate(batch):
                    global_idx = batch_start + idx
                    if global_idx in result_map:
                        item = result_map[global_idx]
                        cursor.execute("SELECT id FROM posts WHERE url = ?", (post.get('url'),))
                        post_row = cursor.fetchone()
                        post_id = post_row[0] if post_row else None
                        cursor.execute("""
                            INSERT OR REPLACE INTO post_analysis (post_id, post_url, summary, sentiment, crisis_score, analyzed_at)
                            VALUES (?, ?, ?, ?, ?, ?)
                        """, (
                            post_id,
                            post.get('url'),
                            item.summary,
                            item.sentiment,
                            item.crisis_score,
                            datetime.now().isoformat()
                        ))
                conn.commit()
                conn.close()

                print(f"  ✅ 批次完成")
                success = True
                time.sleep(3)
                break
            except Exception as e:
                print(f"  ⚠️ Gemini 錯誤 (嘗試 {attempt + 1}/2): {e}")
                time.sleep(2)

        if not success:
            print(f"  ❌ 批次分析失敗，跳過")

    print("✅ 危機分析完成，結果已存入 post_analysis 表")


async def scrape_threads_hourly(keywords):
    """
    執行 Threads 爬蟲並存入 SQLite 資料庫
    只抓取 24 小時內的貼文，不限數量
    """
    results = []
    user_data_dir = os.path.join(BASE_DIR, "browser_data")

    async with async_playwright() as p:
        print(f"[{datetime.now()}] 正在啟動瀏覽器...")

        context = await p.chromium.launch_persistent_context(
            user_data_dir=user_data_dir,
            headless=False,
            args=["--disable-blink-features=AutomationControlled"],
            viewport={'width': 1280, 'height': 800},
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        )

        page = await context.new_page()

        print("正在開啟 Threads 首頁...")
        await page.goto("https://www.threads.com/", wait_until="domcontentloaded")

        await asyncio.sleep(5)
        print("[OK] Page loaded, starting search...")

        await asyncio.sleep(2)

        from datetime import timedelta
        yesterday = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')

        for keyword in keywords:
            print(f"\n========= 正在搜尋關鍵字：{keyword} =========")
            search_url = f"https://www.threads.com/search?after_date={yesterday}&q={keyword}&serp_type=default&hl=zh-tw"
            print(f"   搜尋網址：{search_url}")
            await page.goto(search_url, wait_until="domcontentloaded")
            await asyncio.sleep(4)

            SCROLL_TIMES = 30
            print(f"模擬滾動載入貼文中... (共 {SCROLL_TIMES} 次)")

            import random
            for i in range(SCROLL_TIMES):
                scroll_distance = random.randint(800, 1500)
                await page.mouse.wheel(0, scroll_distance)

                wait_time = random.uniform(0.5, 1.5)
                await asyncio.sleep(wait_time)

                if random.random() < 0.2:
                    await asyncio.sleep(random.uniform(1, 2))

                if (i + 1) % 10 == 0:
                    print(f"   已捲動 {i + 1}/{SCROLL_TIMES} 次...")

            posts_data = await page.evaluate('''() => {
                let data = [];
                let postLinks = Array.from(document.querySelectorAll('a[href*="/post/"]'));
                let seenUrls = new Set();
                let seenContentKeys = new Set();

                for (let link of postLinks) {
                    let postUrl = link.href.split('?')[0].replace(/\\/media$/, '');
                    if (seenUrls.has(postUrl)) continue;
                    seenUrls.add(postUrl);

                    try {
                        let container = link;
                        for (let i = 0; i < 10; i++) {
                            if (container.parentElement && container.parentElement.tagName !== 'BODY') {
                                container = container.parentElement;
                            }
                        }

                        let authorMatch = postUrl.match(/@([^/]+)/);
                        let author = authorMatch ? authorMatch[1] : "Unknown";

                        let timeElement = container.querySelector('time');
                        let timeText = timeElement ? timeElement.textContent.trim() : link.textContent.trim();

                        let textNodes = Array.from(container.querySelectorAll('span[dir="auto"]'));
                        // 去除結尾輪播頁碼（如 \xa01/6、\xa02/2），再過濾純數字 span（互動數）
                        let contentText = textNodes.map(n => {
                            let t = n.textContent.replace(/\\u00a0\\d+(\\/\\d+)?$/, '').trimEnd();
                            return t;
                        }).filter(t => {
                            let s = t.trim();
                            return s.length > 0 && !/^[\\d,\\.]+([\\s,]+[\\d,\\.]+)*[萬KMkm]?$/.test(s);
                        }).join('\\n');

                        // 以 author + content 前 200 字為去重鍵，避免同容器產生重複貼文
                        let contentKey = author + '|' + contentText.substring(0, 200);
                        if (seenContentKeys.has(contentKey)) continue;
                        seenContentKeys.add(contentKey);

                        // 支援中英雙語的 aria-label，並往上多找幾層
                        function getCount(ctx, enLabel, zhLabel, zhLabel2) {
                            // 組合多種可能的標籤 (例如 Like, Unlike, 讚, 收回讚)
                            let selectors = [`svg[aria-label="${enLabel}"]`];
                            if (zhLabel) selectors.push(`svg[aria-label="${zhLabel}"]`);
                            if (zhLabel2) selectors.push(`svg[aria-label="${zhLabel2}"]`);
                            if (enLabel === "Like") selectors.push(`svg[aria-label="Unlike"]`, `svg[aria-label="收回讚"]`);
                            
                            const svg = ctx.querySelector(selectors.join(', '));
                            if (!svg) return "0";

                            // 往上找 4 層，尋找同一區塊內包含純數字的 span
                            let parent = svg;
                            for (let i = 0; i < 4; i++) {
                                parent = parent.parentElement;
                                if (!parent) return "0";
                                
                                const spans = parent.querySelectorAll("span");
                                for (const span of spans) {
                                    // 確保只抓純文字節點 (沒有包其他標籤的 span)
                                    if (span.children.length > 0) continue;
                                    const text = span.textContent.trim();
                                    // 驗證是否為數字格式 (例如 503, 125, 1.2萬)
                                    if (/^[\d,\.]+[萬KkMm]?$/.test(text)) {
                                        return text;
                                    }
                                }
                            }
                            return "0";
                        }

                        // 使用新的函數抓取
                        let likes   = getCount(container, "Like", "讚", "按讚");
                        let replies = getCount(container, "Reply", "回覆", "留言");
                        let reposts = getCount(container, "Repost", "轉貼", "轉發");
                        let shares  = getCount(container, "Share", "分享", "傳送");

                        data.push({
                            "author": author,
                            "time": timeText,
                            "content": contentText,
                            "url": postUrl,
                            "likes": likes,
                            "replies": replies,
                            "reposts": reposts,
                            "shares": shares
                        });
                    } catch(e) {
                        console.error("解析單篇貼文失敗", e);
                    }
                }
                return data;
            }''')

            print(f"   抓到 {len(posts_data)} 筆貼文")
            results.extend(posts_data)

        await context.close()

    seen_urls = set()
    unique_results = []
    for post in results:
        if post['url'] not in seen_urls:
            seen_urls.add(post['url'])
            unique_results.append(post)

    stats = save_to_database(unique_results, keywords)

    print(f"\n[OK] Scraping completed!")
    print(f"   - 總共擷取：{stats['total']} 筆")
    print(f"   - 新增貼文：{stats['new']} 筆")

    # 對新增貼文進行危機分析
    analyze_new_posts(stats['new_posts'])

    return stats


if __name__ == "__main__":
    keywords_to_search = ["政大"]

    init_database()

    asyncio.run(scrape_threads_hourly(keywords_to_search))
