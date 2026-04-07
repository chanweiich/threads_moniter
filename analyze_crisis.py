import json
import os
import time
from datetime import datetime
from google import genai
import groq
from pydantic import BaseModel, Field
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

class BatchItemAnalysis(BaseModel):
    id: int = Field(description="The matching index/ID passed in the prompt")
    summary: str
    sentiment: str
    crisis_score: int

class BatchCrisisResponse(BaseModel):
    results: list[BatchItemAnalysis]

def update_api_status(gemini_status: str, groq_status: str):
    status = {"gemini": gemini_status, "groq": groq_status, "last_updated": datetime.now().isoformat()}
    with open("dashboard/api_status.json", "w", encoding="utf-8") as f:
        json.dump(status, f, ensure_ascii=False, indent=4)

def analyze_crisis():
    # if not os.environ.get("GEMINI_API_KEY"):
    #     print("請先設定 GEMINI_API_KEY 環境變數！")
    #     return
    # gemini_client = genai.Client()
    
    groq_api_key = os.environ.get("GROQ_API_KEY")
    if not groq_api_key:
        print("請檢查 .env 裡的 GROQ_API_KEY 是否正確")
        return
        
    groq_client = groq.Groq(api_key=groq_api_key)

    try:
        with open("threads_data.json", "r", encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        print("找不到 threads_data.json")
        return

    history_db = {}
    if os.path.exists("history_db.json"):
        try:
            with open("history_db.json", "r", encoding="utf-8") as f:
                history_db = json.load(f)
        except: pass

    data.sort(key=lambda x: 0 if x.get('risk_tag') else 1)
    print(f"開始全量分析，共 {len(data)} 筆貼文...")
    
    old_reports = {}
    if os.path.exists("final_crisis_report.json"):
        try:
            with open("final_crisis_report.json", "r", encoding="utf-8") as f:
                for rep in json.load(f):
                    if "analysis" in rep:
                        old_reports[rep['url']] = rep['analysis']
        except: pass
            
    # Step 1: Filter and assign placeholders
    results = [None] * len(data)
    batch_queue = []

    update_api_status("Active", "Standby")

    for i, post in enumerate(data):
        url = post.get('url', str(i))
        new_likes = parse_number_text(post.get('likes', '0'))
        new_replies = parse_number_text(post.get('replies', '0'))
        
        is_escalating = False
        old_score = 0
        if url in old_reports:
            old_likes = old_reports[url].get('likes_numeric', 0)
            if old_likes > 0 and new_likes >= old_likes * 1.5:
                is_escalating = True
                post['analysis'] = post.get('analysis', {})
                post['analysis']['is_escalating'] = True
                print(f"🔥 危機升級偵測！按讚數飆升至 {new_likes}")
                
        needs_reanalysis = post.get('needs_reanalysis', True)
        current_score = post.get('analysis', {}).get('crisis_score', 1)
        if current_score == 0 or current_score == "N/A" or is_escalating:
            needs_reanalysis = True
            
        if not needs_reanalysis and url in old_reports:
            post['analysis'] = old_reports[url]
            results[i] = post
            print(f"⏩ 沿用舊分析 (分數: {post['analysis'].get('crisis_score', 0)})")
            continue

        # If needs reanalysis, put it in queue
        placeholder = post.copy()
        placeholder['analysis'] = {
            "summary": "分析中... (排隊等候背景引擎處理)",
            "sentiment": "-",
            "crisis_score": 0
        }
        results[i] = placeholder
        batch_queue.append((i, post, is_escalating))

    # Flush fast placeholders
    with open("final_crisis_report.json", "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=4)

    # Step 2: Process batch queue
    BATCH_SIZE = 5
    for batch_idx in range(0, len(batch_queue), BATCH_SIZE):
        batch = batch_queue[batch_idx:min(batch_idx+BATCH_SIZE, len(batch_queue))]
        
        prompt_lines = ["請分析以下多篇 Threads 貼文的內容，並以 JSON Array 的形式回傳結果。\\n"]
        for idx, post, is_escalating in batch:
            escalation_ctx = "【🚨 危機升級重新評估指令：注意此篇按讚數近期暴增(>50%)！若內容與政大宿舍自強七舍相關，極易引發大量學生共鳴，請從嚴評估危機分數！】\\n" if is_escalating else ""
            prompt_lines.append(f"【ID: {idx}】\\n{escalation_ctx}內容：{post.get('content')}\\n---\\n")
            
        prompt_lines.append("""
你是一位政大秘書處的資深公關專家。請針對這篇來自 Threads 的貼文進行危機評估：
評分 (1-10)：1 為純日常，10 為重大公關災難（如校園安全、宿舍爆發大規模抗議、學術誠信）。
情緒 (Sentiment)：正面、中立或負面。
摘要 (Summary)：簡短說明學生在吵什麼。

請嚴格依照結構提供 JSON：
```json
{
  "results": [
    {
      "id": "匹配上方傳入的整數 ID",
      "summary": "簡短說明學生在吵什麼",
      "sentiment": "正面/中立/負面",
      "crisis_score": 1
    }
  ]
}
```""")
        full_prompt = "".join(prompt_lines)
        
        print(f"\\n🔄 正在批次分析 {len(batch)} 筆貼文...")
        success = False
        retry_count = 0
        engine_used = "Groq" if groq_client else "Gemini"
        batch_response_json = None
        
        while retry_count < 2 and not success:
            try:
                # 優先使用 Gemini
                # if engine_used == "Gemini":
                #     response = gemini_client.models.generate_content(
                #         model='gemini-2.5-flash',
                #         contents=full_prompt,
                #         config=genai.types.GenerateContentConfig(
                #             response_mime_type="application/json",
                #             response_schema=BatchCrisisResponse,
                #             temperature=0.2
                #         )
                #     )
                #     batch_response_json = response.text
                
                # 若 Groq 模式
                if engine_used == "Groq" and groq_client:
                    print(f"[Groq Engine] Analyzing content...")
                    sys_prompt = {"role": "system", "content": "You are a crisis analysis bot. Output precisely valid JSON matching the requested structure."}
                    user_prompt = {"role": "user", "content": full_prompt}
                    completion = groq_client.chat.completions.create(
                        model="llama-3.3-70b-versatile",
                        messages=[sys_prompt, user_prompt],
                        response_format={"type": "json_object"},
                        temperature=0.2
                    )
                    batch_response_json = completion.choices[0].message.content
                    
                start_idx = batch_response_json.find('{')
                end_idx = batch_response_json.rfind('}')
                if start_idx != -1 and end_idx != -1:
                    batch_response_json = batch_response_json[start_idx:end_idx+1]
                
                analysis_obj = BatchCrisisResponse.model_validate_json(batch_response_json)
                
                # Apply map back results
                result_map = {str(item.id): item.model_dump() for item in analysis_obj.results}
                
                for idx, post, is_escalating in batch:
                    idx_str = str(idx)
                    if idx_str in result_map:
                        analysis = result_map[idx_str]
                        analysis['is_escalating'] = is_escalating
                        analysis['engine'] = engine_used
                        
                        post['analysis'] = analysis
                        results[idx] = post
                        
                        # History DB updating
                        if analysis.get('crisis_score', 0) > 4:
                            history_db[post.get('url')] = {
                                "likes": parse_number_text(post.get('likes', '0')),
                                "replies": parse_number_text(post.get('replies', '0')),
                                "crisis_score": analysis['crisis_score'],
                                "last_seen": datetime.now().isoformat()
                            }
                
                print(f"✅ 批次完成 (使用引擎: {engine_used})")
                success = True
                
                if engine_used == "Gemini":
                    update_api_status("Healthy", "Standby")
                
                time.sleep(3)
                
            except Exception as e:
                error_msg = str(e)
                print(f"⚠️ {engine_used} API 發生錯誤：{error_msg}")
                if batch_response_json:
                    print(f"--- 原始回傳內容 ---\n{batch_response_json}\n--------------------")
                
                # if engine_used == "Groq":
                #     print("🔄 觸發自動備援切換，轉交 Gemini 處理...")
                #     engine_used = "Gemini"
                #     update_api_status("Active", "RateLimited" if '429' in error_msg else "Error")
                # else:
                retry_count += 1
                time.sleep(2)
                    
        if not success:
            print("❌ 批次最終失敗")
            for idx, post, _ in batch:
                post['analysis'] = {"summary": "分析失敗", "sentiment": "中立", "crisis_score": 1, "engine": "Failed"}
                results[idx] = post

        # Incremental File Write per batch
        with open("final_crisis_report.json", "w", encoding="utf-8") as f:
            json.dump(results, f, ensure_ascii=False, indent=4)

    # 寫入最終清理檔
    for post in data:
        post.pop('needs_reanalysis', None)
    with open("threads_data.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

    with open("history_db.json", "w", encoding="utf-8") as f:
        json.dump(history_db, f, ensure_ascii=False, indent=4)
        
    watchlist = []
    for r in results:
        if r and r.get('analysis', {}).get('crisis_score', 0) >= 7:
            watchlist.append({
                "url": r.get('url'),
                "original_content": r.get('content', ''),
                "original_sentiment": r.get('analysis', {}).get('sentiment', '中立')
            })
    with open("crisis_watchlist.json", "w", encoding="utf-8") as f:
        json.dump(watchlist, f, ensure_ascii=False, indent=4)

if __name__ == "__main__":
    analyze_crisis()
