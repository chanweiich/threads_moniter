import asyncio
import json
import os
import time
from datetime import datetime
from playwright.async_api import async_playwright
from google import genai
from pydantic import BaseModel
from dotenv import load_dotenv

load_dotenv()

class TrendAnalysis(BaseModel):
    trend: str 
    reasoning: str
    gemini_sentiment_score: int
    negative_words: list[str]
    pr_analysis: str
    top_3_complaints: list[str]

# 輔助函式：文字轉數字 ("1.1 萬" -> 11000)
def parse_number_text(text):
    if not text or text == "N/A": return 0
    text = text.replace(',', '')
    if '萬' in text:
        try: return int(float(text.replace('萬', '').strip()) * 10000)
        except: return 0
    try: return int(text)
    except: return 0

async def track_trends():
    # 從 SQLite 讀取 crisis_watchlist
    watchlist_urls = {}
    try:
        import sqlite3
        conn = sqlite3.connect("threads_posts.db")
        cursor = conn.cursor()
        cursor.execute("SELECT url, original_content, original_sentiment FROM crisis_watchlist")
        for row in cursor.fetchall():
            url, original_content, original_sentiment = row
            watchlist_urls[url] = {
                'url': url,
                'original_content': original_content,
                'original_sentiment': original_sentiment
            }
        conn.close()
    except Exception as e:
        print(f"❌ 讀取 crisis_watchlist 錯誤: {e}")
        return

    # 從 SQLite 讀取 history_db
    if watchlist_urls:  # 只在有 watchlist 時才檢查歷史數據
        try:
            conn = sqlite3.connect("threads_posts.db")
            cursor = conn.cursor()
            cursor.execute("SELECT key, data FROM history")
            history_db = {}
            for row in cursor.fetchall():
                key, data_str = row
                if data_str:
                    history_db[key] = json.loads(data_str)
            conn.close()
            
            now = datetime.now()
            for url, data in history_db.items():
                if data.get('crisis_score', 0) > 4:
                    try:
                        last_seen = datetime.fromisoformat(data.get('last_seen', now.isoformat()))
                    except:
                        last_seen = now
                    if (now - last_seen).days <= 7 and url not in watchlist_urls:
                        watchlist_urls[url] = {
                            'url': url,
                            'original_sentiment': '負面',
                            'original_content': '歷史監測高分貼文 (7天內 >4分)'
                        }
        except Exception as e:
            print(f"❌ 讀取 history_db 錯誤: {e}")
    
    watchlist = list(watchlist_urls.values())
        
    if not watchlist:
        print("目前沒有高危機案件或 7 天內 >4 分的歷史貼文需要追蹤。")
        return
        
    user_data_dir = os.path.join(os.getcwd(), "browser_data")
    
    # 從 SQLite 讀取 trend_results 和 time_series_data
    trend_results = {}
    time_series_data = []
    
    try:
        conn = sqlite3.connect("threads_posts.db")
        cursor = conn.cursor()
        
        # 讀取 trend_analysis 表
        cursor.execute("SELECT post_url, trend, reasoning, gemini_sentiment_score, negative_words, pr_analysis, top_3_complaints FROM trend_analysis")
        for row in cursor.fetchall():
            trend_results[row[0]] = {
                "trend": row[1],
                "reasoning": row[2],
                "gemini_sentiment_score": row[3],
                "negative_words": json.loads(row[4]) if row[4] else [],
                "pr_analysis": row[5],
                "top_3_complaints": json.loads(row[6]) if row[6] else []
            }
        
        # 讀取 time_series 表
        cursor.execute("SELECT data FROM time_series ORDER BY date DESC LIMIT 1")
        row = cursor.fetchone()
        if row and row[0]:
            time_series_data = json.loads(row[0])
        
        conn.close()
    except Exception as e:
        print(f"❌ 讀取趨勢數據錯誤: {e}")
        # 如果讀取失敗，使用空的數據結構

    client = genai.Client()
    
    async with async_playwright() as p:
        print(f"啟動瀏覽器進行高危機精準跳轉追蹤 (共 {len(watchlist)} 筆)...")
        context = await p.chromium.launch_persistent_context(
            user_data_dir=user_data_dir,
            headless=False,
            args=["--disable-blink-features=AutomationControlled"],
            viewport={'width': 1280, 'height': 800},
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        )
        page = await context.new_page()
        
        for item in watchlist:
            url = item['url']
            print(f"\\n🔍 正在追蹤高危機網址：{url}")
            await page.goto(url, wait_until="domcontentloaded")
            await asyncio.sleep(6)
            
            for _ in range(5):
                await page.mouse.wheel(0, 1000)
                await asyncio.sleep(2)
                
            # 抓取留言內容、按讚數與留言數
            page_data = await page.evaluate('''() => {
                let textNodes = Array.from(document.querySelectorAll('span[dir="auto"]'));
                let comments = textNodes.map(n => n.textContent).filter(t => t.length > 3).slice(0, 50);
                
                let likes = "0", replies = "0";
                let allText = document.body.innerText;
                let lines = allText.split('\\n');
                for (let line of lines) {
                    if (line.includes('個讚') || line.includes('likes') || line.includes('讚')) likes = line.trim();
                    if (line.includes('則回覆') || line.includes('replies') || line.includes('回覆')) replies = line.trim();
                }
                
                return { comments: comments, likes: likes, replies: replies };
            }''')
            
            def extract_digits(text):
                import re
                match = re.search(r'([\\d\\.\\,萬]+)', text)
                return match.group(1) if match else "0"

            likes_num = parse_number_text(extract_digits(page_data['likes']))
            replies_num = parse_number_text(extract_digits(page_data['replies']))
            
            # 將最新抓取的互動數據回寫至 SQLite 資料庫
            try:
                conn = sqlite3.connect("threads_posts.db")
                cursor = conn.cursor()
                cursor.execute("""
                    UPDATE posts 
                    SET likes = ?, comments = ?, likes_numeric = ?, comments_numeric = ?, last_updated = ?
                    WHERE url = ?
                """, (
                    page_data['likes'],
                    page_data['replies'],  # comments field in DB
                    likes_num,
                    replies_num,
                    datetime.now().isoformat(),
                    url
                ))
                conn.commit()
                conn.close()
                print(f"✅ 已更新 {url} 的互動數據至 SQLite")
            except Exception as e:
                print(f"⚠️ 無法更新 SQLite 數據: {e}")
            
            comments = page_data['comments']
            combined_comments = "\\n".join(comments[:25]) if comments else "無擷取到任何留言資訊"
            
            prompt = f"""請分析這則 Threads 原文與其最新留言的『輿情走向』：
【原文情緒】：{item.get('original_sentiment', '中立')}
【原文內容片段】：{item.get('original_content', '')}

【最新網頁留言擷取 (深度爬取取前 25 筆)】：
{combined_comments}

請嚴格判斷輿情走向，並回傳指定的 JSON 結構：
1. `trend`: 必須是 "擴大中", "出現反彈聲浪", 或是 "校方已平息情緒" 其中之一。
2. `gemini_sentiment_score`: 1-10 分，評估『最新留言』有多負面（10分最負面，1分最正面）
3. `negative_words`: 從留言中提取 3-5 個最常出現的關鍵詞彙。若適用，請確保包含『會研所』、『公平性』、『學歷』、『道歉』等。
4. `reasoning`: 簡短解釋。
5. `pr_analysis`: 撰寫一份大約 150 字的『政大公關處置分析報告』，點出校方當下主要被攻擊的危機點、學生核心訴求與建議作法。
6. `top_3_complaints`: 特別注意，如果擷取到的留言總數量超過 10 則，請以簡短的一句話條列出『學生最不滿的三個點是什麼？』，否則請回傳空陣列。
"""
            retry_count = 0
            success = False
            while retry_count < 3 and not success:
                try:
                    response = client.models.generate_content(
                        model='gemini-2.5-flash',
                        contents=prompt,
                        config=genai.types.GenerateContentConfig(
                            response_mime_type="application/json",
                            response_schema=TrendAnalysis,
                            temperature=0.2
                        ),
                    )
                    analysis = json.loads(response.text)
                    
                    # 覆寫 trend_data.json
                    trend_results[url] = analysis
                    
                    # 追加 time_series_data.json
                    time_series_data.append({
                        "url": url,
                        "timestamp": datetime.now().isoformat(),
                        "likes": likes_num,
                        "replies": replies_num,
                        "gemini_sentiment_score": analysis['gemini_sentiment_score'],
                        "negative_words": analysis['negative_words'],
                        "pr_analysis": analysis['pr_analysis'],
                        "top_3_complaints": analysis.get('top_3_complaints', [])
                    })
                    
                    print(f"✅ {url} 解析完成：{analysis['trend']} (情緒分數: {analysis['gemini_sentiment_score']})")
                    success = True
                except Exception as e:
                    retry_count += 1
                    print(f"⚠️ API 錯誤重試 ({retry_count}/3)...", end=" ", flush=True)
                    time.sleep(3)
            
            if not success:
                print(f"❌ {url} API 最終失敗")
                
            time.sleep(2)
            
        await context.close()
        
    # 寫入SQLite數據庫
    import sqlite3
    conn = sqlite3.connect("threads_posts.db")
    cursor = conn.cursor()
    
    # 清空並寫入trend_analysis表
    cursor.execute("DELETE FROM trend_analysis")
    for url, data in trend_results.items():
        cursor.execute("""
            INSERT INTO trend_analysis (post_url, trend, reasoning, gemini_sentiment_score, negative_words, pr_analysis, top_3_complaints)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            url,
            data.get("trend"),
            data.get("reasoning"),
            data.get("gemini_sentiment_score"),
            json.dumps(data.get("negative_words", [])),
            data.get("pr_analysis"),
            json.dumps(data.get("top_3_complaints", []))
        ))
    
    # 清空並寫入time_series表
    cursor.execute("DELETE FROM time_series")
    cursor.execute("""
        INSERT INTO time_series (date, data)
        VALUES (?, ?)
    """, (
        datetime.datetime.now().strftime("%Y-%m-%d"),
        json.dumps(time_series_data)
    ))
    
    conn.commit()
    conn.close()
        
    print(f"\\n🎯 追蹤任務結束！已更新趨勢庫與時序資料。")

if __name__ == "__main__":
    asyncio.run(track_trends())
