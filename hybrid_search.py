import asyncio
import json
import os
import sys
import subprocess
from datetime import datetime
from playwright.async_api import async_playwright

def parse_number_text(text):
    if not isinstance(text, str): return int(text)
    if not text or text == "N/A": return 0
    text = text.replace(',', '')
    if '萬' in text:
        try: return int(float(text.replace('萬', '').strip()) * 10000)
        except: return 0
    try: return int(text)
    except: return 0

async def hybrid_scrape(keyword):
    results = []
    user_data_dir = os.path.join(os.getcwd(), "browser_data")
    
    async with async_playwright() as p:
        print(f"[HybridSearch] 正在啟動瀏覽器進行即時網搜: {keyword}")
        
        context = await p.chromium.launch_persistent_context(
            user_data_dir=user_data_dir,
            headless=False,
            args=["--disable-blink-features=AutomationControlled"],
            viewport={'width': 1280, 'height': 800},
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        )
        
        page = await context.new_page()
        print("[HybridSearch] 套用 Persistent Cookie...")
        await page.goto("https://www.threads.net/", wait_until="domcontentloaded")
        await asyncio.sleep(2)
        
        search_url = f"https://www.threads.net/search?q={keyword}"
        await page.goto(search_url, wait_until="domcontentloaded")
        await asyncio.sleep(4)
        
        print("[HybridSearch] 小規模捲動以載入最新 10 筆...")
        for i in range(4):
            await page.mouse.wheel(0, 1500)
            await asyncio.sleep(2)

        posts_data = await page.evaluate('''() => {
            let data = [];
            let postLinks = Array.from(document.querySelectorAll('a[href*="/post/"]'));
            let seen = new Set();
            
            for (let link of postLinks) {
                if (seen.has(link.href)) continue;
                seen.add(link.href);
                
                try {
                    let container = link.parentElement;
                    for (let i = 0; i < 8; i++) {
                        if (container && container.parentElement && container.tagName !== 'BODY') {
                            container = container.parentElement;
                        }
                    }
                    
                    let authorNode = container.querySelector('a[href^="/@"]:not([href*="/post/"])');
                    let author = authorNode ? authorNode.textContent.trim() : "Unknown";
                    
                    let timeText = link.textContent.trim();
                    
                    let textNodes = Array.from(container.querySelectorAll('span[dir="auto"]'));
                    let contentText = textNodes.map(n => n.textContent).filter(t => t.length > 0).join('\\n');
                    
                    let postUrl = link.href;
                    let fullText = container.innerText; 
                    
                    let likes = "N/A", replies = "N/A", reposts = "N/A";
                    let lines = fullText.split('\\n');
                    for (let line of lines) {
                        if (line.includes('個讚') || line.includes('likes') || line.includes('讚')) likes = line.trim();
                        if (line.includes('則回覆') || line.includes('replies') || line.includes('回覆')) replies = line.trim();
                        if (line.includes('次轉發') || line.includes('reposts') || line.includes('轉發')) reposts = line.trim();
                    }
                    
                    data.push({
                        "author": author,
                        "time": timeText,
                        "content": contentText,
                        "url": postUrl,
                        "likes": likes,
                        "replies": replies,
                        "reposts": reposts
                    });
                } catch(e) {
                    console.error("解析單篇貼文失敗", e);
                }
            }
            return data;
        }''')
        
        # 開發限制：擷取最新 10 筆
        posts_data = posts_data[:10]
        print(f"[HybridSearch] 針對關鍵字 '{keyword}' 擷取到 {len(posts_data)} 筆即時情資。")
        results.extend(posts_data)
        
        await context.close()

async def main(keywords):
    results = []
    user_data_dir = os.path.join(os.getcwd(), "browser_data")
    
    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(
            user_data_dir=user_data_dir,
            headless=False,
            args=["--disable-blink-features=AutomationControlled"],
            viewport={'width': 1280, 'height': 800},
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        )
        page = await context.new_page()
        await page.goto("https://www.threads.net/", wait_until="domcontentloaded")
        await asyncio.sleep(2)
        
        for kw in keywords:
            batch_results = await hybrid_scrape(page, kw)
            results.extend(batch_results)
            
        await context.close()
        
    return results

if __name__ == "__main__":
    if len(sys.argv) > 1:
        keywords = sys.argv[1:]
        
        # Scrape all keywords
        results = asyncio.run(main(keywords))
        
        # Open Database
        try:
            with open("threads_data.json", "r", encoding="utf-8") as f:
                existing_list = json.load(f)
                existing_data = {item['url']: item for item in existing_list}
        except:
            existing_list = []
            existing_data = {}
    
        try:
            with open("nccu_risk_keywords.json", "r", encoding="utf-8") as f:
                risk_keywords = json.load(f)
        except:
            risk_keywords = ["宿舍", "性平", "洩題", "莊敬", "環山道", "會研所", "歧視"]
    
        new_posts_count = 0
        updated_posts_count = 0
    
        for item in results:
            url = item["url"]
            content = item.get('content', '')
            is_risky = any(risk_word in content for risk_word in risk_keywords)
            item['risk_tag'] = is_risky
            
            current_time = datetime.now().isoformat()
            
            if url in existing_data:
                old_item = existing_data[url]
                old_likes = parse_number_text(old_item.get('likes', '0'))
                old_replies = parse_number_text(old_item.get('replies', '0'))
                new_likes = parse_number_text(item.get('likes', '0'))
                new_replies = parse_number_text(item.get('replies', '0'))
                
                needs_reanalysis = old_item.get('needs_reanalysis', False)
                if new_likes > old_likes + 50 or new_replies > old_replies + 10:
                    needs_reanalysis = True
                    old_item['is_updated'] = True
                    updated_posts_count += 1
                    
                old_item['likes'] = item['likes']
                old_item['replies'] = item['replies']
                old_item['reposts'] = item['reposts']
                old_item['last_updated'] = current_time
                old_item['needs_reanalysis'] = needs_reanalysis
                old_item['risk_tag'] = is_risky
                
            else:
                item['needs_reanalysis'] = True
                item['is_new'] = True
                item['last_updated'] = current_time
                existing_list.insert(0, item)
                existing_data[url] = item
                new_posts_count += 1
    
        with open("threads_data.json", "w", encoding="utf-8") as f:
            json.dump(existing_list, f, ensure_ascii=False, indent=4)
            
        venv_python = os.path.abspath(os.path.join(os.getcwd(), ".venv", "bin", "python3"))
        if not os.path.exists(venv_python):
            venv_python = "python3"
            
        subprocess.run([venv_python, "analyze_crisis.py"], check=False)
        
        print("---OUTPUT_START---")
        print(json.dumps({"status": "success", "new_count": new_posts_count, "updated_count": updated_posts_count}))
        print("---OUTPUT_END---")
    else:
        print("請提供 Keyword 參數")
