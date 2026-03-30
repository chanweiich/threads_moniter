import json
import os
import time
from google import genai
from pydantic import BaseModel
from dotenv import load_dotenv

load_dotenv()

def parse_number_text(text):
    if not isinstance(text, str): return int(text)
    if not text or text == "N/A": return 0
    text = text.replace(',', '')
    if '萬' in text:
        try: return int(float(text.replace('萬', '').strip()) * 10000)
        except: return 0
    try: return int(text)
    except: return 0

class CrisisAnalysis(BaseModel):
    summary: str
    sentiment: str
    crisis_score: int

def analyze_crisis():
    if not os.environ.get("GEMINI_API_KEY"):
        print("請先設定 GEMINI_API_KEY 環境變數！")
        return

    client = genai.Client()
    
    try:
        with open("threads_data.json", "r", encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        print("找不到 threads_data.json")
        return

    total = len(data)
    
    # 讀取 history_db.json
    history_db = {}
    if os.path.exists("history_db.json"):
        try:
            with open("history_db.json", "r", encoding="utf-8") as f:
                history_db = json.load(f)
        except:
            history_db = {}
            
    # 優先級排序：有 risk_tag 的排在前面 (0), 否則在後面 (1)
    data.sort(key=lambda x: 0 if x.get('risk_tag') else 1)

    print(f"開始全量分析，共 {len(data)} 筆貼文...")
    results = []
    
    # 讀取舊的分析報告，用於 API 最佳化 (沿用未變動的分析結果)
    old_reports = {}
    if os.path.exists("final_crisis_report.json"):
        try:
            with open("final_crisis_report.json", "r", encoding="utf-8") as f:
                for rep in json.load(f):
                    if "analysis" in rep:
                        old_reports[rep['url']] = rep['analysis']
        except:
            pass
            
    # 預先寫入佔位符，讓前端 Dashboard 秒速載入
    for item in data:
        placeholder = item.copy()
        placeholder['analysis'] = {
            "summary": "分析中... (排隊等候背景處理)",
            "sentiment": "-",
            "crisis_score": 0
        }
        results.append(placeholder)
        
    with open("final_crisis_report.json", "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=4)
        
    from datetime import datetime
    for i, post in enumerate(data):
        url = post.get('url', '未知連結')
        content = post.get('content', '')
        if not content.strip():
            content = "[無文字內容]"
            
        new_likes = parse_number_text(post.get('likes', '0'))
        new_replies = parse_number_text(post.get('replies', '0'))
        
        # 判斷是否為炎上擴大 (按讚數增加超過 50%)
        is_escalating = False
        if url in old_reports:
            old_likes = old_reports[url].get('likes_numeric', 0)
            if old_likes > 0 and new_likes >= old_likes * 1.5:
                is_escalating = True
                post['analysis']['is_escalating'] = True
                print(f"🔥 危機升級偵測！按讚數從 {old_likes} 飆升至 {new_likes}", end=" ", flush=True)

        print(f"進度 [{i+1}/{total}] 正在分析...", end=" ", flush=True)

        needs_reanalysis = post.get('needs_reanalysis', True)
        
        # --- 實作『缺漏補齊』功能 ---
        current_score = post.get('analysis', {}).get('crisis_score', 1)
        if current_score == 0 or current_score == "N/A":
            needs_reanalysis = True
            
        if is_escalating:
            needs_reanalysis = True
            
        if not needs_reanalysis and url in old_reports:
            post['analysis'] = old_reports[url]
            results[i] = post
            print(f"⏩ 沿用舊分析 (分數: {post['analysis'].get('crisis_score', 0)})", flush=True)
            
            with open("final_crisis_report.json", "w", encoding="utf-8") as f:
                json.dump(results, f, ensure_ascii=False, indent=4)
            continue

        escalation_ctx = ""
        if is_escalating:
            escalation_ctx = "【🚨 危機升級重新評估指令】：此篇貼文的按讚關注度在近期發生異常暴增(飆升超過 50%)！請注意，若這是一篇關於『政大宿舍（自強 7 舍）』或類似校園環境條件的抱怨，根據歷史經驗這屬於極高風險的地雷話題，極易引發大量學生共鳴與媒體關注。請重新、從嚴評估其潛在危機分數！\n"
            
        prompt = f"""請分析以下 Threads 貼文內容：
{escalation_ctx}
【貼文內容】：{post.get('content')}

請嚴格依照結構提供 JSON：
1. `summary`: 30字以內的摘要。若無意義或太短，請寫「無具體內容」。
2. `sentiment`: 情緒判定，只能是 "正面"、"中立" 或 "負面"。
3. `crisis_score`: 危機指數 (1-10分)，評分標準：
   - 1-3分：一般日常、正面、無爭議的內容或單純疑問。
   - 4-6分：微抱怨、個人不滿、討論度可能升溫但不至於嚴重損害校譽。
   - 7-10分：嚴重負面、炎上潛力、霸凌、公共安全或嚴重損害校譽的危機。
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
                        response_schema=CrisisAnalysis,
                        temperature=0.2
                    ),
                )
                
                # 使用 Pydantic v2 最新語法取代 json.loads
                analysis_obj = CrisisAnalysis.model_validate_json(response.text)
                analysis = analysis_obj.model_dump()
                
                analysis['is_escalating'] = is_escalating
                if is_escalating:
                    analysis['old_score'] = old_score
                
                post['analysis'] = analysis
                results[i] = post
                
                if analysis.get('crisis_score', 0) > 4:
                    history_db[url] = {
                        "likes": new_likes,
                        "replies": new_replies,
                        "crisis_score": analysis['crisis_score'],
                        "last_seen": datetime.now().isoformat()
                    }
                    
                with open("final_crisis_report.json", "w", encoding="utf-8") as f:
                    json.dump(results, f, ensure_ascii=False, indent=4)
                
                print(f"✅ 完成 (分數: {analysis['crisis_score']})", flush=True)
                success = True
                
                # 穩定調用 API：每筆補分析間隔 5 秒
                time.sleep(5)
                
            except Exception as e:
                retry_count += 1
                import traceback
                error_msg = traceback.format_exc()
                print(f"⚠️ 遇到 API 限制或錯誤，等待後重試 ({retry_count}/3)... 錯誤細節: {e}", end=" ", flush=True)
                time.sleep(2)
        
        if not success:
            print("❌ 最終失敗，標註為重試中", flush=True)
            # 依要求，失敗時不顯示空白，而是標記為分析中並統一給予基礎分數
            analysis = {"summary": "分析中/重試中", "sentiment": "中立", "crisis_score": 1}
            post['analysis'] = analysis
            results[i] = post
            
        # 短暫暫停以避免擁塞
        time.sleep(1)
            
    # --- 【新增】手動注入測試：政大會研所爭議貼文 ---
    fake_post = {
        "author": "wuu11.__",
        "time": "2026-03-25",
        "content": "【政大會研所】關於推甄公平性爭議",
        "url": "https://www.threads.net/@wuu11.__/post/DVdz_7PkhLS",
        "likes": "4000",
        "replies": "200",
        "reposts": "0",
        "analysis": {
            "summary": "政大會研所推甄公平性遭強烈質疑，引發大量網友與學生反彈炎上。",
            "sentiment": "負面",
            "crisis_score": 9
        }
    }
    
    # 若陣列中沒有該網址，則插入
    if not any(r.get('url') == fake_post['url'] for r in results):
        results.insert(0, fake_post)
        
    # 清理 threads_data 內的 needs_reanalysis 標記，避免無限觸發
    for post in data:
        post.pop('needs_reanalysis', None)
    with open("threads_data.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

    # 寫入 history_db.json
    with open("history_db.json", "w", encoding="utf-8") as f:
        json.dump(history_db, f, ensure_ascii=False, indent=4)
        
    output_file = "final_crisis_report.json"
    print(f"\\n全量進度結束，將資料同步寫入 {output_file} ...")
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=4)
        
    # --- 【新增】高危機自動監視名單 ---
    watchlist = []
    for r in results:
        if r.get('analysis', {}).get('crisis_score', 0) >= 7:
            watchlist.append({
                "url": r.get('url'),
                "original_content": r.get('content', ''),
                "original_sentiment": r.get('analysis', {}).get('sentiment', '中立')
            })
    with open("crisis_watchlist.json", "w", encoding="utf-8") as f:
        json.dump(watchlist, f, ensure_ascii=False, indent=4)
    print(f"✅ 高危機追蹤清單已更新：寫入 {len(watchlist)} 筆待追蹤案件")
        
    print(f"✅ 全量分析結束！共處理 {len(results)} 筆，結果已儲存！")

if __name__ == "__main__":
    analyze_crisis()
