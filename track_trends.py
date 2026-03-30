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
    if not os.path.exists("crisis_watchlist.json"):
        print("找不到 crisis_watchlist.json，無法進行追蹤。")
        return
        
    watchlist_urls = {}
    if os.path.exists("crisis_watchlist.json"):
        with open("crisis_watchlist.json", "r", encoding="utf-8") as f:
            for item in json.load(f):
                watchlist_urls[item['url']] = item

    if os.path.exists("history_db.json"):
        with open("history_db.json", "r", encoding="utf-8") as f:
            history_db = json.load(f)
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
                        
    watchlist = list(watchlist_urls.values())
        
    if not watchlist:
        print("目前沒有高危機案件或 7 天內 >4 分的歷史貼文需要追蹤。")
        return
        
    user_data_dir = os.path.join(os.getcwd(), "browser_data")
    
    # 讀取既有 trend_data 和 time_series_data
    trend_results = {}
    if os.path.exists("trend_data.json"):
        try:
            with open("trend_data.json", "r", encoding="utf-8") as f:
                trend_results = json.load(f)
        except: pass

    time_series_data = []
    if os.path.exists("time_series_data.json"):
        try:
            with open("time_series_data.json", "r", encoding="utf-8") as f:
                time_series_data = json.load(f)
        except: pass

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
            
            # 將最新抓取的互動數據回寫至 threads_data.json
            try:
                if os.path.exists("threads_data.json"):
                    with open("threads_data.json", "r", encoding="utf-8") as f:
                        t_data = json.load(f)
                    for t in t_data:
                        if t.get('url') == url:
                            t['likes'] = page_data['likes']
                            t['replies'] = page_data['replies']
                            t['likes_numeric'] = likes_num
                            t['replies_numeric'] = replies_num
                            t['last_updated'] = datetime.now().isoformat()
                            break
                    with open("threads_data.json", "w", encoding="utf-8") as f:
                        json.dump(t_data, f, ensure_ascii=False, indent=4)
            except Exception as e:
                print(f"⚠️ 無法更新 threads_data.json 數值: {e}")
            
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
                        "pr_analysis": analysis['pr_analysis']
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
        
    with open("trend_data.json", "w", encoding="utf-8") as f:
        json.dump(trend_results, f, ensure_ascii=False, indent=4)
        
    with open("time_series_data.json", "w", encoding="utf-8") as f:
        json.dump(time_series_data, f, ensure_ascii=False, indent=4)
        
    print(f"\\n🎯 追蹤任務結束！已更新趨勢庫與時序資料。")

if __name__ == "__main__":
    asyncio.run(track_trends())
