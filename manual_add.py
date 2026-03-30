import sys
import os
import json
import asyncio
from datetime import datetime
from pydantic import BaseModel
import google.generativeai as genai
from dotenv import load_dotenv
from playwright.async_api import async_playwright

load_dotenv()

class CrisisAnalysis(BaseModel):
    summary: str
    sentiment: str
    crisis_score: int

def parse_number_text(text):
    if not isinstance(text, str): return int(text)
    if not text or text == "N/A": return 0
    text = text.replace(',', '')
    if '萬' in text:
        try: return int(float(text.replace('萬', '').strip()) * 10000)
        except: return 0
    try: return int(text)
    except: return 0

async def manual_add(url):
    print(f"正在手動抓取單一網址：{url}")
    user_data_dir = os.path.join(os.getcwd(), "browser_data")
    
    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(
            user_data_dir=user_data_dir,
            headless=True,
            args=["--disable-blink-features=AutomationControlled"],
            viewport={'width': 1280, 'height': 800},
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        )
        page = await context.new_page()
        
        try:
            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=15000)
            except Exception as nav_e:
                print(f"導航超時或發生跳轉，繼續嘗試抓取: {nav_e}")
                
            try:
                # 強制等待內容載入
                await page.wait_for_selector('div[data-pressable-container="true"], [data-testid="post-card-content"]', timeout=15000)
            except Exception as wait_e:
                print(f"等待主要內容容器出現時超時: {wait_e}")
                await page.screenshot(path="error_screenshot.png")
                
            await asyncio.sleep(2)
            
            # Find the main post container (usually the first article or generic div)
            post_data = await page.evaluate('''() => {
                try {
                    let container = document.querySelector('div[data-pressable-container="true"]') || document.querySelector('[data-testid="post-card-content"]');
                    if (!container) {
                        return {
                            "author": "Unknown",
                            "time": "剛剛",
                            "content": document.body.innerText.substring(0, 500) || "Pending (待處理) - 內容解析失敗",
                            "url": window.location.href,
                            "likes": "0",
                            "replies": "0",
                            "reposts": "0"
                        };
                    }
                    
                    let authorNode = container.querySelector('a[href^="/@"]:not([href*="/post/"])');
                    let author = authorNode ? authorNode.textContent.trim() : "Unknown";
                    
                    let timeNode = container.querySelector('time');
                    let timeText = timeNode ? timeNode.textContent.trim() : "剛剛";
                    
                    let textNodes = Array.from(container.querySelectorAll('span[dir="auto"]'));
                    let contentText = textNodes.map(n => n.textContent).filter(t => t.length > 0).join('\\n');
                    
                    let fullText = container.innerText || "";
                    let likes = "0", replies = "0", reposts = "0";
                    let lines = fullText.split('\\n');
                    for (let line of lines) {
                        if (line.includes('個讚') || line.includes('likes') || line.includes('讚')) likes = line.trim();
                        if (line.includes('則回覆') || line.includes('replies') || line.includes('回覆')) replies = line.trim();
                        if (line.includes('次轉發') || line.includes('reposts') || line.includes('轉發')) reposts = line.trim();
                    }
                    
                    return {
                        "author": author,
                        "time": timeText,
                        "content": contentText,
                        "url": window.location.href,
                        "likes": likes,
                        "replies": replies,
                        "reposts": reposts
                    };
                } catch(e) {
                    return null;
                }
            }''')
        except Exception as e:
            print(f"ERROR DETAILS - Playwright DOM 解析發生不可預期的錯誤:")
            import traceback
            traceback.print_exc()
            post_data = None
        finally:
            await context.close()
            
    if not post_data or len(post_data.get('content', '')) < 5:
        print("ERROR: 無法抓取到貼文內容，將寫入預設佔位資料。")
        post_data = {
            "author": "Unknown",
            "time": "剛剛",
            "content": "Pending (待處理) - 內容解析失敗",
            "url": url,
            "likes": "0",
            "replies": "0",
            "reposts": "0"
        }

    post_data['analysis'] = {"summary": "處理中/待 AI 評分", "sentiment": "中立", "crisis_score": 0}
    
    # --- 3. 實作非阻塞存檔 (Non-blocking Save/First Pass) ---
    try:
        with open("threads_data.json", "r", encoding="utf-8") as f:
            t_data = json.load(f)
    except:
        t_data = []

    t_data = [t for t in t_data if t.get('url') != post_data['url']]

    try:
        with open("nccu_risk_keywords.json", "r", encoding="utf-8") as f:
            risk_keywords = json.load(f)
    except:
        risk_keywords = ["宿舍", "性平", "洩題", "莊敬", "環山道", "會研所", "歧視"]

    post_data['risk_tag'] = any(rw in post_data['content'] for rw in risk_keywords)
    post_data['is_new'] = True
    post_data['last_updated'] = datetime.now().isoformat()
    t_data.insert(0, post_data)

    with open("threads_data.json", "w", encoding="utf-8") as f:
        json.dump(t_data, f, ensure_ascii=False, indent=4)
        
    print("✅ 數據已初步存檔！(預設分數: 0 待處理)")

    # --- 4. 隔離 API 錯誤：啟動 Gemini 分析 ---
    analysis = post_data['analysis']
    score = 0
    if "Pending (待處理)" in post_data["content"] or "暫掛監控" in post_data["content"] or "無法抓取" in post_data["content"]:
        print("跳過 Gemini 分析，直接賦予初始 0 分待處理狀態。")
        analysis = {"summary": "抓取失敗/待更新", "sentiment": "中立", "crisis_score": 0}
    else:
        print("啟動 Gemini 分析...")
        try:
            client = genai.Client()
            prompt = f"""請分析以下 Threads 貼文內容：
【貼文內容】：{post_data['content']}

請嚴格依照結構提供 JSON：
1. `summary`: 30字以內的摘要。若無意義或太短，請寫「無具體內容」。
2. `sentiment`: 情緒判定，只能是 "正面"、"中立" 或 "負面"。
3. `crisis_score`: 危機指數 (1-10分)，評分標準：
   - 1-3分：一般日常、正面、無爭議的內容或單純疑問。
   - 4-6分：微抱怨、個人不滿、討論度可能升溫但不至於嚴重損害校譽。
   - 7-10分：嚴重負面、炎上潛力、霸凌、公共安全或嚴重損害校譽的危機。
"""
            response = client.models.generate_content(
                model='gemini-2.5-flash',
                contents=prompt,
                config=genai.types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=CrisisAnalysis,
                    temperature=0.2
                )
            )
            analysis_obj = CrisisAnalysis.model_validate_json(response.text)
            analysis = analysis_obj.model_dump()
            score = analysis.get('crisis_score', 0)
            print(f"分析完成！危機分數: {score}")
        except Exception as e:
            print(f"⚠️ Gemini 分析遭遇錯誤或超時: {e}")
            analysis = {"summary": "數據已存檔，但 AI 分析暫時不可用", "sentiment": "中立", "crisis_score": 0}
            score = 0

    post_data['analysis'] = analysis

    # --- 5. 再次更新所有檔案 (Second Pass) ---
    t_data = [t for t in t_data if t.get('url') != post_data['url']]
    t_data.insert(0, post_data)
    with open("threads_data.json", "w", encoding="utf-8") as f:
        json.dump(t_data, f, ensure_ascii=False, indent=4)

    # 寫入 final_crisis_report.json
    try:
        with open("final_crisis_report.json", "r", encoding="utf-8") as f:
            c_data = json.load(f)
    except:
        c_data = []

    c_data = [c for c in c_data if c.get('url') != post_data['url']]
    c_data.insert(0, post_data)
    with open("final_crisis_report.json", "w", encoding="utf-8") as f:
        json.dump(c_data, f, ensure_ascii=False, indent=4)

    # 強制追蹤 crisis_watchlist.json
    try:
        with open("crisis_watchlist.json", "r", encoding="utf-8") as f:
            w_data = json.load(f)
    except:
        w_data = []
        
    if not any(w.get('url') == post_data['url'] for w in w_data):
        w_data.append({
            "url": post_data['url'],
            "original_content": post_data['content'],
            "original_sentiment": post_data['analysis']['sentiment']
        })
        with open("crisis_watchlist.json", "w", encoding="utf-8") as f:
            json.dump(w_data, f, ensure_ascii=False, indent=4)

    # Output JSON string exactly for app.py to parse
    output_result = {
        "status": "success",
        "score": score,
        "summary": analysis.get('summary')
    }
    
    print("---OUTPUT_START---")
    print(json.dumps(output_result))
    print("---OUTPUT_END---")

if __name__ == "__main__":
    if len(sys.argv) > 1:
        url = sys.argv[1]
        asyncio.run(manual_add(url))
