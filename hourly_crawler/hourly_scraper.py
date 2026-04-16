"""
每小時 Threads 爬蟲模組
使用與 scrape_threads.py 相同的爬取邏輯，將資料存入 SQLite 資料庫
支援 Windows 工作排程器單次執行模式
"""
import asyncio
import sqlite3
import os
import re
from datetime import datetime
from playwright.async_api import async_playwright

# 取得專案根目錄 (hourly_crawler 的上層)
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE_DIR, "threads_posts.db")


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
    
    # 剛剛 / now / just now / 空字串時間可能是最新的
    if time_text in ['剛剛', 'now', 'just now']:
        return True
    
    # 秒 (s, 秒, 秒鐘)
    if re.search(r'(\d+)\s*(s|秒)', time_text):
        return True
    
    # 分鐘 (m, 分, 分鐘)
    if re.search(r'(\d+)\s*(m|分)', time_text):
        return True
    
    # 小時 (h, 小時, 時)
    match = re.search(r'(\d+)\s*(h|小時|時)', time_text)
    if match:
        return True  # 小時內一定在 7 天內
    
    # 天 (d, 天)
    match = re.search(r'(\d+)\s*(d|天)', time_text)
    if match:
        num_days = int(match.group(1))
        return num_days <= days
    
    # 週 (w, 週, 周)
    match = re.search(r'(\d+)\s*(w|週|周)', time_text)
    if match:
        num_weeks = int(match.group(1))
        return num_weeks * 7 <= days
    
    # 絕對日期格式：YYYY-M-D 或 YYYY-MM-DD
    match = re.search(r'(\d{4})-(\d{1,2})-(\d{1,2})', time_text)
    if match:
        try:
            year, month, day = int(match.group(1)), int(match.group(2)), int(match.group(3))
            post_date = datetime(year, month, day)
            diff = datetime.now() - post_date
            return diff.days <= days
        except:
            return False
    
    # 無法判斷的預設為不在時間範圍內
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
    
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_url ON posts(url)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_author ON posts(author)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_updated ON posts(updated_at)')
    
    conn.commit()
    conn.close()
    print(f"[OK] SQLite database initialized: {DB_PATH}")


def save_to_database(posts_data, keywords):
    """將爬取的貼文資料存入 SQLite 資料庫 (先清空再寫入)"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # 不要清空現有資料
    #cursor.execute('DELETE FROM posts')
    #print("🗑️ 已清空舊資料")
    
    new_posts = 0
    updated_posts = 0
    current_time = datetime.now().isoformat()
    
    for post in posts_data:
        url = post.get('url', '')
        if not url:
            continue
            
        likes = parse_number_text(post.get('likes', '0'))
        comments = parse_number_text(post.get('replies', '0'))
        
        # 使用 INSERT OR REPLACE 或是先檢查是否存在
        # 這裡建議保留 created_at，只更新 likes, comments 和 updated_at
        cursor.execute("SELECT id FROM posts WHERE url = ?", (url,))
        row = cursor.fetchone()
        
        if row:
            # 已經存在的貼文 -> 更新數據
            cursor.execute('''
                UPDATE posts 
                SET likes = ?, comments = ?, updated_at = ?
                WHERE url = ?
            ''', (likes, comments, current_time, url))
            updated_posts += 1
        else:
            # 新貼文 -> 插入
            cursor.execute('''
                INSERT INTO posts (url, author, content, post_date, likes, comments, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (url, post.get('author'), post.get('content'), post.get('time'), 
                  likes, comments, current_time, current_time))
            new_posts += 1
            
        # 【進階：存入歷史記錄表】
        # cursor.execute('INSERT INTO stats_history (post_url, likes, comments, check_time) VALUES (?,?,?,?)')
    
    conn.commit()
    conn.close()
    
    return {
        'total': len(posts_data),
        'new': new_posts
    }


async def scrape_threads_hourly(keywords):
    """
    執行 Threads 爬蟲並存入 SQLite 資料庫
    只抓取 24 小時內的貼文，不限數量
    """
    results = []
    # browser_data 放在專案根目錄
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
        
        # 等待頁面穩定
        await asyncio.sleep(5)
        print("[OK] Page loaded, starting search...")
        
        await asyncio.sleep(2)
        
        # 計算昨天的日期（用於 after_date 參數）
        from datetime import timedelta
        yesterday = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
        
        for keyword in keywords:
            print(f"\n========= 正在搜尋關鍵字：{keyword} =========")
            search_url = f"https://www.threads.com/search?after_date={yesterday}&q={keyword}&serp_type=default&hl=zh-tw"
            print(f"   搜尋網址：{search_url}")
            await page.goto(search_url, wait_until="domcontentloaded")
            await asyncio.sleep(4)
            
            # 模擬人類滑鼠滾動行為
            SCROLL_TIMES = 30
            print(f"模擬滾動載入貼文中... (共 {SCROLL_TIMES} 次)")
            
            import random
            for i in range(SCROLL_TIMES):
                # 隨機滾動距離 (800-1500 像素)
                scroll_distance = random.randint(800, 1500)
                await page.mouse.wheel(0, scroll_distance)
                
                # 隨機等待時間 (0.5-1.5 秒)，模擬人類閱讀
                wait_time = random.uniform(0.5, 1.5)
                await asyncio.sleep(wait_time)
                
                # 偶爾停頓久一點 (模擬閱讀貼文)
                if random.random() < 0.2:
                    await asyncio.sleep(random.uniform(1, 2))
                
                if (i + 1) % 10 == 0:
                    print(f"   已捲動 {i + 1}/{SCROLL_TIMES} 次...")

            posts_data = await page.evaluate('''() => {
                let data = [];
                let postLinks = Array.from(document.querySelectorAll('a[href*="/post/"]'));
                let seen = new Set();
                
                for (let link of postLinks) {
                    if (seen.has(link.href)) continue;
                    seen.add(link.href);
                    
                    try {
                        // 找到貼文容器（往上爬 10 層）
                        let container = link;
                        for (let i = 0; i < 10; i++) {
                            if (container.parentElement && container.parentElement.tagName !== 'BODY') {
                                container = container.parentElement;
                            }
                        }
                        
                        // 從 URL 提取作者名稱
                        let postUrl = link.href;
                        let authorMatch = postUrl.match(/@([^/]+)/);
                        let author = authorMatch ? authorMatch[1] : "Unknown";
                        
                        // 抓取時間（通常在連結的 time 元素或連結文字）
                        let timeElement = container.querySelector('time');
                        let timeText = timeElement ? timeElement.textContent.trim() : link.textContent.trim();
                        
                        // 抓取貼文內容
                        let textNodes = Array.from(container.querySelectorAll('span[dir="auto"]'));
                        let contentText = textNodes.map(n => n.textContent).filter(t => t.length > 0).join('\\n');
                        
                        // 抓取互動數據 - 從整個容器的文字中尋找數字模式
                        let fullText = container.innerText || "";
                        let likes = 0, replies = 0, reposts = 0;
                        
                        // 尋找所有數字（包含 萬、K、M 等）
                        let numbers = fullText.match(/[\\d,\\.]+[萬KMkm]?/g) || [];
                        
                        // Threads 互動順序通常是：讚、留言、轉發
                        // 嘗試從 SVG 圖示附近找數字
                        let svgs = container.querySelectorAll('svg');
                        svgs.forEach((svg, idx) => {
                            let parent = svg.parentElement;
                            if (parent) {
                                let nearbyText = parent.textContent || "";
                                let num = nearbyText.match(/([\\d,\\.]+[萬KMkm]?)/);
                                if (num) {
                                    let value = num[1];
                                    if (idx === 0 || nearbyText.includes('讚') || nearbyText.includes('like')) {
                                        likes = value;
                                    } else if (idx === 1 || nearbyText.includes('回') || nearbyText.includes('repl')) {
                                        replies = value;
                                    } else if (idx === 2 || nearbyText.includes('轉') || nearbyText.includes('repost')) {
                                        reposts = value;
                                    }
                                }
                            }
                        });
                        
                        data.push({
                            "author": author,
                            "time": timeText,
                            "content": contentText,
                            "url": postUrl,
                            "likes": likes || "0",
                            "replies": replies || "0",
                            "reposts": reposts || "0"
                        });
                    } catch(e) {
                        console.error("解析單篇貼文失敗", e);
                    }
                }
                return data;
            }''')
            
            # 顯示抓到的資料
            print(f"   抓到 {len(posts_data)} 筆貼文")
            
            # Threads 的 after_date 參數已過濾日期，直接全部加入
            results.extend(posts_data)
            
        await context.close()
    
    # 去除重複 URL
    seen_urls = set()
    unique_results = []
    for post in results:
        if post['url'] not in seen_urls:
            seen_urls.add(post['url'])
            unique_results.append(post)
    
    # 存入資料庫
    stats = save_to_database(unique_results, keywords)
    
    print(f"\n[OK] Scraping completed!")
    print(f"   - 總共擷取：{stats['total']} 筆")
    print(f"   - 新增貼文：{stats['new']} 筆")
    
    return stats


if __name__ == "__main__":
    # 關鍵字
    keywords_to_search = ["政大"]
    
    # 初始化資料庫
    init_database()
    
    # 執行爬蟲
    asyncio.run(scrape_threads_hourly(keywords_to_search))
