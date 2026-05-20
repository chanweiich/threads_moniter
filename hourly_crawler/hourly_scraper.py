"""
每小時 Threads 爬蟲模組 (雙階段智慧整合深爬版)
第一階段：資訊流極速掃描收集基礎指標
第二階段：精準進入單獨貼文網址深度提取「真實瀏覽量 (views)」，內建軍規級反偵測保護
"""
import asyncio
import sqlite3
import os
import re
import json
import random
import time
from datetime import datetime, timedelta
from playwright.async_api import async_playwright
from pydantic import BaseModel, Field
from dotenv import load_dotenv

# 嘗試載入隱形斗篷模組，提升反爬蟲穿透力
try:
    from playwright_stealth import stealth_async
    HAS_STEALTH = True
except ImportError:
    HAS_STEALTH = False

# 載入根目錄的 .env
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENV_PATH = os.path.join(BASE_DIR, ".env")
load_dotenv(ENV_PATH, override=True)

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


def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_database():
    """初始化 SQLite 資料庫與相容性升級"""
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
            views INTEGER DEFAULT 0,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    try:
        cursor.execute("ALTER TABLE posts ADD COLUMN views INTEGER DEFAULT 0")
    except sqlite3.OperationalError:
        pass

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS post_analysis (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            post_id INTEGER,
            post_url TEXT UNIQUE,
            summary TEXT,
            sentiment TEXT,
            crisis_score INTEGER,
            analyzed_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    try:
        cursor.execute("ALTER TABLE post_analysis ADD COLUMN post_id INTEGER")
    except sqlite3.OperationalError:
        pass

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS post_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            post_id INTEGER,
            url TEXT NOT NULL,
            likes INTEGER DEFAULT 0,
            comments INTEGER DEFAULT 0,
            views INTEGER DEFAULT 0,
            captured_at TEXT NOT NULL
        )
    ''')
    try:
        cursor.execute("ALTER TABLE post_snapshots ADD COLUMN views INTEGER DEFAULT 0")
    except sqlite3.OperationalError:
        pass
    try:
        cursor.execute("ALTER TABLE post_snapshots ADD COLUMN post_id INTEGER")
    except sqlite3.OperationalError:
        pass

    cursor.execute('CREATE INDEX IF NOT EXISTS idx_url ON posts(url)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_author ON posts(author)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_updated ON posts(updated_at)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_snapshots_url ON post_snapshots(url)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_snapshots_captured ON post_snapshots(captured_at)')

    conn.commit()
    conn.close()
    print(f"[OK] SQLite database initialized & safety checks completed: {DB_PATH}")


def save_to_database(posts_data, keywords):
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
        views    = parse_number_text(post.get('views', '0'))

        cursor.execute("SELECT id FROM posts WHERE url = ?", (url,))
        row = cursor.fetchone()

        if row:
            cursor.execute('''
                UPDATE posts
                SET likes = ?, comments = ?, reposts = ?, shares = ?, views = ?, updated_at = ?
                WHERE url = ?
            ''', (likes, comments, reposts, shares, views, current_time, url))
            updated_posts += 1
        else:
            cursor.execute('''
                INSERT INTO posts (url, author, content, post_date, likes, comments, reposts, shares, views, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (url, post.get('author'), post.get('content'), post.get('time'),
                  likes, comments, reposts, shares, views, current_time, current_time))
            new_posts_list.append(post)

        cursor.execute("SELECT id FROM posts WHERE url = ?", (url,))
        snap_post_row = cursor.fetchone()
        snap_post_id = snap_post_row[0] if snap_post_row else None
        
        cursor.execute('''
            INSERT INTO post_snapshots (post_id, url, likes, comments, views, captured_at)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (snap_post_id, url, likes, comments, views, current_time))

    conn.commit()
    conn.close()

    return {
        'total': len(posts_data),
        'new': len(new_posts_list),
        'updated': updated_posts,
        'new_posts': new_posts_list
    }


def analyze_new_posts(new_posts):
    if not new_posts:
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
      5 = 重大公關危機
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
                print(f"  ⚠️ Gemini 錯誤: {e}")
                time.sleep(2)

    print("✅ 危機分析完成，結果已存入 post_analysis 表")


async def scrape_threads_hourly(keywords):
    results = []
    user_data_dir = os.path.join(BASE_DIR, "browser_data")

    async with async_playwright() as p:
        print(f"[{datetime.now()}] 🚀 啟動雙階段高階反反爬蟲引擎...")
        
        # 載入憑證與狀態
        context = await p.chromium.launch_persistent_context(
            user_data_dir=user_data_dir,
            headless=True,
            channel="chrome",
            args=["--disable-blink-features=AutomationControlled", "--no-sandbox"],
            viewport={'width': random.randint(1200, 1420), 'height': random.randint(800, 1020)},
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        )

        page = await context.new_page()
        if HAS_STEALTH:
            await stealth_async(page)

        print("正在初始化連線狀態...")
        await page.goto("https://www.threads.com/", wait_until="domcontentloaded")
        await asyncio.sleep(random.uniform(3, 5))

        yesterday = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')

        # === 第一階段：資訊流淺層滾動收集 ===
        for keyword in keywords:
            print(f"\n========= 第一階段：搜尋關鍵字資訊流 [{keyword}] =========")
            search_url = f"https://www.threads.com/search?after_date={yesterday}&q={keyword}&serp_type=default&hl=zh-tw"
            await page.goto(search_url, wait_until="domcontentloaded")
            await asyncio.sleep(random.uniform(3, 5))

            MAX_SCROLLS = 30
            previous_post_count = 0
            no_new_posts_streak = 0

            for i in range(MAX_SCROLLS):
                await page.mouse.wheel(0, random.randint(800, 1500))
                await asyncio.sleep(random.uniform(0.8, 2.0))

                current_post_count = await page.evaluate("document.querySelectorAll('a[href*=\"/post/\"]').length")
                if current_post_count == previous_post_count:
                    no_new_posts_streak += 1
                    if no_new_posts_streak >= 3:
                        break
                else:
                    no_new_posts_streak = 0
                previous_post_count = current_post_count

            posts_data = await page.evaluate('''() => {
                let data = [];
                let postLinks = Array.from(document.querySelectorAll('a[href*="/post/"]'));
                let seenUrls = new Set();

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

                        let textNodes = Array.from(container.querySelectorAll('span[dir="auto"]'));
                        let contentText = textNodes.map(n => n.textContent.trim()).filter(t => t.length > 0).join('\\n');

                        if (contentText.includes('正在回覆') || contentText.toLowerCase().includes('replying to @')) continue;

                        function getCount(ctx, enLabel, zhLabel) {
                            const svg = ctx.querySelector(`svg[aria-label="${enLabel}"], svg[aria-label="${zhLabel}"]`);
                            if (!svg) return "0";
                            let parent = svg;
                            for (let i = 0; i < 4; i++) {
                                parent = parent.parentElement;
                                if (!parent) return "0";
                                const spans = parent.querySelectorAll("span");
                                for (const span of spans) {
                                    if (span.children.length === 0 && /^[\d,\.]+[萬KkMm]?$/.test(span.textContent.trim())) {
                                        return span.textContent.trim();
                                    }
                                }
                            }
                            return "0";
                        }

                        let timeEl = container.querySelector('time');
                        let timeText = timeEl ? (timeEl.getAttribute('datetime') || timeEl.textContent.trim()) : '';

                        data.push({
                            "author": author,
                            "time": timeText,
                            "content": contentText,
                            "url": postUrl,
                            "likes": getCount(container, "Like", "讚"),
                            "replies": getCount(container, "Reply", "回覆"),
                            "reposts": getCount(container, "Repost", "轉貼"),
                            "shares": getCount(container, "Share", "分享"),
                            "views": "0"  // 預設為0，留給第二階段深爬
                        });
                    } catch(e) {}
                }
                return data;
            }''')
            results.extend(posts_data)

        # 整理去重
        seen_urls = set()
        unique_results = []
        for post in results:
            if post['url'] not in seen_urls:
                seen_urls.add(post['url'])
                unique_results.append(post)

        # === 第二階段：擬人化單篇網址深度訪問 (捕捉瀏覽量) ===
        print(f"\n[{datetime.now()}] 🕵️ 啟動第二階段：獨立貼文深層解析 (共 {len(unique_results)} 筆待處理)...")
        
        deep_page = await context.new_page()
        if HAS_STEALTH:
            await stealth_async(deep_page)

        for idx, post in enumerate(unique_results):
            print(f"   ➔ 深度訪問 ({idx+1}/{len(unique_results)}): {post['url']}")
            try:
                # 注入 referer 來源偽裝，假裝是從主頁點擊進入
                await deep_page.goto(post['url'], referer="https://www.threads.com/", wait_until="domcontentloaded")
                
                # 智慧動態延遲 (隨機讀取 3.5 到 6.5 秒)，絕對避免高頻觸發雷達
                await asyncio.sleep(random.uniform(3.5, 6.5))

                # 強力檢索內頁文字節點中的瀏覽量字樣 (相容頂部串文標頭與底層詳情)
                views_str = await deep_page.evaluate('''() => {
                    let elements = Array.from(document.querySelectorAll('span, div'));
                    for (let el of elements) {
                        let txt = el.textContent.trim();
                        // 鎖定如 "456次瀏覽", "1.2萬次瀏覽", "查看次數：1.2萬" 等深層 UI 結構
                        let m1 = txt.match(/^([\d,\.]+[萬KkMm]?)\s*次[瀏覽觀看查看]/);
                        if (m1) return m1[1];
                        let m2 = txt.match(/[瀏覽觀看查看]次數[：:\s]*([\d,\.]+[萬KkMm]?)/);
                        if (m2) return m2[1];
                    }
                    return "0";
                }''')

                if views_str and views_str != "0":
                    post['views'] = views_str
                    print(f"     ✅ 成功捕獲隱藏瀏覽量: {views_str}")
                else:
                    print("     ➖ 未對外顯示或權限隱藏")

            except Exception as e:
                print(f"     ⚠️ 訪問超時或失效，自動略過")

            # 軍規級防護：每深爬 4 篇，強制進行一次大休打散規律
            if (idx + 1) % 4 == 0 and (idx + 1) < len(unique_results):
                pause_time = random.uniform(8.0, 14.0)
                print(f"   💤 觸發動態防禦暫停 {pause_time:.1f} 秒，模擬真人中場休息...")
                await asyncio.sleep(pause_time)

        await deep_page.close()
        await context.close()

    # 寫入資料庫
    stats = save_to_database(unique_results, keywords)

    print(f"\n[OK] 雙階段爬蟲與資料庫同步大功告成！")
    print(f"   - 總掃描數：{stats['total']} 筆")
    print(f"   - 新增貼文：{stats['new']} 筆")
    print(f"   - 更新指標：{stats['updated']} 筆")

    analyze_new_posts(stats['new_posts'])
    return stats


if __name__ == "__main__":
    keywords_to_search = ["政大"]
    init_database()
    asyncio.run(scrape_threads_hourly(keywords_to_search))