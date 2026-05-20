"""
每小時指標更新模組 (hourly_update.py)
訪問近 3 天貼文的 URL，更新 posts 表的 likes/comments 欄位
由 hourly_scheduler.py 每小時呼叫一次，執行完即結束
"""
import asyncio
import sqlite3
import os
import re
import time
from datetime import datetime, timedelta
from playwright.async_api import async_playwright
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "threads_posts.db")


def parse_number_text(text):
    if not text or text == "N/A":
        return 0
    if not isinstance(text, str):
        try:
            return int(text)
        except:
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


def get_posts_to_update():
    """取得近 3 天內被爬蟲加入 DB 的貼文 URL（以 created_at 判斷，避免 updated_at 自循環膨脹清單）"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    three_days_ago = (datetime.now() - timedelta(days=3)).isoformat()
    cursor.execute("""
        SELECT url FROM posts
        WHERE created_at >= ?
        ORDER BY created_at DESC
    """, (three_days_ago,))
    rows = cursor.fetchall()
    conn.close()
    return [row['url'] for row in rows]


async def update_metrics():
    urls = get_posts_to_update()
    if not urls:
        print("無近 3 天貼文需要更新指標。")
        return

    print(f"共 {len(urls)} 篇貼文需要更新指標...")
    user_data_dir = os.path.join(BASE_DIR, "browser_data")

    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(
            user_data_dir=user_data_dir,
            headless=True,
            channel="chrome",
            args=["--disable-blink-features=AutomationControlled", "--no-sandbox"],
            viewport={'width': 1280, 'height': 800},
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        )
        page = await context.new_page()

        for url in urls:
            print(f"  更新指標：{url}")
            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            except Exception as e:
                print(f"  警告 導航失敗：{e}")
                continue

            await asyncio.sleep(4)

            page_data = await page.evaluate('''() => {
                // 透過 SVG aria-label 定位互動按鈕，支援中英雙語，並往上找多層容器
                function getCount(enLabel, zhLabel, zhLabel2) {
                    let selectors = [`svg[aria-label="${enLabel}"]`];
                    if (zhLabel) selectors.push(`svg[aria-label="${zhLabel}"]`);
                    if (zhLabel2) selectors.push(`svg[aria-label="${zhLabel2}"]`);
                    if (enLabel === "Like") selectors.push(`svg[aria-label="Unlike"]`, `svg[aria-label="收回讚"]`);

                    const svg = document.querySelector(selectors.join(', '));
                    if (!svg) return "0";
                    
                    let parent = svg;
                    for (let i = 0; i < 4; i++) {
                        parent = parent.parentElement;
                        if (!parent) return "0";
                        
                        const spans = parent.querySelectorAll("span");
                        for (const span of spans) {
                            if (span.children.length > 0) continue;
                            const text = span.textContent.trim();
                            if (/^[\d,\.]+[萬KkMm]?$/.test(text)) {
                                return text;
                            }
                        }
                    }
                    return "0";
                }
                
                let viewsStr = "0";
                for (let el of document.querySelectorAll('span, div')) {
                    let txt = el.textContent.trim();
                    let m1 = txt.match(/^([\d,\.]+[萬KkMm]?)\s*次[瀏覽觀看查看]/);
                    if (m1) { viewsStr = m1[1]; break; }
                    let m2 = txt.match(/[瀏覽觀看查看]次數[：:\s]*([\d,\.]+[萬KkMm]?)/);
                    if (m2) { viewsStr = m2[1]; break; }
                }

                return {
                    likes:   getCount("Like", "讚", "按讚"),
                    replies: getCount("Reply", "回覆", "留言"),
                    reposts: getCount("Repost", "轉貼", "轉發"),
                    shares:  getCount("Share", "分享", "傳送"),
                    views:   viewsStr
                };
            }''')

            def extract_digits(text):
                match = re.search(r'([\d\.,萬]+)', text)
                return match.group(1) if match else "0"

            likes_num   = parse_number_text(extract_digits(page_data['likes']))
            replies_num = parse_number_text(extract_digits(page_data['replies']))
            reposts_num = parse_number_text(extract_digits(page_data['reposts']))
            shares_num  = parse_number_text(extract_digits(page_data['shares']))
            views_num   = parse_number_text(extract_digits(page_data['views']))

            try:
                now_iso = datetime.now().isoformat()
                conn = sqlite3.connect(DB_PATH)
                cursor = conn.cursor()
                cursor.execute("""
                    UPDATE posts SET likes = ?, comments = ?, reposts = ?, shares = ?, views = ?, updated_at = ? WHERE url = ?
                """, (likes_num, replies_num, reposts_num, shares_num, views_num, now_iso, url))
                cursor.execute("""
                    INSERT INTO post_snapshots (url, likes, comments, views, captured_at)
                    VALUES (?, ?, ?, ?, ?)
                """, (url, likes_num, replies_num, views_num, now_iso))
                conn.commit()
                conn.close()
                print(f"    讚 {likes_num}，回覆 {replies_num}，轉發 {reposts_num}，分享 {shares_num}，瀏覽 {views_num}")
            except Exception as e:
                print(f"  警告 更新 posts 失敗：{e}")

            time.sleep(1)

        await context.close()

    print(f"完成 指標更新完成，共處理 {len(urls)} 篇貼文。")


if __name__ == "__main__":
    asyncio.run(update_metrics())
