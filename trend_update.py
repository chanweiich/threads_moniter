"""
趨勢分析更新模組 (trend_update.py)
條件：crisis_score >= 3 的負面貼文，7 天內，距上次分析超過 6 小時
排序：crisis_score 最高優先
結果存入 trend_analysis 表 (SQLite)
由 hourly_scheduler.py 每 6 小時呼叫一次，執行完即結束
"""
import asyncio
import sqlite3
import os
import json  # 僅用於 json.dumps/loads 序列化 SQLite TEXT 欄位中的 list，非 JSON 檔案
import re
import time
from datetime import datetime, timedelta
from playwright.async_api import async_playwright
from pydantic import BaseModel
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "threads_posts.db")


class TrendAnalysis(BaseModel):
    trend: str
    reasoning: str
    gemini_sentiment_score: int  # 1-5，與 post_analysis.crisis_score 量表一致
    negative_words: list[str]
    pr_analysis: str
    top_3_complaints: list[str]


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


def get_posts_for_trend():
    """
    取得需要趨勢分析的貼文：
    - sentiment = '負面' 且 crisis_score >= 3
    - 貼文建立於近 7 天內
    - 從未分析過，或距上次分析已超過 6 小時
    - 按 crisis_score 由高到低排序
    """
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    seven_days_ago = (datetime.now() - timedelta(days=7)).isoformat()
    six_hours_ago = (datetime.now() - timedelta(hours=6)).isoformat()
    cursor.execute("""
        SELECT p.url, p.content, pa.crisis_score, pa.sentiment
        FROM posts p
        JOIN post_analysis pa ON p.url = pa.post_url
        LEFT JOIN trend_analysis ta ON p.url = ta.post_url
        WHERE pa.sentiment = '負面'
          AND pa.crisis_score >= 3
          AND p.created_at >= ?
          AND (ta.analyzed_at IS NULL OR ta.analyzed_at < ?)
        ORDER BY pa.crisis_score DESC
    """, (seven_days_ago, six_hours_ago))
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def ensure_trend_table():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS trend_analysis (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            post_url TEXT UNIQUE,
            trend TEXT,
            reasoning TEXT,
            gemini_sentiment_score INTEGER,
            negative_words TEXT,
            pr_analysis TEXT,
            top_3_complaints TEXT,
            analyzed_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()


def save_trend_result(url, data):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM posts WHERE url = ?", (url,))
    post_row = cursor.fetchone()
    post_id = post_row[0] if post_row else None
    cursor.execute("""
        INSERT OR REPLACE INTO trend_analysis
            (post_id, post_url, trend, reasoning, gemini_sentiment_score, negative_words, pr_analysis, top_3_complaints, analyzed_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        post_id,
        url,
        data.get('trend'),
        data.get('reasoning'),
        data.get('gemini_sentiment_score'),
        json.dumps(data.get('negative_words', []), ensure_ascii=False),
        data.get('pr_analysis'),
        json.dumps(data.get('top_3_complaints', []), ensure_ascii=False),
        datetime.now().isoformat()
    ))
    conn.commit()
    conn.close()


async def run_trend_analysis():
    if not os.environ.get("GEMINI_API_KEY"):
        print("警告 未設定 GEMINI_API_KEY，跳過趨勢分析")
        return

    posts = get_posts_for_trend()
    if not posts:
        print("目前沒有符合條件的貼文需要趨勢分析。")
        return

    ensure_trend_table()
    print(f"共 {len(posts)} 篇貼文需要趨勢分析（crisis_score >= 3，7 天內，超過 6 小時未分析）...")

    from google import genai
    client = genai.Client()

    user_data_dir = os.path.join(BASE_DIR, "browser_data")

    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(
            user_data_dir=user_data_dir,
            headless=False,
            args=["--disable-blink-features=AutomationControlled"],
            viewport={'width': 1280, 'height': 800},
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        )
        page = await context.new_page()

        for post in posts:
            url = post['url']
            score = post['crisis_score']
            print(f"\n  分析 (crisis_score={score})：{url}")

            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            except Exception as e:
                print(f"  警告 導航失敗：{e}")
                continue

            await asyncio.sleep(5)

            for _ in range(5):
                await page.mouse.wheel(0, 1000)
                await asyncio.sleep(2)

            page_data = await page.evaluate('''() => {
                let textNodes = Array.from(document.querySelectorAll('span[dir="auto"]'));
                let comments = textNodes.map(n => n.textContent).filter(t => t.length > 3).slice(0, 50);
                return { comments: comments };
            }''')

            comments_list = page_data.get('comments', [])
            combined_comments = "\n".join(comments_list[:25]) if comments_list else "無擷取到任何留言資訊"

            prompt = f"""請分析這則 Threads 原文與其最新留言的『輿情走向』：
【原文情緒】：負面（危機分數 {score}/5）
【原文內容片段】：{post.get('content', '')[:300]}

【最新網頁留言擷取 (前 25 筆)】：
{combined_comments}

請嚴格判斷輿情走向，回傳指定的 JSON 結構：
1. `trend`: 必須是 "擴大中", "出現反彈聲浪", 或 "校方已平息情緒" 其中之一。
2. `gemini_sentiment_score`: 1-5 分，評估『最新留言』有多負面
   （5分最負面，1分最正面；量表與 crisis_score 一致）
3. `negative_words`: 從留言中提取 3-5 個最常出現的關鍵詞彙。
4. `reasoning`: 簡短解釋。
5. `pr_analysis`: 約 150 字的『政大公關處置分析報告』，點出危機點、學生核心訴求與建議作法。
6. `top_3_complaints`: 若留言超過 10 則，以簡短一句話條列『學生最不滿的三個點』；否則回傳空陣列。
"""
            success = False
            for attempt in range(3):
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
                    analysis = TrendAnalysis.model_validate_json(response.text)
                    save_trend_result(url, analysis.model_dump())
                    print(f"  完成 {analysis.trend}（情緒分數: {analysis.gemini_sentiment_score}）")
                    success = True
                    break
                except Exception as e:
                    print(f"  警告 Gemini 重試 ({attempt + 1}/3)：{e}")
                    time.sleep(3)

            if not success:
                print(f"  錯誤 趨勢分析失敗，跳過此貼文")

            time.sleep(2)

        await context.close()

    print(f"\n完成 趨勢分析結束，結果已存入 trend_analysis 表。")


if __name__ == "__main__":
    asyncio.run(run_trend_analysis())
